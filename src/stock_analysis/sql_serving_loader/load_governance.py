"""
===================================================================================
MODULE: src/stock_analysis/sql_serving_loader/load_governance.py
CHỨC NĂNG: NẠP DỮ LIỆU QUẢN TRỊ & MẠNG LƯỚI QUAN HỆ SỞ HỮU TỪ GOLD/SILVER VÀO POSTGRESQL
===================================================================================
Kiến trúc Medallion Lakehouse:
  - NGUỒN CHÍNH:
    1. data_lake/03_gold/04_Do_Thi_Mang_Luoi_Quan_Tri/part-00000.snappy.parquet
    2. data_lake/02_silver/02_structured/04_Quan_Tri_So_Huu/entity_relationships
  - ĐÍCH:
    - master_data.dim_stakeholder (SCD Type 1)
    - mart_governance.bridge_governance_network (Cầu nối Mạng lưới quan hệ)
===================================================================================
"""

import os
import sys
import time
import uuid
import hashlib
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

GOLD_GOV_PATH = DATA_LAKE_DIR / "03_gold" / "04_Do_Thi_Mang_Luoi_Quan_Tri" / "part-00000.snappy.parquet"
SILVER_GOV_PATH = (
    DATA_LAKE_DIR
    / "02_silver"
    / "02_structured"
    / "04_Quan_Tri_So_Huu"
    / "entity_relationships"
    / "snapshot_year=2026.snappy.parquet"
)

# Dự phòng Bronze
BRONZE_DIR = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "04_Quan_Tri_So_Huu"
OFFICERS_PATH = BRONZE_DIR / "bank_officers.parquet"
SHAREHOLDERS_PATH = BRONZE_DIR / "bank_shareholders.parquet"
SUBSIDIARIES_PATH = BRONZE_DIR / "bank_subsidiaries.parquet"

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
logger = logging.getLogger("ServingLoader_Governance")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def make_stakeholder_code(name: str) -> str:
    cleaned = "".join(c for c in name.strip().lower() if c.isalnum() or c.isspace())
    h = hashlib.md5(cleaned.encode("utf-8")).hexdigest()[:12]
    return f"STK_{h.upper()}"


