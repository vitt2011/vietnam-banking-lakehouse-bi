"""
===================================================================================
MODULE: src/common/trading_calendar.py
CHỨC NĂNG: QUẢN LÝ LỊCH GIAO DỊCH CHỨNG KHOÁN & QUY TẮC CUT-OFF 15:00 ICT
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 3, Mục 258-266)
Mục tiêu: Triệt tiêu hoàn toàn thiên lệch nhìn trước tương lai (Look-ahead Bias)
===================================================================================
"""

from datetime import datetime, date, time, timedelta
from typing import Optional, Set
import pandas as pd

# Giờ chốt phiên giao dịch khớp lệnh sàn HOSE/HNX/UPCOM (15:00:00 ICT)
CUT_OFF_TIME = time(15, 0, 0)

# Danh sách ngày nghỉ lễ cố định Dương lịch tại Việt Nam (Tháng, Ngày)
VN_FIXED_HOLIDAYS = {
    (1, 1),    # Tết Dương Lịch
    (4, 30),   # Giải phóng Miền Nam
    (5, 1),    # Quốc tế Lao động
    (9, 2),    # Quốc khánh
    (9, 3),    # Nghỉ liền kề Quốc khánh
}


def is_weekend(d: date) -> bool:
    """Thứ 7 (5) và Chủ nhật (6) không giao dịch"""
    return d.weekday() >= 5


def is_fixed_vn_holiday(d: date) -> bool:
    """Kiểm tra ngày lễ cố định theo Dương lịch"""
    return (d.month, d.day) in VN_FIXED_HOLIDAYS


def is_trading_day(d: date, known_holidays: Optional[Set[date]] = None) -> bool:
    """
    Xác định một ngày có phải là phiên giao dịch của sàn chứng khoán Việt Nam hay không.
    """
    if is_weekend(d):
        return False
    if is_fixed_vn_holiday(d):
        return False
    if known_holidays and d in known_holidays:
        return False
    return True


def get_next_trading_date(d: date, known_holidays: Optional[Set[date]] = None) -> date:
    """Tìm ngày giao dịch hợp lệ kế tiếp (T+1)"""
    candidate = d + timedelta(days=1)
    while not is_trading_day(candidate, known_holidays):
        candidate += timedelta(days=1)
    return candidate


def get_prev_trading_date(d: date, known_holidays: Optional[Set[date]] = None) -> date:
    """Tìm ngày giao dịch hợp lệ liền trước (T-1)"""
    candidate = d - timedelta(days=1)
    while not is_trading_day(candidate, known_holidays):
        candidate -= timedelta(days=1)
    return candidate


def get_effective_trading_date(
    published_dt: datetime,
    known_holidays: Optional[Set[date]] = None
) -> date:
    """
    Quy tắc Cut-off 15:00 ICT (Anti Look-ahead Bias Rule):
    - Nếu tin ra vào ngày thường và trước hoặc đúng 15:00:00 -> tính vào phiên hôm đó.
    - Nếu tin ra sau 15:00:00, hoặc vào ngày cuối tuần/nghỉ lễ -> tính vào phiên giao dịch kế tiếp.
    """
    pub_date = published_dt.date()
    pub_time = published_dt.time()

    if is_trading_day(pub_date, known_holidays) and pub_time <= CUT_OFF_TIME:
        return pub_date
    else:
        return get_next_trading_date(pub_date, known_holidays)


def generate_dim_date_records(start_year: int = 2015, end_year: int = 2030) -> pd.DataFrame:
    """
    Sinh toàn bộ dữ liệu Dimension thời gian chuẩn cho master_data.dim_date (2015 - 2030).
    Bao gồm cờ trading_day, prev_trading_date_sk, next_trading_date_sk.
    """
    start_dt = date(start_year, 1, 1)
    end_dt = date(end_year, 12, 31)
    curr = start_dt

    dates = []
    while curr <= end_dt:
        dates.append(curr)
        curr += timedelta(days=1)

    df = pd.DataFrame({"full_date": dates})
    df["date_sk"] = df["full_date"].apply(lambda d: int(d.strftime("%Y%m%d")))
    df["day_of_week"] = df["full_date"].apply(lambda d: d.weekday() + 1)  # 1: Thứ Hai -> 7: Chủ Nhật
    df["day_name_vi"] = df["day_of_week"].map({
        1: "Thứ Hai", 2: "Thứ Ba", 3: "Thứ Tư", 4: "Thứ Năm",
        5: "Thứ Sáu", 6: "Thứ Bảy", 7: "Chủ Nhật"
    })
    df["day_of_month"] = df["full_date"].apply(lambda d: d.day)
    df["week_of_year"] = df["full_date"].apply(lambda d: d.isocalendar()[1])
    df["month_num"] = df["full_date"].apply(lambda d: d.month)
    df["month_name_vi"] = df["month_num"].apply(lambda m: f"Tháng {m}")
    df["quarter_num"] = df["month_num"].apply(lambda m: (m - 1) // 3 + 1)
    df["year_num"] = df["full_date"].apply(lambda d: d.year)
    df["year_quarter"] = df.apply(lambda r: f"{r['year_num']}-Q{r['quarter_num']}", axis=1)
    df["is_weekend"] = df["full_date"].apply(is_weekend)
    df["is_vn_holiday"] = df["full_date"].apply(is_fixed_vn_holiday)
    df["is_trading_day"] = df["full_date"].apply(is_trading_day)

    # Tính prev_trading_date_sk và next_trading_date_sk
    trading_dates = sorted(df[df["is_trading_day"]]["full_date"].tolist())
    trading_set = set(trading_dates)

    next_map = {}
    prev_map = {}

    for d in dates:
        # Next trading
        cand_next = d if (d in trading_set) else d + timedelta(days=1)
        while cand_next not in trading_set and cand_next <= end_dt:
            cand_next += timedelta(days=1)
        next_map[d] = int(cand_next.strftime("%Y%m%d")) if cand_next in trading_set else int(d.strftime("%Y%m%d"))

        # Prev trading
        cand_prev = d if (d in trading_set) else d - timedelta(days=1)
        while cand_prev not in trading_set and cand_prev >= start_dt:
            cand_prev -= timedelta(days=1)
        prev_map[d] = int(cand_prev.strftime("%Y%m%d")) if cand_prev in trading_set else int(d.strftime("%Y%m%d"))

    df["next_trading_date_sk"] = df["full_date"].map(next_map)
    df["prev_trading_date_sk"] = df["full_date"].map(prev_map)
    df["is_quarter_end"] = df["full_date"].apply(lambda d: (d.month in [3, 6, 9, 12]) and (d.day in [30, 31]))

    return df
