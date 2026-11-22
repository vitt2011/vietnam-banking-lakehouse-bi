"""

Tập lệnh: stock_analysis/data/vnstock_financials.py

Chức năng: Thu thập toàn bộ Dữ liệu Cơ bản (Fundamental Data) cho 27 mã cổ phiếu Ngân hàng:

          - Báo cáo tài chính (Statements): Cân đối kế toán (Balance Sheet), Kết quả kinh doanh (Income Statement),

            Lưu chuyển tiền tệ (Cash Flow).

          - Tỷ số tài chính (Financial Ratios): P/E, P/B, ROE, ROA, NIM, CASA, CIR...

          Sử dụng trực tiếp module cấp thấp VCIFinance (vnstock.explorer.vci.financial.Finance) với tham số limit=100,

          vượt qua hoàn toàn giới hạn 4 kỳ (max_periods = 4) của bản cộng đồng.

          Thu thập đầy đủ toàn bộ 8.5 năm dữ liệu (34 quý & 8 năm từ 2018 đến 2026).

          Tối ưu hóa:

          - Gán com_type_code = 'NH' trực tiếp cho nhóm Ngân hàng để tránh gọi endpoint search-bar (dễ gặp lỗi 502).

          - Tích hợp cơ chế tự động thử lại (Retry with Backoff) khi gặp 502/503/Rate Limit.

          - Trang bị cơ chế Graceful Exit (Ctrl+C), Memory Downcasting và lưu trữ Parquet Snappy chuẩn Bronze.

Tuân thủ tuyệt đối quy tắc phân tách Mã nguồn (Code) và Dữ liệu (Data Lake Bronze).

"""



import argparse

import logging

import sys

import time

from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple, Union



import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR, BRONZE_FIN_DIR



# Ngăn chặn vnai/vnstock gọi sys.exit() khi gặp sự cố rate limit / quota

try:

    import vnai.beam.quota

    vnai.beam.quota.CleanErrorContext.__exit__ = lambda self, exc_type, exc_val, exc_tb: False

except Exception:

    pass



from vnstock.explorer.vci.financial import Finance as VCIFinance



# Tối ưu hóa: Khóa loại hình công ty cho nhóm Ngân hàng để không gọi Listing.symbols_by_industries()

# Tránh được lỗi 502 Bad Gateway từ endpoint search-bar của Vietcap

VCIFinance._get_company_type = lambda self: "NH"



# Cấu hình logging chuyên nghiệp cho môi trường production

FIN_LOG_FILE = LOGS_DIR / "financial_ingestion.log"

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] %(message)s",

    datefmt="%Y-%m-%d %H:%M:%S",

    handlers=[

        logging.StreamHandler(sys.stdout),

        logging.FileHandler(FIN_LOG_FILE, encoding="utf-8"),

    ],

)

logger = logging.getLogger(__name__)



# ------------------------------------------------------------------------------

# 1. KHAI BÁO DANH MỤC MỤC TIÊU (27 MÃ CỔ PHIẾU NGÂN HÀNG)

# ------------------------------------------------------------------------------

BANKING_TICKERS: List[str] = [

    "ACB", "ABB", "BAB", "BID", "BVB", "CTG", "EIB", "HDB", "KLB", "LPB",

    "MBB", "MSB", "NAB", "NVB", "OCB", "PGB", "SGB", "SHB", "SSB", "STB",

    "TCB", "TPB", "VAB", "VBB", "VCB", "VIB", "VPB",

]



TARGET_SECTOR: str = "Ngan_Hang"



# ------------------------------------------------------------------------------

# 2. QUY TẮC I/O (ĐƯỜNG DẪN TƯƠNG ĐỐI TRỎ VỀ DATA LAKE BRONZE LAYER)

# ------------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

RAW_LAKE_DIR: Path = BRONZE_FIN_DIR



RATIOS_OUTPUT_FILE: Path = RAW_LAKE_DIR / "vnstock_financial_ratios.parquet"

