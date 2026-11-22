"""
===================================================================================
MODULE: src/stock_analysis/sql_serving_loader/load_macro_indicators.py
CHỨC NĂNG: NẠP CHỈ SỐ KINH TẾ VĨ MÔ & THỊ TRƯỜNG TỪ SILVER VÀO POSTGRESQL SERVING
===================================================================================
Kiến trúc Medallion Lakehouse:
  - NGUỒN CHÍNH (Silver):
    1. data_lake/02_silver/02_structured/03_Kinh_Te_Vi_Mo/daily_macro_series
    2. data_lake/02_silver/02_structured/01_Giao_Dich_Gia_OHLCV/index_ohlcv
  - NGUỒN DỰ PHÒNG: data_lake/01_bronze/...
  - ĐÍCH: mart_technical.fact_macro_indicators (PostgreSQL Serving)
  - IDEMPOTENT: Bulk Upsert (ON CONFLICT (indicator_code, date_sk) DO UPDATE)
===================================================================================
"""

import os
import sys
import time
import uuid
import logging
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR

SILVER_MACRO_PATH = (
    DATA_LAKE_DIR
    / "02_silver"
    / "02_structured"
    / "03_Kinh_Te_Vi_Mo"
    / "daily_macro_series"
    / "macro_series_2015_2026.snappy.parquet"
)
SILVER_INDEX_DIR = (
    DATA_LAKE_DIR
    / "02_silver"
    / "02_structured"
    / "01_Giao_Dich_Gia_OHLCV"
    / "index_ohlcv"
)

