"""
===================================================================================
MODULE: src/stock_analysis/pipeline/daily_auxiliary_sync.py
CHỨC NĂNG: ĐỒNG BỘ TỰ ĐỘNG CÁC PHÂN HỆ PHỤ TRỢ HÀNG NGÀY (DAILY AUXILIARY SYNC)
1. Chỉ số thị trường (VNINDEX, VN30, VNFINLEAD, HNXIndex, UPCOMIndex...)
2. Tin tức & Công bố thông tin 27 Ngân hàng + Chấm điểm NLP + Trích xuất PDF
3. Sự kiện Doanh nghiệp & Cổ tức tiền mặt 27 Ngân hàng
Tích hợp trực tiếp vào Pipeline hàng ngày lúc 15:45 (sau phiên ATC).
===================================================================================
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import pandas as pd
import requests
import psycopg2
from psycopg2.extras import execute_values

# Ngăn chặn vnai/vnstock exit khi chạm rate limit
try:
    import vnai.beam.quota
    vnai.beam.quota.CleanErrorContext.__exit__ = lambda self, exc_type, exc_val, exc_tb: False
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.sql_serving_loader.load_corporate_disclosures import (
    CATEGORY_MAP,
    extract_pdf_url,
    compute_sentiment,
)

logger = logging.getLogger("DailyAuxiliarySync")

BRONZE_NEWS_PATH = DATA_LAKE_DIR / "01_bronze" / "02_unstructured" / "financial_news" / "banking_news_raw.jsonl"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")


def get_db_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)


# =============================================================================
# 1. ĐỒNG BỘ CHỈ SỐ THỊ TRƯỜNG (MARKET INDICES)
# =============================================================================
def sync_market_indices(target_date: Optional[str] = None) -> int:
    """
    Đồng bộ gia tăng chuỗi điểm số VN-Index, VN30, VNFINLEAD, HNX-Index, UPCOM...
    Tự động quét từ ngày max_date hiện có trong DB đến ngày hiện tại.
    """
    logger.info(">>> [ĐỒNG BỘ CHỈ SỐ THỊ TRƯỜNG] Bắt đầu quét chỉ số VNINDEX, VN30, VNFINLEAD...")
    
    from vnstock.explorer.vci.quote import Quote as VCIQuote

    conn = get_db_connection()
    cur = conn.cursor()

    INDICES = [
        ("VNINDEX", "Chỉ số VN-Index (HOSE)", "INDEX_VNINDEX_CLOSE"),
        ("VN30", "Chỉ số VN30", "INDEX_VN30_CLOSE"),
        ("VNFINLEAD", "Chỉ số Tài chính Chọn lọc VNFINLEAD", "INDEX_VNFINLEAD_CLOSE"),
        ("VN100", "Chỉ số VN100", "INDEX_VN100_CLOSE"),
        ("VNMID", "Chỉ số VN Midcap", "INDEX_VNMID_CLOSE"),
        ("VNSML", "Chỉ số VN Smallcap", "INDEX_VNSML_CLOSE"),
        ("HNXIndex", "Chỉ số HNX-Index", "INDEX_HNXINDEX_CLOSE"),
        ("HNX30", "Chỉ số HNX30", "INDEX_HNX30_CLOSE"),
        ("UPCOMIndex", "Chỉ số UPCOM-Index", "INDEX_UPCOMINDEX_CLOSE"),
    ]

    total_inserted = 0
    today_str = target_date or datetime.now().strftime("%Y-%m-%d")

    for sym, name, code in INDICES:
        try:
            cur.execute("SELECT MAX(date_sk) FROM mart_technical.fact_macro_indicators WHERE indicator_code = %s;", (code,))
            max_sk = cur.fetchone()[0]

            today_sk = int(datetime.strptime(today_str, "%Y-%m-%d").strftime("%Y%m%d"))
            if max_sk and max_sk >= today_sk:
                continue

            if not max_sk:
                start_date = "2024-01-01"
            else:
                dt = datetime.strptime(str(max_sk), "%Y%m%d")
                start_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

            q = VCIQuote(symbol=sym)
            df = q.history(start=start_date, end=today_str)
            if df is not None and not df.empty:
                records = []
                for _, r in df.iterrows():
                    d_sk = int(pd.to_datetime(r["time"]).strftime("%Y%m%d"))
                    val = float(r["close"])
                    records.append((
                        d_sk, code, f"Điểm đóng cửa {name}", "MARKET_INDEX", val, "POINTS", "DAILY"
                    ))

                if records:
                    sql = """
                        INSERT INTO mart_technical.fact_macro_indicators (
                            date_sk, indicator_code, indicator_name, category, value, unit, frequency
                        ) VALUES %s
                        ON CONFLICT (indicator_code, date_sk) DO UPDATE SET value = EXCLUDED.value;
                    """
                    execute_values(cur, sql, records)
                    conn.commit()
                    total_inserted += len(records)
            time.sleep(0.5)
        except Exception as e:
            logger.warning("      [!] Lỗi quét chỉ số %s: %s", sym, e)

    cur.close()
    conn.close()
    logger.info("      [✓] Hoàn tất đồng bộ Chỉ số thị trường: +%d bản ghi mới.", total_inserted)
    return total_inserted


# =============================================================================
# 2. ĐỒNG BỘ GIA TĂNG TIN TỨC & VĂN BẢN CÔNG BỐ (AI NLP SENTIMENT)
# =============================================================================
def sync_daily_news_disclosures(lookback_days: int = 3) -> int:
    """
    Quét cào gia tăng tin tức và văn bản công bố thông tin mới nhất cho 27 ngân hàng,
    chấm điểm sắc thái NLP, trích xuất link PDF và nạp vào mart_sentiment.
    """
    logger.info(">>> [ĐỒNG BỘ TIN TỨC NLP] Bắt đầu quét tin tức & công bố mới 27 Ngân hàng...")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank WHERE is_active = TRUE AND bank_sk > 0 ORDER BY ticker;")
    banks = cur.fetchall()

    list_url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/news"
    detail_url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/news/{news_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    session = requests.Session()
    session.headers.update(headers)

    cur.execute("SELECT article_external_id FROM mart_sentiment.fact_media_sentiment_daily;")
    existing_ext_ids = {r[0] for r in cur.fetchall()}

    all_new_articles = []
    to_date = datetime.now().strftime("%Y%m%d")

    for ticker, bsk in banks:
        cur.execute("SELECT MAX(date_sk) FROM mart_sentiment.fact_media_sentiment_daily WHERE bank_sk = %s;", (bsk,))
        max_sk = cur.fetchone()[0]

        if max_sk:
            dt = datetime.strptime(str(max_sk), "%Y%m%d") - timedelta(days=lookback_days)
            from_date = dt.strftime("%Y%m%d")
        else:
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

        params = {
            "ticker": ticker,
            "fromDate": from_date,
            "toDate": to_date,
            "languageId": 1,
            "page": 0,
            "size": 50,
        }

        try:
            resp = session.get(list_url, params=params, timeout=8)
            if resp.status_code == 200:
                content = resp.json().get("data", {}).get("content", [])
                for item in content:
                    item_id = str(item.get("id") or "")
                    if item_id and item_id not in existing_ext_ids:
                        time.sleep(0.08)
                        det_resp = session.get(detail_url.format(news_id=item_id), timeout=8)
                        if det_resp.status_code == 200:
                            det_data = det_resp.json().get("data", {})
                            if det_data:
                                det_data["_target_ticker"] = ticker
                                det_data["_bank_sk"] = bsk
                                all_new_articles.append(det_data)
                                existing_ext_ids.add(item_id)
        except Exception as e:
            logger.warning("      [!] Lỗi quét tin tức %s: %s", ticker, e)

        time.sleep(0.15)

    total_inserted = 0
    if all_new_articles:
        # 1. Lưu Bronze Data Lake
        BRONZE_NEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BRONZE_NEWS_PATH, "a", encoding="utf-8") as f:
            for art in all_new_articles:
                f.write(json.dumps(art, ensure_ascii=False) + "\n")

        # 2. Xử lý NLP & Nạp PostgreSQL
        records_to_insert = []
        for art in all_new_articles:
            bsk = art["_bank_sk"]
            ext_id = str(art.get("id") or art.get("newsId"))
            pub_str = art.get("publicDate") or ""
            try:
                dt_obj = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                d_sk = int(dt_obj.strftime("%Y%m%d"))
            except Exception:
                d_sk = int(datetime.now().strftime("%Y%m%d"))

            title = str(art.get("newsTitle") or "").strip()
            source = str(art.get("newsSource") or "Vietcap").strip()
            source_url = str(art.get("newsSourceLink") or "")
            cat_code = str(art.get("newsCategoryCode") or "OAct").strip()
            cat_name = CATEGORY_MAP.get(cat_code, "Thông tin Doanh nghiệp & Thị trường")

            full_c = art.get("newsFullContent") or ""
            short_c = art.get("newsShortContent") or ""
            pdf_url = extract_pdf_url(full_c, short_c)
            is_official = (source in ["HOSE", "HNX", "UBCKNN"]) or (cat_code in ["BOD", "AGM", "IndTr", "OIss", "ManaC", "EAnno"])
            sent_score, sent_label = compute_sentiment(title, short_c)

            records_to_insert.append((
                bsk, d_sk, ext_id, title, source, source_url, is_official,
                cat_code, cat_name, sent_score, sent_label, pdf_url
            ))

        insert_sql = """
            INSERT INTO mart_sentiment.fact_media_sentiment_daily (
                bank_sk, date_sk, article_external_id, title, source_name, source_url,
                is_official_disclosure, category_code, category_name, sentiment_score,
                sentiment_label, attachment_pdf_url
            ) VALUES %s
            ON CONFLICT (bank_sk, article_external_id) DO UPDATE SET
                date_sk = EXCLUDED.date_sk,
                title = EXCLUDED.title,
                source_url = EXCLUDED.source_url,
                is_official_disclosure = EXCLUDED.is_official_disclosure,
                attachment_pdf_url = EXCLUDED.attachment_pdf_url;
        """
        execute_values(cur, insert_sql, records_to_insert, page_size=2000)
        conn.commit()
        total_inserted = len(records_to_insert)

    cur.close()
    conn.close()
    logger.info("      [✓] Hoàn tất đồng bộ Tin tức & NLP: +%d bài viết mới nạp DWH.", total_inserted)
    return total_inserted


# =============================================================================
# 3. ĐỒNG BỘ SỰ KIỆN DOANH NGHIỆP & CỔ TỨC TIỀN MẶT
# =============================================================================
def sync_corporate_events() -> int:
    """
    Quét và cập nhật các sự kiện doanh nghiệp, ngày chốt quyền và chi trả cổ tức mới.
    """
    logger.info(">>> [ĐỒNG BỘ SỰ KIỆN DOANH NGHIỆP] Quét sự kiện & cổ tức mới 27 Ngân hàng...")

    from vnstock.explorer.vci.company import Company

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank WHERE is_active = TRUE AND bank_sk > 0 ORDER BY ticker;")
    banks = cur.fetchall()

    cur.execute("SELECT ticker, event_name_vi, record_date FROM mart_governance.fact_corporate_events;")
    existing_events = {(tk, str(ename).strip(), str(rdate)) for tk, ename, rdate in cur.fetchall()}

    total_added = 0

    for ticker, bsk in banks:
        try:
            c = Company(ticker)
            ev = c.events()
            if ev is not None and not ev.empty:
                for _, r in ev.iterrows():
                    ename = str(r.get("event_name_vi") or r.get("event_title") or "Sự kiện").strip()
                    rdate = str(r.get("record_date") or "")
                    if (ticker, ename, rdate) not in existing_events:
                        exdate = r.get("exright_date")
                        pdate = r.get("payout_date")
                        val_share = float(r.get("value_per_share") or 0.0) if pd.notnull(r.get("value_per_share")) else 0.0
                        ratio = float(r.get("exercise_ratio") or 0.0) if pd.notnull(r.get("exercise_ratio")) else 0.0
                        ecode = str(r.get("event_code") or "OTHE")
                        ename_en = str(r.get("event_name_en") or ename)

                        insert_sql = """
                            INSERT INTO mart_governance.fact_corporate_events (
                                ticker, event_code, event_name_vi, event_name_en,
                                exright_date, record_date, payout_date,
                                value_per_share, exercise_ratio, bank_sk
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """
                        cur.execute(insert_sql, (
                            ticker, ecode, ename, ename_en,
                            exdate if pd.notnull(exdate) else None,
                            rdate if pd.notnull(rdate) and rdate not in ("", "None", "nan") else None,
                            pdate if pd.notnull(pdate) and pdate not in ("", "None", "nan") else None,
                            val_share, ratio, bsk
                        ))
                        existing_events.add((ticker, ename, rdate))
                        total_added += 1

                conn.commit()
            time.sleep(2.0)
        except Exception as e:
            logger.warning("      [!] Lỗi quét sự kiện %s: %s", ticker, e)

    cur.close()
    conn.close()
    logger.info("      [✓] Hoàn tất đồng bộ Sự kiện doanh nghiệp: +%d sự kiện mới.", total_added)
    return total_added


def run_all_auxiliary_sync(target_date: Optional[str] = None) -> Dict[str, int]:
    """Hàm chạy toàn bộ các phân hệ phụ trợ hàng ngày"""
    t0 = time.time()
    n_idx = sync_market_indices(target_date=target_date)
    n_news = sync_daily_news_disclosures(lookback_days=3)
    n_ev = sync_corporate_events()
    duration = round(time.time() - t0, 2)
    logger.info(">>> HOÀN TẤT ĐỒNG BỘ PHỤ TRỢ: %d chỉ số, %d tin tức, %d sự kiện (%.1fs)", n_idx, n_news, n_ev, duration)
    return {"indices": n_idx, "news": n_news, "events": n_ev, "duration_seconds": duration}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_all_auxiliary_sync()