STATEMENTS_OUTPUT_FILE: Path = RAW_LAKE_DIR / "vnstock_financial_statements.parquet"



API_CALL_SLEEP_SECONDS: float = 1.2  # Khoảng nghỉ an toàn giữa các lần gọi





def check_and_throttle_quota(safety_buffer: int = 2) -> None:

    """

    Kiểm tra chủ động quota của vnai để tạm nghỉ trước khi chạm trần 429.

    Chia nhỏ thời gian nghỉ để xử lý phản hồi Ctrl+C ngay lập tức nếu cần.

    """

    try:

        from vnai.beam.quota import guardian

        status = guardian.get_limit_status()

        remaining = status.get("minute_limit", {}).get("remaining", 20)

        reset_in = status.get("minute_limit", {}).get("reset_in_seconds", 60)

        if remaining <= safety_buffer:

            wait_time = max(reset_in + 2.0, 5.0)

            logger.info("Chủ động điều tiết quota: Còn %d lượt. Đang tạm nghỉ %.1f giây...", remaining, wait_time)

            slept = 0.0

            while slept < wait_time:

                step = min(1.0, wait_time - slept)

                time.sleep(step)

                slept += step

    except KeyboardInterrupt:

        raise

    except Exception:

        pass





def format_vci_report_to_timeseries(raw_df: pd.DataFrame, ticker: str) -> pd.DataFrame:

    """

    Chuyển đổi DataFrame báo cáo tài chính từ định dạng báo cáo hàng ngang sang định dạng Time Series.

    Mỗi hàng là một kỳ (Period: Quý hoặc Năm), các cột là các chỉ tiêu tài chính.

    """

    if raw_df is None or raw_df.empty:

        return pd.DataFrame()



    metadata_cols = ["item", "item_en", "unit", "levels", "row_number", "item_id"]

    period_cols = [c for c in raw_df.columns if c not in metadata_cols]



    if not period_cols or "item_id" not in raw_df.columns:

        return pd.DataFrame()



    # Chuẩn hóa tên cột thời gian (loại bỏ hậu tố '-Năm' nếu có)

    rename_dict = {p: p.replace("-Năm", "") for p in period_cols if isinstance(p, str) and p.endswith("-Năm")}

    if rename_dict:

        raw_df = raw_df.rename(columns=rename_dict)

        period_cols = [rename_dict.get(p, p) for p in period_cols]



    # Chuyển vị bảng (Transpose)

    df_t = raw_df.set_index("item_id")[period_cols].transpose().reset_index()

    df_t = df_t.rename(columns={"index": "period"})

    df_t.insert(1, "ticker", ticker)



    return df_t





def downcast_financial_df(

    df: pd.DataFrame,

    ticker: str,

    sector: str = TARGET_SECTOR,

    report_type: Optional[str] = None,

    period_type: str = "year",

) -> pd.DataFrame:

    """

    Tối ưu hóa RAM tức thời cho DataFrame tài chính (Memory Downcasting):

    - Khử trùng lặp tên cột sinh ra trong quá trình chuyển vị của API.

    - Gán các cột ticker, sector, period_type (và report_type) rồi ép sang 'category'.

    - Ép tất cả các cột giá trị tài chính số thực về 'float32', số nguyên về 'int32'.

    """

    df_opt = df.copy()



    # Khử trùng lặp cột nếu có

    if df_opt.columns.duplicated().any():

        df_opt = df_opt.loc[:, ~df_opt.columns.duplicated(keep="first")]



    # Đảm bảo tên cột ở dạng chuỗi

    df_opt.columns = [str(col) for col in df_opt.columns]



    # Gán nhãn phân loại & ép category

    df_opt["ticker"] = ticker

    df_opt["ticker"] = df_opt["ticker"].astype("category")



    df_opt["sector"] = sector

    df_opt["sector"] = df_opt["sector"].astype("category")



    df_opt["period_type"] = period_type

    df_opt["period_type"] = df_opt["period_type"].astype("category")



    if report_type is not None:

        df_opt["report_type"] = report_type

        df_opt["report_type"] = df_opt["report_type"].astype("category")



    if "period" in df_opt.columns:

        df_opt["period"] = df_opt["period"].astype("category")



    # Ép kiểu dữ liệu số thực về float32

    for col in df_opt.select_dtypes(include=["float64"]).columns:

        df_opt[col] = df_opt[col].astype("float32")



    # Ép kiểu dữ liệu số nguyên về int32

    for col in df_opt.select_dtypes(include=["int64"]).columns:

        df_opt[col] = df_opt[col].astype("int32")



    return df_opt





