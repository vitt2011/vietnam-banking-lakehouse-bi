"""
===================================================================================
MODULE: src/common/db.py
CHỨC NĂNG: KẾT NỐI POSTGRESQL 16, CONNECTION POOL & TYPE CASTING TỰ ĐỘNG
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md
===================================================================================
"""

import os
from pathlib import Path
from typing import Optional, List, Tuple, Any

import psycopg2
import psycopg2.extensions
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_values
import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"

# Đọc cấu hình từ settings.yaml nếu có
if SETTINGS_PATH.exists():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        _settings = yaml.safe_load(f)
    _db_cfg = _settings.get("database", {})
else:
    _db_cfg = {}

DB_HOST = os.getenv("DB_HOST", _db_cfg.get("host", "localhost"))
DB_PORT = os.getenv("DB_PORT", str(_db_cfg.get("port", 5432)))
DB_NAME = os.getenv("DB_NAME", _db_cfg.get("dbname", "Stock_Warehouse"))
DB_USER = os.getenv("DB_USER", _db_cfg.get("user", "postgres"))
DB_PASS = os.getenv("DB_PASS", "")

# Đăng ký Type Caster tự động ép PostgreSQL NUMERIC sang Python float
# Ngăn ngừa lỗi TypeError: unsupported operand type(s) for /: 'decimal.Decimal' and 'float'
DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None
)
psycopg2.extensions.register_type(DEC2FLOAT)

_POOL: Optional[SimpleConnectionPool] = None


def get_connection_pool() -> SimpleConnectionPool:
    """Khởi tạo và duy trì Connection Pool kết nối PostgreSQL 16"""
    global _POOL
    if _POOL is None or _POOL.closed:
        _POOL = SimpleConnectionPool(
            minconn=2,
            maxconn=20,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
        )
    return _POOL


def get_db_connection():
    """Tạo kết nối đơn lẻ trực tiếp"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def execute_sql(sql: str, params: Optional[Tuple] = None, commit: bool = True):
    """Thực thi một câu lệnh SQL đơn lẻ"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if commit:
                conn.commit()
    finally:
        conn.close()


def execute_values_bulk(sql: str, records: List[Tuple], page_size: int = 2000):
    """Nạp dữ liệu hàng loạt tốc độ cao bằng execute_values"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, records, page_size=page_size)
            conn.commit()
    finally:
        conn.close()
