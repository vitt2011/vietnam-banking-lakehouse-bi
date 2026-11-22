"""
===================================================================================
PIPELINE: src/orchestration/run_daily_pipeline.py
CHỨC NĂNG: LUỒNG ĐỒNG BỘ GIÁ HÀNG NGÀY CHUẨN 1 CHIỀU (MEDALLION TO SERVING)
===================================================================================
Quy trình thực thi tuần tự bất biến:
  Bước 1 [Ingest]  : API Vietcap -> Bronze Parquet Delta & Append Historical
  Bước 2 [DQ1]     : Kiểm định chất lượng Bronze Gateway (giá âm, volume âm, boundary)
  Bước 3 [Silver]  : Chuẩn hóa VND, tính daily return, phân vùng Hive exchange/year
  Bước 4 [Gold]    : Tính toán chỉ báo kỹ thuật (RSI, MA20/50, MACD, Bollinger Bands)
  Bước 5 [Serving] : Công bố có kiểm soát sang PostgreSQL mart_technical.fact_daily_market_ohlcv
  Bước 6 [Lineage] : Ghi nhận run_id, manifest JSON và cập nhật ops.pipeline_runs
===================================================================================
"""

import os
import sys
import time
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

# Ngăn chặn vnstock/vnai gọi sys.exit() khi chạm rate limit
try:
    import vnai.beam.quota
    vnai.beam.quota.CleanErrorContext.__exit__ = lambda self, exc_type, exc_val, exc_tb: False
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.governance.lineage_tracker import PipelineRunContext, update_dataset_state
from stock_analysis.governance.gateways import validate_dq1
from stock_analysis.transformation.bronze_to_silver.clean_market import run_clean_stock_ohlcv
from stock_analysis.transformation.silver_to_gold.feature_technical_indicators import run_feature_technical_indicators
from stock_analysis.sql_serving_loader.publish_to_postgres import publish_stock_ohlcv

# Logging setup
LOG_FILE = LOGS_DIR / "pipeline" / f"daily_{datetime.now().strftime('%Y%m%d')}.log"
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
logger = logging.getLogger("DailyMarketPipeline")

BANKING_TICKERS = [
    "ACB", "ABB", "BAB", "BID", "BVB", "CTG", "EIB", "HDB", "KLB", "LPB",
    "MBB", "MSB", "NAB", "NVB", "OCB", "PGB", "SGB", "SHB", "SSB", "STB",
    "TCB", "TPB", "VAB", "VBB", "VCB", "VIB", "VPB",
]

BRONZE_MARKET_DIR = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "01_Giao_Dich_Gia_OHLCV"
HISTORICAL_PARQUET = BRONZE_MARKET_DIR / "vnstock_historical.parquet"


def is_trading_day(dt: Optional[date] = None) -> bool:
    """Kiểm tra ngày làm việc giao dịch (Thứ 2 đến Thứ 6)"""
    if dt is None:
        dt = date.today()
    return dt.weekday() < 5