def safe_api_call(

    func: Any,

    ticker: str,

    call_name: str,

    max_retries: int = 2,

    sleep_seconds: float = API_CALL_SLEEP_SECONDS,

    **kwargs: Any,

) -> Optional[pd.DataFrame]:

    """

    Bọc lệnh gọi API với cơ chế Retry tự động khi gặp sự cố mạng (502, 503, 429).

    """

    for attempt in range(max_retries + 1):

        check_and_throttle_quota()



        try:

            df = func(**kwargs)

            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:

                time.sleep(sleep_seconds)

                return df

            time.sleep(sleep_seconds)

            return None

        except KeyboardInterrupt:

            raise

        except Exception as exc:

            err_msg = str(exc).lower()

            if "rate limit" in err_msg or "429" in err_msg:

                if attempt < max_retries:

                    logger.warning(" -> Mã %s [%s]: Chạm Rate Limit. Đang chờ 60 giây để thử lại...", ticker, call_name)

                    time.sleep(60.0)

                    continue

            elif "502" in err_msg or "503" in err_msg or "bad gateway" in err_msg or "service unavailable" in err_msg:

                if attempt < max_retries:

                    wait_sec = 3.0 * (attempt + 1)

                    logger.warning(" -> Mã %s [%s]: Máy chủ trả về %s. Tự động thử lại sau %.1fs (lần %d)...", ticker, call_name, exc, wait_sec, attempt + 1)

                    time.sleep(wait_sec)

                    continue

            logger.warning(" -> Mã %s [%s]: Gặp lỗi (%s): %s", ticker, call_name, type(exc).__name__, exc)

            time.sleep(sleep_seconds)

            return None



    return None





def scrape_fundamental_data_for_ticker(

    ticker: str,

    sector: str = TARGET_SECTOR,

    periods: Tuple[str, ...] = ("year", "quarter"),

    sleep_seconds: float = API_CALL_SLEEP_SECONDS,

) -> Tuple[List[pd.DataFrame], List[pd.DataFrame]]:

    """

    Cào toàn bộ Tỷ số tài chính và Báo cáo tài chính cho 1 mã ngân hàng:

    - Bỏ qua wrapper thương mại bằng cách gọi trực tiếp VCIFinance._get_report(..., limit=100).

    - Lấy trọn vẹn toàn bộ 8.5 năm dữ liệu (34 quý & 8 năm).

    """

    ratios_list: List[pd.DataFrame] = []

    statements_list: List[pd.DataFrame] = []



    try:

        client = VCIFinance(symbol=ticker)

    except Exception as init_exc:

        logger.warning(" -> Không thể khởi tạo VCIFinance cho mã %s: %s", ticker, init_exc)

        return ratios_list, statements_list



    # 1. Luồng Tỷ số tài chính (Financial Ratios: limit=100 lấy tối đa ~41 kỳ cả Quý & Năm)

    raw_ratio = safe_api_call(

        client._get_report,

        ticker=ticker,

        call_name="ratio",

        report_type="ratio",

        limit=100,

        sleep_seconds=sleep_seconds,

    )

    if raw_ratio is not None and not raw_ratio.empty:

        df_ratio = format_vci_report_to_timeseries(raw_ratio, ticker=ticker)

        if not df_ratio.empty:

            df_opt = downcast_financial_df(df_ratio, ticker=ticker, sector=sector, period_type="all")

            ratios_list.append(df_opt)

            logger.info(" -> Mã %s: Tải thành công Tỷ số tài chính (%d kỳ).", ticker, len(df_opt))



    # 2. Luồng Báo cáo tài chính (Statements: balance_sheet, income_statement, cash_flow)

    statement_types = ["balance_sheet", "income_statement", "cash_flow"]

    for p in periods:

        for report_type in statement_types:

            raw_stmt = safe_api_call(

                client._get_report,

                ticker=ticker,

                call_name=f"{report_type}_{p}",

                report_type=report_type,

                period=p,

                limit=100,

                sleep_seconds=sleep_seconds,

            )

            if raw_stmt is not None and not raw_stmt.empty:

                df_stmt = format_vci_report_to_timeseries(raw_stmt, ticker=ticker)

                if not df_stmt.empty:

                    df_opt = downcast_financial_df(

                        df_stmt,

                        ticker=ticker,

                        sector=sector,

                        report_type=report_type,

                        period_type=p,

                    )

                    statements_list.append(df_opt)

                    logger.info(" -> Mã %s: Tải thành công BCTC %s (%s, %d kỳ).", ticker, report_type, p, len(df_opt))



    return ratios_list, statements_list





