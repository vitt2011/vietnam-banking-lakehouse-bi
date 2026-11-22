"""
===================================================================================
ỨNG DỤNG WEB NỀN TẢNG NGHIÊN CỨU ĐẦU TƯ CỔ PHIẾU NGÂN HÀNG ĐỊNH LƯỢNG
Path: apps/dashboard/app.py
Kiến trúc V3 (Chuẩn hóa toàn diện theo Báo cáo Phản biện ChatGPT 19/11/2026):
  - Định vị: Vietnam Banking Quantitative Research Workstation (Nền tảng hỗ trợ chuyên viên phân tích)
  - Tái cấu trúc 5 Phân hệ Nghiên cứu Chuẩn mực (Gộp Mod 2, 3, 4 thành Hồ sơ Ngân hàng Toàn diện)
  - Loại bỏ hoàn toàn ngôn từ kiêu ngạo / black-box, áp dụng phong cách học thuật khiêm tốn
  - Tích hợp PostgreSQL 16 Data Warehouse (8 Schemas), Lakehouse Medallion & Headless Quant Engine
  - Hỗ trợ Chế độ kép (LIGHT / DARK MODE) 1-click
===================================================================================
"""

import sys
from pathlib import Path

# Thêm đường dẫn project vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import streamlit as st
from dashboard.common_theme import (
    apply_global_theme, get_theme_palette, get_theme_mode, set_theme_mode,
)
from dashboard.services.query_service import get_data_source_label

