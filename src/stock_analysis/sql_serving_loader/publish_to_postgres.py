"""
===================================================================================
MODULE: src/stock_analysis/sql_serving_loader/publish_to_postgres.py
CHỨC NĂNG: LỚP CÔNG BỐ DỮ LIỆU TỪ DATA LAKE SANG POSTGRESQL SERVING STORE
===================================================================================
Quy tắc:
  - Đọc từ DataLake/02_silver/ và DataLake/03_gold/ nạp vào Database PostgreSQL.
  - Sử dụng UPSERT (ON CONFLICT DO UPDATE) đảm bảo tính Idempotent 100%.
  - Đếm số lượng bản ghi THẬT từ Database, tuyệt đối KHÔNG hardcode số liệu.
  - Cập nhật ops.dataset_publish_state và ops.pipeline_runs.
===================================================================================
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.governance.lineage_tracker import PipelineRunContext, update_dataset_state

logger = logging.getLogger("ServingPublisher")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


def publish_stock_ohlcv(specific_date_sk: Optional[int] = None) -> int:
    """
    Công bố chuỗi giá và thanh khoản OHLCV từ Silver sang mart_technical.fact_daily_market_ohlcv.
    """
    silver_stock_dir = DATA_LAKE_DIR / "02_silver" / "02_structured" / "01_Giao_Dich_Gia_OHLCV" / "stock_ohlcv"
    if not silver_stock_dir.exists():
        logger.warning("Thư mục Silver Stock OHLCV không tồn tại: %s", silver_stock_dir)
        return 0

    logger.info("Đang đọc Parquet từ Silver: %s ...", silver_stock_dir)
    parquet_files = list(silver_stock_dir.glob("**/*.parquet"))
    if not parquet_files:
        logger.warning("Không tìm thấy file parquet nào trong %s", silver_stock_dir)
        return 0

    dfs = []
    for pf in parquet_files:
        try:
            df_part = pd.read_parquet(pf)
            if specific_date_sk:
                df_part = df_part[df_part["date_sk"] == specific_date_sk]
            if not df_part.empty:
                dfs.append(df_part)
        except Exception as e:
            logger.warning("Lỗi khi đọc file %s: %s", pf, e)

    if not dfs:
        return 0

    df_all = pd.concat(dfs, ignore_index=True)
    if df_all.empty:
        return 0

    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        sql = """
        INSERT INTO mart_technical.fact_daily_market_ohlcv (
            bank_sk, date_sk, open_price, high_price, low_price, close_price,
            volume, turnover_vnd, return_daily_pct
        ) VALUES %s
        ON CONFLICT (bank_sk, date_sk) DO UPDATE SET
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume,
            turnover_vnd = EXCLUDED.turnover_vnd,
            return_daily_pct = EXCLUDED.return_daily_pct;
        """
        records = [
            (
                int(r["bank_sk"]),
                int(r["date_sk"]),
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                int(r["volume"]),
                float(r.get("turnover_vnd", r["close"] * r["volume"])),
                float(r.get("return_daily_pct", 0.0))
            )
            for _, r in df_all.iterrows()
        ]

        execute_values(cur, sql, records, page_size=2000)
        conn.commit()
        published_count = len(records)
        logger.info("[✓] Đã công bố thành công %d bản ghi OHLCV vào mart_technical.", published_count)
        update_dataset_state("stock_ohlcv", "mart_technical.fact_daily_market_ohlcv", "run_sync", published_count)
        return published_count
    except Exception as e:
        conn.rollback()
        logger.error("Lỗi khi công bố OHLCV vào PostgreSQL: %s", e)
        raise e
    finally:
        conn.close()


def publish_financial_statements() -> int:
    """
    Công bố Báo cáo tài chính chuẩn hóa sang mart_camels.fact_quarterly_financial_statements.
    Đếm số lượng bản ghi thực tế từ database, không hardcode.
    """
    from stock_analysis.sql_serving_loader.load_financial_statements import run_pipeline as run_fs_sync
    success = run_fs_sync()
    if not success:
        return 0

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mart_camels.fact_quarterly_financial_statements;")
        total_count = cur.fetchone()[0]
        cur.close()
        logger.info("[✓] Đã công bố thành công BCTC vào mart_camels: %d bản ghi thực tế.", total_count)
        update_dataset_state("financial_statements", "mart_camels.fact_quarterly_financial_statements", "run_sync", total_count)
        return total_count
    finally:
        conn.close()


def publish_banking_ratios_and_camels() -> int:
    """
    Công bố Tỷ số tài chính và CAMELS scorecard sang mart_camels.fact_quarterly_banking_ratios.
    Đếm số lượng bản ghi thực tế từ database, không hardcode.
    """
    from stock_analysis.sql_serving_loader.load_banking_ratios import run_pipeline as run_ratios_sync
    success = run_ratios_sync()
    if not success:
        return 0

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mart_camels.fact_quarterly_banking_ratios;")
        total_count = cur.fetchone()[0]
        cur.close()
        logger.info("[✓] Đã công bố thành công Tỷ số CAMELS vào mart_camels: %d bản ghi thực tế.", total_count)
        update_dataset_state("banking_ratios_camels", "mart_camels.fact_quarterly_banking_ratios", "run_sync", total_count)
        return total_count
    finally:
        conn.close()


def publish_macro_and_governance() -> int:
    """
    Công bố dữ liệu vĩ mô và mạng lưới quản trị từ Gold sang mart_technical & mart_governance.
    """
    from stock_analysis.sql_serving_loader.load_macro_indicators import run_pipeline as run_macro_sync
    from stock_analysis.sql_serving_loader.load_governance import run_pipeline as run_gov_sync
    ok_macro = run_macro_sync()
    ok_gov = run_gov_sync()
    return 1 if (ok_macro and ok_gov) else 0


def publish_all_to_postgres() -> Dict[str, Any]:
    """
    Master Serving Publisher: Đồng bộ toàn bộ các sản phẩm từ Data Lake sang PostgreSQL Serving.
    """
    logger.info("=" * 80)
    logger.info(">>> BẮT ĐẦU CÔNG BỐ TOÀN BỘ SẢN PHẨM TỪ DATA LAKE SANG POSTGRESQL SERVING <<<")
    logger.info("=" * 80)
    
    results = {}
    results["stock_ohlcv"] = publish_stock_ohlcv()
    results["financial_statements"] = publish_financial_statements()
    results["banking_ratios_camels"] = publish_banking_ratios_and_camels()
    results["macro_and_governance"] = publish_macro_and_governance()
    
    logger.info(">>> HOÀN TẤT CÔNG BỐ SANG POSTGRESQL: %s", results)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    publish_all_to_postgres()