def save_parquet_dataset(
    df: pd.DataFrame, 
    output_path: Union[str, Path], 
    label: str, 
    merge_existing: bool = True
) -> None:
    """Lưu trữ DataFrame vào Data Lake Bronze theo chuẩn Parquet PyArrow Snappy (hỗ trợ hợp nhất cuốn chiếu)."""
    if df.empty:
        logger.warning("DataFrame %s rỗng. Bỏ qua ghi file.", label)
        return

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Hỗ trợ cào cuốn chiếu (Incremental): Nếu cào một tập con mã, hợp nhất an toàn với tệp Bronze hiện có
    if merge_existing and target_path.exists() and "ticker" in df.columns:
        try:
            existing_df = pd.read_parquet(target_path)
            new_tickers = set(df["ticker"].dropna().unique())
            existing_tickers = set(existing_df["ticker"].dropna().unique())
            
            # Chỉ hợp nhất nếu tệp hiện có chứa các mã khác mà đợt cào mới này không bao phủ
            if not new_tickers.issuperset(existing_tickers):
                kept_existing = existing_df[~existing_df["ticker"].isin(new_tickers)]
                df = pd.concat([kept_existing, df], ignore_index=True)
                logger.info(
                    "Đã hợp nhất cuốn chiếu với Bronze hiện có: cập nhật %d mã mới, bảo toàn %d mã cũ (Tổng: %d mã).",
                    len(new_tickers), len(existing_tickers - new_tickers), df["ticker"].nunique()
                )
        except Exception as merge_err:
            logger.warning("Không thể đọc tệp Bronze hiện có để hợp nhất (%s). Tiến hành ghi đè dữ liệu mới.", merge_err)

    logger.info("Đang lưu %s vào Data Lake: %s...", label, target_path)
    df.to_parquet(
        target_path,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    size_kb = target_path.stat().st_size / 1024
    logger.info(
        "Lưu thành công %s! Dung lượng: %.2f KB (%.2f MB) | %d dòng x %d cột.",
        label, size_kb, size_kb / 1024, len(df), df.shape[1],
    )





def scrape_all_fundamentals(

    tickers: Optional[List[str]] = None,

    sector: str = TARGET_SECTOR,

    periods: Tuple[str, ...] = ("year", "quarter"),

    sleep_seconds: float = API_CALL_SLEEP_SECONDS,

    save_to_disk: bool = True,

    ratios_output_path: Union[str, Path] = RATIOS_OUTPUT_FILE,

    statements_output_path: Union[str, Path] = STATEMENTS_OUTPUT_FILE,

) -> Tuple[pd.DataFrame, pd.DataFrame]:

    """

    Duyệt qua danh sách 27 mã ngân hàng với kỹ thuật Graceful Exit (Bảo toàn dữ liệu khi nhấn Ctrl+C):

    - Thu thập toàn bộ 8.5 năm dữ liệu (34 quý & 8 năm).

    - Toàn bộ luồng cào dữ liệu được bọc trong khối try... except KeyboardInterrupt:.

    - Khi nhận Ctrl+C: KHÔNG CRASH, bảo toàn dữ liệu hiện có và lưu xuống Parquet.

    """

    if tickers is None:

        tickers = BANKING_TICKERS



    total_tickers = len(tickers)



    logger.info("=" * 80)

    logger.info(

        "BẮT ĐẦU CÀO TOÀN DIỆN BCTC & TỶ SỐ TÀI CHÍNH (8.5 NĂM / 34 QUÝ) CHO %d MÃ NGÂN HÀNG",

        total_tickers,

    )

    logger.info("Phương thức: Bypass module vnai bằng VCIFinance._get_report(limit=100) & tối ưu hóa com_type='NH'")

    logger.info("=" * 80)



    ratios_list: List[pd.DataFrame] = []

    statements_list: List[pd.DataFrame] = []

    interrupted = False



    try:

        for idx, ticker in enumerate(tickers, start=1):

            logger.info("[%02d/%02d] Đang xử lý tài chính mã: %s...", idx, total_tickers, ticker)



            try:

                r_sub, s_sub = scrape_fundamental_data_for_ticker(

                    ticker=ticker,

                    sector=sector,

                    periods=periods,

                    sleep_seconds=sleep_seconds,

                )



                ratios_list.extend(r_sub)

                statements_list.extend(s_sub)

            except Exception as tick_exc:

                logger.warning(" -> Mã %s: Xảy ra lỗi ngoại lệ (%s). Đang bỏ qua để tiếp tục mã kế tiếp...", ticker, tick_exc)



    except KeyboardInterrupt:

        interrupted = True

        logger.warning(

            "Tiến trình bị ngắt bởi người dùng (Ctrl+C). Bắt đầu gom và lưu các dữ liệu đã thu thập được..."

        )



    if not ratios_list and not statements_list:

        if interrupted:

            logger.warning("Chưa có dữ liệu nào được thu thập trước khi bị ngắt bằng Ctrl+C.")

            return pd.DataFrame(), pd.DataFrame()

        raise RuntimeError("Lỗi: Không thu thập được bất kỳ dữ liệu tài chính nào!")



    logger.info("=" * 80)

    logger.info(

        "TỔNG KẾT: Đã gom được %d bảng Ratios và %d bảng Statements. Đang hợp nhất DataFrames...",

        len(ratios_list), len(statements_list),

    )



    # 1. Hợp nhất Ratios

    if ratios_list:

        combined_ratios = pd.concat(ratios_list, ignore_index=True)

        combined_ratios["ticker"] = combined_ratios["ticker"].astype("category")

        combined_ratios["sector"] = combined_ratios["sector"].astype("category")

        combined_ratios["period_type"] = combined_ratios["period_type"].astype("category")

    else:

        combined_ratios = pd.DataFrame()



    # 2. Hợp nhất Statements

    if statements_list:

        combined_statements = pd.concat(statements_list, ignore_index=True)

        combined_statements["ticker"] = combined_statements["ticker"].astype("category")

        combined_statements["sector"] = combined_statements["sector"].astype("category")

        combined_statements["period_type"] = combined_statements["period_type"].astype("category")

        if "report_type" in combined_statements.columns:

            combined_statements["report_type"] = combined_statements["report_type"].astype("category")

    else:

        combined_statements = pd.DataFrame()



    # 3. Tiến hành lưu an toàn xuống file .parquet

    if save_to_disk:

        if not combined_ratios.empty:

            save_parquet_dataset(combined_ratios, ratios_output_path, "Tỷ số tài chính (Ratios)")

        if not combined_statements.empty:

            save_parquet_dataset(combined_statements, statements_output_path, "Báo cáo tài chính (Statements)")



    if interrupted:

        logger.info("Dữ liệu đã được bảo toàn thành công sau khi ngắt tiến trình.")



    return combined_ratios, combined_statements





# Alias hỗ trợ tính tương thích ngược

scrape_all_banking_fundamentals = scrape_all_fundamentals





def main() -> None:

    """Hàm main thực thi kịch bản cào dữ liệu trực tiếp từ Terminal."""

    parser = argparse.ArgumentParser(

        description="Thu thập toàn bộ BCTC & Tỷ số tài chính 8.5 năm cho 27 mã ngân hàng."

    )

    parser.add_argument(

        "--period", type=str, choices=["year", "quarter", "both"], default="both",

        help="Tần suất báo cáo: 'year', 'quarter' hoặc 'both' (mặc định: both)."

    )

    parser.add_argument(

        "--sleep", type=float, default=API_CALL_SLEEP_SECONDS,

        help="Thời gian nghỉ an toàn (1.2s - 1.5s) giữa các lần gọi API (mặc định: 1.2s)."

    )

    parser.add_argument(

        "--ratios-output", type=str, default=str(RATIOS_OUTPUT_FILE),

        help="Đường dẫn lưu trữ tệp tỷ số tài chính Parquet."

    )

    parser.add_argument(

        "--statements-output", type=str, default=str(STATEMENTS_OUTPUT_FILE),

        help="Đường dẫn lưu trữ tệp báo cáo tài chính Parquet."

    )

    parser.add_argument(

        "--limit-tickers", type=int, default=None,

        help="Giới hạn số lượng mã ngân hàng cần cào (ví dụ 1 hoặc 2 để kiểm thử nhanh)."

    )

    args = parser.parse_args()



    periods: Tuple[str, ...] = ("year", "quarter") if args.period == "both" else (args.period,)

    target_tickers = BANKING_TICKERS[:args.limit_tickers] if args.limit_tickers else BANKING_TICKERS



    start_time = time.time()

    logger.info("=== BẮT ĐẦU PIPELINE THU THẬP BCTC VÀ TỶ SỐ TÀI CHÍNH TOÀN DIỆN (8.5 NĂM / 34 QUÝ) ===")



    try:

        ratios_df, statements_df = scrape_all_fundamentals(

            tickers=target_tickers,

            sector=TARGET_SECTOR,

            periods=periods,

            sleep_seconds=args.sleep,

            save_to_disk=True,

            ratios_output_path=args.ratios_output,

            statements_output_path=args.statements_output,

        )



        # Xác thực tính toàn vẹn của dữ liệu sau khi ghi

        if not ratios_df.empty and Path(args.ratios_output).exists():

            ver_ratios = pd.read_parquet(args.ratios_output, engine="pyarrow")

            assert len(ver_ratios) == len(ratios_df), "Lỗi: Số dòng tệp Ratios không khớp!"

            logger.info("Xác thực Ratios thành công: %d dòng x %d cột.", len(ver_ratios), ver_ratios.shape[1])



        if not statements_df.empty and Path(args.statements_output).exists():

            ver_stmts = pd.read_parquet(args.statements_output, engine="pyarrow")

            assert len(ver_stmts) == len(statements_df), "Lỗi: Số dòng tệp Statements không khớp!"

            logger.info("Xác thực Statements thành công: %d dòng x %d cột.", len(ver_stmts), ver_stmts.shape[1])



        elapsed = time.time() - start_time

        logger.info("=== QUY TRÌNH HOÀN TẤT TRONG %.2f GIÂY (%.2f PHÚT) ===", elapsed, elapsed / 60)



    except Exception as exc:

        logger.exception("Đã xảy ra lỗi nghiêm trọng: %s", exc)

        sys.exit(1)





if __name__ == "__main__":

    main()