def fetch_latest_eod_quotes(target_date: Optional[str] = None, start_date: Optional[str] = None) -> pd.DataFrame:
    """
    Thu thập giá đóng cửa EOD từ Vietcap API cho 27 mã ngân hàng với kiểm soát rate limit.
    Tự động lùi về ngày có dữ liệu gần nhất trong Bronze để quét bù (backfill) toàn bộ
    các ngày giao dịch bị gián đoạn (do tắt máy, ngày nghỉ, cúp điện).
    """
    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")

    if start_date is None:
        # Tự động xác định ngày gần nhất đã lưu trong Bronze Lake
        if HISTORICAL_PARQUET.exists():
            try:
                df_hist = pd.read_parquet(HISTORICAL_PARQUET, columns=["time"])
                max_time = pd.to_datetime(df_hist["time"]).max()
                # Lùi lại 2 ngày từ max_time để quét bù và đối soát trùng lặp
                start_date = (max_time - timedelta(days=2)).strftime("%Y-%m-%d")
            except Exception:
                start_date = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")
        else:
            start_date = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")

    logger.info("Đang thu thập giá EOD từ %s đến %s cho %d mã ngân hàng...", start_date, target_date, len(BANKING_TICKERS))
    
    collected_rows = []
    
    try:
        from vnstock.explorer.vci.quote import Quote as VCIQuote
        for idx, ticker in enumerate(BANKING_TICKERS, start=1):
            try:
                client = VCIQuote(symbol=ticker)
                df_quote = client.history(start=start_date, end=target_date)
                if df_quote is not None and not df_quote.empty:
                    df_quote["ticker"] = ticker
                    df_quote["sector"] = "Ngan_Hang"
                    collected_rows.append(df_quote)
                    logger.info("  [%02d/%02d] %s: OK (%d dòng)", idx, len(BANKING_TICKERS), ticker, len(df_quote))
                else:
                    logger.info("  [%02d/%02d] %s: Không có dữ liệu mới.", idx, len(BANKING_TICKERS), ticker)
                # Nghỉ 3.1 giây giữa mỗi request để đảm bảo < 20 req/phút không bao giờ dính rate limit
                time.sleep(3.1)
            except Exception as e:
                logger.warning("  [%02d/%02d] %s: Bỏ qua lỗi (%s)", idx, len(BANKING_TICKERS), ticker, e)
                time.sleep(2.0)
    except Exception as e:
        logger.warning("VCIQuote client init error: %s", e)

    if collected_rows:
        df_all = pd.concat(collected_rows, ignore_index=True)
        return df_all
    else:
        logger.info("Không có dữ liệu mới từ sàn hôm nay hoặc ngoài giờ giao dịch.")
        return pd.DataFrame()


