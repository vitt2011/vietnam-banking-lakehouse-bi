"""
===================================================================================
PIPELINE: src/orchestration/run_quarterly_pipeline.py
CHỨC NĂNG: LUỒNG ĐỒNG BỘ BÁO CÁO TÀI CHÍNH & CAMELS QUÝ CHUẨN 1 CHIỀU
===================================================================================
Quy trình thực thi tuần tự bất biến:
  Bước 1 [Ingest]  : Cào BCTC & Tỷ số từ nguồn -> Bronze Parquet
  Bước 2 [DQ1]     : Kiểm định chất lượng Bronze Gateway BCTC
  Bước 3 [Silver]  : Chuẩn hóa kỳ kế toán, quy chuẩn mã tài khoản, Silver Parquet
  Bước 4 [Gold]    : Tính toán CAMELS Composite Scorecard & Ma trận Định giá Gordon
  Bước 5 [Serving] : Công bố có kiểm soát sang PostgreSQL mart_camels.*
  Bước 6 [Lineage] : Ghi nhận run_id, manifest JSON và cập nhật ops.pipeline_runs
===================================================================================
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.governance.lineage_tracker import PipelineRunContext, update_dataset_state
from stock_analysis.transformation.bronze_to_silver.clean_financials import (
    run_clean_financial_statements,
    run_clean_financial_ratios,
)
from stock_analysis.transformation.silver_to_gold.feature_camels_engine import run_feature_camels_engine
from stock_analysis.transformation.silver_to_gold.feature_valuation_matrix import run_feature_valuation_matrix
from stock_analysis.sql_serving_loader.publish_to_postgres import (
    publish_financial_statements,
    publish_banking_ratios_and_camels,
)

LOG_FILE = LOGS_DIR / "pipeline" / f"quarterly_{datetime.now().strftime('%Y%m%d')}.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("QuarterlyCAMELSPipeline")


def run_pipeline(skip_crawl: bool = True) -> bool:
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(">>> KHỞI CHẠY PIPELINE BÁO CÁO TÀI CHÍNH & TỶ SỐ CAMELS QUÝ <<<")
    logger.info("Chế độ bỏ qua cào lại từ nguồn (skip_crawl): %s", skip_crawl)
    logger.info("=" * 80)

    run_ctx = PipelineRunContext(job_name="quarterly_camels_pipeline", trigger_type="MANUAL")
    run_ctx.source_dataset = "Vietcap_Financial_API"
    run_ctx.add_target("DataLake/01_bronze/financial_statements")
    run_ctx.add_target("DataLake/02_silver/financials")
    run_ctx.add_target("DataLake/03_gold/camels_scorecard")
    run_ctx.add_target("PostgreSQL:mart_camels.fact_quarterly_financial_statements")
    run_ctx.add_target("PostgreSQL:mart_camels.fact_quarterly_banking_ratios")

    try:
        # Bước 1: Ingestion (nếu không skip)
        if not skip_crawl:
            logger.info("\n>>> [1/5] BƯỚC 1: CÀO BCTC VÀ TỶ SỐ NGUYÊN BẢN VÀO BRONZE...")
            from stock_analysis.ingestion.ingest_financial_statements import scrape_all_fundamentals
            scrape_all_fundamentals()
        else:
            logger.info("\n>>> [1/5] BƯỚC 1: SỬ DỤNG DỮ LIỆU BRONZE BCTC HIỆN CÓ...")

        # Bước 2 & 3: Silver Transformation
        logger.info("\n>>> [2/5] BƯỚC 2: LÀM SẠCH & CHUẨN HÓA SANG SILVER PARQUET...")
        silver_fs = run_clean_financial_statements()
        silver_ratios = run_clean_financial_ratios()
        logger.info("      [✓] Hoàn tất Silver: %d BCTC, %d Tỷ số tài chính.", silver_fs, silver_ratios)

        # Bước 4: Gold Feature Engineering (CAMELS & Valuation)
        logger.info("\n>>> [3/5] BƯỚC 3: TÍNH TOÁN CAMELS SCORECARD & MA TRẬN ĐỊNH GIÁ GORDON...")
        gold_camels = run_feature_camels_engine()
        gold_val = run_feature_valuation_matrix()
        logger.info("      [✓] Hoàn tất Gold: %d CAMELS, %d Định giá.", gold_camels, gold_val)

        # Bước 5: Publish sang PostgreSQL Serving
        logger.info("\n>>> [4/5] BƯỚC 4: CÔNG BỐ DỮ LIỆU ĐÃ KIỂM ĐỊNH VÀO POSTGRESQL SERVING...")
        pub_fs = publish_financial_statements()
        pub_ratios = publish_banking_ratios_and_camels()
        run_ctx.records_published = pub_fs + pub_ratios
        logger.info("      [✓] Đã công bố vào PostgreSQL: %d BCTC, %d Tỷ số CAMELS.", pub_fs, pub_ratios)

        # Bước 6: Lineage & Manifest
        logger.info("\n>>> [5/5] BƯỚC 5: GHI NHẬN LINEAGE & TRẠNG THÁI VẬN HÀNH...")
        run_ctx.complete(status="SUCCESS")
        
        update_dataset_state(
            dataset_name="financial_statements",
            target_table="mart_camels.fact_quarterly_financial_statements",
            run_id=run_ctx.run_id,
            record_count=pub_fs,
            snapshot_date=datetime.now().strftime("%Y-%m-%d")
        )
        update_dataset_state(
            dataset_name="banking_ratios_camels",
            target_table="mart_camels.fact_quarterly_banking_ratios",
            run_id=run_ctx.run_id,
            record_count=pub_ratios,
            snapshot_date=datetime.now().strftime("%Y-%m-%d")
        )

        duration = time.time() - start_time
        logger.info("\n" + "=" * 80)
        logger.info(">>> [THÀNH CÔNG] PIPELINE QUÝ HOÀN TẤT XUẤT SẮC TRONG %.2f GIÂY <<<", duration)
        logger.info("Run ID: %s | Manifest: %s", run_ctx.run_id, run_ctx.manifest_path)
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error("!!! [THẤT BẠI] PIPELINE BỊ LỖI: %s", e, exc_info=True)
        run_ctx.complete(status="FAILED", error_msg=str(e))
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Chạy luồng đồng bộ BCTC và CAMELS Quý")
    parser.add_argument("--crawl", action="store_true", help="Cào lại từ nguồn")
    args = parser.parse_args()

    success = run_pipeline(skip_crawl=not args.crawl)
    sys.exit(0 if success else 1)
