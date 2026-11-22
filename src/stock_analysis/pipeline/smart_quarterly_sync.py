"""
===================================================================================
MODULE: src/stock_analysis/pipeline/smart_quarterly_sync.py
CHỨC NĂNG: ĐIỀU PHỐI ĐỒNG BỘ BÁO CÁO TÀI CHÍNH QUÝ THÔNG MINH (SMART QUARTERLY SYNC)
===================================================================================
Nguyên lý vận hành chuẩn Financial Data Engineering:
  1. Cửa sổ Mùa BCTC (Season Window): Tự động mở radar quét từ ngày 01 của tháng 
     ngay sau khi kết thúc quý (01/04, 01/07, 01/10, 01/01).
  2. Cào cuốn chiếu giảm dần (Incremental Drain): Chỉ gửi request kiểm tra các ngân 
     hàng CHƯA CÓ BCTC trong CSDL. Mã nào đã có -> BỎ QUA, tuyệt đối không spam API.
  3. Đối soát cuối mùa (Reconciliation Sweep): Vào giai đoạn chốt sổ cuối mùa,
     chạy 1 lượt quét đối soát toàn diện để cập nhật BCTC Đính chính hoặc Hợp nhất.
  4. Hoàn tất chu kỳ (Self-Terminating): Khi đủ 27/27 ngân hàng, tự động đóng mùa 
     và chuyển sang trạng thái ngủ (Dormant) cho đến mùa quý tiếp theo.
===================================================================================
"""

import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import psycopg2

# Ngăn chặn vnstock/vnai gọi sys.exit() khi chạm rate limit
try:
    import vnai.beam.quota
    vnai.beam.quota.CleanErrorContext.__exit__ = lambda self, exc_type, exc_val, exc_tb: False
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.ingestion.ingest_financial_statements import (
    BANKING_TICKERS,
    scrape_all_fundamentals,
)
from stock_analysis.sql_serving_loader.publish_to_postgres import (
    get_connection,
    publish_financial_statements,
    publish_banking_ratios_and_camels,
)
from stock_analysis.transformation.bronze_to_silver.clean_financials import (
    run_clean_financial_statements,
    run_clean_financial_ratios,
)
from stock_analysis.transformation.silver_to_gold.feature_camels_engine import run_feature_camels_engine
from stock_analysis.transformation.silver_to_gold.feature_valuation_matrix import run_feature_valuation_matrix

SYNC_STATE_DIR = PROJECT_ROOT / "runtime" / "sync_state"
SYNC_STATE_FILE = SYNC_STATE_DIR / "quarterly_sync_state.json"

LOG_FILE = LOGS_DIR / "pipeline" / f"smart_sync_{datetime.now().strftime('%Y%m%d')}.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("SmartQuarterlySync")