# Dự phòng Bronze
BRONZE_DIR = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "03_Kinh_Te_Vi_Mo"
BRONZE_MACRO_PATH = BRONZE_DIR / "macro_economic_indicators.parquet"
BRONZE_INDICES_PATH = BRONZE_DIR / "market_indices_historical.parquet"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ServingLoader_MacroIndicators")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def run_pipeline() -> bool:
    batch_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(">>> [SERVING LOADER] NẠP CHỈ SỐ KINH TẾ VĨ MÔ & THỊ TRƯỜNG SANG POSTGRESQL <<<")
    logger.info("Batch ID: %s", batch_id)
    logger.info("=" * 80)

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO metadata.pipeline_execution_log 
            (pipeline_name, batch_id, stage_name, status, records_extracted, records_loaded)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            ("load_macro_indicators", batch_id, "SERVING_LOAD", "RUNNING", 0, 0),
        )
        conn.commit()

        # 1. Đọc dữ liệu chỉ số vĩ mô từ Silver (hoặc Bronze)
        records_macro = []
        macro_source_path = SILVER_MACRO_PATH if SILVER_MACRO_PATH.exists() else BRONZE_MACRO_PATH
        if macro_source_path.exists():
            logger.info("[1/4] Đang đọc chỉ số vĩ mô từ: %s", macro_source_path)
            macro_df = pd.read_parquet(macro_source_path)
            macro_df["date_sk"] = pd.to_datetime(macro_df["date"]).dt.strftime("%Y%m%d").astype(int)

            for r in macro_df.itertuples(index=False):
                records_macro.append({
                    "date_sk": int(r.date_sk),
                    "indicator_code": str(r.indicator_code),
                    "indicator_name": str(r.indicator_name),
                    "category": str(r.category),
                    "value": float(r.value),
                    "unit": str(r.unit) if pd.notna(r.unit) else "",
                    "frequency": str(r.frequency) if pd.notna(r.frequency) else "DAILY",
                })
        else:
            logger.warning("Không tìm thấy file chỉ số vĩ mô!")

        # 2. Đọc dữ liệu chỉ số thị trường (VNINDEX, VN30...) từ Silver index_ohlcv (hoặc Bronze)
        records_idx = []
        if SILVER_INDEX_DIR.exists() and list(SILVER_INDEX_DIR.rglob("*.parquet")):
            logger.info("[2/4] Đang đọc chuỗi chỉ số thị trường từ Silver: %s", SILVER_INDEX_DIR)
            idx_files = list(SILVER_INDEX_DIR.rglob("*.parquet"))
            idx_dfs = [pd.read_parquet(f) for f in idx_files]
            idx_df = pd.concat(idx_dfs, ignore_index=True)
            for r in idx_df.itertuples(index=False):
                sym = str(r.symbol).upper()
                idx_name = str(r.index_name) if pd.notna(getattr(r, "index_name", None)) else f"Chỉ số {sym}"
                d_sk = int(r.date_sk) if hasattr(r, "date_sk") and pd.notna(r.date_sk) else int(pd.to_datetime(r.time).strftime("%Y%m%d"))
                records_idx.append({
                    "date_sk": d_sk,
                    "indicator_code": f"INDEX_{sym}_CLOSE",
                    "indicator_name": f"Điểm đóng cửa {idx_name}",
                    "category": "MARKET_INDEX",
                    "value": float(r.close),
                    "unit": "POINTS",
                    "frequency": "DAILY",
                })
        elif BRONZE_INDICES_PATH.exists():
            logger.info("[2/4] Đọc dự phòng chỉ số thị trường từ Bronze: %s", BRONZE_INDICES_PATH)
            idx_df = pd.read_parquet(BRONZE_INDICES_PATH)
            idx_df["date_sk"] = pd.to_datetime(idx_df["time"]).dt.strftime("%Y%m%d").astype(int)
            for r in idx_df.itertuples(index=False):
                sym = str(r.symbol).upper()
                idx_name = str(r.index_name) if pd.notna(r.index_name) else f"Chỉ số {sym}"
                records_idx.append({
                    "date_sk": int(r.date_sk),
                    "indicator_code": f"INDEX_{sym}_CLOSE",
                    "indicator_name": f"Điểm đóng cửa {idx_name}",
                    "category": "MARKET_INDEX",
                    "value": float(r.close),
                    "unit": "POINTS",
                    "frequency": "DAILY",
                })

        all_records = records_macro + records_idx
        if not all_records:
            logger.warning("Không có bản ghi chỉ số vĩ mô/thị trường nào để nạp!")
            return False

        df_combined = pd.DataFrame(all_records)
        records_read = len(df_combined)
        logger.info("      Tổng số bản ghi đọc được: %d (Vĩ mô: %d, Chỉ số: %d)", records_read, len(records_macro), len(records_idx))

        # 3. Lọc trùng lặp và khớp dim_date
        cur.execute("SELECT date_sk FROM master_data.dim_date;")
        valid_dates = set(r[0] for r in cur.fetchall())
        clean_df = df_combined.drop_duplicates(subset=["indicator_code", "date_sk"], keep="last")
        clean_df = clean_df[clean_df["date_sk"].isin(valid_dates)].copy()

        # 4. Cổng kiểm định chất lượng Serving
        logger.info("[3/4] Cổng kiểm định chất lượng dữ liệu vĩ mô (DQ Gateway 3)...")
        cur.execute(
            """
            INSERT INTO metadata.data_quality_log 
            (batch_id, gateway_level, rule_code, rule_description, records_tested, records_passed, records_failed, check_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                batch_id,
                "GATEWAY_3",
                "DQ_SERVING_MACRO_NOT_NULL",
                "Giá trị chỉ số vĩ mô nạp Serving không được rỗng",
                records_read,
                len(clean_df),
                records_read - len(clean_df),
                "PASSED",
            ),
        )

        logger.info("[4/4] Bulk Upsert vào mart_technical.fact_macro_indicators...")
        insert_sql = """
            INSERT INTO mart_technical.fact_macro_indicators (
                date_sk, indicator_code, indicator_name, category, value, unit, frequency
            ) VALUES %s
            ON CONFLICT (indicator_code, date_sk) DO UPDATE SET
                indicator_name = EXCLUDED.indicator_name,
                category = EXCLUDED.category,
                value = EXCLUDED.value,
                unit = EXCLUDED.unit,
                frequency = EXCLUDED.frequency;
        """

        records_to_insert = [
            (
                int(r.date_sk),
                str(r.indicator_code),
                str(r.indicator_name),
                str(r.category),
                float(r.value),
                str(r.unit),
                str(r.frequency),
            )
            for r in clean_df.itertuples(index=False)
        ]

        execute_values(cur, insert_sql, records_to_insert, page_size=10000)
        conn.commit()

        records_loaded = len(records_to_insert)
        duration = round(time.time() - start_time, 2)

        cur.execute(
            """
            UPDATE metadata.pipeline_execution_log
            SET status = 'SUCCESS',
                records_extracted = %s,
                records_loaded = %s,
                execution_duration_sec = %s
            WHERE batch_id = %s;
            """,
            (records_read, records_loaded, duration, batch_id),
        )
        conn.commit()

        logger.info("=" * 80)
        logger.info(">>> HOÀN THÀNH NẠP CHỈ SỐ VĨ MÔ & THỊ TRƯỜNG VÀO POSTGRESQL! <<<")
        logger.info("Đã nạp: %d dòng chỉ số vào fact_macro_indicators", records_loaded)
        logger.info("Thời gian thực thi: %.2f giây", duration)
        logger.info("=" * 80)
        return True

    except Exception as e:
        conn.rollback()
        duration = round(time.time() - start_time, 2)
        logger.error("LỖI SERVING LOADER VĨ MÔ: %s", str(e), exc_info=True)
        try:
            cur.execute(
                """
                UPDATE metadata.pipeline_execution_log
                SET status = 'FAILED',
                    error_message = %s,
                    execution_duration_sec = %s
                WHERE batch_id = %s;
                """,
                (str(e), duration, batch_id),
            )
            conn.commit()
        except Exception:
            pass
        return False
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    if not run_pipeline():
        sys.exit(1)
