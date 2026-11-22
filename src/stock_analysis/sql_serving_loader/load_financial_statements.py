"""
===================================================================================
MODULE: src/stock_analysis/sql_serving_loader/load_financial_statements.py
CHỨC NĂNG: NẠP BÁO CÁO TÀI CHÍNH TỪ TẦNG SILVER VÀO POSTGRESQL SERVING MART
===================================================================================
Kiến trúc Medallion Lakehouse:
  - NGUỒN: data_lake/02_silver/02_structured/02_Bao_Cao_Tai_Chinh/standardized_statements
    (Đã qua kiểm định DQ1 Schema và DQ2 Cân đối Kế toán: Tài sản = Nợ + Vốn)
  - ĐÍCH: mart_camels.fact_quarterly_financial_statements (PostgreSQL Serving)
  - IDEMPOTENT: Bulk Upsert (ON CONFLICT DO UPDATE)
  - KIỂM SOÁT VẬN HÀNH: metadata.pipeline_execution_log, ops.dataset_publish_state
===================================================================================
"""

import os
import sys
import time
import uuid
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.governance.lineage_tracker import update_dataset_state

SILVER_FIN_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "02_Bao_Cao_Tai_Chinh" / "standardized_statements"

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
logger = logging.getLogger("ServingLoader_FinancialStatements")


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
    logger.info(">>> [SERVING LOADER] NẠP BÁO CÁO TÀI CHÍNH TỪ SILVER SANG POSTGRESQL <<<")
    logger.info("Batch ID: %s", batch_id)
    logger.info("Thư mục nguồn (Silver): %s", SILVER_FIN_DIR)
    logger.info("=" * 80)

    if not SILVER_FIN_DIR.exists():
        logger.error("Không tìm thấy thư mục Silver Statements: %s", SILVER_FIN_DIR)
        return False

    parquet_files = list(SILVER_FIN_DIR.rglob("*.parquet"))
    if not parquet_files:
        logger.error("Không có file Parquet nào trong thư mục Silver Statements: %s", SILVER_FIN_DIR)
        return False

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
            ("load_financial_statements", batch_id, "SERVING_LOAD", "RUNNING", 0, 0),
        )
        conn.commit()

        logger.info("[1/4] Đang đọc dữ liệu BCTC đã chuẩn hóa từ Silver Lakehouse...")
        dfs = [pd.read_parquet(pf) for pf in parquet_files]
        df_silver = pd.concat(dfs, ignore_index=True)
        records_read = len(df_silver)
        logger.info("      Đã đọc %d bản ghi từ %d file Parquet Silver.", records_read, len(parquet_files))

        # Lọc chỉ lấy báo cáo các Quý (fiscal_quarter = 1, 2, 3, 4)
        df_quarterly = df_silver[df_silver["fiscal_quarter"].isin([1, 2, 3, 4])].copy()

        # Luôn luôn ánh xạ chuẩn xác bank_sk từ master_data.dim_bank theo ticker (tránh lỗi alphabetical index từ Silver)
        cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank;")
        bank_mapping = dict(cur.fetchall())
        df_quarterly["bank_sk"] = df_quarterly["ticker"].astype(str).str.strip().str.upper().map(bank_mapping)

        df_quarterly = df_quarterly.dropna(subset=["bank_sk"]).copy()
        df_quarterly["bank_sk"] = df_quarterly["bank_sk"].astype(int)
        df_quarterly["fiscal_year"] = df_quarterly["fiscal_year"].astype(int)
        df_quarterly["fiscal_quarter"] = df_quarterly["fiscal_quarter"].astype(int)

        # Tính period_date_sk
        q_dates = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
        df_quarterly["period_date_sk"] = [
            int(str(y) + q_dates.get(q, "1231"))
            for y, q in zip(df_quarterly["fiscal_year"], df_quarterly["fiscal_quarter"])
        ]

        logger.info("[2/4] Chuẩn hóa các trường chỉ tiêu kế toán...")
        def _get_num(col: str, default: float = 0.0) -> pd.Series:
            if col in df_quarterly.columns:
                return pd.to_numeric(df_quarterly[col], errors="coerce").fillna(default)
            return pd.Series(default, index=df_quarterly.index)

        df_quarterly["total_assets"] = _get_num("total_assets").round(2)
        df_quarterly["cash_and_gold"] = _get_num("cash_and_precious_metals").round(2)
        df_quarterly["balances_with_sbv"] = _get_num("balances_with_the_sbv").round(2)
        df_quarterly["loans_to_customers"] = _get_num("loans_and_advances_to_customers").round(2)
        
        # Dự phòng rủi ro cho vay khách hàng trên CĐKT
        prov_col = "less_provision_for_losses_on_loans_and_advances_to_customers"
        if prov_col not in df_quarterly.columns:
            prov_col = "provision_for_credit_losses"
        df_quarterly["provision_for_credit_losses"] = _get_num(prov_col).round(2)

        df_quarterly["total_liabilities"] = _get_num("total_liabilities").round(2)
        df_quarterly["deposits_from_customers"] = _get_num("deposits_from_customers").round(2)
        df_quarterly["owners_equity"] = _get_num("owners_equity").round(2)
        df_quarterly["charter_capital"] = _get_num("charter_capital").round(2)

        # KQKD
        df_quarterly["net_interest_income"] = _get_num("net_interest_income").round(2)
        df_quarterly["net_fee_income"] = _get_num("net_fee_and_commission_income").round(2)
        df_quarterly["net_gain_fx"] = _get_num("net_gain_loss_from_foreign_currency_and_gold_dealings").round(2)

        gain_trade = _get_num("net_gain_loss_from_trading_of_trading_securities")
        gain_invest = _get_num("net_gain_loss_from_disposal_of_investment_securities")
        df_quarterly["net_gain_securities"] = (gain_trade + gain_invest).round(2)

        df_quarterly["total_operating_income"] = _get_num("total_operating_income").round(2)
        df_quarterly["general_and_admin_expenses"] = _get_num("general_and_admin_expenses").round(2)
        df_quarterly["provision_expense"] = _get_num("provision_for_credit_losses").abs().round(2)
        df_quarterly["net_profit_before_tax"] = _get_num("net_accounting_profit_loss_before_tax").round(2)
        df_quarterly["net_profit_after_tax"] = _get_num("net_profit_loss_after_tax").round(2)

        df_quarterly["other_operating_income_residual"] = (
            df_quarterly["total_operating_income"]
            - df_quarterly["net_interest_income"]
            - df_quarterly["net_fee_income"]
        ).round(2)
        df_quarterly["is_standalone_quarter"] = True
        df_quarterly["reporting_scope"] = "CONSOLIDATED"

        logger.info("[3/4] Cổng kiểm soát chất lượng Serving (DQ Gateway 3)...")
        # Kiểm tra tổng tài sản phải > 0
        dq_asset_invalid = int((df_quarterly["total_assets"] <= 0).sum())
        cur.execute(
            """
            INSERT INTO metadata.data_quality_log 
            (batch_id, gateway_level, rule_code, rule_description, records_tested, records_passed, records_failed, check_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                batch_id,
                "GATEWAY_3",
                "DQ_SERVING_FS_ASSETS_POSITIVE",
                "Tổng tài sản ngân hàng phục vụ Dashboard phải lớn hơn 0",
                len(df_quarterly),
                len(df_quarterly) - dq_asset_invalid,
                dq_asset_invalid,
                "PASSED" if dq_asset_invalid == 0 else "WARNING",
            ),
        )

        clean_df = df_quarterly[df_quarterly["total_assets"] > 0].copy()
        clean_df = clean_df.drop_duplicates(subset=["bank_sk", "fiscal_year", "fiscal_quarter"], keep="last")
        logger.info("      Số quý tài chính hợp lệ nạp DWH: %d quý.", len(clean_df))

        logger.info("[4/4] Bulk Upsert vào mart_camels.fact_quarterly_financial_statements...")
        insert_sql = """
            INSERT INTO mart_camels.fact_quarterly_financial_statements (
                bank_sk, fiscal_year, fiscal_quarter, period_date_sk,
                total_assets, cash_and_gold, balances_with_sbv, loans_to_customers, provision_for_credit_losses,
                total_liabilities, deposits_from_customers, owners_equity, charter_capital,
                net_interest_income, net_fee_income, net_gain_fx, net_gain_securities, other_operating_income_residual,
                total_operating_income, general_and_admin_expenses, provision_expense,
                net_profit_before_tax, net_profit_after_tax, is_standalone_quarter, reporting_scope
            ) VALUES %s
            ON CONFLICT (bank_sk, fiscal_year, fiscal_quarter) DO UPDATE SET
                period_date_sk = EXCLUDED.period_date_sk,
                total_assets = EXCLUDED.total_assets,
                cash_and_gold = EXCLUDED.cash_and_gold,
                balances_with_sbv = EXCLUDED.balances_with_sbv,
                loans_to_customers = EXCLUDED.loans_to_customers,
                provision_for_credit_losses = EXCLUDED.provision_for_credit_losses,
                total_liabilities = EXCLUDED.total_liabilities,
                deposits_from_customers = EXCLUDED.deposits_from_customers,
                owners_equity = EXCLUDED.owners_equity,
                charter_capital = EXCLUDED.charter_capital,
                net_interest_income = EXCLUDED.net_interest_income,
                net_fee_income = EXCLUDED.net_fee_income,
                net_gain_fx = EXCLUDED.net_gain_fx,
                net_gain_securities = EXCLUDED.net_gain_securities,
                other_operating_income_residual = EXCLUDED.other_operating_income_residual,
                total_operating_income = EXCLUDED.total_operating_income,
                general_and_admin_expenses = EXCLUDED.general_and_admin_expenses,
                provision_expense = EXCLUDED.provision_expense,
                net_profit_before_tax = EXCLUDED.net_profit_before_tax,
                net_profit_after_tax = EXCLUDED.net_profit_after_tax,
                is_standalone_quarter = EXCLUDED.is_standalone_quarter,
                reporting_scope = EXCLUDED.reporting_scope;
        """

        records = [
            (
                int(r.bank_sk),
                int(r.fiscal_year),
                int(r.fiscal_quarter),
                int(r.period_date_sk),
                float(r.total_assets),
                float(r.cash_and_gold),
                float(r.balances_with_sbv),
                float(r.loans_to_customers),
                float(r.provision_for_credit_losses),
                float(r.total_liabilities),
                float(r.deposits_from_customers),
                float(r.owners_equity),
                float(r.charter_capital),
                float(r.net_interest_income),
                float(r.net_fee_income),
                float(r.net_gain_fx),
                float(r.net_gain_securities),
                float(r.other_operating_income_residual),
                float(r.total_operating_income),
                float(r.general_and_admin_expenses),
                float(r.provision_expense),
                float(r.net_profit_before_tax),
                float(r.net_profit_after_tax),
                bool(r.is_standalone_quarter),
                str(r.reporting_scope),
            )
            for r in clean_df.itertuples(index=False)
        ]

        execute_values(cur, insert_sql, records, page_size=2000)
        conn.commit()

        records_loaded = len(records)
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

        update_dataset_state(
            dataset_name="financial_statements",
            target_table="mart_camels.fact_quarterly_financial_statements",
            run_id=batch_id,
            record_count=records_loaded,
        )

        logger.info("=" * 80)
        logger.info(">>> HOÀN TẤT NẠP BÁO CÁO TÀI CHÍNH TỪ SILVER SANG POSTGRESQL! <<<")
        logger.info("Đã nạp: %d quý tài chính vào fact_quarterly_financial_statements", records_loaded)
        logger.info("Thời gian thực thi: %.2f giây", duration)
        logger.info("=" * 80)
        return True

    except Exception as e:
        conn.rollback()
        duration = round(time.time() - start_time, 2)
        logger.error("LỖI SERVING LOADER BCTC: %s", str(e), exc_info=True)
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