def get_earnings_season_info(check_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Xác định Quý mục tiêu và kiểm tra ngày hiện tại có nằm trong Cửa sổ Mùa BCTC hay không.
    - Quý 1 (kết thúc 31/03): Cửa sổ từ 01/04 đến 15/05 (Chốt đối soát: 10/05 - 15/05)
    - Quý 2 (kết thúc 30/06): Cửa sổ từ 01/07 đến 25/08 (Chốt đối soát: 10/08 - 25/08)
    - Quý 3 (kết thúc 30/09): Cửa sổ từ 01/10 đến 15/11 (Chốt đối soát: 10/11 - 15/11)
    - Quý 4 (kết thúc 31/12): Cửa sổ từ 01/01 đến 15/02 năm sau (Chốt đối soát: 10/02 - 15/02)
    """
    if check_date is None:
        check_date = date.today()

    year = check_date.year
    month = check_date.month
    day = check_date.day

    target_year = year
    target_q = 1
    is_in_season = False
    is_sweep_period = False
    season_name = ""

    if month in (4, 5):
        target_year = year
        target_q = 1
        season_name = f"Mùa BCTC Quý 1/{target_year}"
        is_in_season = (month == 4) or (month == 5 and day <= 15)
        is_sweep_period = (month == 5 and 10 <= day <= 15)
    elif month in (7, 8):
        target_year = year
        target_q = 2
        season_name = f"Mùa BCTC Quý 2/{target_year}"
        is_in_season = (month == 7) or (month == 8 and day <= 25)
        is_sweep_period = (month == 8 and 10 <= day <= 25)
    elif month in (10, 11):
        target_year = year
        target_q = 3
        season_name = f"Mùa BCTC Quý 3/{target_year}"
        is_in_season = (month == 10) or (month == 11 and day <= 15)
        is_sweep_period = (month == 11 and 10 <= day <= 15)
    elif month in (1, 2):
        target_year = year - 1
        target_q = 4
        season_name = f"Mùa BCTC Quý 4/{target_year}"
        is_in_season = (month == 1) or (month == 2 and day <= 15)
        is_sweep_period = (month == 2 and 10 <= day <= 15)
    else:
        # Các tháng 3, 6, 9, 12 nằm ngoài mùa cao điểm
        # Mặc định lấy quý gần nhất đã hoàn tất
        if month == 3:
            target_year = year - 1
            target_q = 4
        elif month == 6:
            target_year = year
            target_q = 1
        elif month == 9:
            target_year = year
            target_q = 2
        else: # month == 12
            target_year = year
            target_q = 3
        season_name = f"Giai đoạn chuyển mùa (Quý {target_q}/{target_year})"
        is_in_season = False
        is_sweep_period = False

    target_quarter_str = f"{target_year}-Q{target_q}"

    return {
        "target_year": target_year,
        "target_quarter": target_q,
        "target_quarter_str": target_quarter_str,
        "is_in_season": is_in_season,
        "is_sweep_period": is_sweep_period,
        "season_name": season_name,
        "check_date": check_date.strftime("%Y-%m-%d"),
    }


def load_sync_state() -> Dict[str, Any]:
    """Tải tệp trạng thái đồng bộ BCTC từ disk."""
    if SYNC_STATE_FILE.exists():
        try:
            with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Không thể đọc tệp sync state (%s), khởi tạo mới.", e)
    return {}


def save_sync_state(state: Dict[str, Any]) -> None:
    """Lưu tệp trạng thái đồng bộ BCTC xuống disk."""
    SYNC_STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Lỗi khi ghi tệp sync state: %s", e)


def get_db_synced_tickers(target_year: int, target_quarter: int) -> Set[str]:
    """Truy vấn PostgreSQL để lấy danh sách mã ngân hàng ĐÃ CÓ BCTC quý chỉ định."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT b.ticker 
            FROM mart_camels.fact_quarterly_financial_statements f
            JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
            WHERE f.fiscal_year = %s AND f.fiscal_quarter = %s;
            """,
            (target_year, target_quarter),
        )
        tickers = {row[0] for row in cur.fetchall()}
        cur.close()
        conn.close()
        return tickers
    except Exception as e:
        logger.warning("Không thể truy vấn CSDL để kiểm tra BCTC hiện có (%s).", e)
        return set()


def probe_ticker_for_quarter(ticker: str, target_quarter_str: str) -> bool:
    """
    Thăm dò siêu nhẹ vào API Vietcap: Kiểm tra mã ngân hàng này đã có BCTC quý mới chưa.
    Chỉ tốn đúng 1 request kiểm tra cột của Balance Sheet.
    """
    from vnstock.explorer.vci.financial import Finance as VCIFinance
    try:
        f = VCIFinance(ticker)
        f._get_company_type = lambda: "NH"
        df = f._get_report("balance_sheet", period="quarter", limit=100)
        time.sleep(2.0)  # Throttling an toàn tránh 429
        if df is not None and not df.empty and target_quarter_str in df.columns:
            return True
        return False
    except Exception as e:
        logger.warning("Thăm dò mã %s thất bại: %s", ticker, e)
        time.sleep(2.0)
        return False


def run_smart_quarterly_sync(
    force_all: bool = False,
    force_season: bool = False,
    target_quarter_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Hàm điều phối cốt lõi của Smart Quarterly Sync:
    1. Xác định mùa và quý mục tiêu.
    2. Kiểm tra CSDL xem mã nào đã có, mã nào còn thiếu.
    3. Thăm dò và cào cuốn chiếu chỉ các mã có BCTC mới.
    4. Kích hoạt toàn bộ luồng Silver -> Gold CAMELS -> PostgreSQL DWH.
    """
    start_time = time.time()
    season_info = get_earnings_season_info()

    if target_quarter_override:
        parts = target_quarter_override.split("-Q")
        target_year = int(parts[0])
        target_q = int(parts[1])
        target_quarter_str = target_quarter_override
        is_in_season = True
        is_sweep = force_all
        season_name = f"Chỉ định thủ công ({target_quarter_str})"
    else:
        target_year = season_info["target_year"]
        target_q = season_info["target_quarter"]
        target_quarter_str = season_info["target_quarter_str"]
        is_in_season = season_info["is_in_season"] or force_season
        season_name = season_info["season_name"]

    state = load_sync_state()
    season_state = state.get(target_quarter_str, {})
    sweep_already_done = season_state.get("reconciliation_sweep_completed", False)

    if not target_quarter_override:
        # Nếu đã đối soát cuối mùa một lần rồi thì không đối soát lặp lại mỗi ngày
        is_sweep = force_all or (season_info["is_sweep_period"] and not sweep_already_done)

    logger.info("=" * 80)
    logger.info(">>> TIẾN TRÌNH ĐỒNG BỘ BCTC QUÝ THÔNG MINH (SMART QUARTERLY SYNC) <<<")
    logger.info("Kỳ mục tiêu        : %s (%s)", target_quarter_str, season_name)
    logger.info("Đang trong mùa BCTC: %s | Chế độ quét toàn diện (Sweep): %s", is_in_season, is_sweep)
    logger.info("=" * 80)

    # 1. Kiểm tra nếu nằm ngoài mùa BCTC và không bị ép chạy
    if not is_in_season and not is_sweep and not force_all:
        logger.info("[-] Hôm nay nằm ngoài Cửa sổ Mùa BCTC. Tự động bỏ qua quét BCTC (0 API calls).")
        return {
            "status": "DORMANT",
            "message": "Outside earnings season window",
            "target_quarter": target_quarter_str,
            "crawled_count": 0,
        }

    # 2. Đọc trạng thái từ Database
    synced_tickers = get_db_synced_tickers(target_year, target_q)
    pending_tickers = [t for t in BANKING_TICKERS if t not in synced_tickers]
    completeness_pct = round((len(synced_tickers) / len(BANKING_TICKERS)) * 100, 1)

    logger.info(
        "Trạng thái DWH hiện tại: Đã có %d/%d ngân hàng (%.1f%%) cho quý %s.",
        len(synced_tickers), len(BANKING_TICKERS), completeness_pct, target_quarter_str
    )

    # 3. Nếu đã đủ 27/27 ngân hàng và không phải đợt đối soát cuối mùa
    if len(pending_tickers) == 0 and not is_sweep and not force_all:
        logger.info("[✓] Toàn bộ 27 ngân hàng đã nạp đủ cho quý %s. Kỳ báo cáo đã hoàn tất xuất sắc!", target_quarter_str)
        season_state["status"] = "COMPLETED"
        season_state["last_checked"] = datetime.now().isoformat()
        state[target_quarter_str] = season_state
        save_sync_state(state)
        return {
            "status": "COMPLETED",
            "message": "All 27 banks already synced",
            "target_quarter": target_quarter_str,
            "crawled_count": 0,
            "completeness_pct": 100.0,
        }

    # 4. Xác định danh sách cần kiểm tra
    if force_all or is_sweep:
        tickers_to_check = BANKING_TICKERS
        logger.info("[!] Kích hoạt quét đối soát toàn diện (Sweep/Reconciliation) cho cả 27 mã ngân hàng...")
    else:
        tickers_to_check = pending_tickers
        logger.info("[-] Đang kiểm tra cuốn chiếu %d mã ngân hàng CÒN THIẾU BCTC...", len(tickers_to_check))

    # 5. Thăm dò từng mã
    tickers_ready_to_crawl = []
    for idx, ticker in enumerate(tickers_to_check, start=1):
        logger.info("  [%02d/%02d] Thăm dò mã %s trên Vietcap API...", idx, len(tickers_to_check), ticker)
        has_new = probe_ticker_for_quarter(ticker, target_quarter_str)
        if has_new:
            logger.info("    -> [PHÁT HIỆN MỚI] Mã %s ĐÃ CÓ BCTC %s!", ticker, target_quarter_str)
            tickers_ready_to_crawl.append(ticker)
        else:
            logger.info("    -> Mã %s chưa có %s.", ticker, target_quarter_str)

    if not tickers_ready_to_crawl:
        logger.info("[*] Chưa phát hiện thêm ngân hàng nào công bố BCTC mới trong phiên hôm nay.")
        return {
            "status": "NO_NEW_DATA",
            "message": "No new statements found today",
            "target_quarter": target_quarter_str,
            "crawled_count": 0,
            "completeness_pct": completeness_pct,
        }

    # 6. Cào cuốn chiếu các mã đã sẵn sàng vào Bronze
    logger.info("\n>>> [1/5] BẮT ĐẦU CÀO NẠP %d NGÂN HÀNG VÀO BRONZE LAKE...", len(tickers_ready_to_crawl))
    scrape_all_fundamentals(
        tickers=tickers_ready_to_crawl,
        periods=("year", "quarter"),
        sleep_seconds=1.5,
        save_to_disk=True,
    )

    # 7. Chuyển đổi Silver & Kiểm định kế toán DQ1/DQ2
    logger.info("\n>>> [2/5] LÀM SẠCH VÀ ĐỐI SOÁT CÂN ĐỐI KẾ TOÁN SANG SILVER...")
    silver_fs = run_clean_financial_statements()
    silver_ratios = run_clean_financial_ratios()

    # 8. Tính toán CAMELS Scorecard & Định giá Gordon sang Gold
    logger.info("\n>>> [3/5] TÍNH TOÁN ĐIỂM CAMELS & MA TRẬN ĐỊNH GIÁ GORDON TẦNG GOLD...")
    gold_camels = run_feature_camels_engine()
    gold_val = run_feature_valuation_matrix()

    # 9. Công bố Idempotent Upsert vào PostgreSQL Serving
    logger.info("\n>>> [4/5] CÔNG BỐ DỮ LIỆU ĐÃ KIỂM ĐỊNH VÀO POSTGRESQL SERVING...")
    pub_fs = publish_financial_statements()
    pub_ratios = publish_banking_ratios_and_camels()

    # 10. Cập nhật Sync State
    synced_after = get_db_synced_tickers(target_year, target_q)
    new_completeness = round((len(synced_after) / len(BANKING_TICKERS)) * 100, 1)

    season_state["target_quarter"] = target_quarter_str
    season_state["status"] = "COMPLETED" if len(synced_after) == len(BANKING_TICKERS) else "ACTIVE"
    season_state["last_sync_timestamp"] = datetime.now().isoformat()
    season_state["synced_tickers"] = sorted(list(synced_after))
    season_state["completeness_pct"] = new_completeness
    if is_sweep:
        season_state["reconciliation_sweep_completed"] = True
    state[target_quarter_str] = season_state
    save_sync_state(state)

    duration = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info(">>> [THÀNH CÔNG] ĐÃ HOÀN TẤT ĐỒNG BỘ CUỐN CHIẾU TRONG %.2f GIÂY <<<", duration)
    logger.info("Số mã vừa cập nhật : %d (%s)", len(tickers_ready_to_crawl), tickers_ready_to_crawl)
    logger.info("Độ phủ toàn ngành  : %d/27 ngân hàng (%.1f%%)", len(synced_after), new_completeness)
    logger.info("=" * 80)

    return {
        "status": "SUCCESS",
        "target_quarter": target_quarter_str,
        "crawled_count": len(tickers_ready_to_crawl),
        "crawled_tickers": tickers_ready_to_crawl,
        "completeness_pct": new_completeness,
        "duration_seconds": round(duration, 2),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trạm đồng bộ BCTC Quý thông minh (Smart Quarterly Sync)")
    parser.add_argument("--force-all", action="store_true", help="Quét đối soát toàn bộ 27 ngân hàng")
    parser.add_argument("--force-season", action="store_true", help="Bắt buộc quét kể cả ngoài mùa")
    parser.add_argument("--quarter", type=str, default=None, help="Chỉ định quý (ví dụ 2026-Q3)")
    args = parser.parse_args()

    res = run_smart_quarterly_sync(
        force_all=args.force_all,
        force_season=args.force_season,
        target_quarter_override=args.quarter,
    )
    print("\nKết quả đồng bộ:", res)
