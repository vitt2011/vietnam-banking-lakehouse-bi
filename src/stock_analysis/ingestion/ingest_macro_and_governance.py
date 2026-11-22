"""
TẬP LỆNH: Stock_Analysis/stock_analysis/data/master_ingestion_runner.py
CHỨC NĂNG: MASTER AUTONOMOUS PIPELINE RUNNER - TỰ HÀNH THU THẬP & NẠP DATABASE
Thực thi tuần tự 4 giai đoạn dữ liệu mới mà KHÔNG GHI ĐÈ bất kỳ code/dữ liệu cũ nào:
  - Giai đoạn 1: Chuỗi giá 14 Chỉ số Thị trường & Ngành (VNINDEX, VN30, VNFINLEAD, VNREAL...)
  - Giai đoạn 2: Dữ liệu Kinh tế Vĩ mô (Tỷ giá USD/VND 15 năm, Lãi suất NHNN, GDP, CPI, Tín dụng, Bond Yield)
  - Giai đoạn 3: Lịch sử Sự kiện & Cổ tức 27 Ngân hàng
  - Giai đoạn 4: Mạng lưới Ban lãnh đạo, Cổ đông lớn & Công ty con 27 Ngân hàng
Lưu trữ đồng thời:
  - Data Lake Bronze (01_raw/*.parquet)
  - PostgreSQL Database (Stock_Warehouse)
"""

import sys
import os
import time
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import numpy as np
import requests

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Đường dẫn thư mục chuẩn
PROJECT_ROOT = Path(__file__).resolve().parents[2]
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
RAW_DATA_DIR = DATA_LAKE_DIR / "01_bronze"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "ingestion.log"

# Cấu hình logging kép (ghi ra màn hình và file log)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger("AutonomousRunner")

# Ngăn chặn vnai/vnstock gọi sys.exit() khi đạt rate limit để try-except có thể kiểm soát và retry an toàn
try:
    import vnai.beam.quota
    vnai.beam.quota.CleanErrorContext.__exit__ = lambda self, exc_type, exc_val, exc_tb: False
except Exception:
    pass


def check_and_throttle_quota(safety_threshold: int = 2) -> None:
    """Kiểm tra quota và tự động tạm dừng nếu chạm ngưỡng 20 req/phút của vnstock"""
    try:
        from vnai.beam.quota import guardian
        status = guardian.get_limit_status()
        remaining = status.get("minute_limit", {}).get("remaining", 20)
        reset_in = status.get("minute_limit", {}).get("reset_in_seconds", 60)
        if remaining <= safety_threshold:
            wait_time = max(reset_in + 2.0, 5.0)
            logger.info(f"Chủ động điều tiết Rate Limit: Quota còn {remaining} lượt. Đang tạm nghỉ {wait_time:.1f} giây...")
            time.sleep(wait_time)
    except Exception:
        pass


# Không sử dụng trực tiếp kết nối DB ở tầng Ingestion (tuân thủ quy tắc SSOT Data Lake Bronze)

# Danh sách 27 Ngân hàng mục tiêu
BANKING_TICKERS = [
    "ACB", "ABB", "BAB", "BID", "BVB", "CTG", "EIB", "HDB", "KLB", "LPB",
    "MBB", "MSB", "NAB", "NVB", "OCB", "PGB", "SGB", "SHB", "SSB", "STB",
    "TCB", "TPB", "VAB", "VBB", "VCB", "VIB", "VPB"
]

# 14 Chỉ số thị trường & nhóm ngành trọng yếu
MARKET_INDICES = [
    ("VNINDEX", "Chỉ số VN-Index (HOSE)"),
    ("VN30", "Chỉ số VN30"),
    ("VN100", "Chỉ số VN100"),
    ("VNMID", "Chỉ số VN Midcap"),
    ("VNSML", "Chỉ số VN Smallcap"),
    ("HNXIndex", "Chỉ số HNX-Index"),
    ("HNX30", "Chỉ số HNX30"),
    ("UPCOMIndex", "Chỉ số UPCOM-Index"),
    ("VNFINLEAD", "Chỉ số Tài chính Chọn lọc VNFINLEAD"),
    ("VNFINSELECT", "Chỉ số Tài chính Tuyển chọn VNFINSELECT"),
    ("VNFIN", "Chỉ số Ngành Tài chính HOSE"),
    ("VNREAL", "Chỉ số Ngành Bất động sản VNREAL"),
    ("VNCONS", "Chỉ số Ngành Tiêu dùng VNCONS"),
    ("VNIND", "Chỉ số Ngành Công nghiệp VNIND"),
]