# 1. THIẾT LẬP CẤU HÌNH TRANG STREAMLIT
st.set_page_config(
    page_title="Nền Tảng Nghiên Cứu Định Lượng Ngân Hàng | Research Workstation",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Nhập 5 Phân hệ nghiên cứu chuẩn hóa theo cấu trúc mới
from dashboard.modules.mod0_overview import render_overview
from dashboard.modules.mod1_valuation_gordon import render_valuation_gordon
from dashboard.modules.mod2_bank_profile import render_bank_profile
from dashboard.modules.mod3_catalysts_context import render_catalysts_context
from dashboard.modules.mod4_research_evidence import render_research_evidence


def main():
    # 2. ÁP DỤNG BỘ CSS THEME TOÀN CỤC MỖI LẦN RERUN (HỖ TRỢ LIGHT / DARK MODE)
    apply_global_theme()
    pal = get_theme_palette()

    # KHỞI TẠO VÀ BẢO TOÀN TRẠNG THÁI TOÀN CỤC (GLOBAL PERSISTENT STATE)
    if "selected_ticker" not in st.session_state:
        st.session_state["selected_ticker"] = "VCB"
    if "selected_bank" not in st.session_state:
        st.session_state["selected_bank"] = "VCB"

    # SIDEBAR: THÔNG TIN DỰ ÁN & MENU ĐIỀU HƯỚNG
    with st.sidebar:
        st.markdown(f"""
            <div style="padding: 6px 2px 14px 2px; border-bottom: 1px solid {pal['border_color']}; margin-bottom: 14px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 32px; height: 32px; background: linear-gradient(135deg, {pal['color_brand']} 0%, {pal['color_brand_led']} 100%); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 900; color: #FFFFFF; font-size: 13px; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);">VQ</div>
                    <div>
                        <div style="font-size: 13px; font-weight: 800; color: {pal['text_heading']}; letter-spacing: -0.2px; line-height: 1.15;">VIETNAM BANKING QUANT</div>
                        <div style="font-size: 11px; font-weight: 700; color: {pal['color_brand_led']}; text-transform: uppercase; letter-spacing: 0.5px;">Trạm Nghiên Cứu Định Lượng</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # CỤM NÚT CHUYỂN ĐỔI GIAO DIỆN (SÁNG / TỐI) TRỰC QUAN 1-CLICK
        current_m = get_theme_mode()
        is_dark = (current_m == "DARK")
        c_th1, c_th2 = st.columns(2)
        with c_th1:
            if st.button("☀️ Sáng", use_container_width=True, key="btn_switch_light", type="primary" if not is_dark else "secondary"):
                if is_dark:
                    set_theme_mode("LIGHT")
                    st.rerun()
        with c_th2:
            if st.button("🌙 Tối", use_container_width=True, key="btn_switch_dark", type="primary" if is_dark else "secondary"):
                if not is_dark:
                    set_theme_mode("DARK")
                    st.rerun()

        st.markdown(f"<div style='font-size: 11px; font-weight: 800; color: {pal['text_muted']}; text-transform: uppercase; letter-spacing: 1px; margin-top: 14px; margin-bottom: 8px;'>PHÂN HỆ NGHIÊN CỨU</div>", unsafe_allow_html=True)

        menu_options = [
            "01 · Toàn Cảnh Ngành & Nền Tảng",
            "02 · Sàng Lọc & Định Giá P/B - ROE",
            "03 · Hồ Sơ Ngân Hàng Toàn Diện",
            "04 · Xúc Tác Sự Kiện & Vĩ Mô",
            "05 · Trung Tâm Bằng Chứng Định Lượng",
        ]

        choice = st.radio(
            label="Chọn Phân Hệ:",
            options=menu_options,
            index=0,
            label_visibility="collapsed"
        )

        st.markdown(f"<div style='font-size: 11px; font-weight: 800; color: {pal['text_muted']}; text-transform: uppercase; letter-spacing: 1px; margin-top: 18px; margin-bottom: 8px;'>TRẢI NGHIỆM & DỮ LIỆU</div>", unsafe_allow_html=True)
        guided_mode = st.toggle("📖 Chế độ Giải thích Nhanh (F0 / HR)", value=True, key="guided_mode_toggle")
        if st.button("🔄 Xóa Cache & Làm Mới Dữ Liệu", use_container_width=True):
            st.cache_data.clear()
            st.success("Đã làm mới bộ nhớ đệm (Đã xóa cache)!")
            st.rerun()

        ds_label = get_data_source_label()
        st.markdown(f"""
            <div style="padding-top: 14px; font-size: 11px; color: {pal['text_muted']}; line-height: 1.6; border-top: 1px solid {pal['border_color']}; margin-top: 14px;">
                <b>Kiến trúc:</b> Medallion Lakehouse + BI<br>
                <b>Nguồn phục vụ:</b> {ds_label}<br>
                <b>Độ phủ BCTC:</b> 35 quý (2018Q1–2026Q3)<br>
                <b>Đối tượng:</b> Chuyên viên phân tích & Nhà đầu tư
            </div>
        """, unsafe_allow_html=True)

    # BREADCRUMB HEADER ĐỊNH VỊ NGỮ CẢNH
    active_bank = st.session_state.get("selected_ticker", "VCB")
    clean_choice_name = choice
    st.markdown(f"""
        <div style='display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; font-size: 12px; color: {pal['text_muted']}; margin-bottom: 14px; padding: 8px 14px; background: {pal['bg_card']}; border-radius: 6px; border: 1px solid {pal['border_color']};'>
            <div style='display: flex; align-items: center; gap: 8px; white-space: nowrap;'>
                <span style='color: {pal['text_muted']}; font-weight: 600;'>TRẠM NGHIÊN CỨU</span>
                <span>/</span>
                <span style='color: {pal['text_heading']}; font-weight: 700;'>{clean_choice_name}</span>
            </div>
            <div style='display: flex; flex-wrap: wrap; align-items: center; gap: 8px;'>
                <span style='font-size: 11.5px; color: {pal['text_muted']};'>NGÂN HÀNG MỤC TIÊU:</span>
                <span style='background: rgba(37, 99, 235, 0.12); border: 1px solid {pal["color_brand_led"]}; color: {pal["color_brand_led"]}; padding: 2px 8px; border-radius: 4px; font-weight: 800; font-size: 11.5px;'>{active_bank}</span>
                <span style='background: rgba(16, 185, 129, 0.12); color: #059669; border: 1px solid rgba(16, 185, 129, 0.30); padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; white-space: nowrap;'><span style='display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #10B981; margin-right: 5px; animation: pulseGlow 1.8s infinite;'></span>{ds_label.upper()}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if guided_mode:
        guide_bg = "#EFF6FF" if pal["mode"] == "LIGHT" else "rgba(37, 99, 235, 0.14)"
        guide_map = {
            menu_options[0]: "💡 <b>Gợi ý đọc nhanh (Bước 1/5):</b> Xem bức tranh 27 ngân hàng đang niêm yết, phân nhóm quy mô (Big4 nhà nước vs TMCP tư nhân) và chất lượng độ phủ dữ liệu.",
            menu_options[1]: "💡 <b>Gợi ý đọc nhanh (Bước 2/5):</b> Tìm ngân hàng <b>'Rẻ + Khỏe'</b> — nằm bên phải (ROE sinh lời cao) nhưng phía dưới đường định giá trung bình (P/B thấp). Nhấn vào điểm trên biểu đồ để chọn mã soi tiếp ở Bước 3.",
            menu_options[2]: "💡 <b>Gợi ý đọc nhanh (Bước 3/5):</b> Khám sức khỏe nội tại bằng thẻ điểm CAMELS 6 trụ cột, kiểm tra lợi nhuận cốt lõi so với chi phí dự phòng, cổ đông lớn và file PDF BCTC gốc.",
            menu_options[3]: "💡 <b>Gợi ý đọc nhanh (Bước 4/5):</b> Quan sát giá cổ phiếu so với VN-Index & lãi suất điều hành SBV, lịch chia cổ tức và tra cứu công bố thông tin chính thức có file PDF.",
            menu_options[4]: "💡 <b>Gợi ý đọc nhanh (Bước 5/5):</b> Kiểm chứng các giả thuyết đầu tư bằng thống kê thực nghiệm (Granger Lead-Lag, Hồi quy Phần dư OLS, Event Study cổ tức có hiệu chỉnh FDR).",
        }
        st.markdown(
            f"<div style='background: {guide_bg}; border: 1px solid {pal['border_color']}; border-left: 4px solid {pal['color_brand_led']}; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; font-size: 13px; color: {pal['text_body']};'>{guide_map.get(choice, '')}</div>",
            unsafe_allow_html=True,
        )

    # ĐIỀU HƯỚNG ROUTING TỚI 5 PHÂN HỆ NGHIÊN CỨU
    try:
        if choice == menu_options[0]:
            render_overview()
        elif choice == menu_options[1]:
            render_valuation_gordon()
        elif choice == menu_options[2]:
            render_bank_profile()
        elif choice == menu_options[3]:
            render_catalysts_context()
        elif choice == menu_options[4]:
            render_research_evidence()
    except Exception as exc:
        import traceback
        st.error(f"⚠️ Đã xảy ra lỗi khi thực thi phân hệ: {exc}")
        with st.expander("🛠️ Chi tiết kỹ thuật (Traceback):", expanded=False):
            st.code(traceback.format_exc(), language="python")


if __name__ == "__main__":
    main()
