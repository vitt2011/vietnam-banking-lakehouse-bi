"""
===================================================================================
MODULE: src/common/hashing.py
CHỨC NĂNG: ĐỊNH DANH BẤT BIẾN DETERMINISTIC UUIDv5 & BỘ BĂM SIÊU DỮ LIỆU (MDM)
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 3, Mục 272-274)
===================================================================================
"""

import uuid
import hashlib
from pathlib import Path
from typing import Union

# Namespace UUID tĩnh cho toàn bộ hệ thống Ngân hàng Việt Nam (Deterministic)
NAMESPACE_VN_BANKING = uuid.UUID("7b3f9420-a8c1-4d3e-9b25-8a1e2f3d4c5b")
NAMESPACE_URL = uuid.NAMESPACE_URL


def generate_bank_uuid(tax_code: str) -> str:
    """
    Tạo Deterministic UUIDv5 cho Ngân hàng từ Mã Số Thuế (bất biến theo thời gian).
    VD: 0100112437 -> 94a1b2c3-...
    """
    clean_code = str(tax_code).strip().upper()
    return str(uuid.uuid5(NAMESPACE_VN_BANKING, f"BANK:{clean_code}"))


def generate_stakeholder_uuid(entity_type: str, composite_key: str) -> str:
    """
    Tạo Deterministic UUIDv5 cho Cổ đông hoặc Lãnh đạo.
    composite_key = normalized_name + "_" + birth_year hoặc tax_code
    """
    clean_type = str(entity_type).strip().upper()
    clean_key = str(composite_key).strip().lower()
    return str(uuid.uuid5(NAMESPACE_VN_BANKING, f"STAKEHOLDER:{clean_type}:{clean_key}"))


def generate_article_uuid(canonical_url: str) -> str:
    """
    Tạo Deterministic UUIDv5 cho bài báo/công bố thông tin từ URL gốc (chống trùng lặp).
    """
    clean_url = str(canonical_url).strip().lower()
    return str(uuid.uuid5(NAMESPACE_URL, clean_url))


def generate_asset_urn(layer: str, domain: str, entity: str) -> str:
    """
    Sinh định danh URN tiêu chuẩn cho Data Asset trong Metadata Catalog.
    VD: urn:lake:silver:financials:camels_ratios
    """
    l = layer.lower().strip()
    d = domain.lower().strip()
    e = entity.lower().strip()
    return f"urn:lake:{l}:{d}:{e}"


def compute_file_checksum(file_path: Union[str, Path]) -> str:
    """
    Tính mã băm SHA-256 của file phục vụ kiểm toán toàn vẹn và Data Lineage.
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return ""
    sha256 = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()
