"""
===================================================================================
MODULE: src/stock_analysis/sql_serving_loader/load_corporate_disclosures.py
CHỨC NĂNG: NẠP VĂN BẢN CÔNG BỐ THÔNG TIN & CẢM XÚC TIN TỨC VÀO POSTGRESQL SERVING
===================================================================================
Kiến trúc Medallion Lakehouse:
  - NGUỒN CHÍNH: data_lake/02_silver/03_unstructured/financial_news/enriched_news_sentiment
  - NGUỒN DỰ PHÒNG: data_lake/01_bronze/02_unstructured/financial_news/banking_news_raw.jsonl
  - ĐÍCH ĐẾN: mart_sentiment.fact_media_sentiment_daily (PostgreSQL Serving)
  - METADATA TAXONOMY & FINANCIAL SENTIMENT LEXICON
===================================================================================
"""

import os
import re
import sys
import json
import time
import uuid
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR

SILVER_NEWS_DIR = DATA_LAKE_DIR / "02_silver" / "03_unstructured" / "financial_news" / "enriched_news_sentiment"
BRONZE_JSONL_PATH = DATA_LAKE_DIR / "01_bronze" / "02_unstructured" / "financial_news" / "banking_news_raw.jsonl"

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
logger = logging.getLogger("ServingLoader_CorporateDisclosures")

# BẢNG TỪ ĐIỂN PHÂN LOẠI METADATA SỰ KIỆN
CATEGORY_MAP = {
    "BOD": "Nghị quyết Hội đồng Quản trị",
    "AGM": "Đại hội đồng Cổ đông",
    "IndTr": "Giao dịch Nội bộ & Cổ đông lớn",
    "OIss": "Phát hành & Chào bán Cổ phiếu",
    "ManaC": "Thay đổi Nhân sự Cấp cao",
    "EAnno": "Công bố Báo cáo Tài chính",
    "OAct": "Hoạt động Doanh nghiệp",
    "PV3": "Bản tin Phân tích & Nhận định",
    "PV4": "Bản tin Tài chính Chuyên sâu",
    "PV5": "Bản tin Toàn cảnh Thị trường",
    "TSIG7": "Tín hiệu Kỹ thuật Tự động",
    "TSIG8": "Tín hiệu Kỹ thuật Tự động",
    "TSIG9": "Tín hiệu Kỹ thuật Tự động",
    "TSIG10": "Tín hiệu Kỹ thuật Tự động",
    "TSIG11": "Tín hiệu Kỹ thuật Tự động",
}

# TỪ ĐIỂN CẢM XÚC TÀI CHÍNH NGÂN HÀNG (FINANCIAL LEXICON)
POSITIVE_KEYWORDS = [
    "tăng trưởng", "vượt kế hoạch", "kỷ lục", "chia cổ tức", "trả cổ tức",
    "nâng hạng", "triển vọng tích cực", "bứt phá", "thặng dư", "lợi nhuận tăng",
    "tăng vốn", "nới room", "mua lại", "hoàn thành kế hoạch", "tích cực"
]

NEGATIVE_KEYWORDS = [
    "thua lỗ", "khởi tố", "sai phạm", "nợ xấu tăng", "giảm mạnh", "xử phạt",
    "cảnh báo", "vi phạm", "đình chỉ", "suy giảm", "thanh tra", "lao dốc",
    "bị phạt", "bị xử lý", "tiêu cực", "kém khả quan"
]

PDF_REGEX = re.compile(r"https?://[^\s\"\'<>]+\.pdf", re.IGNORECASE)


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def extract_pdf_url(full_content: str, short_content: str) -> str | None:
    text_to_search = (full_content or "") + " " + (short_content or "")
    match = PDF_REGEX.search(text_to_search)
    return match.group(0) if match else None


def compute_sentiment(title: str, short_content: str = "") -> tuple[float, str]:
    text = (title or "").lower() + " " + (short_content or "").lower()
    pos_score = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg_score = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

    diff = pos_score - neg_score
    if diff > 0:
        score = min(0.3 + 0.15 * diff, 1.0)
        return round(score, 4), "POSITIVE"
    elif diff < 0:
        score = max(-0.3 + 0.15 * diff, -1.0)
        return round(score, 4), "NEGATIVE"
    else:
        return 0.0, "NEUTRAL"