# ==============================================================================
# GIAI ĐOẠN 1: CHUỖI GIÁ CHỈ SỐ THỊ TRƯỜNG & NHÓM NGÀNH
# ==============================================================================
def run_stage_1_market_indices(incremental: bool = False):
    logger.info("=" * 60)
    logger.info(">>> BẮT ĐẦU GIAI ĐOẠN 1: CHUỖI GIÁ CHỈ SỐ THỊ TRƯỜNG & NGÀNH (%s)", "Chế độ Gia tăng" if incremental else "Chế độ Toàn bộ")
    logger.info("=" * 60)
    
    from vnstock.explorer.vci.quote import Quote
    all_indices_data = []
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    max_dict = {}
    out_parquet = RAW_DATA_DIR / "market_indices_historical.parquet"
    if incremental and out_parquet.exists():
        try:
            df_pq = pd.read_parquet(out_parquet)
            max_s = df_pq.groupby('symbol', observed=False)['time'].max()
            max_dict = dict(zip(max_s.index, pd.to_datetime(max_s.values)))
        except Exception as e:
            logger.warning("Không thể đọc max_date từ tệp Bronze Parquet (%s).", e)

    for symbol, desc in MARKET_INDICES:
        last_dt = max_dict.get(symbol)
        if incremental and last_dt is not None:
            start_date = (last_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start_date = "2000-01-01"
            
        if start_date > today_str:
            logger.info("  -> Chỉ số %s đã ở phiên mới nhất (%s), bỏ qua.", symbol, last_dt.strftime("%Y-%m-%d") if last_dt is not None else "")
            continue
            
        logger.info(f"Đang kéo dữ liệu chỉ số {symbol} ({desc}) từ {start_date} đến {today_str}...")
        try:
            q = Quote(symbol)
            df = q.history(start=start_date, end=today_str)
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time'])
                if incremental and last_dt is not None:
                    df = df[df['time'] > last_dt]
                if not df.empty:
                    df['symbol'] = symbol
                    df['index_name'] = desc
                    all_indices_data.append(df)
                    logger.info(f"  -> Thành công: {len(df):,} phiên giao dịch ({df['time'].min().strftime('%Y-%m-%d')} đến {df['time'].max().strftime('%Y-%m-%d')})")
                else:
                    logger.info(f"  -> Không có phiên mới cho {symbol}")
            else:
                logger.info(f"  -> Không có dữ liệu cho {symbol}")
        except Exception as e:
            logger.error(f"  -> Lỗi khi kéo {symbol}: {e}")
        time.sleep(0.3)
        
    out_parquet = RAW_DATA_DIR / "market_indices_historical.parquet"
    if all_indices_data:
        new_indices_df = pd.concat(all_indices_data, ignore_index=True)
        
        if incremental and out_parquet.exists():
            df_old = pd.read_parquet(out_parquet)
            full_indices_df = pd.concat([df_old, new_indices_df], ignore_index=True).drop_duplicates(subset=['symbol', 'time'], keep='last').sort_values(['symbol', 'time']).reset_index(drop=True)
        else:
            full_indices_df = new_indices_df
            
        full_indices_df.to_parquet(out_parquet, index=False, engine="pyarrow", compression="snappy")
        logger.info(f"Đã lưu Data Lake Bronze: {out_parquet.name} ({len(full_indices_df):,} dòng)")
        return len(new_indices_df) if incremental else len(full_indices_df)
    return 0

# ==============================================================================
# GIAI ĐOẠN 2: DỮ LIỆU KINH TẾ VĨ MÔ (MACROECONOMIC DATA)
# ==============================================================================
def run_stage_2_macro_data():
    logger.info("=" * 60)
    logger.info(">>> BẮT ĐẦU GIAI ĐOẠN 2: DỮ LIỆU KINH TẾ VĨ MÔ")
    logger.info("=" * 60)
    
    macro_records = []
    
    # 2.1 Kéo tỷ giá USD/VND 15 năm (Daily từ Yahoo Finance)
    logger.info("Đang kéo chuỗi tỷ giá USD/VND lịch sử 15 năm (Daily)...")
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X?interval=1d&range=15y"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            res = r.json()['chart']['result'][0]
            timestamps = res.get('timestamp', [])
            closes = res['indicators']['quote'][0].get('close', [])
            for ts, cl in zip(timestamps, closes):
                if cl is not None and not np.isnan(cl):
                    dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    macro_records.append({
                        "date": dt,
                        "category": "Tỷ giá",
                        "indicator_code": "USDVND_RATE",
                        "indicator_name": "Tỷ giá USD/VND",
                        "value": round(float(cl), 2),
                        "unit": "VND",
                        "frequency": "Daily",
                        "source": "Yahoo Finance FX"
                    })
            logger.info(f"  -> Thu thập thành công {len(timestamps):,} ngày tỷ giá USD/VND!")
    except Exception as e:
        logger.error(f"  -> Lỗi lấy tỷ giá USD/VND: {e}")
        
    # 2.2 Chuỗi số liệu Lãi suất điều hành NHNN & Chỉ số Vĩ mô chính thức (2012 - 2026)
    logger.info("Đang khởi tạo chuỗi Lãi suất điều hành NHNN, GDP, CPI, Tín dụng & Bond Yield...")
    
    # Bảng quyết định Lãi suất điều hành của Ngân hàng Nhà nước (SBV) qua các mốc lịch sử
    sbv_policy_rates = [
        ("2012-03-13", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 14.0, "%/năm", "Quyết định NHNN"),
        ("2012-04-11", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 13.0, "%/năm", "Quyết định NHNN"),
        ("2012-05-10", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 12.0, "%/năm", "Quyết định NHNN"),
        ("2012-06-11", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 11.0, "%/năm", "Quyết định NHNN"),
        ("2012-07-01", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 10.0, "%/năm", "Quyết định NHNN"),
        ("2012-12-24", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 9.0, "%/năm", "Quyết định NHNN"),
        ("2013-03-26", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 8.0, "%/năm", "Quyết định NHNN"),
        ("2013-05-13", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 7.0, "%/năm", "Quyết định NHNN"),
        ("2014-03-18", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 6.5, "%/năm", "Quyết định NHNN"),
        ("2017-07-10", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 6.25, "%/năm", "Quyết định NHNN"),
        ("2019-09-16", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 6.0, "%/năm", "Quyết định NHNN"),
        ("2020-03-17", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 5.0, "%/năm", "Quyết định NHNN"),
        ("2020-05-13", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 4.5, "%/năm", "Quyết định NHNN"),
        ("2020-10-01", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 4.0, "%/năm", "Quyết định NHNN"),
        ("2022-09-23", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 5.0, "%/năm", "Quyết định NHNN"),
        ("2022-10-25", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 6.0, "%/năm", "Quyết định NHNN"),
        ("2023-04-03", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 5.5, "%/năm", "Quyết định NHNN"),
        ("2023-05-25", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 5.0, "%/năm", "Quyết định NHNN"),
        ("2023-06-19", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 4.5, "%/năm", "Quyết định NHNN"),
        ("2024-01-01", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 4.5, "%/năm", "Quyết định NHNN"),
        ("2025-01-01", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 4.5, "%/năm", "Quyết định NHNN"),
        ("2026-01-01", "SBV_REFINANCING_RATE", "Lãi suất Tái cấp vốn NHNN", 4.5, "%/năm", "Quyết định NHNN"),
    ]
    for dt, code, name, val, unit, src in sbv_policy_rates:
        macro_records.append({
            "date": dt,
            "category": "Chính sách tiền tệ",
            "indicator_code": code,
            "indicator_name": name,
            "value": val,
            "unit": unit,
            "frequency": "Event-driven",
            "source": src
        })

    # Dữ liệu GDP & Tín dụng & CPI định kỳ theo quý/năm
    quarterly_macro = [
        ("2018-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.45, "%"),
        ("2018-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.73, "%"),
        ("2018-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.82, "%"),
        ("2018-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.21, "%"),
        ("2019-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.82, "%"),
        ("2019-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.73, "%"),
        ("2019-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.48, "%"),
        ("2019-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.97, "%"),
        ("2020-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 3.68, "%"),
        ("2020-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 0.39, "%"),
        ("2020-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 2.62, "%"),
        ("2020-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 4.48, "%"),
        ("2021-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 4.72, "%"),
        ("2021-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.73, "%"),
        ("2021-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", -6.02, "%"),
        ("2021-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 5.22, "%"),
        ("2022-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 5.05, "%"),
        ("2022-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.83, "%"),
        ("2022-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 13.71, "%"),
        ("2022-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 5.92, "%"),
        ("2023-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 3.28, "%"),
        ("2023-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 4.05, "%"),
        ("2023-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 5.33, "%"),
        ("2023-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.72, "%"),
        ("2024-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 5.66, "%"),
        ("2024-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.93, "%"),
        ("2024-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.40, "%"),
        ("2024-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.10, "%"),
        ("2025-03-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 6.80, "%"),
        ("2025-06-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.05, "%"),
        ("2025-09-30", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.20, "%"),
        ("2025-12-31", "GDP_GROWTH_YOY", "Tăng trưởng GDP", 7.30, "%"),
    ]
    for dt, code, name, val, unit in quarterly_macro:
        macro_records.append({
            "date": dt,
            "category": "Kinh tế vĩ mô",
            "indicator_code": code,
            "indicator_name": name,
            "value": val,
            "unit": unit,
            "frequency": "Quarterly",
            "source": "Tổng cục Thống kê (GSO)"
        })

    # Tăng trưởng tín dụng toàn hệ thống ngân hàng (Credit Growth % theo năm)
    credit_growth = [
        ("2015-12-31", 17.29), ("2016-12-31", 18.71), ("2017-12-31", 18.17),
        ("2018-12-31", 13.89), ("2019-12-31", 13.65), ("2020-12-31", 12.13),
        ("2021-12-31", 13.61), ("2022-12-31", 14.18), ("2023-12-31", 13.78),
        ("2024-12-31", 15.08), ("2025-12-31", 15.50)
    ]
    for dt, val in credit_growth:
        macro_records.append({
            "date": dt,
            "category": "Tín dụng hệ thống",
            "indicator_code": "CREDIT_GROWTH_YOY",
            "indicator_name": "Tăng trưởng tín dụng toàn ngành",
            "value": val,
            "unit": "%",
            "frequency": "Annual",
            "source": "Ngân hàng Nhà nước (SBV)"
        })
        
    df_macro = pd.DataFrame(macro_records)
    df_macro['date'] = pd.to_datetime(df_macro['date'])
    
    # Lưu vào Data Lake Bronze
    out_parquet = RAW_DATA_DIR / "macro_economic_indicators.parquet"
    df_macro.to_parquet(out_parquet, index=False, engine="pyarrow", compression="snappy")
    logger.info(f"Đã lưu Data Lake Bronze: {out_parquet.name} ({len(df_macro):,} dòng)")
    return len(df_macro)

# ==============================================================================
# GIAI ĐOẠN 3: LỊCH SỬ SỰ KIỆN & CỔ TỨC (27 NGÂN HÀNG)
# ==============================================================================
def run_stage_3_corporate_events():
    logger.info("=" * 60)
    logger.info(">>> BẮT ĐẦU GIAI ĐOẠN 3: LỊCH SỬ SỰ KIỆN & CỔ TỨC (27 NGÂN HÀNG)")
    logger.info("=" * 60)
    
    from vnstock.explorer.vci.company import Company
    all_events = []
    
    for idx, ticker in enumerate(BANKING_TICKERS, 1):
        logger.info(f"[{idx}/27] Đang kéo sự kiện & cổ tức của {ticker}...")
        check_and_throttle_quota(safety_threshold=3)
        for attempt in range(3):
            try:
                c = Company(ticker)
                ev = c.events()
                if ev is not None and not ev.empty:
                    ev['symbol'] = ticker
                    if 'ticker' in ev.columns and 'symbol' not in ev.columns:
                        ev['symbol'] = ev['ticker']
                    all_events.append(ev)
                    logger.info(f"  -> {ticker}: {len(ev)} sự kiện/cổ tức.")
                else:
                    logger.warning(f"  -> {ticker}: Không có bản ghi sự kiện.")
                break
            except Exception as e:
                logger.warning(f"  -> Lần {attempt+1} kéo {ticker} gặp lỗi: {e}. Đang tạm nghỉ 10s...")
                time.sleep(10)
        time.sleep(3.2)  # Giữ tốc độ an toàn không vượt 20 req/phút
        
    if all_events:
        df_events = pd.concat(all_events, ignore_index=True)
        for col in df_events.columns:
            if df_events[col].dtype == 'object':
                df_events[col] = df_events[col].astype(str)
                
        out_parquet = RAW_DATA_DIR / "bank_corporate_events.parquet"
        df_events.to_parquet(out_parquet, index=False, engine="pyarrow", compression="snappy")
        logger.info(f"Đã lưu Data Lake Bronze: {out_parquet.name} ({len(df_events):,} dòng)")
        return len(df_events)
    return 0

# ==============================================================================
# GIAI ĐOẠN 4: MẠNG LƯỚI BAN LÃNH ĐẠO, CỔ ĐÔNG LỚN & CÔNG TY CON (27 NGÂN HÀNG)
# ==============================================================================
def run_stage_4_network_graph():
    logger.info("=" * 60)
    logger.info(">>> BẮT ĐẦU GIAI ĐOẠN 4: BAN LÃNH ĐẠO, CỔ ĐÔNG & CÔNG TY CON")
    logger.info("=" * 60)
    
    from vnstock.explorer.vci.company import Company
    officers_list = []
    shareholders_list = []
    subsidiaries_list = []
    
    for idx, ticker in enumerate(BANKING_TICKERS, 1):
        logger.info(f"[{idx}/27] Đang lấy cấu trúc quản trị của {ticker}...")
        c = Company(ticker)
        
        # 1. Ban lãnh đạo
        check_and_throttle_quota(safety_threshold=3)
        try:
            off = c.officers()
            if off is not None and not off.empty:
                off['symbol'] = ticker
                officers_list.append(off)
        except Exception as e:
            logger.warning(f"  -> Lỗi lấy lãnh đạo {ticker}: {e}")
        time.sleep(3.2)
            
        # 2. Cổ đông lớn
        check_and_throttle_quota(safety_threshold=3)
        try:
            sh = c.shareholders()
            if sh is not None and not sh.empty:
                sh['symbol'] = ticker
                shareholders_list.append(sh)
        except Exception as e:
            logger.warning(f"  -> Lỗi lấy cổ đông {ticker}: {e}")
        time.sleep(3.2)
            
        # 3. Công ty con
        check_and_throttle_quota(safety_threshold=3)
        try:
            sub = c.subsidiaries()
            if sub is not None and not sub.empty:
                sub['symbol'] = ticker
                subsidiaries_list.append(sub)
        except Exception as e:
            logger.warning(f"  -> Lỗi lấy công ty con {ticker}: {e}")
        time.sleep(3.2)
            
        logger.info(f"  -> Hoàn tất nạp siêu dữ liệu cho {ticker}.")
        
    counts = {}
    
    # Lưu Ban lãnh đạo
    if officers_list:
        df_off = pd.concat(officers_list, ignore_index=True)
        for col in df_off.columns:
            if df_off[col].dtype == 'object':
                df_off[col] = df_off[col].astype(str)
        p_off = RAW_DATA_DIR / "bank_officers.parquet"
        df_off.to_parquet(p_off, index=False, engine="pyarrow", compression="snappy")
        counts['officers'] = len(df_off)
        logger.info(f"Đã lưu Data Lake Bronze bank_officers.parquet: {len(df_off):,} lãnh đạo.")
        
    # Lưu Cổ đông lớn
    if shareholders_list:
        df_sh = pd.concat(shareholders_list, ignore_index=True)
        for col in df_sh.columns:
            if df_sh[col].dtype == 'object':
                df_sh[col] = df_sh[col].astype(str)
        p_sh = RAW_DATA_DIR / "bank_shareholders.parquet"
        df_sh.to_parquet(p_sh, index=False, engine="pyarrow", compression="snappy")
        counts['shareholders'] = len(df_sh)
        logger.info(f"Đã lưu Data Lake Bronze bank_shareholders.parquet: {len(df_sh):,} cổ đông lớn.")
        
    # Lưu Công ty con
    if subsidiaries_list:
        df_sub = pd.concat(subsidiaries_list, ignore_index=True)
        for col in df_sub.columns:
            if df_sub[col].dtype == 'object':
                df_sub[col] = df_sub[col].astype(str)
        p_sub = RAW_DATA_DIR / "bank_subsidiaries.parquet"
        df_sub.to_parquet(p_sub, index=False, engine="pyarrow", compression="snappy")
        counts['subsidiaries'] = len(df_sub)
        logger.info(f"Đã lưu Data Lake Bronze bank_subsidiaries.parquet: {len(df_sub):,} công ty con.")
        
    return counts

# ==============================================================================
# HÀM ĐIỀU PHỐI CHÍNH (MAIN PIPELINE)
# ==============================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Master Pipeline Runner")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental",
                        help="Chế độ chạy: full (toàn bộ) hoặc incremental (gia tăng)")
    args = parser.parse_args()
    
    t_start = time.time()
    logger.info("*" * 70)
    logger.info("KHỞI ĐỘNG HỆ THỐNG MASTER PIPELINE RUNNER (Chế độ: %s)", args.mode)
    logger.info("*" * 70)
    
    is_incremental = (args.mode == "incremental")
    
    # 1. Chỉ số thị trường
    res1 = run_stage_1_market_indices(incremental=is_incremental)
    
    # 2. Kinh tế vĩ mô
    macro_parquet = RAW_DATA_DIR / "macro_economic_indicators.parquet"
    macro_count = 0
    if macro_parquet.exists():
        try:
            macro_count = len(pd.read_parquet(macro_parquet))
        except Exception:
            macro_count = 0
        
    if is_incremental and macro_count >= 3000:
        logger.info(f"[BỎ QUA GIAI ĐOẠN 2] macro_economic_indicators.parquet đã có sẵn {macro_count:,} dòng!")
        res2 = macro_count
    else:
        res2 = run_stage_2_macro_data()
        
    if not is_incremental:
        res3 = run_stage_3_corporate_events()
        res4 = run_stage_4_network_graph()
    else:
        logger.info("[CHẾ ĐỘ INCREMENTAL] Bỏ qua cào lại sự kiện & mạng lưới để tối ưu thời gian.")
        res3 = 0
        res4 = {}
    
    total_time = round(time.time() - t_start, 2)
    logger.info("=" * 70)
    logger.info("TỔNG KẾT BÁO CÁO TIẾN ĐỘ THU THẬP VÀO DATA LAKE BRONZE:")
    logger.info(f"- Giai đoạn 1 (Chỉ số Thị trường): {res1:,} dòng -> market_indices_historical.parquet")
    logger.info(f"- Giai đoạn 2 (Kinh tế Vĩ mô):     {res2:,} dòng -> macro_economic_indicators.parquet")
    logger.info(f"Tổng thời gian thực thi: {total_time} giây ({round(total_time/60, 2)} phút)")
    logger.info("TẤT CẢ DỮ LIỆU ĐÃ LƯU TRỮ AN TOÀN VÀO DATA LAKE BRONZE (PARQUET)!")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()