def run_pipeline() -> bool:
    batch_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(">>> [SERVING LOADER] NẠP MẠNG LƯỚI QUẢN TRỊ TỪ LAKE SANG POSTGRESQL <<<")
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
            ("load_governance", batch_id, "SERVING_LOAD", "RUNNING", 0, 0),
        )
        conn.commit()

        # 1. Đọc dữ liệu Quản trị từ Gold hoặc Silver
        source_df = None
        source_layer = None
        if GOLD_GOV_PATH.exists():
            logger.info("[1/4] Đang đọc đồ thị quản trị từ Gold: %s", GOLD_GOV_PATH)
            source_df = pd.read_parquet(GOLD_GOV_PATH)
            source_layer = "03_gold"
        elif SILVER_GOV_PATH.exists():
            logger.info("[1/4] Đang đọc quan hệ quản trị từ Silver: %s", SILVER_GOV_PATH)
            source_df = pd.read_parquet(SILVER_GOV_PATH)
            source_layer = "02_silver"
        else:
            logger.warning("[1/4] Đọc dự phòng dữ liệu quản trị từ Bronze...")
            records_dfs = []
            if OFFICERS_PATH.exists():
                records_dfs.append(pd.read_parquet(OFFICERS_PATH))
            if SHAREHOLDERS_PATH.exists():
                records_dfs.append(pd.read_parquet(SHAREHOLDERS_PATH))
            if SUBSIDIARIES_PATH.exists():
                records_dfs.append(pd.read_parquet(SUBSIDIARIES_PATH))
            if records_dfs:
                source_df = pd.concat(records_dfs, ignore_index=True)
                source_layer = "01_bronze"

        if source_df is None or source_df.empty:
            logger.error("Không tìm thấy dữ liệu quản trị nào!")
            return False

        records_read = len(source_df)
        logger.info("      Đã đọc %d liên kết mạng lưới quản trị từ %s.", records_read, source_layer)

        # Lấy dim_bank mapping
        cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank;")
        bank_mapping = dict(cur.fetchall())

        # 2. Xây dựng danh sách bên liên quan (master_data.dim_stakeholder)
        logger.info("[2/4] Nạp danh mục bên liên quan vào master_data.dim_stakeholder...")
        stakeholders = {}

        if "stakeholder_name" in source_df.columns:
            for _, r in source_df.iterrows():
                name = str(r.get("stakeholder_name", "")).strip()
                if name and name != "nan":
                    code = make_stakeholder_code(name)
                    stk_type = str(r.get("stakeholder_type", "INDIVIDUAL"))
                    stakeholders[code] = (code, name, stk_type)
        else:
            # Fallback format từ Bronze
            for _, r in source_df.iterrows():
                name = str(r.get("officer_name") or r.get("share_holder") or r.get("organ_name", "")).strip()
                if name and name != "nan":
                    code = make_stakeholder_code(name)
                    stk_type = "ORGANIZATION" if any(k in name.lower() for k in ["công ty", "tập đoàn", "quỹ", "fund", "corp"]) else "INDIVIDUAL"
                    stakeholders[code] = (code, name, stk_type)

        insert_stk_sql = """
            INSERT INTO master_data.dim_stakeholder (stakeholder_code, full_name, stakeholder_type)
            VALUES %s
            ON CONFLICT (stakeholder_code) DO NOTHING;
        """
        execute_values(cur, insert_stk_sql, list(stakeholders.values()), page_size=2000)
        conn.commit()

        # Lấy mapping stakeholder_sk
        cur.execute("SELECT stakeholder_code, stakeholder_sk FROM master_data.dim_stakeholder;")
        stk_mapping = dict(cur.fetchall())

        # 3. Xây dựng dữ liệu cầu nối (bridge_governance_network)
        logger.info("[3/4] Xây dựng mắt xích mạng lưới quan hệ sở hữu...")
        bridge_records = []

        if "stakeholder_name" in source_df.columns and "bank_sk" in source_df.columns:
            for _, r in source_df.iterrows():
                b_sk = int(r["bank_sk"]) if pd.notna(r["bank_sk"]) and int(r["bank_sk"]) > 0 else bank_mapping.get(str(r.get("ticker", "")).upper())
                name = str(r["stakeholder_name"]).strip()
                code = make_stakeholder_code(name)
                s_sk = stk_mapping.get(code)
                if b_sk and s_sk:
                    rel_type = str(r.get("relationship_type", "OFFICER"))
                    role = str(r.get("role_title", ""))
                    own_pct = float(r.get("ownership_pct", 0.0))
                    if 0 < own_pct <= 1.0:
                        own_pct = round(own_pct * 100.0, 4)
                    qty = int(r.get("shares_quantity", 0)) if pd.notna(r.get("shares_quantity")) else 0
                    is_cur = bool(r.get("is_current", True))
                    bridge_records.append((b_sk, s_sk, rel_type, role, own_pct, qty, is_cur))

        df_bridge = pd.DataFrame(
            bridge_records,
            columns=["bank_sk", "stakeholder_sk", "relationship_type", "role_title", "ownership_pct", "shares_quantity", "is_current"],
        )
        df_bridge = df_bridge.drop_duplicates(subset=["bank_sk", "stakeholder_sk", "relationship_type"], keep="last")

        logger.info("[4/4] Bulk Upsert vào mart_governance.bridge_governance_network...")
        insert_bridge_sql = """
            INSERT INTO mart_governance.bridge_governance_network (
                bank_sk, stakeholder_sk, relationship_type, role_title, ownership_pct, shares_quantity, is_current
            ) VALUES %s
            ON CONFLICT (bank_sk, stakeholder_sk, relationship_type) DO UPDATE SET
                role_title = EXCLUDED.role_title,
                ownership_pct = EXCLUDED.ownership_pct,
                shares_quantity = EXCLUDED.shares_quantity,
                is_current = EXCLUDED.is_current,
                updated_at = CURRENT_TIMESTAMP;
        """

        clean_records = [
            (
                int(r.bank_sk),
                int(r.stakeholder_sk),
                str(r.relationship_type),
                str(r.role_title),
                float(r.ownership_pct),
                int(r.shares_quantity),
                bool(r.is_current),
            )
            for r in df_bridge.itertuples(index=False)
        ]

        execute_values(cur, insert_bridge_sql, clean_records, page_size=2000)
        conn.commit()

        records_loaded = len(clean_records)
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
        logger.info(">>> HOÀN THÀNH NẠP MẠNG LƯỚI QUẢN TRỊ TỪ LAKE SANG POSTGRESQL! <<<")
        logger.info("Đã nạp: %d bên liên quan vào dim_stakeholder", len(stakeholders))
        logger.info("Đã nạp: %d mắt xích quan hệ vào bridge_governance_network", records_loaded)
        logger.info("Thời gian thực thi: %.2f giây", duration)
        logger.info("=" * 80)
        return True

    except Exception as e:
        conn.rollback()
        duration = round(time.time() - start_time, 2)
        logger.error("LỖI SERVING LOADER QUẢN TRỊ: %s", str(e), exc_info=True)
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
