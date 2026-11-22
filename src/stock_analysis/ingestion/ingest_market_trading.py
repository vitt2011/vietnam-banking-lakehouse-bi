"""

Tập lệnh: stock_analysis/data/vnstock_api.py

Chức năng: Thu thập toàn bộ 15-20 năm dữ liệu lịch sử giá (OHLCV) cho 27 mã cổ phiếu Ngân hàng từ năm 2000 đến nay.

          Sử dụng trực tiếp module gốc VCI (vnstock.explorer.vci.quote.Quote) để vượt qua giới hạn 8 năm của bản cộng đồng.

          Tối ưu bộ nhớ tức thời (Memory Downcasting), lưu trữ Data Lake Bronze định dạng .parquet (pyarrow + snappy).

Tuân thủ tuyệt đối quy tắc phân tách Mã nguồn (Code) và Dữ liệu (Data).

"""



import logging

import sys

# Configure UTF-8 for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import time

from datetime import date

from pathlib import Path

from typing import List, Optional



import pandas as pd



# Ngăn chặn vnai/vnstock gọi sys.exit() khi đạt rate limit để try-except có thể kiểm soát và retry an toàn

try:

    import vnai.beam.quota

    vnai.beam.quota.CleanErrorContext.__exit__ = lambda self, exc_type, exc_val, exc_tb: False

except Exception:

    pass



from vnstock.explorer.vci.quote import Quote as VCIQuote



# Cấu hình logging chuyên nghiệp cho môi trường production

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] %(message)s",

    datefmt="%Y-%m-%d %H:%M:%S",

)

logger = logging.getLogger(__name__)



# ------------------------------------------------------------------------------

# 1. KHAI BÁO DANH MỤC MỤC TIÊU (27 MÃ NGÂN HÀNG)

# ------------------------------------------------------------------------------

BANKING_TICKERS: List[str] = [

    "ACB", "ABB", "BAB", "BID", "BVB", "CTG", "EIB", "HDB", "KLB", "LPB",

    "MBB", "MSB", "NAB", "NVB", "OCB", "PGB", "SGB", "SHB", "SSB", "STB",

    "TCB", "TPB", "VAB", "VBB", "VCB", "VIB", "VPB",

]



TARGET_SECTOR: str = "Ngan_Hang"

START_DATE: str = "2000-01-01"



# ------------------------------------------------------------------------------

# QUY TẮC I/O (ĐƯỜNG DẪN TƯƠNG ĐỐI TRỎ VỀ DATA LAKE BRONZE LAYER)

# ------------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR, BRONZE_MARKET_DIR

BRONZE_DATA_DIR: Path = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "01_Giao_Dich_Gia_OHLCV"

OUTPUT_PARQUET_PATH: Path = BRONZE_DATA_DIR / "vnstock_historical.parquet"





def check_and_throttle_quota(safety_threshold: int = 2) -> None:

    """

    Kiểm tra chủ động quota API của vnai/vnstock (hạn mức 20 req/phút gói Guest).

    Nếu số lượt còn lại <= safety_threshold, tự động tạm dừng để reset cửa sổ 1 phút.

    """

    try:

        from vnai.beam.quota import guardian

        status = guardian.get_limit_status()

        remaining = status.get("minute_limit", {}).get("remaining", 20)

        reset_in = status.get("minute_limit", {}).get("reset_in_seconds", 60)

        if remaining <= safety_threshold:

            wait_time = max(reset_in + 2.0, 5.0)

            logger.info("Chủ động điều tiết Rate Limit: Quota còn %d lượt. Đang tạm nghỉ %.1f giây...", remaining, wait_time)

            time.sleep(wait_time)

    except Exception:

        pass





