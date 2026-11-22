"""
===================================================================================
PIPELINE: src/transformation/bronze_to_silver/clean_news.py
CHỨC NĂNG: LÀM SẠCH VĂN BẢN, GÁN UUID, ÁP DỤNG CUT-OFF 15:00 VÀO TẦNG SILVER
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 106-107 & Phần 3, Mục 261-266)
Đầu ra: data_lake/02_silver/financial_news/enriched_news_sentiment/year=YYYY/month=MM/
===================================================================================
"""

import sys
import json
import gzip
import html
import unicodedata
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR

from stock_analysis.common.hashing import generate_article_uuid
from stock_analysis.common.trading_calendar import get_effective_trading_date

BRONZE_NEWS_JSONL = DATA_LAKE_DIR / "01_bronze" / "02_unstructured" / "financial_news" / "banking_news_raw.jsonl"
BRONZE_NEWS_GZ = DATA_LAKE_DIR / "01_bronze" / "02_unstructured" / "financial_news" / "banking_news_raw.jsonl.gz"
SILVER_BANK_PATH = DATA_LAKE_DIR / "02_silver" / "01_master_data" / "mdm_bank.snappy.parquet"
SILVER_NEWS_DIR = DATA_LAKE_DIR / "02_silver" / "03_unstructured" / "financial_news" / "enriched_news_sentiment"


def clean_text_nfc(text: str) -> str:
    """Giải mã HTML entities và chuẩn hóa Unicode NFC tiếng Việt"""
    if not text or not isinstance(text, str):
        return ""
    decoded = html.unescape(text)
    normalized = unicodedata.normalize("NFC", decoded)
    return normalized.strip()


def check_bot_generated(title: str) -> bool:
    """Gán cờ bài viết sinh tự động từ robot bản tin chứng khoán"""
    t_lower = title.lower()
    patterns = [
        "bản tin thị trường", "nhật ký giao dịch", "tổng hợp phiên",
        "khối ngoại mua ròng", "tự doanh mua bán", "nhận định chứng khoán",
        "top cổ phiếu", "tổng quan giao dịch"
    ]
    return any(p in t_lower for p in patterns)


def run_clean_news() -> int:
    print(">>> [SILVER NEWS] Chuyển đổi Bronze -> Silver: Tin tức & Văn bản công bố thông tin...")
    if not BRONZE_NEWS_JSONL.exists():
        print(f"      Không tìm thấy {BRONZE_NEWS_JSONL}, bỏ qua.")
        return 0

    # 1. Đóng gói nén Bronze .jsonl.gz nếu chưa có
    if not BRONZE_NEWS_GZ.exists():
        print("      Đang nén Bronze JSONL sang .jsonl.gz (chuẩn bất biến)...")
        with open(BRONZE_NEWS_JSONL, "rb") as f_in, gzip.open(BRONZE_NEWS_GZ, "wb") as f_out:
            while chunk := f_in.read(1048576):
                f_out.write(chunk)
        print(f"      [✓] Đã tạo Bronze bất biến: {BRONZE_NEWS_GZ}")

    # Đọc MDM bank
    df_banks = pd.read_parquet(SILVER_BANK_PATH)
    bank_map = df_banks.set_index("ticker")[["bank_uuid", "bank_sk"]].to_dict(orient="index")

    # 2. Đọc và làm sạch streaming từng bài báo
    print("      Đang làm sạch và tính toán ngày Cut-off 15:00 cho 44,684 bài báo...")
    articles = []
    with open(BRONZE_NEWS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                ext_id = str(r.get("id") or r.get("newsId", "")).strip()
                if not ext_id:
                    continue

                ticker = str(r.get("_target_ticker") or r.get("ticker", "")).strip()
                if not ticker or ticker not in bank_map:
                    continue

                pub_str = str(r.get("publicDate") or "")
                try:
                    dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.now()

                # Áp dụng quy tắc Cut-off 15:00
                eff_date = get_effective_trading_date(dt)
                eff_date_sk = int(eff_date.strftime("%Y%m%d"))

                title_clean = clean_text_nfc(str(r.get("newsTitle") or ""))
                source_link = str(r.get("newsSourceLink") or "")
                source_name = clean_text_nfc(str(r.get("newsSource") or "Vietcap"))
                cat_code = str(r.get("newsCategoryCode") or "OAct").strip()

                # Sinh article_uuid bất biến từ source_link hoặc ext_id
                art_uuid = generate_article_uuid(source_link if source_link.startswith("http") else f"{ticker}_{ext_id}")

                articles.append({
                    "article_uuid": art_uuid,
                    "external_id": ext_id,
                    "ticker": ticker,
                    "bank_uuid": bank_map[ticker]["bank_uuid"],
                    "bank_sk": bank_map[ticker]["bank_sk"],
                    "published_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "publish_date": dt.date(),
                    "publish_year": dt.year,
                    "publish_month": dt.month,
                    "effective_trading_date_sk": eff_date_sk,
                    "title": title_clean,
                    "source_name": source_name,
                    "source_url": source_link,
                    "category_code": cat_code,
                    "is_official": source_name in ["HOSE", "HNX", "UBCKNN"] or cat_code in ["BOD", "AGM", "IndTr", "OIss", "ManaC", "EAnno"],
                    "is_bot_generated": check_bot_generated(title_clean)
                })
            except Exception:
                continue

    df_news = pd.DataFrame(articles)
    df_news = df_news.drop_duplicates(subset=["ticker", "external_id"], keep="last")
    print(f"      Đã làm sạch {len(df_news):,} bài báo hợp lệ.")

    # 3. Ghi Hive partitioned: year=YYYY/month=MM/
    total_written = 0
    for (year, month), part_df in df_news.groupby(["publish_year", "publish_month"]):
        part_dir = SILVER_NEWS_DIR / f"year={year}" / f"month={month:02d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.drop(columns=["publish_year", "publish_month"]).to_parquet(part_file, compression="snappy", index=False)
        total_written += len(part_df)

    print(f"      [✓] Đã xuất bản Silver News: {total_written:,} bài tại {SILVER_NEWS_DIR}")
    return total_written


if __name__ == "__main__":
    run_clean_news()
