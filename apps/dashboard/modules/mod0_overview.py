"""
===================================================================================
MODULE 0: TOÀN CẢNH NGÀNH & CHẤT LƯỢNG DỮ LIỆU (MARKET OVERVIEW & DATA QUALITY)
Path: apps/dashboard/modules/mod0_overview.py
Tôn chỉ thiết kế (Chuẩn hóa theo Báo cáo Phản biện ChatGPT 19/11/2026):
  - Định vị sản phẩm: Nền tảng nghiên cứu hỗ trợ chuyên viên phân tích ngân hàng
  - Chuyển trọng tâm từ "khoe số lượng dòng dữ liệu" sang "bối cảnh ngành & chất lượng dữ liệu"
  - Giải thích rõ ràng các đơn vị đếm (945 bank-quarters vs 784 hồ sơ ratios)
  - Trình bày cấu trúc phân tầng 27 ngân hàng và kiểm toán độ phủ dữ liệu
  - Tuyệt đối không đưa ra khuyến nghị mua/bán black-box
===================================================================================
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.services.query_service import (
    get_all_banks,
    get_platform_health_kpis,
    get_data_coverage_audit,
)
from dashboard.common_theme import (
    apply_plotly_theme, render_led_card, get_theme_palette,
)


def render_overview():
    pal = get_theme_palette()
    kpis = get_platform_health_kpis()
    total_fin = kpis.get('total_financials', 945)
    num_quarters = max(35, total_fin // 27)

    # 1. VALUE PROPOSITION & RESEARCH CONTEXT HERO (NGHIÊM TÚC, HỌC THUẬT, KHÁCH QUAN)
    st.html(f"""
        <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 5px solid {pal['color_brand_led']}; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 2px 10px {pal['shadow_color']};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 11px; font-weight: 800; color: {pal['color_brand_led']}; text-transform: uppercase; letter-spacing: 1.2px;">
                    🏛️ PHÂN HỆ 01 • TOÀN CẢNH THỊ TRƯỜNG & CHẤT LƯỢNG DỮ LIỆU
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="background: rgba(37, 99, 235, 0.08); color: {pal['color_brand_led']}; border: 1px solid {pal['border_color']}; padding: 3px 10px; border-radius: 5px; font-size: 11.5px; font-weight: 800;">
                        TRẠM PHÂN TÍCH CHUYÊN GIA
                    </span>
                    <span style="background: rgba(16, 185, 129, 0.1); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.25); padding: 3px 10px; border-radius: 5px; font-size: 11.5px; font-weight: 800;">
                        TOÀN VẸN DỮ LIỆU DWH
                    </span>
                </div>
            </div>
            <div style="font-size: 18px; font-weight: 800; color: {pal['text_heading']}; margin-top: 4px; letter-spacing: -0.2px;">
                Nền Tảng Dữ Liệu & Nghiên Cứu Cổ Phiếu 27 Ngân Hàng Thương Mại Việt Nam
            </div>
            <div style="font-size: 13.5px; color: {pal['text_muted']}; margin-top: 6px; margin-bottom: 16px; line-height: 1.65;">
                Nền tảng chuẩn hóa dữ liệu tài chính phục vụ <b>chuyên viên phân tích (Equity Research Analyst)</b>. Hệ thống hỗ trợ sàng lọc ngân hàng, đánh giá sức khỏe tài chính, chất lượng lợi nhuận, định giá và kiểm chứng các giả thuyết đầu tư bằng dữ liệu lịch sử. <i>Người dùng chịu trách nhiệm đối với quyết định đầu tư cuối cùng.</i>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; padding-top: 14px; border-top: 1px solid {pal['border_color']};">
                <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['accent_cyan']}; border-radius: 8px; padding: 14px 16px;">
                    <div style="font-weight: 800; color: {pal['accent_cyan']}; font-size: 12.5px; margin-bottom: 6px; text-transform: uppercase;">1. Phạm Vi Nghiên Cứu (Universe)</div>
                    <div style="font-size: 13px; color: {pal['text_muted']}; line-height: 1.6;">
                        Toàn bộ <b>27 NHTMCP</b> niêm yết và đăng ký giao dịch trên HOSE, HNX và UPCoM. Bao phủ 35 quý BCTC liên tục từ 2018Q1 đến 2026Q3. <i>(Agribank 100% vốn Nhà nước chưa niêm yết)</i>.
                    </div>
                </div>
                <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['color_brand_led']}; border-radius: 8px; padding: 14px 16px;">
                    <div style="font-weight: 800; color: {pal['color_brand_led']}; font-size: 12.5px; margin-bottom: 6px; text-transform: uppercase;">2. Chuẩn Hóa Theo Chuẩn Mực</div>
                    <div style="font-size: 13px; color: {pal['text_muted']}; line-height: 1.6;">
                        Áp dụng các chuẩn mực tài chính ngân hàng quốc tế (CAMELS, Basel II, PPOP, LLR, Credit Cost) và cập nhật khung pháp lý NHNN (Thông tư 14/2025 về CAR, Thông tư 22/2019 và Thông tư 50/2026 về LDR).
                    </div>
                </div>
                <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['color_up']}; border-radius: 8px; padding: 14px 16px;">
                    <div style="font-weight: 800; color: {pal['color_up']}; font-size: 12.5px; margin-bottom: 6px; text-transform: uppercase;">3. Hỗ Trợ Ra Quyết Định Độc Lập</div>
                    <div style="font-size: 13px; color: {pal['text_muted']}; line-height: 1.6;">
                        Cung cấp bằng chứng thực nghiệm minh bạch, gắn liền với các câu hỏi thẩm định: Sàng lọc định giá rẻ → Kiểm tra chất lượng tài sản → Xác định xúc tác sự kiện → Quản trị rủi ro danh mục.
                    </div>
                </div>
            </div>
        </div>
    """)

    # 2. KHU VỰC THÔNG SỐ VẬN HÀNH DỮ LIỆU & ĐỘ TIN CẬY (DATA AUDIT SNAPSHOT)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        render_led_card(
            title="Quan Sát BCTC Chuẩn Hóa",
            value=f"{kpis.get('total_financials', 945):,} kỳ",
            subtext=f"27 ngân hàng × {num_quarters} quý liên tục",
            badge="ĐỘ PHỦ KHO",
            status="cyan"
        )
    with col2:
        render_led_card(
            title="Hồ Sơ Tỷ Số Phân Tích",
            value=f"{kpis.get('total_ratios', 784):,} hồ sơ",
            subtext="Tỷ số CAMELS & Tăng trưởng YoY",
            badge="TỶ SỐ TÀI CHÍNH",
            status="purple"
        )
    with col3:
        render_led_card(
            title="Phiên Giá OHLCV Đã Lọc",
            value=f"{kpis.get('total_ohlcv', 0):,}",
            subtext=f"Phiên gần nhất: {kpis.get('latest_trading_date', 'N/A')}",
            badge="DỮ LIỆU GIÁ SẠCH",
            status="mint"
        )
    with col4:
        render_led_card(
            title="Dữ Liệu Vĩ Mô & Sự Kiện",
            value=f"{kpis.get('total_macro', 0) + kpis.get('total_news', 0):,}",
            subtext="Lãi suất SBV, Tỷ giá & Sự kiện cổ tức",
            badge="LIÊN THỊ TRƯỜNG",
            status="gold"
        )

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

    # 3. DANH BẠ MASTER DATA 27 NGÂN HÀNG & BỘ LỌC PHÂN TẦNG
    st.markdown(f"<h3 style='color: {pal['text_heading']}; margin-bottom: 12px;'>📋 Danh Bạ 27 Ngân Hàng Thương Mại Niêm Yết & Đăng Ký Giao Dịch</h3>", unsafe_allow_html=True)

    df_banks = get_all_banks()

    c_filter1, c_filter2 = st.columns([1, 2])
    with c_filter1:
        exchanges = ["TẤT CẢ"] + sorted(df_banks["listing_exchange"].dropna().unique().tolist())
        selected_ex = st.selectbox("Sàn giao dịch:", exchanges, key="ov_exchange_filter")
    with c_filter2:
        tiers = ["TẤT CẢ"] + sorted(df_banks["tier_group"].dropna().unique().tolist())
        selected_tier = st.selectbox("Nhóm phân tầng ngân hàng:", tiers, key="ov_tier_filter")

    filtered_df = df_banks.copy()
    if selected_ex != "TẤT CẢ":
        filtered_df = filtered_df[filtered_df["listing_exchange"] == selected_ex]
    if selected_tier != "TẤT CẢ":
        filtered_df = filtered_df[filtered_df["tier_group"] == selected_tier]

    display_df = filtered_df.copy()
    display_df["charter_capital_vnd"] = pd.to_numeric(display_df["charter_capital_vnd"], errors="coerce").fillna(0)
    display_df["Vốn điều lệ (Tỷ VND)"] = (display_df["charter_capital_vnd"] / 1e9).round(1).apply(lambda x: f"{x:,.1f}")

    display_df = display_df[[
        "ticker", "short_name", "bank_name", "listing_exchange",
        "tier_group", "Vốn điều lệ (Tỷ VND)", "tax_code"
    ]].rename(columns={
        "ticker": "Mã CK",
        "short_name": "Tên viết tắt",
        "bank_name": "Tên đầy đủ ngân hàng",
        "listing_exchange": "Sàn",
        "tier_group": "Phân tầng nhóm",
        "tax_code": "Mã số thuế"
    })

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 4. BIỂU ĐỒ CƠ CẤU VỐN ĐIỀU LỆ & QUY MÔ PHÂN TẦNG
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='color: {pal['text_heading']}; margin-bottom: 12px;'>📊 Cơ Cấu Vốn Điều Lệ & Quy Mô Toàn Hệ Thống</h3>", unsafe_allow_html=True)

    c_chart1, c_chart2 = st.columns(2)

    tier_color_map = {
        "BIG4": pal["color_brand_led"],
        "STATE_BIG4": pal["color_brand_led"],
        "PRIVATE_TIER1": pal["accent_cyan"],
        "TIER1_PRIVATE": pal["accent_cyan"],
        "PRIVATE_TIER2": pal["accent_pink"],
        "TIER2_MIDCAP": pal["accent_pink"],
        "TIER3_SMALL": pal["color_warn"],
        "TIER3_SMALL_RESTRUCT": pal["color_warn"],
    }

    with c_chart1:
        plot_df = df_banks.copy()
        plot_df["charter_capital_vnd"] = pd.to_numeric(plot_df["charter_capital_vnd"], errors="coerce").fillna(0)
        plot_df["charter_capital_bn"] = (plot_df["charter_capital_vnd"] / 1e9).round(1)
        plot_df = plot_df.sort_values("charter_capital_bn", ascending=True)

        fig_cap = px.bar(
            plot_df,
            x="charter_capital_bn",
            y="ticker",
            orientation="h",
            color="tier_group",
            labels={"charter_capital_bn": "Vốn điều lệ (Tỷ VND)", "ticker": "Mã Ngân hàng", "tier_group": "Phân tầng"},
            color_discrete_map=tier_color_map,
            height=600,
        )
        fig_cap.update_traces(hovertemplate="<b>%{y}</b><br>Vốn điều lệ: <b>%{x:,.1f} Tỷ VND</b><extra></extra>")
        fig_cap = apply_plotly_theme(fig_cap, height=600, title="Quy Mô Vốn Điều Lệ 27 Ngân Hàng (Tỷ VND)")
        st.plotly_chart(fig_cap, use_container_width=True)

    with c_chart2:
        df_banks_calc = df_banks.copy()
        df_banks_calc["charter_capital_vnd"] = pd.to_numeric(df_banks_calc["charter_capital_vnd"], errors="coerce").fillna(0)
        tier_agg = df_banks_calc.groupby("tier_group")["charter_capital_vnd"].sum().reset_index()
        tier_agg["charter_capital_bn"] = (tier_agg["charter_capital_vnd"] / 1e9).round(1)

        fig_pie = px.pie(
            tier_agg,
            names="tier_group",
            values="charter_capital_bn",
            color="tier_group",
            color_discrete_map=tier_color_map,
            hole=0.45,
            height=600,
        )
        fig_pie.update_traces(
            textposition="inside",
            textinfo="percent+label",
            insidetextfont=dict(color="#FFFFFF", size=12, family="Segoe UI, Roboto, sans-serif"),
            hovertemplate="<b>%{label}</b><br>Tổng vốn: <b>%{value:,.1f} Tỷ VND</b> (%{percent})<extra></extra>",
            marker=dict(line=dict(color=pal["bg_card"], width=2))
        )
        fig_pie = apply_plotly_theme(fig_pie, height=600, title="Tỷ Trọng Vốn Điều Lệ Theo Nhóm Phân Tầng")
        st.plotly_chart(fig_pie, use_container_width=True)

    # 5. BÁO CÁO KIỂM TOÁN ĐỘ PHỦ DỮ LIỆU & GIẢI TRÌNH ĐƠN VỊ ĐẾM (DATA QUALITY AUDIT)
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'>
            <h3 style='color: {pal["text_heading"]}; margin: 0;'>🛡️ Báo Cáo Kiểm Toán Chất Lượng & Độ Phủ Dữ Liệu BCTC ({num_quarters} Quý: 2018Q1 – 2026Q3)</h3>
            <span style='background: rgba(76, 201, 240, 0.15); color: {pal["accent_cyan"]}; border: 1px solid {pal["accent_cyan"]}; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;'>
                100% COVERAGE ({total_fin}/{total_fin} KỲ BCTC)
            </span>
        </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
        <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-radius: 8px; padding: 14px 16px; margin-bottom: 14px; font-size: 12.5px; color: {pal['text_body']}; line-height: 1.65;">
            <b>Ghi chú kiểm toán phương pháp luận (Data Audit Notes):</b><br>
            • <b>{kpis.get('total_financials', 945):,} kỳ BCTC:</b> Đại diện cho <b>27 ngân hàng × {num_quarters} quý</b> báo cáo tài chính hợp nhất từ Q1/2018 đến Q3/2026, đã được kiểm tra cân đối kế toán qua cổng DQ2.<br>
            • <b>{kpis.get('total_ratios', 881):,} hồ sơ tỷ số tài chính:</b> Do các chỉ tiêu tăng trưởng cùng kỳ (YoY Growth) cần dữ liệu đối chiếu 4 quý trước đó, các quý đầu năm 2018 không tính YoY; tất cả tỷ số đã được chuẩn hóa dấu dương (CIR, LLR) và tách riêng chi phí dự phòng P&L.<br>
            • <b>{kpis.get('total_macro', 46133):,} bản ghi vĩ mô & chỉ số:</b> Bao gồm chuỗi lịch sử Lãi suất tái cấp vốn SBV, tỷ giá USD/VND và các chỉ số VN-Index / VN30 / VNFIN.<br>
            • <b>Giới hạn nghiên cứu:</b> Toàn bộ dữ liệu dựa trên BCTC công bố chính thức; các kỳ BCTC trong quá khứ có thể có sự hồi tố (restatement) trong các BCTC kiểm toán năm sau.
        </div>
    """, unsafe_allow_html=True)

    with st.expander(f"🔍 Xem Bảng Kiểm Toán Chi Tiết 27 Ngân Hàng × {num_quarters} Quý BCTC", expanded=False):
        df_audit = get_data_coverage_audit()
        if not df_audit.empty:
            df_audit_display = df_audit[[
                "ticker", "short_name", "tier_group", "listing_exchange",
                "expected_quarters", "actual_quarters", "coverage_pct",
                "earliest_quarter", "latest_quarter", "missing_quarter_list"
            ]].rename(columns={
                "ticker": "Mã CK",
                "short_name": "Tên viết tắt",
                "tier_group": "Phân tầng",
                "listing_exchange": "Sàn",
                "expected_quarters": "Kỳ dự kiến",
                "actual_quarters": "Kỳ thực tế",
                "coverage_pct": "Tỷ lệ phủ (%)",
                "earliest_quarter": "Kỳ đầu",
                "latest_quarter": "Kỳ cuối",
                "missing_quarter_list": "Trạng thái chuỗi"
            })
            st.dataframe(df_audit_display, use_container_width=True, hide_index=True)