def downcast_memory(df: pd.DataFrame, ticker: str, sector: str = TARGET_SECTOR) -> pd.DataFrame:

    """

    Tối ưu hóa bộ nhớ RAM cho DataFrame:

    - Gán ticker và sector rồi ép sang kiểu category.

    - Ép kiểu open, high, low, close sang float32.

    - Ép kiểu volume sang int32.

    """

    df_opt = df.copy()



    # Khử trùng lặp cột nếu có

    if df_opt.columns.duplicated().any():

        df_opt = df_opt.loc[:, ~df_opt.columns.duplicated(keep="first")]



    # Gán nhãn nhận diện

    df_opt["ticker"] = ticker

    df_opt["ticker"] = df_opt["ticker"].astype("category")



    df_opt["sector"] = sector

    df_opt["sector"] = df_opt["sector"].astype("category")



    # Chuẩn hóa cột thời gian

    if "time" in df_opt.columns:

        df_opt["time"] = pd.to_datetime(df_opt["time"])



    # Ép kiểu giá sang float32

    price_cols = ["open", "high", "low", "close"]

    for col in price_cols:

        if col in df_opt.columns:

            df_opt[col] = df_opt[col].astype("float32")



    # Ép kiểu khối lượng sang int32

    if "volume" in df_opt.columns:

        df_opt["volume"] = df_opt["volume"].fillna(0).astype("int32")



    return df_opt





def fetch_full_banking_history(

    tickers: Optional[List[str]] = None,

    start_date: str = START_DATE,

    end_date: Optional[str] = None,

    sleep_interval: float = 1.0,

) -> pd.DataFrame:

    """

    Thu thập dữ liệu lịch sử giá toàn bộ (15-20 năm) bằng VCIQuote trực tiếp.

    """

    if tickers is None:

        tickers = BANKING_TICKERS



    if end_date is None:

        end_date = date.today().strftime("%Y-%m-%d")



    total_tickers = len(tickers)

    collected_dfs: List[pd.DataFrame] = []

    failed_tickers: List[str] = []



    logger.info("=" * 80)

    logger.info(

        "BẮT ĐẦU THU THẬP DỮ LIỆU LỊCH SỬ TOÀN DIỆN CHO %d MÃ NGÂN HÀNG (TỪ %s ĐẾN %s)",

        total_tickers, start_date, end_date,

    )

    logger.info("Phương thức: Bypass module vnai bằng VCIQuote gốc để lấy trọn vẹn dữ liệu từ ngày chào sàn")

    logger.info("=" * 80)



    for idx, ticker in enumerate(tickers, start=1):

        logger.info("[%02d/%02d] Đang tải toàn bộ dữ liệu lịch sử mã: %s...", idx, total_tickers, ticker)



        success = False

        max_retries = 2



        for attempt in range(max_retries + 1):

            check_and_throttle_quota()



            try:

                client = VCIQuote(symbol=ticker)

                df = client.history(start=start_date, end=end_date)



                if df is not None and not df.empty:

                    # Sắp xếp theo dòng thời gian

                    if "time" in df.columns:

                        df["time"] = pd.to_datetime(df["time"])

                        df = df.sort_values("time").reset_index(drop=True)

                        earliest_date = df["time"].min().strftime("%d/%m/%Y")

                        latest_date = df["time"].max().strftime("%d/%m/%Y")

                    else:

                        earliest_date = "N/A"

                        latest_date = "N/A"



                    # Ép kiểu Downcasting ngay lập tức

                    df_opt = downcast_memory(df, ticker=ticker, sector=TARGET_SECTOR)

                    collected_dfs.append(df_opt)



                    logger.info(

                        " -> Mã %s: Thành công tải %d phiên giao dịch (Từ %s đến %s).",

                        ticker, len(df_opt), earliest_date, latest_date,

                    )

                    success = True

                    break

                else:

                    logger.warning(" -> Mã %s: API trả về DataFrame rỗng.", ticker)

                    break



            except Exception as exc:

                err_msg = str(exc).lower()

                if "rate limit" in err_msg or "429" in err_msg:

                    if attempt < max_retries:

                        logger.warning(" -> Mã %s: Chạm ngưỡng Rate Limit. Đang chờ 60 giây trước khi thử lại...", ticker)

                        time.sleep(60.0)

                        continue

                logger.warning(" -> Mã %s: Xảy ra lỗi - %s: %s", ticker, type(exc).__name__, exc)

                break



        if not success:

            failed_tickers.append(ticker)



        # Rate limiting: nghỉ 1.0 giây giữa mỗi mã

        if idx < total_tickers:

            time.sleep(sleep_interval)



    if not collected_dfs:

        raise RuntimeError("Không thu thập được dữ liệu cho bất kỳ mã cổ phiếu nào!")



    logger.info("=" * 80)

    logger.info("HOÀN TẤT THU THẬP: %d/%d mã thành công | %d mã thất bại.", len(collected_dfs), total_tickers, len(failed_tickers))

    if failed_tickers:

        logger.warning("Danh sách mã thất bại: %s", failed_tickers)



    # Nối tất cả DataFrames

    combined_df = pd.concat(collected_dfs, ignore_index=True)

    combined_df["ticker"] = combined_df["ticker"].astype("category")

    combined_df["sector"] = combined_df["sector"].astype("category")



    return combined_df





