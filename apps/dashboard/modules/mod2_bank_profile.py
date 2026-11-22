"""
===================================================================================
MODULE 2: HỒ SƠ NGÂN HÀNG TOÀN DIỆN (BANK FUNDAMENTAL PROFILE)
Path: apps/dashboard/modules/mod2_bank_profile.py
Tái cấu trúc theo Báo cáo Phản biện ChatGPT 19/11/2026:
  - Hợp nhất 4 khía cạnh của một ngân hàng vào MỘT MÀN HÌNH DUY NHẤT:
    * Tab 1: An Toàn Vốn & Chất Lượng Tài Sản (Capital & Asset Quality)
    * Tab 2: Tín Dụng & Thanh Khoản (Funding & Credit Dynamics)
    * Tab 3: Chất Lượng Lợi Nhuận & Dự Phòng (Earnings Quality & Provisions)
    * Tab 4: Quản Trị Doanh Nghiệp (Corporate Governance)
  - Sửa đổi LDR: Phân biệt Analytical LDR vs Quy định pháp lý (TT22 và TT50)
  - Sửa đổi CAMELS: Đổi tên thành CAMELS-inspired Analytical Score, sửa trục S
  - Sửa đổi Waterfall: Phân rã chuẩn kế toán TOI -> OPEX -> PPOP -> Provision -> PBT -> Tax -> NPAT
  - Tra cứu sâu: Bảng BCTC 14 cột đưa vào Expander tầng 3
===================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.services.query_service import (
    get_all_banks,
    get_available_quarter_periods,
    get_camels_radar_data,
    get_camels_peer_comparison,
    get_credit_growth_dynamics,
    get_earnings_quality_breakdown,
    get_bank_shareholders,
    get_bank_officers,
    get_bank_subsidiaries,
    get_technical_ohlcv_data,
    get_macro_market_correlation,
    get_financial_statement_notes,
    get_real_bctc_pdfs,
)
from dashboard.common_theme import (
    apply_plotly_theme, render_led_card, get_theme_palette,
)


def render_bank_profile():
    pal = get_theme_palette()

    # 1. BỘ CHỌN TOÀN CỤC CHO HỒ SƠ NGÂN HÀNG (UNIFIED BANK & PERIOD HEADER)
    df_banks = get_all_banks()
    if df_banks.empty:
        st.warning("Chưa có danh bạ ngân hàng trong cơ sở dữ liệu.")
        return

    bank_list = df_banks["ticker"].tolist()
    curr_ticker = st.session_state.get("selected_ticker") or st.session_state.get("selected_bank", "VCB")
    default_idx = bank_list.index(curr_ticker) if curr_ticker in bank_list else 0

    # Header Card định vị hồ sơ ngân hàng
    st.html(f"""
        <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 5px solid {pal['accent_cyan']}; border-radius: 12px; padding: 18px 22px; margin-bottom: 18px; box-shadow: 0 2px 10px {pal['shadow_color']};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <div style="font-size: 11px; font-weight: 800; color: {pal['accent_cyan']}; text-transform: uppercase; letter-spacing: 1.2px;">
                    🏛️ PHÂN HỆ 03 • HỒ SƠ NGÂN HÀNG TOÀN DIỆN (BANK FUNDAMENTAL PROFILE)
                </div>
                <span style="background: rgba(76, 201, 240, 0.08); color: {pal['accent_cyan']}; border: 1px solid {pal['border_color']}; padding: 3px 10px; border-radius: 5px; font-size: 11px; font-weight: 800;">
                    IN-DEPTH DUE DILIGENCE
                </span>
            </div>
            <div style="font-size: 18px; font-weight: 800; color: {pal['text_heading']}; margin-top: 2px; letter-spacing: -0.2px;">
                Thẩm Định Nền Tảng Tài Chính, Động Lực Tín Dụng & Chất Lượng Lợi Nhuận
            </div>
            <div style="font-size: 12.5px; color: {pal['text_muted']}; margin-top: 4px; line-height: 1.55;">
                Tổng hợp 4 lát cắt phân tích của ngân hàng mục tiêu: <b>An toàn vốn & Chất lượng tài sản</b>, <b>Động lực tín dụng & Trần thanh khoản LDR</b>, <b>Chất lượng lợi nhuận PPOP & Chi phí dự phòng</b>, và <b>Cơ cấu quản trị sở hữu</b>.
            </div>
        </div>
    """)

    # Hàng điều khiển chọn ngân hàng và kỳ báo cáo
    c_sel_bank, c_sel_period, c_bank_badge = st.columns([1.2, 1.2, 2.0])
    with c_sel_bank:
        selected_ticker = st.selectbox("Chọn Ngân hàng phân tích:", bank_list, index=default_idx, key="bp_bank_select")
        st.session_state["selected_ticker"] = selected_ticker
        st.session_state["selected_bank"] = selected_ticker

    with c_sel_period:
        available_periods = get_available_quarter_periods()
        selected_period = st.selectbox("Chọn Kỳ BCTC:", ["Kỳ Mới Nhất"] + available_periods, key="bp_period_select")

    bank_meta = df_banks[df_banks["ticker"] == selected_ticker].iloc[0]
    with c_bank_badge:
        st.markdown(f"""
            <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-radius: 8px; padding: 7px 14px; margin-top: 24px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <b style="color: {pal['color_brand_led']}; font-size: 15px;">{selected_ticker}</b> — <span style="font-size: 12.5px; color: {pal['text_heading']}; font-weight: 600;">{bank_meta.get('short_name', '')}</span>
                </div>
                <div style="display: flex; gap: 6px;">
                    <span style="background: rgba(37, 99, 235, 0.1); border: 1px solid {pal['border_color']}; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700; color: {pal['color_brand_led']};">{bank_meta.get('tier_group', 'TIER')}</span>
                    <span style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700; color: #10B981;">{bank_meta.get('listing_exchange', 'HOSE')}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 2. BỐI CẢNH 5 TABS HỒ SƠ NGÂN HÀNG & THUYẾT MINH KIỂM TOÁN
    tab_capital, tab_credit, tab_earnings, tab_gov, tab_notes = st.tabs([
        "🛡️ 1. An Toàn Vốn & Tài Sản (CAMELS)",
        "📈 2. Tín Dụng & Thanh Khoản (LDR)",
        "💰 3. Chất Lượng Lợi Nhuận (PPOP)",
        "👥 4. Quản Trị & Ban Lãnh Đạo",
        "📑 5. Thuyết Minh BCTC & Báo Cáo Kiểm Toán",
    ])

    # =========================================================================
    # TAB 1: AN TOÀN VỐN & CHẤT LƯỢNG TÀI SẢN (CAMELS-INSPIRED)
    # =========================================================================
    with tab_capital:
        st.markdown(f"#### 🛡️ Thẻ Điểm Vận Hành & Khung Phân Tích Tham Khảo CAMELS: {selected_ticker}")

        if selected_period == "Kỳ Mới Nhất":
            target_df = get_camels_radar_data(selected_ticker)
            peer_df = get_camels_peer_comparison()
        else:
            try:
                y = int(selected_period[:4])
                q = int(selected_period[-1])
                target_df = get_camels_radar_data(selected_ticker, y, q)
                peer_df = get_camels_peer_comparison(y, q)
            except Exception:
                target_df = get_camels_radar_data(selected_ticker)
                peer_df = get_camels_peer_comparison()

        if target_df.empty:
            st.warning(f"Chưa có dữ liệu tỷ số tài chính cho {selected_ticker} trong kỳ này.")
        else:
            numeric_cols = [
                "c_capital_car", "a_asset_quality_npl", "a_provision_llr",
                "m_management_cir", "e_earnings_roe", "e_earnings_nim",
                "l_liquidity_ldr", "l_liquidity_casa"
            ]
            for col in numeric_cols:
                if col in target_df.columns:
                    target_df[col] = pd.to_numeric(target_df[col], errors="coerce")
                if col in peer_df.columns:
                    peer_df[col] = pd.to_numeric(peer_df[col], errors="coerce")

            target_row = target_df.iloc[0]

            # 5 KPI Cards Trụ Cột
            k1, k2, k3, k4, k5 = st.columns(5)
            with k1:
                car_val = target_row["c_capital_car"]
                car_cf = bool(target_row.get("is_car_carried_forward", False))
                car_str = f"{car_val * 100:.1f}%" if pd.notnull(car_val) and car_val > 0 else "N/A"
                car_sub = "TT14/2025: ≥ 8.0% (Kỳ bán niên gần nhất)" if car_cf else "TT14/2025: ≥ 8.0%"
                render_led_card("Hệ Số CAR", car_str, car_sub, "AN TOÀN VỐN", "cyan")
            with k2:
                npl_val = target_row["a_asset_quality_npl"]
                npl_str = f"{npl_val * 100:.2f}%" if pd.notnull(npl_val) else "N/A"
                status_npl = "mint" if (pd.notnull(npl_val) and npl_val <= 0.03) else "red"
                render_led_card("Tỷ Lệ NPL", npl_str, "Trần tham chiếu: 3.0%", "CHẤT LƯỢNG TÀI SẢN", status_npl)
            with k3:
                llr_val = target_row.get("a_provision_llr")
                llr_str = f"{llr_val * 100:.1f}%" if pd.notnull(llr_val) else "N/A"
                render_led_card("Bao Nợ Xấu LLR", llr_str, "Bộ đệm dự phòng / NPL", "DỰ PHÒNG RỦI RO", "purple")
            with k4:
                cir_val = target_row["m_management_cir"]
                cir_str = f"{cir_val * 100:.1f}%" if pd.notnull(cir_val) else "N/A"
                render_led_card("Tỷ Lệ CIR", cir_str, "Chi phí / Thu nhập", "HIỆU QUẢ HOẠT ĐỘNG", "pink")
            with k5:
                casa_val = target_row.get("l_liquidity_casa")
                casa_str = f"{casa_val * 100:.1f}%" if pd.notnull(casa_val) else "N/A"
                render_led_card("Tỷ Lệ CASA", casa_str, "Tiền gửi không kỳ hạn", "NGUỒN VỐN RẺ", "gold")

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # CẢNH BÁO PHƯƠNG PHÁP LUẬN VỀ CAMELS VÀ NỢ XẤU
            st.markdown(f"""
                <div style='background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 4px solid {pal['color_brand_led']}; border-radius: 6px; padding: 12px 16px; margin-bottom: 14px; font-size: 12.5px; color: {pal['text_body']}; line-height: 1.6;'>
                    <b>Ghi chú phương pháp luận phân tích vốn & tài sản:</b><br>
                    • <b>Khung phân tích CAMELS tự xây dựng:</b> Đây là bộ điểm chuẩn hóa (0–100) phục vụ nghiên cứu nội bộ của chuyên viên phân tích, không phải là kết quả xếp hạng thanh tra/giám sát chính thức của Ngân hàng Nhà nước.<br>
                    • <b>Tỷ lệ an toàn vốn (CAR):</b> Khung quy định hiện hành theo Thông tư 14/2025/TT-NHNN (hiệu lực 15/09/2025) quy định tỷ lệ an toàn vốn tối thiểu là 8%, đồng thời yêu cầu tỷ lệ vốn Cấp 1 tối thiểu 6% và vốn Vốn chủ sở hữu cấp 1 (CET1) tối thiểu 4.5%. Dữ liệu hiển thị là số liệu công bố hợp nhất.<br>
                    • <b>Đánh giá chất lượng nợ:</b> Tỷ lệ NPL &lt; 3% không đồng nghĩa an toàn tuyệt đối. Chuyên viên cần đối chiếu tỷ lệ bao phủ nợ xấu (LLR), xu hướng nợ nhóm 2 (nợ cần chú ý) và các khoản nợ tái cơ cấu để nhận diện rủi ro nợ xấu tiềm ẩn.
                </div>
            """, unsafe_allow_html=True)

            c_radar, c_npl_bar = st.columns([1, 1])

            # Tính toán điểm chuẩn hóa cho radar
            def compute_camels_scores(row: pd.Series) -> dict:
                car = float(row.get("c_capital_car", 0.08)) if pd.notnull(row.get("c_capital_car")) else 0.08
                score_c = max(10.0, min(100.0, 40.0 + ((car - 0.08) / 0.10) * 60.0)) if car >= 0.08 else max(5.0, (car / 0.08) * 35.0)

                npl = float(row.get("a_asset_quality_npl", 0.02)) if pd.notnull(row.get("a_asset_quality_npl")) else 0.02
                llr = abs(float(row.get("a_provision_llr", 0.80))) if pd.notnull(row.get("a_provision_llr")) else 0.80
                score_npl = float(np.clip(100.0 - (npl / 0.045) * 90.0, 5.0, 100.0))
                score_llr = float(np.clip((llr - 0.30) / 1.70 * 100.0, 10.0, 100.0))
                score_a = round(0.70 * score_npl + 0.30 * score_llr, 1)

                cir = abs(float(row.get("m_management_cir", 0.38))) if pd.notnull(row.get("m_management_cir")) else 0.38
                score_m = float(np.clip(100.0 - ((cir - 0.25) / 0.40) * 90.0, 10.0, 100.0))

                roe = float(row.get("e_earnings_roe", 0.15)) if pd.notnull(row.get("e_earnings_roe")) else 0.15
                nim = float(row.get("e_earnings_nim", 0.03)) if pd.notnull(row.get("e_earnings_nim")) else 0.03
                score_roe = float(np.clip((roe - 0.04) / 0.21 * 100.0, 5.0, 100.0))
                score_nim = float(np.clip((nim - 0.015) / 0.040 * 100.0, 5.0, 100.0))
                score_e = round(0.60 * score_roe + 0.40 * score_nim, 1)

                ldr = float(row.get("l_liquidity_ldr", 0.80)) if pd.notnull(row.get("l_liquidity_ldr")) else 0.80
                casa = float(row.get("l_liquidity_casa", 0.20)) if pd.notnull(row.get("l_liquidity_casa")) else 0.20
                score_ldr = float(20.0 if ldr > 0.85 else np.clip(100.0 - ((ldr - 0.65) / 0.25) * 60.0, 30.0, 100.0))
                score_casa = float(np.clip((casa - 0.05) / 0.40 * 100.0, 10.0, 100.0))
                score_l = round(0.60 * score_ldr + 0.40 * score_casa, 1)

                return {"C": round(score_c, 1), "A": score_a, "M": round(score_m, 1), "E": score_e, "L": score_l}

            target_tier = target_row.get("tier_group")
            tier_label = str(target_tier) if pd.notnull(target_tier) else "Cùng Nhóm"
            df_tier_peers = peer_df[peer_df["tier_group"] == target_tier] if "tier_group" in peer_df.columns else pd.DataFrame()

            if len(df_tier_peers) >= 2:
                peer_bench = df_tier_peers.median(numeric_only=True)
                peer_legend = f"Trung vị Nhóm {tier_label} ({len(df_tier_peers)} NH)"
            else:
                peer_bench = peer_df.median(numeric_only=True)
                peer_legend = "Trung vị Toàn ngành (27 NH)"

            sc_t = compute_camels_scores(target_row)
            sc_p = compute_camels_scores(peer_bench)

            # Tính Beta giá cổ phiếu 252 phiên
            score_s_target = 65.0
            score_s_peer = 60.0
            try:
                df_p_b = get_technical_ohlcv_data(selected_ticker, days=252)
                df_m_b = get_macro_market_correlation(days=252, ticker=selected_ticker)
                if not df_p_b.empty and not df_m_b.empty:
                    df_p_b["ret"] = pd.to_numeric(df_p_b["return_daily_pct"], errors="coerce")
                    df_m_b["vni"] = pd.to_numeric(df_m_b["vnindex_close"], errors="coerce")
                    df_m_b["vni_ret"] = df_m_b["vni"].pct_change(fill_method=None)
                    m_b = df_p_b[["trading_date", "ret"]].merge(df_m_b[["trading_date", "vni_ret"]], on="trading_date").dropna()
                    if len(m_b) >= 30:
                        cov_v = m_b[["ret", "vni_ret"]].cov().iloc[0, 1]
                        var_v = m_b["vni_ret"].var()
                        if var_v > 0 and pd.notnull(cov_v):
                            beta_v = float(cov_v / var_v)
                            score_s_target = float(min(max(100 - abs(beta_v - 0.9) / 1.2 * 100, 15), 100))
            except Exception:
                pass

            categories = [
                "C · Vốn (CAR)",
                "A · Tài sản (NPL/LLR)",
                "M · Vận hành (CIR)",
                "E · Sinh lời (ROE/NIM)",
                "L · Thanh khoản (LDR/CASA)",
                "S · Nhạy TT (Beta)",
            ]

            with c_radar:
                st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-bottom: 8px;'>🕸️ Đa Giác Năng Lực CAMELS vs {peer_legend}</h5>", unsafe_allow_html=True)
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=[sc_t["C"], sc_t["A"], sc_t["M"], sc_t["E"], sc_t["L"], score_s_target],
                    theta=categories,
                    fill='toself',
                    name=f'{selected_ticker} ({tier_label})',
                    line=dict(color=pal["color_brand"], width=2.5),
                    fillcolor='rgba(37, 99, 235, 0.20)'
                ))
                fig_radar.add_trace(go.Scatterpolar(
                    r=[sc_p["C"], sc_p["A"], sc_p["M"], sc_p["E"], sc_p["L"], score_s_peer],
                    theta=categories,
                    fill='toself',
                    name=peer_legend,
                    line=dict(color=pal["color_warn"], width=2, dash='dot'),
                    fillcolor='rgba(217, 119, 6, 0.12)'
                ))
                fig_radar.update_layout(
                    paper_bgcolor=pal["bg_card"],
                    plot_bgcolor=pal["bg_card"],
                    font=dict(color=pal["text_body"], size=11),
                    polar=dict(
                        bgcolor="rgba(0,0,0,0)",
                        radialaxis=dict(visible=True, range=[0, 100], color=pal["chart_tick"], gridcolor=pal["grid_color"]),
                        angularaxis=dict(color=pal["chart_title"], gridcolor=pal["grid_color"])
                    ),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.18, xanchor="center", x=0.5),
                    height=450,
                    margin=dict(l=70, r=70, t=35, b=55)
                )
                st.plotly_chart(fig_radar, use_container_width=True)

            with c_npl_bar:
                st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-bottom: 8px;'>📊 Tỷ Lệ Nợ Xấu (NPL %) Toàn Ngành</h5>", unsafe_allow_html=True)
                npl_c = "a_asset_quality_npl" if "a_asset_quality_npl" in peer_df.columns else "npl"
                npl_sorted = peer_df.dropna(subset=[npl_c]).sort_values(npl_c, ascending=True).copy()
                npl_sorted["NPL_pct"] = (npl_sorted[npl_c] * 100).round(2)
                npl_sorted["bar_color"] = npl_sorted["ticker"].apply(lambda x: pal["color_brand_led"] if x == selected_ticker else pal["chart_bar_peer"])

                fig_npl = px.bar(
                    npl_sorted,
                    x="ticker",
                    y="NPL_pct",
                    text="NPL_pct",
                    labels={"NPL_pct": "Tỷ lệ NPL (%)", "ticker": "Ngân hàng"},
                    height=450,
                )
                fig_npl.update_traces(marker_color=npl_sorted["bar_color"], textposition="outside", textfont=dict(size=10, color=pal["chart_title"]))
                fig_npl.add_hline(y=3.0, line_dash="dash", line_color=pal["color_down"], line_width=1.5, annotation_text="Ngưỡng tham chiếu NHNN: 3.0%", annotation_position="top right")
                fig_npl = apply_plotly_theme(fig_npl, height=450, title="Tỷ Lệ Nợ Xấu NPL (%) Của 27 Ngân Hàng")
                st.plotly_chart(fig_npl, use_container_width=True)

    # =========================================================================
    # TAB 2: TÍN DỤNG & THANH KHOẢN (LDR DYNAMICS)
    # =========================================================================
    with tab_credit:
        st.markdown(f"#### 📈 Động Lực Tín Dụng, Tăng Trưởng Huy Động & Kiểm Soát Thanh Khoản: {selected_ticker}")

        df_growth = get_credit_growth_dynamics(selected_ticker, limit_quarters=16)
        if df_growth.empty:
            st.warning(f"Chưa có dữ liệu tăng trưởng tín dụng cho {selected_ticker}.")
        else:
            latest_g = df_growth.iloc[-1]
            gk1, gk2, gk3, gk4 = st.columns(4)
            with gk1:
                lg_v = latest_g.get("loan_growth_yoy")
                lg_s = f"{lg_v * 100:+.2f}%" if pd.notnull(lg_v) else "N/A"
                render_led_card("Tín Dụng YoY", lg_s, "Tăng trưởng cho vay", "CHO VAY KHÁCH HÀNG", "cyan")
            with gk2:
                dg_v = latest_g.get("deposit_growth_yoy")
                dg_s = f"{dg_v * 100:+.2f}%" if pd.notnull(dg_v) else "N/A"
                render_led_card("Huy Động YoY", dg_s, "Tăng trưởng tiền gửi", "TIỀN GỬI KHÁCH HÀNG", "purple")
            with gk3:
                gap_v = latest_g.get("credit_deposit_gap")
                gap_s = f"{gap_v * 100:+.2f}%" if pd.notnull(gap_v) else "N/A"
                st_gap = "red" if (gap_v and gap_v > 0.05) else ("mint" if (gap_v and gap_v < -0.02) else "gold")
                render_led_card("Chênh Lệch Tín Dụng - Tiền Gửi", gap_s, "Khoảng cách tăng trưởng", "KHOẢNG CÁCH THANH KHOẢN", st_gap)
            with gk4:
                ldr_s = latest_g.get("ldr_simple")
                ldr_str = f"{ldr_s * 100:.1f}%" if pd.notnull(ldr_s) else "N/A"
                render_led_card("Tỷ Lệ LDR BCTC", ldr_str, "Dư nợ / Tiền gửi BCTC", "LDR PHÂN TÍCH", "mint")

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # CẢNH BÁO QUY ĐỊNH PHÁP LÝ CHUYỂN TIẾP VỀ LDR (THÔNG TƯ 22 VÀ THÔNG TƯ 50)
            st.markdown(f"""
                <div style='background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 4px solid {pal['color_warn']}; border-radius: 6px; padding: 12px 16px; margin-bottom: 14px; font-size: 12.5px; color: {pal['text_body']}; line-height: 1.6;'>
                    <b>Ghi chú quy chuẩn pháp lý và phân tích tỷ lệ LDR:</b><br>
                    • <b>Phân biệt tỷ lệ:</b> <i>Analytical LDR</i> là tỷ lệ phân tích đơn giản được tính bằng <b>Dư nợ cho vay / Tiền gửi khách hàng</b> lấy trực tiếp từ BCTC. Tỷ lệ này khác với tỷ lệ tuân thủ pháp lý chính thức (Reported Regulatory LDR) do NHNN có quy định loại trừ và bổ sung các cấu phần nguồn vốn.<br>
                    • <b>Cơ chế chuyển tiếp pháp lý:</b><br>
                    - <i>Giai đoạn trước 01/12/2026:</i> Áp dụng theo Thông tư 22/2019/TT-NHNN (và các văn bản sửa đổi, bổ sung) với trần LDR tối đa là 85% đối với các ngân hàng chưa chuyển đổi sang cơ chế mới.<br>
                    - <i>Giai đoạn từ 01/12/2026:</i> Thông tư 50/2026/TT-NHNN bắt đầu có hiệu lực, thiết kế cơ chế tỷ lệ khả năng chi trả (LCR) và tỷ lệ nguồn vốn ổn định ròng (NSFR). Theo Điều 12 & 13, trần LDR tối đa được điều chỉnh lên mức 95% theo công thức mới khi áp dụng LCR/NSFR; trường hợp ngân hàng đạt 100% cả LCR và NSFR được miễn tuân thủ tỷ lệ LDR nhưng vẫn phải báo cáo theo quy định.<br>
                    • <b>Đánh giá khoảng chênh lệch (Credit Gap):</b> Khi tăng trưởng cho vay vượt huy động trên 5%, ngân hàng chịu áp lực gia tăng chi phí huy động vốn trên thị trường liên ngân hàng hoặc phát hành giấy tờ có giá.
                </div>
            """, unsafe_allow_html=True)

            # Biểu đồ chuỗi thời gian tăng trưởng tín dụng vs huy động
            fig_gap = go.Figure()
            fig_gap.add_trace(go.Scatter(
                x=df_growth["period_name"],
                y=df_growth["loan_growth_yoy"] * 100,
                mode="lines+markers",
                name="Tăng trưởng Dư nợ (YoY %)",
                line=dict(color=pal["accent_cyan"], width=3),
                marker=dict(size=6),
            ))
            fig_gap.add_trace(go.Scatter(
                x=df_growth["period_name"],
                y=df_growth["deposit_growth_yoy"] * 100,
                mode="lines+markers",
                name="Tăng trưởng Tiền gửi (YoY %)",
                line=dict(color=pal["color_brand_led"], width=3, dash="dash"),
                marker=dict(size=6),
            ))
            colors_gap = [pal["color_down"] if g > 0.05 else (pal["color_up"] if g < -0.02 else pal["color_warn"]) for g in df_growth["credit_deposit_gap"].fillna(0)]
            fig_gap.add_trace(go.Bar(
                x=df_growth["period_name"],
                y=df_growth["credit_deposit_gap"] * 100,
                name="Credit-Deposit Gap (%)",
                marker_color=colors_gap,
                opacity=0.45,
            ))
            fig_gap = apply_plotly_theme(fig_gap, height=440, title=f"Diễn Biến Tăng Trưởng Dư Nợ vs Tiền Gửi & Credit Gap: {selected_ticker}")
            fig_gap.update_layout(yaxis_title="Tăng trưởng cùng kỳ (%)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_gap, use_container_width=True)

    # =========================================================================
    # TAB 3: CHẤT LƯỢNG LỢI NHUẬN & DỰ PHÒNG (EARNINGS QUALITY WATERFALL)
    # =========================================================================
    with tab_earnings:
        st.markdown(f"#### 💰 Bóc Tách Chất Lượng Lợi Nhuận & Chi Phí Dự Phòng: {selected_ticker}")

        df_eq = get_earnings_quality_breakdown(selected_ticker, limit_quarters=16)
        if df_eq.empty:
            st.warning(f"Chưa có dữ liệu phân rã kết quả kinh doanh cho {selected_ticker}.")
        else:
            latest_eq = df_eq.iloc[-1]
            ek1, ek2, ek3, ek4, ek5 = st.columns(5)
            with ek1:
                toi_val = latest_eq.get("toi", 0)
                render_led_card("Tổng Thu Nhập (TOI)", f"{toi_val / 1e9:,.0f} Tỷ", "Doanh thu hoạt động", "TỔNG THU NHẬP", "purple")
            with ek2:
                ppop_val = latest_eq.get("ppop", 0)
                render_led_card("Lợi Nhuận PPOP", f"{ppop_val / 1e9:,.0f} Tỷ", "LN thuần trước dự phòng", "LỢI NHUẬN CỐT LÕI", "cyan")
            with ek3:
                prov_val = latest_eq.get("provision_expense", 0)
                render_led_card("Chi Phí Dự Phòng", f"{prov_val / 1e9:,.0f} Tỷ", "Trích lập rủi ro trong kỳ", "TRÍCH LẬP DỰ PHÒNG", "pink")
            with ek4:
                cc_val = latest_eq.get("credit_cost_ratio")
                cc_str = f"{cc_val * 100:.2f}%" if pd.notnull(cc_val) else "N/A"
                render_led_card("Chi Phí Tín Dụng", cc_str, "Chi phí dự phòng / Dư nợ", "CHI PHÍ TÍN DỤNG", "mint")
            with ek5:
                npat_val = latest_eq.get("npat", 0)
                render_led_card("Lợi Nhuận Ròng (NPAT)", f"{npat_val / 1e9:,.0f} Tỷ", f"ROE: {latest_eq.get('roe', 0)*100:.1f}%", "LỢI NHUẬN RÒNG", "gold")

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # WATERFALL CHART PHÂN RÃ THU NHẬP VÀ LỢI NHUẬN ĐẦY ĐỦ CHUẨN KẾ TOÁN
            st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-bottom: 8px;'>🌊 Biểu Đồ Thác Nước (Waterfall): Phân Rã Cơ Cấu Thu Nhập & Lợi Nhuận ({latest_eq['period_name']})</h5>", unsafe_allow_html=True)

            nii_bn = float(latest_eq.get("nii", 0)) / 1e9
            nfi_bn = float(latest_eq.get("nfi", 0)) / 1e9
            fx_bn = float(latest_eq.get("net_gain_fx", 0)) / 1e9
            sec_bn = float(latest_eq.get("net_gain_securities", 0)) / 1e9
            res_bn = float(latest_eq.get("other_operating_income_residual", 0)) / 1e9
            opex_bn = -abs(float(latest_eq.get("opex", 0)) / 1e9)
            prov_bn = -abs(float(latest_eq.get("provision_expense", 0)) / 1e9)
            pbt_bn = float(latest_eq.get("pbt", (toi_val + opex_bn*1e9 + prov_bn*1e9))) / 1e9
            npat_bn = float(latest_eq.get("npat", 0)) / 1e9
            tax_bn = -abs(pbt_bn - npat_bn) if pbt_bn > npat_bn else 0.0

            fig_wf = go.Figure(go.Waterfall(
                name="Phân rã Thu nhập & Lợi nhuận",
                orientation="v",
                measure=["relative", "relative", "relative", "relative", "relative", "total", "relative", "total", "relative", "total", "relative", "total"],
                x=[
                    "Thu nhập Lãi (NII)", "Dịch vụ (NFI)", "Ngoại hối (FX)", "Chứng khoán", "Thu khác",
                    "Tổng Doanh Thu (TOI)",
                    "Chi phí HĐ (OPEX)",
                    "Lợi nhuận PPOP",
                    "Chi phí Dự phòng",
                    "LN Trước Thuế (PBT)",
                    "Thuế TNDN",
                    "LN Ròng (NPAT)"
                ],
                textposition="outside",
                text=[
                    f"+{nii_bn:,.0f}", f"+{nfi_bn:,.0f}", f"{fx_bn:+,.0f}", f"{sec_bn:+,.0f}", f"{res_bn:+,.0f}",
                    f"={toi_val/1e9:,.0f}", f"{opex_bn:,.0f}", f"={ppop_val/1e9:,.0f}", f"{prov_bn:,.0f}",
                    f"={pbt_bn:,.0f}", f"{tax_bn:,.0f}", f"={npat_bn:,.0f}"
                ],
                y=[nii_bn, nfi_bn, fx_bn, sec_bn, res_bn, 0, opex_bn, 0, prov_bn, 0, tax_bn, 0],
                connector={"line": {"color": pal["border_color"], "width": 1.5}},
                decreasing={"marker": {"color": pal["color_down"]}},
                increasing={"marker": {"color": pal["color_up"]}},
                totals={"marker": {"color": pal["color_brand"]}}
            ))
            fig_wf = apply_plotly_theme(fig_wf, height=480, title=f"Phân Rã Thu Nhập Hoạt Động & Lợi Nhuận: {selected_ticker} (Đơn vị: Tỷ VND)")
            fig_wf.update_layout(yaxis_title="Giá trị (Tỷ VND)", showlegend=False)
            st.plotly_chart(fig_wf, use_container_width=True)

            # Biểu đồ chuỗi thời gian Credit Cost
            c_cc1, c_cc2 = st.columns(2)
            with c_cc1:
                fig_cc = go.Figure()
                fig_cc.add_trace(go.Scatter(
                    x=df_eq["period_name"],
                    y=df_eq["credit_cost_ratio"] * 100,
                    mode="lines+markers",
                    name="Credit Cost Ratio (%)",
                    line=dict(color=pal["accent_pink"], width=2.5),
                    marker=dict(size=6),
                ))
                fig_cc = apply_plotly_theme(fig_cc, height=360, title=f"Xu Hướng Chi Phí Tín Dụng Thường Niên (Credit Cost %)")
                fig_cc.update_layout(yaxis_title="Credit Cost (% / Dư nợ)")
                st.plotly_chart(fig_cc, use_container_width=True)

            with c_cc2:
                fig_non_int = go.Figure()
                fig_non_int.add_trace(go.Bar(x=df_eq["period_name"], y=df_eq["nfi"] / 1e9, name="Dịch vụ (NFI)", marker_color=pal["accent_cyan"]))
                fig_non_int.add_trace(go.Bar(x=df_eq["period_name"], y=df_eq["net_gain_fx"] / 1e9, name="Ngoại hối (FX)", marker_color=pal["color_brand_led"]))
                fig_non_int.add_trace(go.Bar(x=df_eq["period_name"], y=df_eq["net_gain_securities"] / 1e9, name="Chứng khoán", marker_color=pal["color_warn"]))
                fig_non_int.add_trace(go.Bar(x=df_eq["period_name"], y=df_eq["other_operating_income_residual"] / 1e9, name="Thu khác", marker_color=pal["color_up"]))
                fig_non_int.update_layout(barmode="stack", yaxis_title="Tỷ VND", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                fig_non_int = apply_plotly_theme(fig_non_int, height=360, title="Cơ Cấu Thu Nhập Ngoài Lãi (Non-Interest Income)")
                st.plotly_chart(fig_non_int, use_container_width=True)

    # =========================================================================
    # TAB 4: QUẢN TRỊ & BAN LÃNH ĐẠO (CORPORATE GOVERNANCE)
    # =========================================================================
    with tab_gov:
        st.markdown(f"#### 👥 Cơ Cấu Sở Hữu, Ban Lãnh Đạo & Công Ty Con: {selected_ticker}")

        df_sh = get_bank_shareholders(selected_ticker)
        df_off = get_bank_officers(selected_ticker)
        df_sub = get_bank_subsidiaries(selected_ticker)

        gk1, gk2, gk3 = st.columns(3)
        with gk1:
            render_led_card("Cổ Đông Lớn (>5%)", f"{len(df_sh)} tổ chức/cá nhân", "Nắm giữ chi phối", "CƠ CẤU CỔ ĐÔNG", "purple")
        with gk2:
            render_led_card("Ban Lãnh Đạo", f"{len(df_off)} thành viên", "HĐQT & Ban Điều Hành", "BAN LÃNH ĐẠO", "cyan")
        with gk3:
            render_led_card("Công Ty Con & Liên Kết", f"{len(df_sub)} đơn vị", "Hệ sinh thái tài chính", "CÔNG TY CON", "mint")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        cg1, cg2 = st.columns([1, 1])
        with cg1:
            st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-bottom: 8px;'>📋 Danh Sách Cổ Đông Lớn</h5>", unsafe_allow_html=True)
            if not df_sh.empty:
                cols = [c for c in ["shareholder_name", "ownership_pct", "quantity", "update_date"] if c in df_sh.columns]
                df_sh_disp = df_sh[cols].copy()
                if "ownership_pct" in df_sh_disp.columns:
                    df_sh_disp["ownership_pct"] = pd.to_numeric(df_sh_disp["ownership_pct"], errors="coerce").apply(
                        lambda x: f"{x*100:.2f}%" if pd.notnull(x) else "-"
                    )
                if "quantity" in df_sh_disp.columns:
                    df_sh_disp["quantity"] = pd.to_numeric(df_sh_disp["quantity"], errors="coerce").apply(
                        lambda x: f"{x:,.0f}" if pd.notnull(x) else "-"
                    )
                df_sh_disp = df_sh_disp.rename(columns={
                    "shareholder_name": "Tên Cổ Đông",
                    "ownership_pct": "Tỷ Lệ Sở Hữu",
                    "quantity": "Số Cổ Phần",
                    "update_date": "Ngày Cập Nhật"
                })
                st.dataframe(df_sh_disp, use_container_width=True, hide_index=True)
            else:
                st.info("Chưa có thông tin cổ đông lớn.")

            with cg2:
                st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-bottom: 8px;'>👔 Thành Viên Ban Điều Hành & HĐQT</h5>", unsafe_allow_html=True)
                if not df_off.empty:
                    df_off_disp = df_off[["officer_name", "position_title"]].copy()
                    df_off_disp = df_off_disp.rename(columns={"officer_name": "Họ và Tên", "position_title": "Chức Danh"})
                    st.dataframe(df_off_disp, use_container_width=True, hide_index=True)
                else:
                    st.info("Chưa có danh sách ban điều hành.")

            if not df_sub.empty:
                st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-top: 16px; margin-bottom: 8px;'>🏢 Hệ Sinh Thái Công Ty Con & Liên Kết ({len(df_sub)})</h5>", unsafe_allow_html=True)
                df_sub_disp = df_sub.copy()
                if "ownership_pct" in df_sub_disp.columns:
                    df_sub_disp["ownership_pct"] = pd.to_numeric(df_sub_disp["ownership_pct"], errors="coerce").apply(lambda x: f"{x*100:.1f}%" if pd.notnull(x) else "-")
                st.dataframe(df_sub_disp.rename(columns={"subsidiary_name": "Tên Công Ty Con / Liên Kết", "ownership_pct": "Tỷ Lệ Sở Hữu"}), use_container_width=True, hide_index=True)

    # =========================================================================
    # TAB 5: THUYẾT MINH BCTC & BÁO CÁO KIỂM TOÁN ĐỘC LẬP
    # =========================================================================
    with tab_notes:
        st.markdown(f"#### 📑 Thuyết Minh Báo Cáo Tài Chính & Báo Cáo Kiểm Toán Độc Lập: {selected_ticker}")
        st.markdown(f"""
            <div style='font-size: 13.5px; color: {pal["text_muted"]}; margin-bottom: 16px; line-height: 1.65;'>
                Dữ liệu bóc tách chuyên sâu từ <b>Thuyết minh BCTC và Báo cáo Kiểm toán độc lập</b> đã được chuẩn hóa qua đường ống trích xuất dữ liệu phi cấu trúc (Unstructured ETL Pipeline): 
                <b>Nợ nhóm 2</b> (chỉ báo sớm NPL hình thành), <b>nợ tái cơ cấu giữ nguyên nhóm nợ</b> theo Thông tư 02/2023 & Thông tư 06/2024, 
                <b>tỷ trọng tài sản bảo đảm là Bất động sản</b>, <b>danh mục Trái phiếu Doanh nghiệp</b>, <b>chất lượng lãi dự thu</b> và <b>ý kiến kiểm toán viên độc lập</b>.
            </div>
        """, unsafe_allow_html=True)

        notes_data = get_financial_statement_notes(selected_ticker)

        if notes_data:
            # 1. HÀNG THÔNG TIN KIỂM TOÁN VIÊN & VĂN BẢN GỐC
            a_col1, a_col2, a_col3 = st.columns([1.2, 1.8, 1.0])
            with a_col1:
                render_led_card("Đơn Vị Kiểm Toán", notes_data.get("auditor_name", "Kiểm toán độc lập"), f"Kỳ: {notes_data.get('period_name', '2026Q3')}", "ĐƠN VỊ KIỂM TOÁN", "cyan")
            with a_col2:
                op_text = notes_data.get("auditor_opinion", "Chấp nhận toàn phần")
                st_op = "mint" if "toàn phần" in op_text.lower() and "ngoại trừ" not in op_text.lower() else "gold"
                render_led_card("Ý Kiến Kiểm Toán", op_text, "Chuẩn mực kiểm toán Việt Nam (VSA)", "Ý KIẾN KIỂM TOÁN", st_op)
            with a_col3:
                pdf_link = notes_data.get("source_pdf_url", "")
                render_led_card("Chứng Từ Lưu Trữ", "BCTC DẤU ĐỎ", "Kho lưu trữ tài liệu SSC", "CHỨNG TỪ", "purple")

            st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

            # 2. BẢN TÓM TẮT ĐIỀU HÀNH THUYẾT MINH BCTC
            st.markdown(f"""
                <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 5px solid {pal['color_brand_led']}; border-radius: 12px; padding: 18px 22px; margin-bottom: 16px; box-shadow: 0 4px 16px {pal['shadow_color']};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 14px; font-weight: 800; color: {pal['text_heading']}; text-transform: uppercase; letter-spacing: 0.5px;">📑 Tóm Tắt Trọng Yếu Thuyết Minh & Kiểm Toán (Executive Summary)</span>
                        <span style="font-size: 12px; font-weight: 700; color: {pal['text_muted']};">Chuẩn hóa DWH</span>
                    </div>
                    <div style="font-size: 13.5px; line-height: 1.7; color: {pal['text_body']}; text-align: justify;">
                        {notes_data.get('executive_summary', '')}
                    </div>
                    {f'<div style="margin-top: 12px; border-top: 1px solid {pal["border_color"]}; padding-top: 8px;"><a href="{pdf_link}" target="_blank" style="font-size: 12.5px; font-weight: 700; color: {pal["accent_cyan"]}; text-decoration: none;">📎 Mở BCTC Kiểm toán PDF Dấu Đỏ Gốc (Toàn văn 80–120 trang) ↗</a></div>' if pdf_link else ''}
                </div>
            """, unsafe_allow_html=True)

            # 3. HAI CỘT: ĐIỂM SÁNG TÀI CHÍNH VS CỜ ĐỎ RỦI RO TRỌNG YẾU (RED FLAGS)
            rf_col1, rf_col2 = st.columns([1, 1.2])

            with rf_col1:
                st.markdown(f"<h5 style='color: {pal['color_up']}; margin-bottom: 10px;'>🌟 3 Điểm Sáng Tài Chính Nổi Bật</h5>", unsafe_allow_html=True)
                strengths = notes_data.get("key_strengths", [])
                if strengths:
                    for s in strengths:
                        st.markdown(f"""
                            <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 3.5px solid {pal['color_up']}; border-radius: 8px; padding: 14px 18px; margin-bottom: 10px; font-size: 13.5px; line-height: 1.65; color: {pal['text_body']};">
                                ✅ {s}
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Chưa có ghi nhận điểm sáng riêng biệt.")

            with rf_col2:
                st.markdown(f"<h5 style='color: {pal['color_down']}; margin-bottom: 10px;'>🚩 Cảnh Báo Trọng Yếu Tại Thuyết Minh & Kiểm Toán (Audit Matters)</h5>", unsafe_allow_html=True)
                red_flags = notes_data.get("red_flags", [])
                if red_flags:
                    for rf in red_flags:
                        r_level = str(rf.get("risk_level", "TRUNG BÌNH")).upper()
                        r_col = pal["color_down"] if "CAO" in r_level else (pal["color_warn"] if "TRUNG BÌNH" in r_level else pal["color_up"])
                        r_bg = "rgba(244, 63, 94, 0.12)" if "CAO" in r_level else ("rgba(245, 158, 11, 0.12)" if "TRUNG BÌNH" in r_level else "rgba(16, 185, 129, 0.12)")
                        r_title = rf.get("title", "")
                        r_desc = rf.get("description", "")
                        r_page = rf.get("page_reference", "")
                        r_cat = rf.get("category", "Rủi ro")

                        st.markdown(f"""
                            <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-size: 12px; font-weight: 800; color: {pal['text_muted']}; text-transform: uppercase;">🏷️ {r_cat}</span>
                                    <span style="font-size: 11.5px; font-weight: 800; color: {r_col}; background: {r_bg}; border: 1px solid {r_col}; padding: 2px 8px; border-radius: 4px;">{r_level}</span>
                                </div>
                                <div style="font-size: 14px; font-weight: 700; color: {pal['text_heading']}; margin-bottom: 6px;">
                                    {r_title}
                                </div>
                                <div style="font-size: 13.5px; line-height: 1.65; color: {pal['text_body']}; margin-bottom: 8px;">
                                    {r_desc}
                                </div>
                                {f'<div style="font-size: 12.5px; font-weight: 600; color: {pal["color_brand_led"]};">📍 Đối chiếu tài liệu gốc: {r_page}</div>' if r_page else ''}
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Chưa phát hiện vấn đề kiểm toán ngoại bảng trọng yếu.")

            # 4. BẢNG BÓC TÁCH THUYẾT MINH CHUYÊN SÂU (STRUCTURED NOTES)
            st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-top: 14px; margin-bottom: 10px;'>📊 Dữ Liệu Bóc Tách Thuyết Minh BCTC Ngoài Bảng Cân Đối</h5>", unsafe_allow_html=True)
            s_notes = notes_data.get("structured_notes", {})
            if s_notes:
                notes_rows = [
                    {"Khoản Mục Thuyết Minh Chuyên Sâu": "Nợ Nhóm 2 (Nợ cần chú ý - Chỉ báo sớm NPL)", "Giá Trị Bóc Tách Thuyết Minh": s_notes.get("group_2_loans_estimate", "Đang cập nhật"), "Mức Độ Trọng Yếu": "RẤT CAO"},
                    {"Khoản Mục Thuyết Minh Chuyên Sâu": "Tỷ Trọng Tài Sản Bảo Đảm Là Bất Động Sản (%)", "Giá Trị Bóc Tách Thuyết Minh": s_notes.get("real_estate_collateral_pct", "Đang cập nhật"), "Mức Độ Trọng Yếu": "CAO"},
                    {"Khoản Mục Thuyết Minh Chuyên Sâu": "Dư Nợ Trái Phiếu Doanh Nghiệp (TPDN)", "Giá Trị Bóc Tách Thuyết Minh": s_notes.get("corporate_bonds_exposure", "Đang cập nhật"), "Mức Độ Trọng Yếu": "CAO"},
                    {"Khoản Mục Thuyết Minh Chuyên Sâu": "Nợ Cơ Cấu Giữ Nguyên Nhóm Nợ (TT02/TT06)", "Giá Trị Bóc Tách Thuyết Minh": s_notes.get("restructured_loans_tt02", "Đang cập nhật"), "Mức Độ Trọng Yếu": "RẤT CAO"},
                    {"Khoản Mục Thuyết Minh Chuyên Sâu": "Chất Lượng Lãi Dự Thu & Khoản Phải Thu", "Giá Trị Bóc Tách Thuyết Minh": s_notes.get("accrued_interest_status", "Đang cập nhật"), "Mức Độ Trọng Yếu": "TRUNG BÌNH"}
                ]
                st.dataframe(pd.DataFrame(notes_rows), use_container_width=True, hide_index=True)
        else:
            st.markdown(f"""
                <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 4px solid {pal['accent_cyan']}; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px; font-size: 13px; color: {pal['text_body']}; line-height: 1.65;">
                    <b>📌 Minh Bạch Dữ Liệu Thuyết Minh PDF:</b> Toàn bộ tỷ số tài chính ở Tab 1–3 lấy từ <b>BCTC có cấu trúc đã kiểm định DQ2</b>. Dưới đây là <b>danh mục văn bản PDF BCTC & giải trình gốc thật</b> công bố trên Sở Giao Dịch / FiinGroup để chuyên viên bấm mở kiểm chứng trực tiếp (không sử dụng nội dung sinh tự động chưa qua kiểm tra PDF gốc).
                </div>
            """, unsafe_allow_html=True)
            df_pdfs = get_real_bctc_pdfs(selected_ticker, limit=15)
            if not df_pdfs.empty:
                for _, prow in df_pdfs.iterrows():
                    pdate = str(prow.get("full_date", ""))[:10]
                    ptitle = prow.get("title", "")
                    purl = prow.get("attachment_pdf_url", "")
                    psrc = prow.get("source_type", "CBTT")
                    st.markdown(f"""
                        <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 12px;">
                            <div>
                                <div style="font-size: 12px; color: {pal['text_muted']}; font-weight: 700;">📅 {pdate} • 🏛️ {psrc}</div>
                                <div style="font-size: 13.5px; color: {pal['text_heading']}; font-weight: 600; margin-top: 2px;">{ptitle}</div>
                            </div>
                            <a href="{purl}" target="_blank" style="background: rgba(37, 99, 235, 0.12); border: 1px solid {pal['color_brand_led']}; color: {pal['color_brand_led']}; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; text-decoration: none; white-space: nowrap;">📎 Mở PDF Gốc ↗</a>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info(f"Hiện kho CBTT chưa có tệp PDF BCTC đính kèm riêng cho {selected_ticker}. Chuyên viên có thể xem bảng cân đối & KQKD đầy đủ tại Tab 3.")

    # =========================================================================
    # TẦNG 3 TRA CỨU SÂU: BẢNG DỮ LIỆU BCTC GỐC (EXPANDER ĐỠ RỐI MÀN HÌNH)
    # =========================================================================
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    with st.expander(f"🔍 Tra Cứu Sâu: Bảng Dữ Liệu Báo Cáo Tài Chính 14 Cột Chi Tiết ({selected_ticker})", expanded=False):
        st.markdown(f"""
            <div style='font-size: 12px; color: {pal["text_muted"]}; margin-bottom: 10px;'>
                Dành cho Chuyên viên Phân tích & Kiểm toán Dữ liệu: Toàn bộ số liệu các khoản mục BCTC (đơn vị: Tỷ VND) và các tỷ số tài chính qua các quý.
            </div>
        """, unsafe_allow_html=True)
        if not df_eq.empty:
            table_eq = df_eq.copy().iloc[::-1]
            for c in ["nii", "nfi", "net_gain_fx", "net_gain_securities", "other_operating_income_residual", "toi", "opex", "ppop", "provision_expense", "pbt", "npat"]:
                if c in table_eq.columns:
                    table_eq[c] = (pd.to_numeric(table_eq[c], errors="coerce").fillna(0) / 1e9).round(1).apply(lambda x: f"{x:,.1f}")

            table_eq["Credit Cost (%)"] = pd.to_numeric(table_eq["credit_cost_ratio"], errors="coerce").apply(lambda x: f"{x * 100:.2f}%" if pd.notnull(x) else "N/A")
            table_eq["NIM (%)"] = pd.to_numeric(table_eq["nim"], errors="coerce").apply(lambda x: f"{x * 100:.2f}%" if pd.notnull(x) else "N/A")
            table_eq["CIR (%)"] = pd.to_numeric(table_eq["cir"], errors="coerce").apply(lambda x: f"{x * 100:.1f}%" if pd.notnull(x) else "N/A")

            display_cols = [
                "period_name", "nii", "nfi", "net_gain_fx", "net_gain_securities",
                "other_operating_income_residual", "toi", "opex", "ppop",
                "provision_expense", "pbt", "npat", "Credit Cost (%)", "NIM (%)", "CIR (%)"
            ]
            renamed_cols = {
                "period_name": "Kỳ BCTC", "nii": "Thu nhập Lãi", "nfi": "Thu phí DV",
                "net_gain_fx": "Kinh doanh FX", "net_gain_securities": "CK Kinh doanh",
                "other_operating_income_residual": "Thu khác", "toi": "Tổng Doanh Thu",
                "opex": "Chi phí HĐ", "ppop": "LN trước DP (PPOP)",
                "provision_expense": "Chi phí Dự phòng", "pbt": "LN trước Thuế (PBT)",
                "npat": "LN Ròng (NPAT)"
            }
            st.dataframe(table_eq[display_cols].rename(columns=renamed_cols), use_container_width=True, hide_index=True)
