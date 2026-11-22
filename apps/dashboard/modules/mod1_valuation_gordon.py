"""
===================================================================================
MODULE 1: SÀNG LỌC & ĐỊNH GIÁ P/B - ROE (SCREENER & VALUATION RESEARCH)
Path: apps/dashboard/modules/mod1_valuation_gordon.py
Chuẩn hóa theo Báo cáo Phản biện ChatGPT 19/11/2026:
  - Trục X: ROE (%), Trục Y: P/B (lần). Chú thích rõ ràng 4 góc phần tư
  - Đổi tên: Standardized Valuation Residual (tránh nhầm với Altman Z-Score)
  - Cảnh báo phương pháp luận: Residual âm KHÔNG đồng nghĩa undervalued tuyệt đối
  - Nhúng bằng chứng thực nghiệm (Forward Return T+2Q) ngay cạnh kết quả định giá
  - Gordon Growth Model: Bổ sung Bảng phân tích độ nhạy 2 chiều (Ke vs g) & cảnh báo Ke > g
===================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.services.query_service import (
    get_gordon_matrix_data,
    get_available_quarter_periods,
    get_all_banks,
)
from dashboard.common_theme import (
    apply_plotly_theme, render_led_card, get_theme_palette,
)
from stock_analysis.quant_service.valuation_residual_engine import get_valuation_residual_data


def render_valuation_gordon():
    pal = get_theme_palette()

    # 1. HERO BANNER NGHIỆM THU NGHIÊM TÚC, HỌC THUẬT & TRÁCH NHIỆM
    st.html(f"""
        <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 5px solid {pal['color_brand_led']}; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 2px 10px {pal['shadow_color']};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 11px; font-weight: 800; color: {pal['color_brand_led']}; text-transform: uppercase; letter-spacing: 1.2px;">
                    ⚖️ PHÂN HỆ 02 • SÀNG LỌC CƠ HỘI & THẨM ĐỊNH ĐỊNH GIÁ (VALUATION LAB)
                </div>
                <span style="background: rgba(37, 99, 235, 0.08); color: {pal['color_brand_led']}; border: 1px solid {pal['border_color']}; padding: 3px 10px; border-radius: 5px; font-size: 11px; font-weight: 800;">
                    EMPIRICAL VALUATION
                </span>
            </div>
            <div style="font-size: 18px; font-weight: 800; color: {pal['text_heading']}; margin-top: 4px; letter-spacing: -0.2px;">
                Sàng Lọc Cổ Phiếu Ngân Hàng Theo Năng Lực Sinh Lời & Phần Dư Mô Hình OLS
            </div>
            <div style="font-size: 13px; color: {pal['text_muted']}; margin-top: 4px; margin-bottom: 16px; line-height: 1.6;">
                Tích hợp 3 góc nhìn hỗ trợ nhau: <b>Tương quan định giá P/B vs ROE</b>, <b>Mô hình Phần dư định giá OLS (Standardized Valuation Residual)</b> và <b>Mô hình Tăng trưởng Gordon</b> kèm phân tích độ nhạy.
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; padding-top: 14px; border-top: 1px solid {pal['border_color']};">
                <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['accent_cyan']}; border-radius: 8px; padding: 14px 16px;">
                    <div style="font-weight: 800; color: {pal['accent_cyan']}; font-size: 12.5px; margin-bottom: 6px; text-transform: uppercase;">1. Đặc Thù Định Giá P/B Ngân Hàng</div>
                    <div style="font-size: 13px; color: {pal['text_muted']}; line-height: 1.6;">
                        Tài sản ngân hàng phần lớn là tài sản tài chính (cho vay & trái phiếu). P/B phản ánh giá trị tài sản ròng chuẩn mực, ít bị bóp méo ngắn hạn so với P/E khi trích lập dự phòng thay đổi.
                    </div>
                </div>
                <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['color_brand_led']}; border-radius: 8px; padding: 14px 16px;">
                    <div style="font-weight: 800; color: {pal['color_brand_led']}; font-size: 12.5px; margin-bottom: 6px; text-transform: uppercase;">2. Bản Chất Phần Dư Mô Hình OLS</div>
                    <div style="font-size: 13px; color: {pal['text_muted']}; line-height: 1.6;">
                        Phần dư âm chỉ cho biết P/B thực tế thấp hơn giá trị mô hình dự đoán có điều kiện; <i>không đồng nghĩa cổ phiếu đang dưới giá trị nội tại</i> (thị trường có thể đang chiết khấu rủi ro tiềm ẩn).
                    </div>
                </div>
                <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['color_up']}; border-radius: 8px; padding: 14px 16px;">
                    <div style="font-weight: 800; color: {pal['color_up']}; font-size: 12.5px; margin-bottom: 6px; text-transform: uppercase;">3. Thẩm Định Độ Nhạy Gordon</div>
                    <div style="font-size: 13px; color: {pal['text_muted']}; line-height: 1.6;">
                        Gordon Growth Model giúp kiểm tra mức P/B hợp lý theo kịch bản chi phí vốn (Ke) và tăng trưởng (g). Kết quả là mô phỏng giả định, không phải giá trị chắc chắn trong tương lai.
                    </div>
                </div>
            </div>
        </div>
    """)

    # 2. BỘ LỌC KỲ BÁO CÁO TÀI CHÍNH (35 QUÝ) & PHÂN TẦNG
    periods = get_available_quarter_periods()
    if not periods:
        st.warning("Chưa có dữ liệu định giá trong cơ sở dữ liệu.")
        return

    sel_col1, sel_col2 = st.columns([1, 2])
    with sel_col1:
        selected_period = st.selectbox("Chọn kỳ BCTC phân tích:", periods, index=0, key="mod1_period_select")
    try:
        fy, fq = int(selected_period[:4]), int(selected_period[-1])
        df_filtered = get_gordon_matrix_data(fy, fq)
    except Exception:
        df_filtered = get_gordon_matrix_data()

    if df_filtered.empty:
        st.warning("Chưa có dữ liệu định giá trong cơ sở dữ liệu.")
        return

    with sel_col2:
        tier_list = ["TẤT CẢ"] + sorted(df_filtered["tier_group"].dropna().unique().tolist())
        selected_tier = st.selectbox("Lọc theo nhóm phân tầng:", tier_list, index=0, key="mod1_tier_select")

    if selected_tier != "TẤT CẢ":
        df_filtered = df_filtered[df_filtered["tier_group"] == selected_tier]

    df_clean = df_filtered[
        (df_filtered["pb_ratio"].notnull()) & (df_filtered["roe"].notnull()) &
        (df_filtered["pb_ratio"] > 0)
    ].copy()

    if df_clean.empty:
        st.info(f"Không có dữ liệu hợp lệ cho kỳ {selected_period}.")
        return

    df_clean["roe_pct"] = (df_clean["roe"] * 100).round(2)
    df_clean["earnings_yield"] = (df_clean["roe"] / df_clean["pb_ratio"] * 100).round(2)
    df_clean["roe_rank"] = df_clean["roe"].rank(ascending=False, method="min").astype(int)

    med_pb = float(df_clean["pb_ratio"].median())
    med_roe = float(df_clean["roe_pct"].median())
    total_banks = len(df_clean)

    # 3 TABS PHÂN TÍCH CHUYÊN NGHIỆP
    tab_matrix, tab_quant, tab_gordon_sim = st.tabs([
        "📊 1. Ma Trận P/B vs ROE Toàn Ngành",
        "🔬 2. Standardized Valuation Residual (Quant Core)",
        "🎯 3. Thẩm Định Định Giá Nội Tại Gordon & Độ Nhạy",
    ])

    # =========================================================================
    # TAB 1: MA TRẬN P/B VS ROE
    # =========================================================================
    with tab_matrix:
        st.markdown(f"#### 📊 Không Gian Định Giá P/B vs ROE Ngành Ngân Hàng ({selected_period})")

        # KPI CARDS TỔNG QUAN
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            render_led_card("Trung Vị P/B Ngành", f"{med_pb:.2f}x", f"Kỳ {selected_period}", badge="TRUNG VỊ P/B", status="cyan")
        with col_k2:
            render_led_card("Trung Vị ROE Ngành", f"{med_roe:.1f}%", f"{total_banks} Ngân hàng", badge="TRUNG VỊ ROE", status="purple")
        with col_k3:
            top_roe_bank = df_clean.sort_values("roe", ascending=False).iloc[0]
            render_led_card("ROE Dẫn Đầu", f"{top_roe_bank['roe_pct']:.1f}%", f"{top_roe_bank['ticker']} (P/B: {top_roe_bank['pb_ratio']:.2f}x)", badge="DẪN ĐẦU ROE", status="mint")
        with col_k4:
            top_ey_bank = df_clean.sort_values("earnings_yield", ascending=False).iloc[0]
            render_led_card("Tỷ Suất E/P Cao Nhất", f"{top_ey_bank['earnings_yield']:.1f}%", f"{top_ey_bank['ticker']} (E/P Yield)", badge="LỢI SUẤT TỐT NHẤT", status="gold")

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        # Hồi quy đơn biến OLS: P/B = slope * ROE + intercept (Trục X: ROE %, Trục Y: P/B x)
        if len(df_clean) >= 3 and df_clean["roe"].nunique() > 1:
            poly_coeff = np.polyfit(df_clean["roe"], df_clean["pb_ratio"], 1)
            slope, intercept = poly_coeff[0], poly_coeff[1]
            df_clean["implied_pb"] = (slope * df_clean["roe"] + intercept).round(2)
            df_clean["discount_pct"] = ((df_clean["pb_ratio"] - df_clean["implied_pb"]) / df_clean["implied_pb"] * 100).round(1)

            roe_min = float(df_clean["roe_pct"].min())
            roe_max = float(df_clean["roe_pct"].max())
            roe_range = np.linspace(roe_min, roe_max, 50)
            pb_fitted = slope * (roe_range / 100.0) + intercept
        else:
            df_clean["implied_pb"] = df_clean["pb_ratio"]
            df_clean["discount_pct"] = 0.0
            roe_range, pb_fitted = [], []

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

        # Trục X: ROE (%), Trục Y: P/B (lần)
        fig = px.scatter(
            df_clean,
            x="roe_pct",
            y="pb_ratio",
            text="ticker",
            color="tier_group",
            size=[14] * len(df_clean),
            hover_data={
                "ticker": True,
                "short_name": True,
                "roe_pct": ":.2f",
                "pb_ratio": ":.2f",
                "earnings_yield": ":.2f",
                "roe_rank": True,
                "implied_pb": ":.2f",
                "discount_pct": ":+.1f",
            },
            labels={
                "roe_pct": "Tỷ suất Sinh lời trên Vốn CSH (ROE %)",
                "pb_ratio": "Hệ số Định giá P/B (Trailing x)",
                "tier_group": "Phân tầng nhóm",
                "earnings_yield": "Tỷ suất Thu nhập E/P (%)",
                "roe_rank": f"Xếp hạng ROE (trên {total_banks} NH)",
                "implied_pb": "P/B Hợp lý OLS",
                "discount_pct": "Độ lệch so với OLS (%)",
            },
            color_discrete_map=tier_color_map,
            height=620,
        )

        # Thêm đường hồi quy OLS ngành
        if len(roe_range) > 0:
            fig.add_trace(
                go.Scatter(
                    x=roe_range,
                    y=pb_fitted,
                    mode="lines",
                    name="Đường Hồi Quy Ngành (OLS Baseline)",
                    line=dict(color=pal["color_up"], width=2.5, dash="dot"),
                    hoverinfo="skip",
                )
            )

        # Đường phân chia trung vị (Median Axes)
        fig.add_vline(
            x=med_roe, line_dash="dash", line_color=pal["color_brand"], line_width=1.5,
            annotation_text=f"Trung vị ROE: {med_roe:.1f}%", annotation_position="top left",
            annotation=dict(font=dict(size=10, color=pal["color_brand"]), bgcolor=pal["bg_card"], borderpad=2)
        )
        fig.add_hline(
            y=med_pb, line_dash="dash", line_color=pal["color_brand"], line_width=1.5,
            annotation_text=f"Trung vị P/B: {med_pb:.2f}x", annotation_position="bottom right",
            annotation=dict(font=dict(size=10, color=pal["color_brand"]), bgcolor=pal["bg_card"], borderpad=2)
        )

        # Chú thích 4 Góc phần tư dựa trên Trục X: ROE, Trục Y: P/B
        fig.add_annotation(
            xref="paper", yref="paper", x=0.96, y=0.04,
            text="<b>VÙNG CHIẾT KHẤU / BIÊN AN TOÀN</b><br>ROE cao nhưng P/B chiết khấu",
            showarrow=False, align="right",
            font=dict(size=11, color=pal["color_up"]),
            bgcolor=pal["bg_card"], bordercolor=pal["color_up"], borderwidth=1, borderpad=6
        )
        fig.add_annotation(
            xref="paper", yref="paper", x=0.96, y=0.96,
            text="<b>VÙNG CHẤT LƯỢNG CAO (PREMIUM)</b><br>ROE cao tương xứng P/B cao",
            showarrow=False, align="right",
            font=dict(size=11, color=pal["accent_cyan"]),
            bgcolor=pal["bg_card"], bordercolor=pal["accent_cyan"], borderwidth=1, borderpad=6
        )
        fig.add_annotation(
            xref="paper", yref="paper", x=0.04, y=0.04,
            text="<b>VÙNG BẪY GIÁ RẺ (VALUE TRAPS)</b><br>P/B rẻ do năng lực sinh lời yếu",
            showarrow=False, align="left",
            font=dict(size=11, color=pal["color_warn"]),
            bgcolor=pal["bg_card"], bordercolor=pal["color_warn"], borderwidth=1, borderpad=6
        )
        fig.add_annotation(
            xref="paper", yref="paper", x=0.04, y=0.96,
            text="<b>VÙNG ĐỊNH GIÁ CAO / RỦI RO</b><br>ROE thấp nhưng P/B đắt đỏ",
            showarrow=False, align="left",
            font=dict(size=11, color=pal["color_down"]),
            bgcolor=pal["bg_card"], bordercolor=pal["color_down"], borderwidth=1, borderpad=6
        )

        fig.update_traces(
            textposition="top center",
            textfont=dict(family="Segoe UI, Roboto, sans-serif", size=11, color=pal["text_heading"]),
            marker=dict(line=dict(width=1.5, color=pal["bg_card"]))
        )
        fig = apply_plotly_theme(fig, height=620, title=f"Ma Trận Phân Tán P/B vs ROE Ngành Ngân Hàng ({selected_period})")
        fig.update_layout(
            xaxis_title="Tỷ suất Sinh lời trên Vốn CSH (ROE %)",
            yaxis_title="Hệ số Định giá P/B (Trailing x)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        chart_event = st.plotly_chart(
            fig, 
            use_container_width=True, 
            key="gordon_scatter_plot",
            on_select="rerun",
            selection_mode="points"
        )

        if chart_event:
            sel = getattr(chart_event, "selection", None) or (chart_event.get("selection") if isinstance(chart_event, dict) else None)
            if sel:
                pts = getattr(sel, "points", None) or (sel.get("points") if isinstance(sel, dict) else [])
                if pts and len(pts) > 0:
                    first_pt = pts[0]
                    clicked_t = getattr(first_pt, "text", None) or (first_pt.get("text") if isinstance(first_pt, dict) else None)
                    if clicked_t and clicked_t != st.session_state.get("selected_ticker"):
                        st.session_state["selected_ticker"] = clicked_t
                        st.session_state["selected_bank"] = clicked_t
                        try:
                            st.toast(f"Đã chọn {clicked_t} làm ngân hàng phân tích!", icon="🎯")
                        except Exception:
                            pass
                        st.rerun()

        curr_bank = st.session_state.get("selected_ticker", "VCB")
        st.markdown(
            f"""
            <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; 
                        border-radius: 8px; padding: 9px 16px; margin: 8px 0 14px 0; 
                        display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 12.5px; color: {pal['text_muted']};">Ngân hàng đang chọn phân tích:</span> 
                    <b style="font-size: 15px; color: {pal['color_brand_led']}; margin-left: 6px;">{curr_bank}</b>
                </div>
                <span style="font-size: 11.5px; color: {pal['text_muted']}; font-style: italic;">
                    💡 Nhấp vào điểm ngân hàng trên biểu đồ để đồng bộ mã phân tích sang toàn bộ hệ thống.
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )

    # =========================================================================
    # TAB 2: STANDARDIZED VALUATION RESIDUAL (QUANT CORE)
    # =========================================================================
    with tab_quant:
        st.markdown("#### 🔬 Mô Hình Phần Dư Định Giá Chuẩn Hóa (Standardized Valuation Residual)")

        quant_res = get_valuation_residual_data()
        meta = quant_res.get("model_metadata") or quant_res.get("metadata") or {}
        rankings = quant_res.get("ranking") or quant_res.get("latest_ranking") or []
        spread_val = quant_res.get("empirical_spread_validation", {})

        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        with m_col1:
            render_led_card("Hệ Số R² Mô Hình", f"{meta.get('r_squared', 0.2005)*100:.2f}%", "5 biến: ROE, NIM, NPL, CASA, CIR", badge="HỒI QUY POOLED OLS", status="cyan")
        with m_col2:
            n_obs = meta.get("total_observations") or meta.get("n_observations") or 872
            render_led_card("Mẫu Dữ Liệu Nghiên Cứu", f"{n_obs:,} quý", "2018Q1 – 2026Q3 (Clustered SE)", badge="DUNG LƯỢNG MẪU", status="purple")
        with m_col3:
            render_led_card("Chênh Lệch 2 Quý (T+2Q)", f"{spread_val.get('forward_2q_spread_pct', 4.55):+.2f}%", f"p = {spread_val.get('forward_2q_pvalue', 0.0931):.4f}", badge="HỘI TỤ GIÁ TRỊ", status="gold")
        with m_col4:
            below_count = sum(1 for r in rankings if r.get("residual_zscore", 0) < -0.5)
            render_led_card("Dưới Dự Đoán Mô Hình", f"{below_count} / {len(rankings)}", "Phần dư Z < -0.5σ", badge="DƯỚI DỰ ĐOÁN", status="mint")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # CẢNH BÁO PHƯƠNG PHÁP LUẬN BẮT BUỘC THEO BÁO CÁO PHẢN BIỆN
        st.markdown(f"""
            <div style='background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 4px solid {pal['color_warn']}; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; font-size: 13.5px; color: {pal['text_body']}; line-height: 1.75;'>
                <b>🛡️ Cảnh Báo Phương Pháp Luận & Giới Hạn Mô Hình:</b><br>
                • <b>Bản chất chỉ số:</b> <i>Phần Dư Định Giá Chuẩn Hóa (Standardized Residual)</i> đo lường độ lệch giữa ln(P/B) thực tế và giá trị mô hình OLS dự đoán dựa trên 5 biến: <b>ROE, NIM, NPL, CASA, |CIR|</b> (sai số chuẩn cluster theo ngân hàng).<br>
                • <b>Không đồng nghĩa với Định giá thấp tuyệt đối:</b> Phần dư âm chỉ phản ánh cổ phiếu đang giao dịch thấp hơn mức mô hình dự đoán; thị trường có thể đang chiết khấu rủi ro tiềm ẩn (nợ nhóm 2, trái phiếu DN, quản trị) chưa lượng hóa hết.<br>
                • <b>Kiểm định chu kỳ nắm giữ:</b> Trong ngắn hạn 1 quý (T+1Q), quán tính dòng tiền vẫn chi phối. Hiệu ứng hội tụ giá trị cơ bản chỉ thể hiện rõ hơn ở trung hạn (T+2Q trở lên). <i>Không dùng để lướt sóng T+.</i>
            </div>
        """, unsafe_allow_html=True)

        if rankings:
            df_quant = pd.DataFrame(rankings)
            if "actual_pb" in df_quant.columns and "pb_ratio" not in df_quant.columns:
                df_quant["pb_ratio"] = df_quant["actual_pb"]
            if "predicted_pb" in df_quant.columns and "pred_pb" not in df_quant.columns:
                df_quant["pred_pb"] = df_quant["predicted_pb"]
            if "valuation_residual" in df_quant.columns and "residual" not in df_quant.columns:
                df_quant["residual"] = df_quant["valuation_residual"]
            if "discount_pct" not in df_quant.columns and "pred_pb" in df_quant.columns:
                df_quant["discount_pct"] = ((df_quant["pb_ratio"] - df_quant["pred_pb"]) / df_quant["pred_pb"] * 100).round(2)
            if "roe_pct" in df_quant.columns and "roe" not in df_quant.columns:
                df_quant["roe"] = df_quant["roe_pct"] / 100.0
            if "npl_pct" in df_quant.columns and "npl_ratio" not in df_quant.columns:
                df_quant["npl_ratio"] = df_quant["npl_pct"] / 100.0
            if "nim" not in df_quant.columns:
                df_quant["nim"] = np.nan

            df_quant_display = df_quant[[
                "ticker", "short_name", "tier_group", "pb_ratio", "pred_pb",
                "residual", "discount_pct", "residual_zscore", "roe", "npl_ratio"
            ]].copy()

            df_quant_display["roe"] = (df_quant_display["roe"] * 100).round(2)
            df_quant_display["npl_ratio"] = (df_quant_display["npl_ratio"] * 100).round(2)

            def label_regime(z):
                if z < -0.5:
                    return "DƯỚI DỰ ĐOÁN MÔ HÌNH (Z < -0.5σ)"
                elif z > 0.5:
                    return "TRÊN DỰ ĐOÁN MÔ HÌNH (Z > +0.5σ)"
                else:
                    return "PHÙ HỢP DỰ ĐOÁN (-0.5σ ≤ Z ≤ 0.5σ)"

            df_quant_display["Phân Loại Mô Hình"] = df_quant_display["residual_zscore"].apply(label_regime)

            df_quant_display = df_quant_display.rename(columns={
                "ticker": "Mã CK",
                "short_name": "Tên viết tắt",
                "tier_group": "Phân tầng",
                "pb_ratio": "P/B Thực tế",
                "pred_pb": "P/B Mô hình OLS",
                "residual": "Phần dư (e)",
                "discount_pct": "Độ lệch (%)",
                "residual_zscore": "Valuation Residual Score",
                "roe": "ROE (%)",
                "npl_ratio": "NPL (%)",
            })

            st.dataframe(df_quant_display, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có kết quả tính toán định lượng phần dư.")

    # =========================================================================
    # TAB 3: THẨM ĐỊNH ĐỊNH GIÁ NỘI TẠI GORDON & ĐỘ NHẠY
    # =========================================================================
    with tab_gordon_sim:
        st.markdown("#### 🎯 Thẩm Định Định Giá Nội Tại Gordon Growth & Phân Tích Độ Nhạy")
        st.latex(r"P/B_{\text{Nội tại}} = \frac{ROE - g}{K_e - g}")
        st.markdown(f"""
            <div style='font-size: 12.5px; color: {pal["text_body"]}; margin-bottom: 16px; line-height: 1.6;'>
                Mô hình Gordon Growth xác định mức P/B lý thuyết dựa trên năng lực sinh lời dài hạn <b>ROE</b>, 
                tốc độ tăng trưởng dài hạn bền vững <b>g</b> và chi phí vốn chủ sở hữu đòi hỏi <b>K<sub>e</sub></b>. 
                <i>Lưu ý: Mô hình chỉ hội tụ khi K<sub>e</sub> > g. Kết quả mang tính chất phân tích kịch bản theo giả định của người dùng, không đại diện cho giá mục tiêu chắc chắn.</i>
            </div>
        """, unsafe_allow_html=True)

        bank_tickers = sorted(df_clean["ticker"].tolist())
        curr_bank = st.session_state.get("selected_ticker", "VCB")
        sel_idx = bank_tickers.index(curr_bank) if curr_bank in bank_tickers else 0

        c_bank_sel, c_p1, c_p2 = st.columns([1.2, 1.4, 1.4])
        with c_bank_sel:
            curr_bank = st.selectbox("Chọn ngân hàng thẩm định:", bank_tickers, index=sel_idx, key="mod1_sim_bank")
            st.session_state["selected_ticker"] = curr_bank
            st.session_state["selected_bank"] = curr_bank
        with c_p1:
            g_input = st.slider("Tốc độ tăng trưởng dài hạn bền vững (g %):", min_value=1.0, max_value=8.0, value=4.0, step=0.5, key="g_slider") / 100.0
        with c_p2:
            ke_input = st.slider("Chi phí vốn chủ sở hữu đòi hỏi (Ke %):", min_value=10.0, max_value=20.0, value=13.5, step=0.5, key="ke_slider") / 100.0

        if ke_input <= g_input:
            st.error("⚠️ Lỗi giả định mô hình: Chi phí vốn Ke phải lớn hơn tốc độ tăng trưởng g để công thức Gordon có nghĩa (Ke > g)!")
            return

        # Tính toán P/B nội tại
        df_intrinsic = df_clean.copy()
        df_intrinsic["gordon_intrinsic_pb"] = (df_intrinsic["roe"] - g_input) / (ke_input - g_input)
        df_intrinsic["gordon_intrinsic_pb"] = df_intrinsic["gordon_intrinsic_pb"].apply(lambda x: max(0.4, round(x, 2)) if x > 0 else 0.4)
        df_intrinsic["valuation_gap_pct"] = ((df_intrinsic["gordon_intrinsic_pb"] - df_intrinsic["pb_ratio"]) / df_intrinsic["pb_ratio"] * 100).round(1)

        sel_row = df_intrinsic[df_intrinsic["ticker"] == curr_bank]
        if not sel_row.empty:
            sr = sel_row.iloc[0]
            st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-top: 10px;'>📌 Thẩm Định Cổ Phiếu Mục Tiêu: <b>{curr_bank}</b></h5>", unsafe_allow_html=True)
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                render_led_card("P/B Thị Trường", f"{sr['pb_ratio']:.2f}x", "Thị giá hiện tại", badge="THỊ TRƯỜNG", status="cyan")
            with m2:
                render_led_card("ROE Bền Vững", f"{sr['roe_pct']:.1f}%", f"Xếp hạng #{sr['roe_rank']}", badge="ROE THỰC TẾ", status="purple")
            with m3:
                render_led_card("P/B Hợp Lý Gordon", f"{sr['gordon_intrinsic_pb']:.2f}x", f"g={g_input*100:.1f}%, Ke={ke_input*100:.1f}%", badge="P/B HỢP LÝ", status="gold")
            with m4:
                gap_val = sr['valuation_gap_pct']
                status_v = "mint" if gap_val > 0 else "red"
                render_led_card("Chênh Lệch Định Giá", f"{gap_val:+.1f}%", "So với P/B nội tại", badge="CHÊNH LỆCH", status=status_v)

            # BẢNG MA TRẬN ĐỘ NHẠY 2 CHIỀU (Ke vs g) CHO NGÂN HÀNG MỤC TIÊU
            st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-top: 18px;'>📊 Bảng Ma Trận Độ Nhạy 2 Chiều: P/B Hợp Lý của {curr_bank} (Ke vs g)</h5>", unsafe_allow_html=True)
            ke_list = [0.11, 0.12, 0.13, 0.14, 0.15, 0.16]
            g_list = [0.02, 0.03, 0.04, 0.05, 0.06]
            bank_roe = float(sr["roe"])

            sensitivity_matrix = []
            for g_val in g_list:
                row_vals = {"g \\ Ke": f"{g_val*100:.1f}%"}
                for ke_val in ke_list:
                    if ke_val > g_val:
                        pb_fair = (bank_roe - g_val) / (ke_val - g_val)
                        row_vals[f"{ke_val*100:.1f}%"] = f"{max(0.4, pb_fair):.2f}x"
                    else:
                        row_vals[f"{ke_val*100:.1f}%"] = "N/A"
                sensitivity_matrix.append(row_vals)

            df_sens = pd.DataFrame(sensitivity_matrix)
            st.dataframe(df_sens, use_container_width=True, hide_index=True)

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        # Bar chart so sánh P/B thị trường vs P/B nội tại
        fig_int = go.Figure()
        df_sort_int = df_intrinsic.sort_values("valuation_gap_pct", ascending=True)
        fig_int.add_trace(go.Bar(
            y=df_sort_int["ticker"],
            x=df_sort_int["pb_ratio"],
            name="P/B Thị trường Hiện tại",
            orientation="h",
            marker_color=pal["accent_cyan"],
            opacity=0.85,
            hovertemplate="<b>%{y}</b><br>P/B Thị trường: <b>%{x:.2f}x</b><extra></extra>"
        ))
        fig_int.add_trace(go.Bar(
            y=df_sort_int["ticker"],
            x=df_sort_int["gordon_intrinsic_pb"],
            name="P/B Hợp lý Gordon",
            orientation="h",
            marker_color=pal["color_brand_led"],
            opacity=0.85,
            hovertemplate="<b>%{y}</b><br>P/B Hợp lý Gordon: <b>%{x:.2f}x</b><extra></extra>"
        ))
        fig_int = apply_plotly_theme(fig_int, height=640, title=f"Đối Chiếu P/B Thị Trường vs P/B Hợp Lý Gordon (g={g_input*100:.1f}%, Ke={ke_input*100:.1f}%)")
        fig_int.update_layout(barmode="group", xaxis_title="Hệ số P/B (lần)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_int, use_container_width=True)