def run_pipeline(force: bool = False, target_date: Optional[str] = None, skip_api: bool = False) -> bool:
    start_time = time.time()
    today_dt = date.today()
    if target_date:
        today_dt = datetime.strptime(target_date, "%Y-%m-%d").date()

    logger.info("=" * 80)
    logger.info(">>> KHỞI CHẠY PIPELINE THỊ TRƯỜNG HÀNG NGÀY (DAILY INCREMENTAL EOD) <<<")
    logger.info("Ngày mục tiêu: %s | Chế độ ép buộc (force): %s | Bỏ qua API: %s", today_dt, force, skip_api)
    logger.info("=" * 80)

    # Tìm ngày giao dịch gần nhất (Thứ 6 nếu hôm nay là cuối tuần)
    def _get_last_trading_day(dt: date) -> date:
        cur = dt
        while cur.weekday() >= 5:  # 5=Sat, 6=Sun
            cur -= timedelta(days=1)
        return cur

    last_market_day = _get_last_trading_day(today_dt)

    # Kiểm tra xem Bronze đã có dữ liệu đến ngày giao dịch gần nhất chưa
    has_latest_market_data = False
    if HISTORICAL_PARQUET.exists():
        try:
            df_h = pd.read_parquet(HISTORICAL_PARQUET, columns=["time"])
            max_lake_date = pd.to_datetime(df_h["time"]).max().date()
            if max_lake_date >= last_market_day:
                has_latest_market_data = True
        except Exception:
            pass

    if not force and not is_trading_day(today_dt) and has_latest_market_data:
        logger.info("[INFO] Hôm nay là ngày nghỉ cuối tuần và dữ liệu đã cập nhật đầy đủ đến phiên gần nhất (%s). Bỏ qua phiên đồng bộ.", last_market_day)
        return True

    # 1. Khởi tạo Run Context
    run_ctx = PipelineRunContext(job_name="daily_market_pipeline", trigger_type="SCHEDULED" if not force else "MANUAL")
    run_ctx.source_dataset = "Vietcap_VCI_API"
    run_ctx.add_target("DataLake/01_bronze/market_trading")
    run_ctx.add_target("DataLake/02_silver/stock_ohlcv")
    run_ctx.add_target("DataLake/03_gold/technical_indicators")
    run_ctx.add_target("PostgreSQL:mart_technical.fact_daily_market_ohlcv")

    try:
        # -------------------------------------------------------------------------
        # BƯỚC 1: INGESTION (NẠP NGUYÊN BẢN VÀO BRONZE ZONE)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [1/5] BƯỚC 1: INGESTION THÔ VÀO BRONZE ZONE...")
        if not skip_api:
            df_new = fetch_latest_eod_quotes(target_date=today_dt.strftime("%Y-%m-%d"))
            
            if not df_new.empty:
                run_ctx.records_ingested = len(df_new)
                
                # Ghi file delta hàng ngày vào Bronze
                delta_dir = BRONZE_MARKET_DIR / "daily_delta"
                delta_dir.mkdir(parents=True, exist_ok=True)
                delta_path = delta_dir / f"date={today_dt.strftime('%Y-%m-%d')}.parquet"
                
                df_new["_ingested_at"] = datetime.now().isoformat()
                df_new["_source"] = "VCI_API"
                df_new["_run_id"] = run_ctx.run_id
                df_new.to_parquet(delta_path, index=False)
                logger.info("      [✓] Đã lưu Bronze Delta: %s (%d bản ghi)", delta_path, len(df_new))
                
                # Khử trùng lặp và ghi nối vào file lịch sử Bronze
                if HISTORICAL_PARQUET.exists():
                    df_hist = pd.read_parquet(HISTORICAL_PARQUET)
                    df_combined = pd.concat([df_hist, df_new.drop(columns=["_ingested_at", "_source", "_run_id"], errors="ignore")], ignore_index=True)
                    df_combined = df_combined.drop_duplicates(subset=["ticker", "time"], keep="last").reset_index(drop=True)
                    df_combined.to_parquet(HISTORICAL_PARQUET, index=False)
                    logger.info("      [✓] Đã cập nhật file Bronze lịch sử: %s (Tổng %d bản ghi)", HISTORICAL_PARQUET, len(df_combined))
            else:
                logger.info("      Không có bản ghi mới từ API. Sử dụng dữ liệu hiện có trong Bronze.")
        else:
            logger.info("      Bỏ qua gọi API (--skip-api). Tái xử lý trực tiếp từ Bronze Parquet.")

        # -------------------------------------------------------------------------
        # BƯỚC 2: DATA QUALITY GATEWAY 1 (KIỂM ĐỊNH BRONZE)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [2/5] BƯỚC 2: KIỂM ĐỊNH CHẤT LƯỢNG DQ1 TRÊN BRONZE...")
        if HISTORICAL_PARQUET.exists():
            df_check = pd.read_parquet(HISTORICAL_PARQUET)
            valid_df, _, dq1_metrics = validate_dq1(df_check.tail(1000), dataset_type="market_ohlcv", quarantine=False)
            passed_dq1 = dq1_metrics.get("is_passed", True)
            run_ctx.records_validated = dq1_metrics["valid_records"]
            run_ctx.validation_status = "PASSED" if passed_dq1 else "FAILED"
            logger.info("      [DQ1] Kết quả kiểm định Bronze: %s (Tỷ lệ đạt: %s%%)", 
                        run_ctx.validation_status, dq1_metrics.get("pass_rate_pct", 100))
        
        # -------------------------------------------------------------------------
        # BƯỚC 3: SILVER TRANSFORMATION (CHUẨN HÓA & PHÂN VÙNG HIVE)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [3/5] BƯỚC 3: CHUẨN HÓA & XUẤT BẢN SILVER PARQUET...")
        silver_written = run_clean_stock_ohlcv()
        logger.info("      [✓] Hoàn tất xuất bản Silver: %d phiên giao dịch.", silver_written)

        # -------------------------------------------------------------------------
        # BƯỚC 4: GOLD FEATURE ENGINEERING (TÍNH CHỈ BÁO KỸ THUẬT)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [4/5] BƯỚC 4: TÍNH TOÁN CHỈ BÁO KỸ THUẬT TẦNG GOLD...")
        gold_written = run_feature_technical_indicators()
        logger.info("      [✓] Hoàn tất xuất bản Gold: %d bản ghi chỉ báo kỹ thuật.", gold_written)

        # -------------------------------------------------------------------------
        # BƯỚC 5: PUBLISH TO POSTGRESQL SERVING LAYER (TRANSACTIONAL UPSERT)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [5/5] BƯỚC 5: CÔNG BỐ DỮ LIỆU ĐÃ KIỂM ĐỊNH VÀO POSTGRESQL SERVING...")
        published_count = publish_stock_ohlcv()
        run_ctx.records_published = published_count
        logger.info("      [✓] Đã đồng bộ thành công %d bản ghi vào mart_technical.", published_count)

        # -------------------------------------------------------------------------
        # BƯỚC 6: GHI NHẬN LINEAGE & TRẠNG THÁI VẬN HÀNH
        # -------------------------------------------------------------------------
        run_ctx.complete(status="SUCCESS")
        update_dataset_state(
            dataset_name="market_ohlcv",
            target_table="mart_technical.fact_daily_market_ohlcv",
            run_id=run_ctx.run_id,
            record_count=published_count,
            snapshot_date=today_dt.strftime("%Y-%m-%d")
        )

        # -------------------------------------------------------------------------
        # BƯỚC 7: TỰ ĐỘNG THĂM DÒ & ĐỒNG BỘ BÁO CÁO TÀI CHÍNH QUÝ (SMART SYNC)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [6/8] BƯỚC 6: KIỂM TRA MÙA BCTC & TỰ ĐỘNG ĐỒNG BỘ CUỐN CHIẾU...")
        try:
            from stock_analysis.pipeline.smart_quarterly_sync import run_smart_quarterly_sync
            run_smart_quarterly_sync()
        except Exception as sync_exc:
            logger.warning("Quá trình kiểm tra BCTC quý tự động gặp lỗi (không ảnh hưởng giá ngày): %s", sync_exc)

        # -------------------------------------------------------------------------
        # BƯỚC 8: ĐỒNG BỘ CHỈ SỐ THỊ TRƯỜNG & VĨ MÔ
        # -------------------------------------------------------------------------
        logger.info("\n>>> [7/8] BƯỚC 7: ĐỒNG BỘ CHỈ SỐ THỊ TRƯỜNG (VNINDEX, VN30, VNFINLEAD)...")
        try:
            from stock_analysis.pipeline.daily_auxiliary_sync import sync_market_indices
            sync_market_indices(target_date=today_dt.strftime("%Y-%m-%d"))
        except Exception as idx_exc:
            logger.warning("Quá trình đồng bộ chỉ số thị trường gặp lỗi: %s", idx_exc)

        # -------------------------------------------------------------------------
        # BƯỚC 9: ĐỒNG BỘ GIA TĂNG TIN TỨC & VĂN BẢN CÔNG BỐ (AI NLP)
        # -------------------------------------------------------------------------
        logger.info("\n>>> [8/8] BƯỚC 8: ĐỒNG BỘ GIA TĂNG TIN TỨC & VĂN BẢN CÔNG BỐ (AI NLP)...")
        try:
            from stock_analysis.pipeline.daily_auxiliary_sync import sync_daily_news_disclosures
            sync_daily_news_disclosures(lookback_days=3)
        except Exception as news_exc:
            logger.warning("Quá trình đồng bộ tin tức NLP gặp lỗi: %s", news_exc)

        duration = time.time() - start_time
        logger.info("\n" + "=" * 80)
        logger.info(">>> [THÀNH CÔNG] PIPELINE THỊ TRƯỜNG & TIN TỨC HÀNG NGÀY HOÀN TẤT TRONG %.2f GIÂY <<<", duration)
        logger.info("Run ID: %s | Manifest: %s", run_ctx.run_id, run_ctx.manifest_path)
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error("!!! [THẤT BẠI] PIPELINE BỊ LỖI: %s", e, exc_info=True)
        run_ctx.complete(status="FAILED", error_msg=str(e))
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Chạy luồng cập nhật giá thị trường hàng ngày (Daily EOD)")
    parser.add_argument("--force", action="store_true", help="Bắt buộc chạy kể cả ngày nghỉ")
    parser.add_argument("--skip-api", action="store_true", help="Bỏ qua gọi API và tái chạy từ Bronze")
    parser.add_argument("--date", type=str, default=None, help="Ngày chỉ định YYYY-MM-DD")
    args = parser.parse_args()

    success = run_pipeline(force=args.force, target_date=args.date, skip_api=args.skip_api)
    sys.exit(0 if success else 1)