def save_to_parquet(df: pd.DataFrame, output_path: Path = OUTPUT_PARQUET_PATH) -> Path:

    """Lưu trữ DataFrame vào Data Lake Bronze theo chuẩn Parquet PyArrow Snappy."""

    output_path.parent.mkdir(parents=True, exist_ok=True)



    logger.info("Đang ghi dữ liệu vào Data Lake (Bronze Layer): %s...", output_path)

    df.to_parquet(

        output_path,

        engine="pyarrow",

        compression="snappy",

        index=False,

    )



    file_size_kb = output_path.stat().st_size / 1024

    logger.info(

        "Lưu thành công tệp Parquet! Dung lượng: %.2f KB (%.2f MB) | Tổng số bản ghi: %d phiên.",

        file_size_kb, file_size_kb / 1024, len(df),

    )

    return output_path





def sync_incremental_stock_prices(

    tickers: Optional[List[str]] = None,

    output_path: Path = OUTPUT_PARQUET_PATH,

) -> int:

    """

    Cập nhật gia tăng (Incremental Sync) dữ liệu giá cho 27 ngân hàng từ ngày gần nhất đến hôm nay.

    - Tự động tra cứu MAX(time) trong tệp Parquet Bronze (Single Source of Truth)

    - Chỉ kéo các phiên giao dịch còn thiếu

    - Cập nhật và đồng bộ tệp Parquet Bronze (DataLake/01_bronze/).

    """

    if tickers is None:

        tickers = BANKING_TICKERS

        

    logger.info("=" * 80)

    logger.info("BẮT ĐẦU CẬP NHẬT GIA TĂNG (INCREMENTAL SYNC) GIÁ CỔ PHIẾU 27 NGÂN HÀNG")

    logger.info("=" * 80)

    

    # 1. Tra cứu ngày lớn nhất hiện có từ tệp Parquet Bronze (SSOT)

    max_dict = {}

    if output_path.exists():

        df_pq = pd.read_parquet(output_path)

        max_s = df_pq.groupby('ticker', observed=False)['time'].max()

        max_dict = dict(zip(max_s.index, pd.to_datetime(max_s.values)))

    else:

        logger.info("Chưa tìm thấy tệp Bronze %s, sẽ thực hiện kéo mới từ %s.", output_path, START_DATE)

            

    today_str = date.today().strftime("%Y-%m-%d")

    collected_new = []

    

    for idx, ticker in enumerate(tickers, start=1):

        last_dt = max_dict.get(ticker)

        if last_dt is not None:

            start_dt = (last_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        else:

            start_dt = START_DATE

            

        if start_dt > today_str:

            logger.info("[%02d/%02d] Mã %s: Đã cập nhật mới nhất (%s), bỏ qua.", idx, len(tickers), ticker, last_dt.strftime("%Y-%m-%d"))

            continue

            

        logger.info("[%02d/%02d] Mã %s: Cần kéo bù từ %s đến %s...", idx, len(tickers), ticker, start_dt, today_str)

        check_and_throttle_quota()

        

        for attempt in range(3):

            check_and_throttle_quota()

            try:

                client = VCIQuote(symbol=ticker)

                df_new = client.history(start=start_dt, end=today_str)

                if df_new is not None and not df_new.empty:

                    df_new['time'] = pd.to_datetime(df_new['time'])

                    if last_dt is not None:

                        df_new = df_new[df_new['time'] > last_dt]

                        

                    if not df_new.empty:

                        df_opt = downcast_memory(df_new, ticker=ticker, sector=TARGET_SECTOR)

                        collected_new.append(df_opt)

                        logger.info("  -> Mã %s: Kéo thành công %d phiên mới (%s đến %s).",

                                    ticker, len(df_opt), df_opt['time'].min().strftime('%Y-%m-%d'), df_opt['time'].max().strftime('%Y-%m-%d'))

                    else:

                        logger.info("  -> Mã %s: Không có phiên giao dịch mới.", ticker)

                else:

                    logger.info("  -> Mã %s: Không có phiên giao dịch mới.", ticker)

                break

            except Exception as e:

                err_str = str(e).lower()

                if "rate limit" in err_str or "giới hạn" in err_str or "429" in err_str:

                    logger.warning("  -> Mã %s chạm Rate Limit. Tự động tạm nghỉ 62s trước khi thử lại...", ticker)

                    time.sleep(62.0)

                else:

                    logger.warning("  -> Mã %s gặp lỗi: %s. Đang thử lại...", ticker, e)

                    time.sleep(3.0)

                    

        time.sleep(3.0)

        

    if not collected_new:

        logger.info("Tất cả mã ngân hàng đã cập nhật đầy đủ, không có dữ liệu mới.")

        return 0

        

    df_all_new = pd.concat(collected_new, ignore_index=True)

    

    # 2. Cập nhật Parquet Bronze (Append & Deduplicate)

    if output_path.exists():

        df_bronze = pd.read_parquet(output_path)

        df_combined = pd.concat([df_bronze, df_all_new], ignore_index=True)

        df_combined = df_combined.drop_duplicates(subset=['ticker', 'time'], keep='last')

        df_combined = df_combined.sort_values(['ticker', 'time']).reset_index(drop=True)

        save_to_parquet(df_combined, output_path)

    else:

        save_to_parquet(df_all_new, output_path)

        

    logger.info("Đã đồng bộ %d dòng mới vào Data Lake Bronze Parquet: %s", len(df_all_new), output_path)

    return len(df_all_new)





def main() -> None:

    """Hàm main thực thi chương trình trực tiếp từ Terminal."""

    import argparse

    parser = argparse.ArgumentParser(description="VNStock API Ingestion Runner")

    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental",

                        help="Chế độ chạy: full (kéo từ 2000) hoặc incremental (kéo bù phiên mới)")

    args = parser.parse_args()

    

    start_time = time.time()

    

    if args.mode == "incremental":

        added = sync_incremental_stock_prices()

        logger.info("Hoàn tất cập nhật gia tăng: %d dòng mới được thêm vào.", added)

    else:

        logger.info("=== KHỞI ĐỘNG TIẾN TRÌNH THU THẬP OHLCV TOÀN THỜI GIAN (27 MÃ NGÂN HÀNG) ===")

        df_all = fetch_full_banking_history(tickers=BANKING_TICKERS, start_date=START_DATE)

        output_file = save_to_parquet(df_all, output_path=OUTPUT_PARQUET_PATH)

        logger.info("Lưu thành công: %s (%d dòng)", output_file, len(df_all))

        

    elapsed = time.time() - start_time

    logger.info("Thời gian thực thi: %.2f giây (%.2f phút)", elapsed, elapsed / 60)





if __name__ == "__main__":

    main()

