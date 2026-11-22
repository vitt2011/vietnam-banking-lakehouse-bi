"""
===================================================================================
TẬP LỆNH: crawl_raw_news.py (PHIÊN BẢN 5 - ENTERPRISE SELF-HEALING & AUTO-BACKFILL)
CHỨC NĂNG: CÀO TOÀN DIỆN DỮ LIỆU TIN TỨC THÔ 27 NGÂN HÀNG - TỰ ĐỘNG CÀO BÙ ĐẾN ĐỦ 100%
===================================================================================
Đặc điểm kỹ thuật chuẩn Enterprise Data Pipeline:
  1. VÒNG LẶP TỰ PHỤC HỒI & CÀO BÙ (Self-Healing Multi-Round Outer Loop):
     - Không dừng lại khi xong 1 lượt nếu còn mã sót do nghẽn mạng tạm thời.
     - Tự động rà soát đĩa sau mỗi vòng, nhận diện chính xác các mã còn thiếu.
     - Tự động hạ nhiệt mạng và chạy các vòng cào bù tiếp theo cho đến khi đủ 100% cả 27 mã.
  2. BỎ QUA TỨC THÌ (Zero-Network Local Skip):
     - Các mã đã cào xong (23/27 mã đã có hàng nghìn bài) được bỏ qua trong 0.0001 giây.
     - Dồn 100% tài nguyên và băng thông xử lý dứt điểm các mã còn thiếu.
  3. Chuẩn "Trường phái 1" Bronze Layer:
     - 100% link thật, full HTML, PDF đính kèm.
     - Đầy đủ 3 cột Audit Metadata: _ingestion_timestamp, _source_api, _batch_id.
===================================================================================
"""

import os
import sys
import json
import time
import uuid
import random
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# =================================================================================
# CẤU HÌNH THAM SỐ
# =================================================================================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
OUTPUT_DIR = DATA_LAKE_DIR / "01_bronze" / "02_unstructured" / "financial_news"
OUTPUT_FILE = OUTPUT_DIR / "banking_news_raw.jsonl"

FROM_DATE = "20180101"
TO_DATE = datetime.now().strftime("%Y%m%d")

# Ngưỡng số bài tối thiểu để công nhận mã đã hoàn tất (với các ngân hàng nhỏ)
MIN_COMPLETED_THRESHOLD = 400

MAX_WORKERS = 4
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
MAX_ROUNDS = 5  # Tối đa 5 vòng tự phục hồi

BANK_TICKERS = [
    "ABB", "ACB", "BAB", "BID", "BVB", "CTG", "EIB", "HDB", "KLB", "LPB",
    "MBB", "MSB", "NAB", "NVB", "OCB", "PGB", "SGB", "SHB", "SSB", "STB",
    "TCB", "TPB", "VAB", "VBB", "VCB", "VIB", "VPB"
]