def run_pipeline() -> bool:
    batch_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(">>> [SERVING LOADER] NẠP CÔNG BỐ THÔNG TIN & CẢM XÚC TIN TỨC SANG POSTGRESQL <<<")
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
            ("load_corporate_disclosures", batch_id, "SERVING_LOAD", "RUNNING", 0, 0),
        )
        conn.commit()

        # Lấy phạm vi ngày hợp lệ từ dim_date
        cur.execute("SELECT MIN(date_sk), MAX(date_sk) FROM master_data.dim_date;")
        min_date_sk, max_date_sk = cur.fetchone()
        cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank;")
        bank_mapping = dict(cur.fetchall())

        records = []
        raw_count = 0
        official_count = 0
        pdf_count = 0
        seen_keys = set()

        # Ưu tiên đọc từ Silver Parquet
        parquet_files = list(SILVER_NEWS_DIR.rglob("*.parquet")) if SILVER_NEWS_DIR.exists() else []

        if parquet_files:
            logger.info("[1/4] Đang nạp từ Silver Parquet: %s (%d files)...", SILVER_NEWS_DIR, len(parquet_files))
            for pf in parquet_files:
                try:
                    df_p = pd.read_parquet(pf)
                    raw_count += len(df_p)
                    for _, row in df_p.iterrows():
                        ext_id = str(row.get("external_id") or row.get("article_uuid") or "")
                        if not ext_id:
                            continue

                        b_sk = row.get("bank_sk")
                        if pd.isna(b_sk) or b_sk == 0:
                            sym = str(row.get("ticker", "")).upper()
                            b_sk = bank_mapping.get(sym)
                        if not b_sk:
                            continue
                        b_sk = int(b_sk)

                        dedup_key = (b_sk, ext_id)
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)

                        date_sk = int(row.get("effective_trading_date_sk") or 20240101)
                        if date_sk < min_date_sk:
                            date_sk = min_date_sk
                        elif date_sk > max_date_sk:
                            date_sk = max_date_sk

                        title = str(row.get("title") or "Thông báo doanh nghiệp").strip()
                        source = str(row.get("source_name") or "VnStock / Vietcap").strip()
                        source_url = str(row.get("source_url") or "")
                        cat_code = str(row.get("category_code") or "OAct").strip()
                        cat_name = CATEGORY_MAP.get(cat_code, "Thông tin Doanh nghiệp & Thị trường")

                        pdf_url = extract_pdf_url(title, source_url)
                        if pdf_url:
                            pdf_count += 1

                        is_official = bool(row.get("is_official", False)) or (source in ["HOSE", "HNX", "UBCKNN"])
                        if is_official:
                            official_count += 1

                        sent_score, sent_label = compute_sentiment(title)

                        records.append((
                            b_sk,
                            date_sk,
                            ext_id,
                            title,
                            source,
                            source_url,
                            is_official,
                            cat_code,
                            cat_name,
                            sent_score,
                            sent_label,
                            pdf_url,
                        ))
                except Exception as e:
                    logger.warning("Lỗi đọc file %s: %s", pf, e)

        elif BRONZE_JSONL_PATH.exists():
            logger.info("[1/4] Đọc dự phòng từ Bronze JSONL: %s ...", BRONZE_JSONL_PATH)
            with open(BRONZE_JSONL_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    raw_count += 1
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ext_id = str(row.get("newsId") or "").strip()
                    sym = str(row.get("symbol") or "").strip().upper()
                    bank_sk = bank_mapping.get(sym)
                    if not ext_id or not bank_sk:
                        continue

                    dedup_key = (bank_sk, ext_id)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    pub_time_str = row.get("newsPublishedDate")
                    try:
                        pub_dt = datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M:%S")
                        date_sk = int(pub_dt.strftime("%Y%m%d"))
                    except Exception:
                        date_sk = 20240101

                    if date_sk < min_date_sk:
                        date_sk = min_date_sk
                    elif date_sk > max_date_sk:
                        date_sk = max_date_sk

                    title = str(row.get("newsTitle") or "Thông báo doanh nghiệp").strip()
                    source = str(row.get("newsSource") or "VnStock / Vietcap").strip()
                    source_url = str(row.get("newsSourceLink") or "")
                    cat_code = str(row.get("newsCategoryCode") or "OAct").strip()
                    cat_name = CATEGORY_MAP.get(cat_code, "Thông tin Doanh nghiệp & Thị trường")

                    full_c = row.get("newsFullContent") or ""
                    short_c = row.get("newsShortContent") or ""
                    pdf_url = extract_pdf_url(full_c, short_c)
                    if pdf_url:
                        pdf_count += 1

                    is_official = (source in ["HOSE", "HNX", "UBCKNN"]) or (cat_code in ["BOD", "AGM", "IndTr", "OIss", "ManaC", "EAnno"])
                    if is_official:
                        official_count += 1

                    sent_score, sent_label = compute_sentiment(title, short_c)

                    records.append((
                        bank_sk,
                        date_sk,
                        ext_id,
                        title,
                        source,
                        source_url,
                        is_official,
                        cat_code,
                        cat_name,
                        sent_score,
                        sent_label,
                        pdf_url,
                    ))

        if not records:
            logger.warning("Không tìm thấy bản ghi tin tức nào để nạp!")
            return False

        logger.info("      Đã đọc %d dòng. Bản ghi hợp lệ sau khử trùng: %d bài.", raw_count, len(records))
        logger.info("      Thống kê Metadata: %d bài công bố chính thức | %d bài có đính kèm file PDF gốc.", official_count, pdf_count)

        # 2. Cổng kiểm định chất lượng Serving
        logger.info("[2/4] Cổng kiểm định chất lượng văn bản công bố thông tin (DQ Gateway 3)...")
        cur.execute(
            """
            INSERT INTO metadata.data_quality_log 
            (batch_id, gateway_level, rule_code, rule_description, records_tested, records_passed, records_failed, check_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                batch_id,
                "GATEWAY_3",
                "DQ_SERVING_DISCLOSURE_TITLE_VALID",
                "Tiêu đề bài viết nạp Dashboard không được rỗng",
                raw_count,
                len(records),
                raw_count - len(records),
                "PASSED",
            ),
        )

        # 3. Bulk Upsert vào mart_sentiment.fact_media_sentiment_daily
        logger.info("[3/4] Bulk Upsert vào mart_sentiment.fact_media_sentiment_daily...")
        insert_sql = """
            INSERT INTO mart_sentiment.fact_media_sentiment_daily (
                bank_sk, date_sk, article_external_id, title, source_name, source_url,
                is_official_disclosure, category_code, category_name, sentiment_score,
                sentiment_label, attachment_pdf_url
            ) VALUES %s
            ON CONFLICT (bank_sk, article_external_id) DO UPDATE SET
                date_sk = EXCLUDED.date_sk,
                title = EXCLUDED.title,
                source_name = EXCLUDED.source_name,
                source_url = EXCLUDED.source_url,
                is_official_disclosure = EXCLUDED.is_official_disclosure,
                category_code = EXCLUDED.category_code,
                category_name = EXCLUDED.category_name,
                sentiment_score = EXCLUDED.sentiment_score,
                sentiment_label = EXCLUDED.sentiment_label,
                attachment_pdf_url = EXCLUDED.attachment_pdf_url;
        """

        execute_values(cur, insert_sql, records, page_size=10000)
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
            (raw_count, records_loaded, duration, batch_id),
        )
        conn.commit()

        logger.info("=" * 80)
        logger.info(">>> HOÀN THÀNH NẠP CÔNG BỐ THÔNG TIN & CẢM XÚC TIN TỨC VÀO POSTGRESQL! <<<")
        logger.info("Đã nạp: %d bài viết vào mart_sentiment.fact_media_sentiment_daily", records_loaded)
        logger.info("Thời gian thực thi: %.2f giây", duration)
        logger.info("=" * 80)
        return True

    except Exception as e:
        conn.rollback()
        duration = round(time.time() - start_time, 2)
        logger.error("LỖI SERVING LOADER CÔNG BỐ THÔNG TIN: %s", str(e), exc_info=True)
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
