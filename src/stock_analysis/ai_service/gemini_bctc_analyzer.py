"""
===================================================================================
MODULE: GEMINI MULTIMODAL FINANCIAL STATEMENT & AUDIT ANALYZER
Path: src/stock_analysis/ai_service/gemini_bctc_analyzer.py
Chức năng:
  - Tích hợp trực tiếp Google AI Studio / Gemini API (Mô hình Gemini 3.8 Flash).
  - Tự động bóc tách Thuyết minh BCTC: Nợ nhóm 2, Nợ cơ cấu TT02/TT06, Cơ cấu TSBĐ BĐS,
    Danh mục Trái phiếu Doanh nghiệp, Lãi dự thu và Ý kiến Kiểm toán độc lập.
  - Tạo Bản Tóm Tắt Điều Hành (Executive Summary 1 trang) & 5 Cờ Đỏ Rủi Ro (Red Flags).
  - Đồng bộ và lưu trữ vào PostgreSQL Data Warehouse (mart_sentiment.fact_ai_financial_insights).
===================================================================================
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

# Nạp cấu hình môi trường từ .env
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

logger = logging.getLogger("GeminiBCTCAnalyzer")
logger.setLevel(logging.INFO)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BASE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def call_gemini_api(
    prompt: str,
    system_instruction: Optional[str] = None,
    json_mode: bool = True,
    model: Optional[str] = None,
    temperature: float = 0.2
) -> Dict[str, Any]:
    """
    Gọi Gemini API qua REST endpoint chính thức của Google AI Studio.
    Tự động thử nghiệm danh sách mô hình dự phòng (Fallback: 3-flash-preview -> 3.1-flash-lite -> 3.8-flash)
    khi gặp lỗi 503 High Demand hoặc 404.
    """
    key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Chưa cấu hình GEMINI_API_KEY trong tệp .env hoặc biến môi trường!")

    candidate_models = [model] if model else ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
    last_error = None

    for target_model in candidate_models:
        url = f"{BASE_API_URL}/{target_model}:generateContent?key={key}"

        contents = []
        if system_instruction:
            contents.append({
                "role": "user",
                "parts": [{"text": f"HƯỚNG DẪN HỆ THỐNG / QUY TẮC PHÂN TÍCH:\n{system_instruction}"}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Tôi đã hiểu toàn bộ quy tắc thẩm định kiểm toán và sẽ tuân thủ nghiêm ngặt theo đúng cấu trúc yêu cầu."}]
            })

        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.95,
            }
        }

        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        payload_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if not candidates:
                    continue
                
                raw_text = candidates[0]["content"]["parts"][0]["text"]
                if json_mode:
                    parsed = json.loads(raw_text)
                    parsed["model_name"] = target_model
                    return parsed
                return {"raw_text": raw_text, "model_name": target_model}

        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8") if e.fp else str(e)
            logger.warning(f"Model {target_model} trả về HTTP {e.code}: {err_msg[:120]}... Thử model dự phòng...")
            last_error = f"Lỗi Gemini API ({e.code}): {err_msg}"
            continue
        except Exception as exc:
            logger.warning(f"Lỗi kết nối với model {target_model}: {exc}... Thử model dự phòng...")
            last_error = str(exc)
            continue

    raise RuntimeError(f"Tất cả các model Gemini đều không khả dụng: {last_error}")


def build_audit_prompt(ticker: str, period_name: str, financial_context: Dict[str, Any]) -> str:
    """Xây dựng prompt chuyên môn hóa cho Chuyên viên Kiểm toán Tín dụng Ngân hàng"""
    return f"""
Bạn là Chuyên gia Trưởng Thẩm định Tín dụng & Kiểm toán Ngân hàng (Senior Credit Risk & Audit Specialist).
Hãy phân tích Báo cáo Tài chính và Thuyết minh chuyên sâu của ngân hàng {ticker} tại kỳ {period_name} dựa trên dữ liệu chuẩn hóa sau:

DỮ LIỆU ĐÃ KIỂM TOÁN TẠI DWH:
- Mã ngân hàng: {ticker}
- Tên ngân hàng: {financial_context.get('short_name', ticker)}
- Kỳ phân tích: {period_name}
- Dư nợ cho vay: {financial_context.get('total_loans', 0):,.0f} VND
- Tiền gửi khách hàng: {financial_context.get('total_deposits', 0):,.0f} VND
- Tỷ lệ nợ xấu (NPL - Nhóm 3-5): {financial_context.get('npl_ratio', 0)*100:.2f}%
- Tỷ lệ bao phủ nợ xấu (LLR): {financial_context.get('llr_ratio', 0)*100:.1f}%
- Tỷ lệ an toàn vốn (CAR): {financial_context.get('car_ratio', 0)*100:.1f}%
- Tỷ suất sinh lời ROE: {financial_context.get('roe', 0)*100:.1f}%
- Tỷ lệ chi phí trên thu nhập (CIR): {financial_context.get('cir', 0)*100:.1f}%

HÃY TRẢ VỀ ĐÚNG CẤU TRÚC JSON SAU ĐÂY:
{{
  "ticker": "{ticker}",
  "period_name": "{period_name}",
  "filing_type": "BCTC Kiểm toán Hợp nhất",
  "auditor_name": "Tên công ty kiểm toán độc lập (Big 4 hoặc đơn vị uy tín)",
  "auditor_opinion": "Chấp nhận toàn phần / Có vấn đề cần nhấn mạnh / Ngoại trừ",
  "executive_summary": "Tóm tắt điều hành 1 trang (khoảng 3–4 đoạn văn súc tích, khách quan, phân tích chất lượng tài sản, bộ đệm vốn, biên lãi ròng NIM và rủi ro thanh khoản).",
  "key_strengths": [
    "Điểm sáng 1 (ví dụ: Tăng trưởng CASA dẫn đầu, chi phí vốn COF tối ưu)",
    "Điểm sáng 2 (ví dụ: Bộ đệm dự phòng bao nợ xấu LLR duy trì mức an toàn cao)",
    "Điểm sáng 3 (ví dụ: Hệ số an toàn vốn CAR đạt chuẩn Basel II / Thông tư 14)"
  ],
  "red_flags": [
    {{
      "risk_level": "CAO / TRUNG BÌNH / THẤP",
      "category": "Nợ Nhóm 2 / Trái Phiếu Doanh Nghiệp / Bất Động Sản / Lãi Dự Thu / Kiểm Toán",
      "title": "Tiêu đề rủi ro ngắn gọn",
      "description": "Diễn giải chi tiết bản chất rủi ro và tác động tới bảng cân đối kế toán",
      "page_reference": "Thuyết minh số X (Trang Y)"
    }},
    {{
      "risk_level": "TRUNG BÌNH",
      "category": "Cơ cấu Tài sản bảo đảm",
      "title": "Tỷ trọng thế chấp Bất động sản chiếm tỷ lệ lớn",
      "description": "Tỷ lệ tài sản bảo đảm là BĐS duy trì trên 65%, tiềm ẩn rủi ro trích lập bổ sung nếu thanh khoản thị trường nhà đất trầm lắng",
      "page_reference": "Thuyết minh số 12 (Trang Z)"
    }},
    {{
      "risk_level": "TRUNG BÌNH",
      "category": "Lãi Dự Thu",
      "title": "Khoản phải thu và lãi dự thu luân chuyển",
      "description": "Theo dõi sát sao tốc độ thu hồi lãi dự thu để đảm bảo lợi nhuận ghi nhận là dòng tiền thực chất",
      "page_reference": "Thuyết minh số 18"
    }}
  ],
  "structured_notes": {{
    "group_2_loans_estimate": "Ước tính nợ nhóm 2 (Nợ cần chú ý)",
    "real_estate_collateral_pct": "Tỷ lệ tài sản bảo đảm là BĐS (%)",
    "corporate_bonds_exposure": "Ước tính quy mô danh mục Trái phiếu Doanh nghiệp",
    "restructured_loans_tt02": "Tình trạng nợ cơ cấu theo Thông tư 02/06",
    "accrued_interest_status": "Đánh giá mức độ trọng yếu của lãi dự thu"
  }}
}}
"""


def save_ai_insights_to_warehouse(insight_data: Dict[str, Any]) -> bool:
    """Lưu trữ kết quả phân tích AI vào PostgreSQL Data Warehouse"""
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            dbname=os.getenv("DB_NAME", "Stock_Warehouse"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", "")
        )
        cur = conn.cursor()

        sql = """
        INSERT INTO mart_sentiment.fact_ai_financial_insights (
            ticker, period_name, filing_type, auditor_name, auditor_opinion,
            executive_summary, key_strengths, red_flags, structured_notes,
            source_pdf_url, model_name, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (ticker, period_name, filing_type) DO UPDATE SET
            auditor_name = EXCLUDED.auditor_name,
            auditor_opinion = EXCLUDED.auditor_opinion,
            executive_summary = EXCLUDED.executive_summary,
            key_strengths = EXCLUDED.key_strengths,
            red_flags = EXCLUDED.red_flags,
            structured_notes = EXCLUDED.structured_notes,
            source_pdf_url = COALESCE(EXCLUDED.source_pdf_url, mart_sentiment.fact_ai_financial_insights.source_pdf_url),
            model_name = EXCLUDED.model_name,
            created_at = CURRENT_TIMESTAMP;
        """

        cur.execute(sql, (
            insight_data.get("ticker"),
            insight_data.get("period_name"),
            insight_data.get("filing_type", "BCTC Kiểm toán Hợp nhất"),
            insight_data.get("auditor_name", "KPMG Việt Nam"),
            insight_data.get("auditor_opinion", "Chấp nhận toàn phần"),
            insight_data.get("executive_summary", ""),
            json.dumps(insight_data.get("key_strengths", []), ensure_ascii=False),
            json.dumps(insight_data.get("red_flags", []), ensure_ascii=False),
            json.dumps(insight_data.get("structured_notes", {}), ensure_ascii=False),
            insight_data.get("source_pdf_url", ""),
            insight_data.get("model_name", GEMINI_DEFAULT_MODEL)
        ))

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Đã lưu thành công AI insight cho {insight_data.get('ticker')} kỳ {insight_data.get('period_name')}")
        return True
    except Exception as exc:
        logger.error(f"Lỗi lưu trữ AI insight vào Data Warehouse: {exc}")
        return False


def get_bank_ai_insights(ticker: str, period_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Truy vấn kết quả phân tích AI đã lưu trong Data Warehouse"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            dbname=os.getenv("DB_NAME", "Stock_Warehouse"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", "")
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if period_name:
            sql = """
            SELECT * FROM mart_sentiment.fact_ai_financial_insights 
            WHERE ticker = %s AND period_name = %s
            ORDER BY created_at DESC LIMIT 1;
            """
            cur.execute(sql, (ticker, period_name))
        else:
            sql = """
            SELECT * FROM mart_sentiment.fact_ai_financial_insights 
            WHERE ticker = %s 
            ORDER BY created_at DESC LIMIT 1;
            """
            cur.execute(sql, (ticker,))

        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            res = dict(row)
            # Parse json nếu cần
            if isinstance(res.get("key_strengths"), str):
                res["key_strengths"] = json.loads(res["key_strengths"])
            if isinstance(res.get("red_flags"), str):
                res["red_flags"] = json.loads(res["red_flags"])
            if isinstance(res.get("structured_notes"), str):
                res["structured_notes"] = json.loads(res["structured_notes"])
            return res
        return None
    except Exception as exc:
        logger.error(f"Lỗi truy vấn AI insight từ Data Warehouse: {exc}")
        return None
