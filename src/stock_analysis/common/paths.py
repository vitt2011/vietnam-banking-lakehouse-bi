"""
Hệ thống quản lý đường dẫn tập trung (Centralized Path Configuration)
Phục vụ nguyên lý Decoupling Compute & Storage:
Tách biệt hoàn toàn Codebase (Stock_Analysis) và Data Lakehouse (DataLake).
"""

import os
from pathlib import Path

# Thư mục gốc của Code Platform: D:\Do_an_II\Stock_Analysis
# Path(__file__) -> common -> stock_analysis -> src -> Stock_Analysis
CODE_ROOT = Path(__file__).resolve().parents[3]

# Thư mục DataLake ngoài: D:\Do_an_II\DataLake (hỗ trợ qua DATA_LAKE_ROOT hoặc DATA_LAKE_PATH)
env_lake = os.getenv("DATA_LAKE_ROOT") or os.getenv("DATA_LAKE_PATH")
if env_lake and Path(env_lake).resolve().exists():
    DATA_LAKE_DIR = Path(env_lake).resolve()
elif (CODE_ROOT.parent / "DataLake").exists():
    DATA_LAKE_DIR = (CODE_ROOT.parent / "DataLake").resolve()
elif (CODE_ROOT.parent / "data_lake").exists():
    DATA_LAKE_DIR = (CODE_ROOT.parent / "data_lake").resolve()
else:
    DATA_LAKE_DIR = (CODE_ROOT / "data_lake").resolve()

# Các tầng Medallion Architecture (3 Tầng Chuẩn Quốc Tế: Bronze -> Silver -> Gold)
BRONZE_DIR = DATA_LAKE_DIR / "01_bronze"
SILVER_DIR = DATA_LAKE_DIR / "02_silver"
GOLD_DIR = DATA_LAKE_DIR / "03_gold"
QUARANTINE_DIR = SILVER_DIR / "_quarantine"  # Lưu trữ phụ trợ nội bộ tầng Silver

# 01_Bronze (Phân tách Có cấu trúc & Phi cấu trúc)
BRONZE_STRUCTURED = BRONZE_DIR / "01_structured"
BRONZE_UNSTRUCTURED = BRONZE_DIR / "02_unstructured"
BRONZE_MARKET_DIR = BRONZE_STRUCTURED / "01_Giao_Dich_Gia_OHLCV"
BRONZE_FIN_DIR = BRONZE_STRUCTURED / "02_Bao_Cao_Tai_Chinh"
BRONZE_MACRO_DIR = BRONZE_STRUCTURED / "03_Kinh_Te_Vi_Mo"
BRONZE_GOV_DIR = BRONZE_STRUCTURED / "04_Quan_Tri_So_Huu"
BRONZE_NEWS_DIR = BRONZE_UNSTRUCTURED / "financial_news"

# 02_Silver (Master Data, Có cấu trúc, Phi cấu trúc)
SILVER_MDM_DIR = SILVER_DIR / "01_master_data"
SILVER_STRUCTURED = SILVER_DIR / "02_structured"
SILVER_UNSTRUCTURED = SILVER_DIR / "03_unstructured"
SILVER_MARKET_DIR = SILVER_STRUCTURED / "01_Giao_Dich_Gia_OHLCV"
SILVER_FIN_DIR = SILVER_STRUCTURED / "02_Bao_Cao_Tai_Chinh"
SILVER_RATIOS_DIR = SILVER_FIN_DIR / "camels_ratios"
SILVER_MACRO_DIR = SILVER_STRUCTURED / "03_Kinh_Te_Vi_Mo"
SILVER_GOV_DIR = SILVER_STRUCTURED / "04_Quan_Tri_So_Huu"
SILVER_NEWS_DIR = SILVER_UNSTRUCTURED / "financial_news"

# 03_Gold (Marts tổng hợp nghiệp vụ - Khớp 5 Modules Dashboard)
GOLD_VALUATION_DIR = GOLD_DIR / "01_Ma_Tran_Dinh_Gia_Gordon"
GOLD_CAMELS_DIR = GOLD_DIR / "02_The_Diem_CAMELS"
GOLD_TECH_DIR = GOLD_DIR / "03_Chi_Bao_Ky_Thuat"
GOLD_GOV_DIR = GOLD_DIR / "04_Do_Thi_Mang_Luoi_Quan_Tri"
GOLD_SENTIMENT_DIR = GOLD_DIR / "05_Chi_So_Cam_Xuc_Tin_Tuc"

# Data Quality Quarantine (Nhánh phụ cách ly dữ liệu lỗi nội bộ tầng Silver)
QUARANTINE_SCHEMA_DIR = QUARANTINE_DIR / "01_Loi_Cau_Truc_Schema"
QUARANTINE_RECON_DIR = QUARANTINE_DIR / "02_Loi_Doi_Soat_Ke_Toan"

# Thư mục Runtime & Logs riêng biệt
RUNTIME_DIR = CODE_ROOT / "runtime"
LOGS_DIR = RUNTIME_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MANIFESTS_DIR = RUNTIME_DIR / "manifests"
MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
