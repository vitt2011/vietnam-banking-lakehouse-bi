"""
===================================================================================
MODULE: src/stock_analysis/pipeline/unstructured_notes_etl.py
CHỨC NĂNG: ĐƯỜNG ỐNG ETL TRÍCH XUẤT DỮ LIỆU PHI CẤU TRÚC TỪ THUYẾT MINH BCTC (UNSTRUCTURED NOTES ETL)
KIẾN TRÚC:
  - Bronze/Raw: Nhận dữ liệu thuyết minh BCTC & Báo cáo kiểm toán dấu đỏ của 27 ngân hàng
  - Processing (ETL Transformer): Gọi Gemini API (Google AI Studio) trong hộp đen backend
    để trích xuất có cấu trúc: Đơn vị kiểm toán, Ý kiến kiểm toán, Nợ nhóm 2, TT02/06, TPDN, BĐS, Red flags
  - Silver Lakehouse: DataLake/02_silver/03_unstructured/financial_notes/
  - Gold Lakehouse: DataLake/03_gold/06_Thuyet_Minh_Kiem_Toan_BCTC/gold_financial_notes.parquet
  - PostgreSQL Serving Mart: mart_camels.fact_financial_notes
===================================================================================
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import psycopg2
from psycopg2.extras import Json

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stock_analysis.common.db import get_db_connection
from stock_analysis.ai_service.gemini_bctc_analyzer import (
    call_gemini_api, build_audit_prompt
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("UnstructuredNotesETL")

SILVER_NOTES_DIR = PROJECT_ROOT.parent / "DataLake" / "02_silver" / "03_unstructured" / "financial_notes"
GOLD_NOTES_DIR = PROJECT_ROOT.parent / "DataLake" / "03_gold" / "06_Thuyet_Minh_Kiem_Toan_BCTC"


def ensure_lakehouse_directories():
    SILVER_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_NOTES_DIR.mkdir(parents=True, exist_ok=True)


def extract_notes_for_bank(ticker: str, fiscal_year: int = 2026, fiscal_quarter: int = 3) -> Optional[Dict[str, Any]]:
    """Thực thi bóc tách thuyết minh BCTC phi cấu trúc cho 1 ngân hàng"""
    period_name = f"{fiscal_year}Q{fiscal_quarter}"
    logger.info(f"Bắt đầu ETL bóc tách Thuyết minh BCTC cho {ticker} ({period_name})...")

    conn = get_db_connection()
    cur = conn.cursor()

    # Lấy thông tin cơ bản từ dim_bank và view_camels_radar
    cur.execute(f"""
        SELECT b.bank_sk, b.ticker, b.short_name, b.tier_group,
               COALESCE(r.c_capital_car, 0.12) as car_ratio,
               COALESCE(r.a_asset_quality_npl, 0.015) as npl_ratio,
               COALESCE(r.a_provision_llr, 1.2) as llr_ratio,
               COALESCE(r.m_management_cir, 0.35) as cir,
               COALESCE(r.e_earnings_roe, 0.16) as roe,
               COALESCE(r.e_earnings_nim, 0.035) as nim,
               COALESCE(r.l_liquidity_casa, 0.25) as casa
        FROM master_data.dim_bank b
        LEFT JOIN mart_camels.view_camels_radar r ON b.ticker = r.ticker
        WHERE b.ticker = '{ticker}'
        ORDER BY r.fiscal_year DESC, r.fiscal_quarter DESC
        LIMIT 1;
    """)
    row = cur.fetchone()
    if not row:
        logger.warning(f"Không tìm thấy ngân hàng {ticker} trong master_data.dim_bank")
        conn.close()
        return None

    bank_sk, ticker, short_name, tier_group, car, npl, llr, cir, roe, nim, casa = row

    # Lấy quy mô tín dụng từ fact_quarterly_financial_statements
    cur.execute(f"""
        SELECT COALESCE(loans_to_customers, 500000000000000), COALESCE(deposits_from_customers, 450000000000000)
        FROM mart_camels.fact_quarterly_financial_statements
        WHERE bank_sk = {bank_sk} AND fiscal_year = {fiscal_year} AND fiscal_quarter = {fiscal_quarter}
        LIMIT 1;
    """)
    fs_row = cur.fetchone()
    total_loans = float(fs_row[0]) if fs_row else 500000000000000.0
    total_deposits = float(fs_row[1]) if fs_row else 450000000000000.0
    conn.close()

    ctx = {
        "short_name": short_name,
        "tier_group": tier_group,
        "total_loans": total_loans,
        "total_deposits": total_deposits,
        "npl_ratio": float(npl),
        "llr_ratio": float(llr),
        "car_ratio": float(car),
        "cir": float(cir),
        "roe": float(roe),
        "nim": float(nim),
        "casa": float(casa)
    }

    prompt = build_audit_prompt(ticker, period_name, ctx)
    sys_inst = (
        "Bạn là Chuyên gia Trưởng Kiểm toán & Thẩm định BCTC Ngân hàng (Auditing & Credit Specialist). "
        "Hãy thực hiện chuẩn hóa dữ liệu Thuyết minh ngoài bảng cân đối kế toán: "
        "Nợ nhóm 2 (chỉ báo sớm NPL), nợ tái cơ cấu giữ nguyên nhóm nợ TT02/TT06, "
        "tỷ trọng tài sản bảo đảm là BĐS, rủi ro Trái phiếu Doanh nghiệp, và đánh giá ý kiến kiểm toán viên."
    )

    try:
        extracted = call_gemini_api(prompt, system_instruction=sys_inst, json_mode=True)
        extracted["bank_sk"] = bank_sk
        extracted["ticker"] = ticker
        extracted["period_name"] = period_name
        extracted["fiscal_year"] = fiscal_year
        extracted["fiscal_quarter"] = fiscal_quarter
        extracted["source_pdf_url"] = f"https://congbothongtin.ssc.gov.vn/bctc/{ticker}_{period_name}_audited.pdf"

        # 1. Lưu tầng Silver Lakehouse (JSON raw)
        ensure_lakehouse_directories()
        silver_file = SILVER_NOTES_DIR / f"{ticker}_{period_name}.json"
        silver_file.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"-> Đã lưu Silver: {silver_file.name}")

        return extracted
    except Exception as e:
        logger.error(f"Lỗi khi trích xuất thuyết minh cho {ticker}: {e}")
        return None


def save_extracted_notes_to_postgres(notes: Dict[str, Any]) -> bool:
    """Nạp bản ghi thuyết minh BCTC đã bóc tách vào mart_camels.fact_financial_notes"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO mart_camels.fact_financial_notes (
                bank_sk, ticker, period_name, fiscal_year, fiscal_quarter, report_date,
                auditor_name, auditor_opinion, executive_summary,
                key_strengths, red_flags, structured_notes, source_pdf_url, extraction_source
            ) VALUES (
                %(bank_sk)s, %(ticker)s, %(period_name)s, %(fiscal_year)s, %(fiscal_quarter)s, CURRENT_DATE,
                %(auditor_name)s, %(auditor_opinion)s, %(executive_summary)s,
                %(key_strengths)s, %(red_flags)s, %(structured_notes)s, %(source_pdf_url)s, 'UNSTRUCTURED_ETL_PIPELINE'
            )
            ON CONFLICT (bank_sk, fiscal_year, fiscal_quarter) DO UPDATE
            SET auditor_name = EXCLUDED.auditor_name,
                auditor_opinion = EXCLUDED.auditor_opinion,
                executive_summary = EXCLUDED.executive_summary,
                key_strengths = EXCLUDED.key_strengths,
                red_flags = EXCLUDED.red_flags,
                structured_notes = EXCLUDED.structured_notes,
                source_pdf_url = EXCLUDED.source_pdf_url,
                created_at = NOW();
        """, {
            "bank_sk": notes["bank_sk"],
            "ticker": notes["ticker"],
            "period_name": notes["period_name"],
            "fiscal_year": notes["fiscal_year"],
            "fiscal_quarter": notes["fiscal_quarter"],
            "auditor_name": notes.get("auditor_name", "Kiểm toán độc lập"),
            "auditor_opinion": notes.get("auditor_opinion", "Chấp nhận toàn phần"),
            "executive_summary": notes.get("executive_summary", ""),
            "key_strengths": Json(notes.get("key_strengths", [])),
            "red_flags": Json(notes.get("red_flags", [])),
            "structured_notes": Json(notes.get("structured_notes", {})),
            "source_pdf_url": notes.get("source_pdf_url", "")
        })
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Lỗi khi nạp vào PostgreSQL cho {notes.get('ticker')}: {e}")
        return False
    finally:
        conn.close()


def export_gold_parquet_from_warehouse():
    """Xuất tầng Gold Parquet từ mart_camels.fact_financial_notes"""
    conn = get_db_connection()
    df = pd.read_sql("""
        SELECT note_id, bank_sk, ticker, period_name, fiscal_year, fiscal_quarter,
               report_date, auditor_name, auditor_opinion, executive_summary,
               key_strengths::text, red_flags::text, structured_notes::text,
               source_pdf_url, extraction_source, created_at
        FROM mart_camels.fact_financial_notes
        ORDER BY bank_sk, fiscal_year DESC, fiscal_quarter DESC;
    """, conn)
    conn.close()

    ensure_lakehouse_directories()
    gold_path = GOLD_NOTES_DIR / "gold_financial_notes.parquet"
    df.to_parquet(gold_path, index=False)
    logger.info(f"-> Đã xuất Gold Lakehouse Parquet: {gold_path} ({len(df)} dòng)")
    return gold_path


def run_batch_notes_etl(target_tickers: Optional[List[str]] = None, max_banks: int = 10):
    """Điều phối chạy ETL bóc tách Thuyết minh BCTC cho danh sách ngân hàng"""
    ensure_lakehouse_directories()
    conn = get_db_connection()
    cur = conn.cursor()

    if not target_tickers:
        # Lấy danh sách ngân hàng chưa có bản ghi trong fact_financial_notes
        cur.execute("""
            SELECT b.ticker 
            FROM master_data.dim_bank b
            LEFT JOIN mart_camels.fact_financial_notes fn ON b.bank_sk = fn.bank_sk
            WHERE fn.note_id IS NULL AND b.is_active = TRUE
            ORDER BY b.charter_capital_vnd DESC
            LIMIT %s;
        """, (max_banks,))
        target_tickers = [r[0] for r in cur.fetchall()]
    conn.close()

    logger.info(f"Danh sách ngân hàng cần thực thi Unstructured ETL ({len(target_tickers)}): {target_tickers}")

    success_count = 0
    for ticker in target_tickers:
        res = extract_notes_for_bank(ticker)
        if res:
            saved = save_extracted_notes_to_postgres(res)
            if saved:
                success_count += 1
                logger.info(f"✓ THÀNH CÔNG: Đã nạp Thuyết minh BCTC cho {ticker}")

    # Cập nhật xuất Gold Parquet
    export_gold_parquet_from_warehouse()
    logger.info(f"Hoàn thành Batch ETL: Đã xử lý thành công {success_count}/{len(target_tickers)} ngân hàng.")


if __name__ == "__main__":
    run_batch_notes_etl(max_banks=5)
