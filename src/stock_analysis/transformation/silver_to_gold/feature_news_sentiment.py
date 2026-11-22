"""
===================================================================================
FEATURE ENGINE: src/transformation/silver_to_gold/feature_news_sentiment.py
CHỨC NĂNG: ĐỊNH LƯỢNG CẢM XÚC TIN TỨC & TỔNG HỢP THEO NGÀY GIAO DỊCH SANG TẦNG GOLD
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 117-118 & Phần 4, Mục 419-423)
Đầu ra: data_lake/03_gold/daily_bank_sentiment_agg/year=YYYY/month=MM/
===================================================================================
"""

import sys
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
SILVER_NEWS_DIR = DATA_LAKE_DIR / "02_silver" / "03_unstructured" / "financial_news" / "enriched_news_sentiment"
GOLD_SENT_DIR = DATA_LAKE_DIR / "03_gold" / "05_Chi_So_Cam_Xuc_Tin_Tuc"
GOLD_SENT_DIR.mkdir(parents=True, exist_ok=True)

# Từ điển sắc thái tài chính ngân hàng
POSITIVE_KEYWORDS = [
    "tăng trưởng", "kỷ lục", "vượt kế hoạch", "lợi nhuận cao", "chia cổ tức",
    "mua ròng", "tăng vốn", "nâng hạng", "khởi sắc", "tích cực", "mở rộng",
    "bứt phá", "dẫn đầu", "nâng trần", "thu hồi nợ", "giảm nợ xấu"
]

NEGATIVE_KEYWORDS = [
    "giảm sút", "thua lỗ", "nợ xấu tăng", "bị phạt", "vi phạm", "khởi tố",
    "điều tra", "hạ bậc", "bán tháo", "áp lực", "rủi ro", "cảnh báo",
    "thanh tra", "khiếu nại", "tiêu cực", "lao dốc"
]


def score_sentiment(title: str) -> tuple:
    """Chấm điểm polarity (-1 đến +1) và gán nhãn cảm xúc"""
    t_lower = str(title).lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in t_lower)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in t_lower)

    if pos > neg:
        score = min(0.3 + 0.2 * pos, 1.0)
        label = "POSITIVE"
    elif neg > pos:
        score = max(-0.3 - 0.2 * neg, -1.0)
        label = "NEGATIVE"
    else:
        score = 0.0
        label = "NEUTRAL"
    return score, label


def run_feature_news_sentiment():
    print(">>> [GOLD 5/5] Feature Engine: Định lượng Cảm xúc & Tổng hợp Tâm lý Truyền thông theo Ngày...")

    news_files = list(SILVER_NEWS_DIR.rglob("*.snappy.parquet"))
    if not news_files:
        print("      Không tìm thấy dữ liệu Silver News!")
        return 0

    all_dfs = [pd.read_parquet(f) for f in news_files]
    df_news = pd.concat(all_dfs, ignore_index=True)
    print(f"      Đã đọc {len(df_news):,} bài báo từ Silver News.")

    # Chấm điểm cảm xúc
    scored = df_news["title"].apply(score_sentiment)
    df_news["polarity_score"] = scored.apply(lambda x: x[0])
    df_news["sentiment_label"] = scored.apply(lambda x: x[1])

    # Trọng số nguồn tin: Văn bản chính thức (w=1.5), Báo chí thường (w=1.0)
    df_news["authority_weight"] = df_news["is_official"].apply(lambda x: 1.5 if x else 1.0)
    df_news["weighted_score"] = df_news["polarity_score"] * df_news["authority_weight"]

    # Tổng hợp theo (ticker, effective_trading_date_sk)
    grouped = df_news.groupby(["ticker", "effective_trading_date_sk"])
    agg_df = grouped.agg(
        bank_uuid=("bank_uuid", "first"),
        bank_sk=("bank_sk", "first"),
        total_articles_count=("article_uuid", "count"),
        official_disclosure_count=("is_official", lambda x: int(sum(x))),
        positive_articles_count=("sentiment_label", lambda x: int(sum(x == "POSITIVE"))),
        neutral_articles_count=("sentiment_label", lambda x: int(sum(x == "NEUTRAL"))),
        negative_articles_count=("sentiment_label", lambda x: int(sum(x == "NEGATIVE"))),
        avg_polarity_score=("polarity_score", "mean"),
        weighted_sentiment_index=("weighted_score", "mean"),
        dominant_event_topic=("category_code", lambda x: x.mode()[0] if not x.empty else "OAct")
    ).reset_index()

    agg_df["avg_polarity_score"] = agg_df["avg_polarity_score"].round(4)
    agg_df["weighted_sentiment_index"] = agg_df["weighted_sentiment_index"].round(4)
    agg_df["year"] = agg_df["effective_trading_date_sk"].apply(lambda d: int(str(d)[:4]))
    agg_df["month"] = agg_df["effective_trading_date_sk"].apply(lambda d: int(str(d)[4:6]))

    # Ghi Hive partitioned: year=YYYY/month=MM/
    total_written = 0
    for (year, month), part_df in agg_df.groupby(["year", "month"]):
        part_dir = GOLD_SENT_DIR / f"year={year}" / f"month={month:02d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.drop(columns=["year", "month"]).to_parquet(part_file, compression="snappy", index=False)
        total_written += len(part_df)

    print(f"      [✓] Hoàn tất xuất bản Gold Daily Sentiment Agg: {total_written:,} phiên tại {GOLD_SENT_DIR}")
    return total_written


if __name__ == "__main__":
    run_feature_news_sentiment()