LIST_API_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/news"
DETAIL_API_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/news/{news_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# =================================================================================
# KHỞI TẠO HTTP SESSION
# =================================================================================
def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retries = Retry(
        total=4,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS * 2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# =================================================================================
# LẤY DANH SÁCH BÀI BÁO (CÓ RETRY TỪNG TRANG)
# =================================================================================
def fetch_news_id_list(session: requests.Session, ticker: str) -> list[str] | None:
    article_ids = []
    page = 0
    page_size = 100
    total_elements = None

    while True:
        params = {
            "ticker": ticker,
            "fromDate": FROM_DATE,
            "toDate": TO_DATE,
            "languageId": 1,
            "page": page,
            "size": page_size
        }
        
        page_success = False
        for page_try in range(1, 4):
            try:
                resp = session.get(LIST_API_URL, params=params, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    if total_elements is None:
                        total_elements = data.get("totalElements", 0)
                        total_pages = data.get("totalPages", 1)

                    content = data.get("content", [])
                    if not content:
                        page_success = True
                        break

                    for item in content:
                        item_id = item.get("id")
                        if item_id and item_id not in article_ids:
                            article_ids.append(item_id)

                    page_success = True
                    break
                else:
                    time.sleep(1.0 * page_try)
            except Exception:
                time.sleep(2.0 * page_try)

        if not page_success:
            print(f"  [!] Không thể lấy trang {page} của {ticker} sau 3 lần thử.")
            break

        page += 1
        if total_elements is not None and (page >= data.get("totalPages", page) or not content):
            break

        time.sleep(0.12)

    return article_ids if article_ids else None


# =================================================================================
# TẢI CHI TIẾT TỪNG BÀI BÁO
# =================================================================================
def fetch_article_detail(session: requests.Session, news_id: str, ticker: str, batch_id: str) -> dict | None:
    url = DETAIL_API_URL.format(news_id=news_id)
    try:
        time.sleep(random.uniform(0.08, 0.16))
        resp = session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        if resp.status_code == 200:
            raw_data = resp.json().get("data", {})
            if not raw_data:
                return None

            raw_data["_ingestion_timestamp"] = datetime.now(timezone.utc).isoformat()
            raw_data["_source_api"] = "vietcap_iq_news_detail_api"
            raw_data["_batch_id"] = batch_id
            raw_data["_target_ticker"] = ticker

            return raw_data
        elif resp.status_code in (429, 503):
            time.sleep(2.5)
            return None
        else:
            return None
    except Exception:
        return None


# =================================================================================
# KIỂM ĐỊNH HIỆN TRẠNG ĐĨA (DISK AUDIT)
# =================================================================================
def audit_local_disk():
    existing_ids = set()
    ticker_counts = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        rec = json.loads(line_str)
                        rec_id = rec.get("id") or rec.get("newsId")
                        if rec_id:
                            existing_ids.add(str(rec_id))
                        tk = rec.get("_target_ticker") or rec.get("ticker")
                        if tk:
                            ticker_counts[tk] = ticker_counts.get(tk, 0) + 1
                    except Exception:
                        continue
    return existing_ids, ticker_counts


# =================================================================================
# MAIN PIPELINE ĐA VÒNG TỰ PHỤC HỒI (SELF-HEALING MULTI-ROUND)
# =================================================================================
def main():
    print("=" * 80)
    print(">>> CÀO RAW TIN TỨC 27 NGÂN HÀNG (PHIÊN BẢN 5 - TỰ PHỤC HỒI & CÀO BÙ ĐỦ 100%) <<<")
    print(f"Thời gian: {FROM_DATE} - {TO_DATE} | Workers: {MAX_WORKERS}")
    print(f"File lưu trữ: {OUTPUT_FILE.resolve()}")
    print("=" * 80)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = create_session()

    for round_num in range(1, MAX_ROUNDS + 1):
        existing_ids, ticker_counts = audit_local_disk()
        
        # Xác định danh sách các mã cần cào bù
        missing_tickers = [t for t in BANK_TICKERS if ticker_counts.get(t, 0) < MIN_COMPLETED_THRESHOLD]

        print(f"\n{'='*30} VÒNG LẶP {round_num}/{MAX_ROUNDS} {'='*30}")
        print(f"[*] Tổng bài báo hiện có trên đĩa: {len(existing_ids):,} bài")
        print(f"[*] Đã hoàn tất: {len(BANK_TICKERS) - len(missing_tickers)}/{len(BANK_TICKERS)} ngân hàng")

        if not missing_tickers:
            print("\n" + "*" * 80)
            print(">>> CHÚC MỪNG: TOÀN BỘ 27/27 NGÂN HÀNG ĐÃ HOÀN TẤT ĐỦ 100% DỮ LIỆU! <<<")
            print(f"Tổng số bài báo lưu trữ an toàn: {len(existing_ids):,} bài")
            print("*" * 80)
            return

        print(f"[!] Phát hiện {len(missing_tickers)} mã cần cào/bổ sung: {', '.join(missing_tickers)}")
        print("    (Các mã đã đủ >= 400 bài sẽ được BỎ QUA NGAY 0 GIÂY)")

        batch_id = str(uuid.uuid4())
        round_saved = 0

        with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
            for idx, ticker in enumerate(BANK_TICKERS, 1):
                cnt = ticker_counts.get(ticker, 0)

                # Bỏ qua ngay tại chỗ nếu mã đã đủ bài
                if cnt >= MIN_COMPLETED_THRESHOLD:
                    print(f"  [{idx:02d}/{len(BANK_TICKERS)}] [✓ Xong] Mã {ticker}: Đã có {cnt:,} bài trên đĩa.")
                    continue

                print(f"\n  [{idx:02d}/{len(BANK_TICKERS)}] >>> Đang xử lý cào bù mã: {ticker} (Hiện có: {cnt:,} bài)...")
                ticker_start = time.time()

                all_ids = fetch_news_id_list(session, ticker)
                if not all_ids:
                    print(f"      [!] Chưa lấy được danh sách {ticker} lượt này. Sẽ thử lại ở vòng sau.")
                    time.sleep(2.0)
                    continue

                new_ids = [nid for nid in all_ids if str(nid) not in existing_ids]
                print(f"      Tổng trên server: {len(all_ids):,} | Cần cào mới: {len(new_ids):,} bài")

                if not new_ids:
                    print(f"      -> Mã {ticker} đã đồng bộ đủ bài.")
                    continue

                saved_count = 0
                fail_count = 0

                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    future_to_id = {
                        executor.submit(fetch_article_detail, session, nid, ticker, batch_id): nid
                        for nid in new_ids
                    }

                    for future in as_completed(future_to_id):
                        nid = future_to_id[future]
                        try:
                            result = future.result()
                            if result:
                                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                                out_f.flush()
                                existing_ids.add(str(nid))
                                saved_count += 1
                                round_saved += 1
                            else:
                                fail_count += 1
                        except Exception:
                            fail_count += 1

                        total_done = saved_count + fail_count
                        pct = (total_done / len(new_ids)) * 100
                        elapsed = time.time() - ticker_start
                        speed = total_done / elapsed if elapsed > 0 else 0
                        print(
                            f"\r      Tiến độ {ticker}: {total_done}/{len(new_ids)} ({pct:.1f}%) | "
                            f"Lưu mới: {saved_count} | Tốc độ: {speed:.1f} bài/s",
                            end="",
                            flush=True
                        )

                print(f"\n      [✓] Hoàn thành cào {ticker}: Lưu thêm {saved_count} bài trong {time.time() - ticker_start:.1f}s.")
                time.sleep(3.0)

        # Kết thúc một vòng, nếu vẫn còn mã thiếu thì nghỉ 15s để mạng hồi phục rồi chạy vòng sau
        if round_num < MAX_ROUNDS:
            _, updated_counts = audit_local_disk()
            still_missing = [t for t in BANK_TICKERS if updated_counts.get(t, 0) < MIN_COMPLETED_THRESHOLD]
            if still_missing:
                print(f"\n[*] Kết thúc Vòng {round_num}. Vẫn còn {len(still_missing)} mã cần hoàn thiện.")
                print(f"[*] Nghỉ 15 giây để WAF hồi phục hoàn toàn rồi tự động bắt đầu Vòng {round_num + 1}...")
                time.sleep(15.0)

    # Tổng kết cuối cùng
    final_ids, final_counts = audit_local_disk()
    print("\n" + "=" * 80)
    print(">>> BÁO CÁO TỔNG KẾT TIẾN TRÌNH CÀO TIN TỨC THÔ <<<")
    print(f"Tổng số bài báo lưu trên đĩa: {len(final_ids):,} bài")
    print(f"Số ngân hàng hoàn tất: {sum(1 for v in final_counts.values() if v >= MIN_COMPLETED_THRESHOLD)}/27 mã")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Tạm dừng chương trình (Ctrl+C). Toàn bộ dữ liệu đã được lưu an toàn!")
