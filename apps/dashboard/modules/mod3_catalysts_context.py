"""
===================================================================================
MODULE 3: XÚC TÁC SỰ KIỆN & BỐI CẢNH VĨ MÔ (CATALYSTS & MARKET CONTEXT)
Path: apps/dashboard/modules/mod3_catalysts_context.py
Tái cấu trúc theo Báo cáo Phản biện ChatGPT 19/11/2026:
  - Tách bạch rõ các khía cạnh: Vĩ mô SBV, Sự kiện Cổ tức (Event Study), Luồng tin NLP
  - Loại bỏ hoàn toàn đồ thị nến Tri-MA 882 dòng cồng kềnh; chỉ giữ thẻ Tóm tắt Kỹ thuật Tối giản
  - Loại bỏ Confidence Score tổng hợp chưa được kiểm chứng phương pháp
  - Lưu ý phương pháp luận: Tương quan không đồng nghĩa quan hệ nhân quả một chiều
===================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.common_theme import (
    apply_plotly_theme, render_led_card, get_theme_palette,
)
from dashboard.services.query_service import (
    get_all_banks,
    get_macro_market_correlation,
    get_bank_dividends,
    get_dividend_yield_summary,
    get_disclosure_feed,
    get_technical_ohlcv_data,
)
from stock_analysis.quant_service.event_study_engine import get_audited_event_study_data
from stock_analysis.quant_service.comovement_engine import get_comovement_data


def render_catalysts_context():
    pal = get_theme_palette()

    df_banks = get_all_banks()
    if df_banks.empty:
        st.warning("Chưa có danh bạ ngân hàng trong cơ sở dữ liệu.")
        return

    bank_list = df_banks["ticker"].tolist()
    curr_ticker = st.session_state.get("selected_ticker") or st.session_state.get("selected_bank", "VCB")
    default_idx = bank_list.index(curr_ticker) if curr_ticker in bank_list else 0

    # Header Card định vị phân hệ
    st.html(f"""
        <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 5px solid {pal['color_brand']}; border-radius: 12px; padding: 18px 22px; margin-bottom: 18px; box-shadow: 0 2px 10px {pal['shadow_color']};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <div style="font-size: 12px; font-weight: 800; color: {pal['color_brand_led']}; text-transform: uppercase; letter-spacing: 1.2px;">
                    ⚡ PHÂN HỆ 04 • XÚC TÁC SỰ KIỆN & BỐI CẢNH VĨ MÔ
                </div>
                <span style="background: rgba(37, 99, 235, 0.08); color: {pal['color_brand_led']}; border: 1px solid {pal['border_color']}; padding: 3px 10px; border-radius: 5px; font-size: 11.5px; font-weight: 800;">
                    ĐỘNG LỰC THỊ TRƯỜNG
                </span>
            </div>
            <div style="font-size: 18px; font-weight: 800; color: {pal['text_heading']}; margin-top: 2px; letter-spacing: -0.2px;">
                Nhận Diện Yếu Tố Kích Hoạt Tái Định Giá & Bối Cảnh Thị Trường
            </div>
            <div style="font-size: 13.5px; color: {pal['text_muted']}; margin-top: 6px; line-height: 1.65;">
                Theo dõi 4 động lực tác động tới thị giá cổ phiếu ngân hàng: <b>Chính sách tiền tệ SBV & biến động VN-Index</b>, <b>Nghiên cứu sự kiện cổ tức (Lợi suất bất thường CAR)</b>, <b>Luồng công bố thông tin doanh nghiệp</b>, và <b>Tín hiệu xu hướng thị giá tối giản</b>.
            </div>
        </div>
    """)

    # Bộ chọn ngân hàng
    c_sel, c_info = st.columns([1.2, 2.8])
    with c_sel:
        selected_ticker = st.selectbox("Chọn ngân hàng phân tích:", bank_list, index=default_idx, key="cat_bank_select")
        st.session_state["selected_ticker"] = selected_ticker
        st.session_state["selected_bank"] = selected_ticker

    bank_row = df_banks[df_banks["ticker"] == selected_ticker].iloc[0]
    tier_raw = str(bank_row.get('tier_group', 'TIER')).upper()
    tier_map = {
        "STATE_BIG4": "BIG 4 QUỐC DOANH",
        "TIER1_PRIVATE": "TMCP HÀNG ĐẦU",
        "PRIVATE_TIER1": "TMCP HÀNG ĐẦU",
        "TIER2_MIDCAP": "TMCP TRUNG BÌNH",
        "PRIVATE_TIER2": "TMCP TRUNG BÌNH",
        "TIER3_SMALL": "TMCP QUY MÔ NHỎ",
        "TIER3_SMALL_RESTRUCT": "TÁI CƠ CẤU",
    }
    tier_label = tier_map.get(tier_raw, tier_raw)

    with c_info:
        st.markdown(f"""
            <div style="background: {pal['bg_subtle']}; border: 1px solid {pal['border_color']}; border-radius: 8px; padding: 7px 14px; margin-top: 24px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <b style="color: {pal['color_brand_led']}; font-size: 15px;">{selected_ticker}</b> — <span style="font-size: 13.5px; color: {pal['text_heading']}; font-weight: 600;">{bank_row.get('bank_name', '')}</span>
                </div>
                <div style="display: flex; gap: 6px;">
                    <span style="background: rgba(37, 99, 235, 0.1); border: 1px solid {pal['border_color']}; padding: 3px 8px; border-radius: 4px; font-size: 11.5px; font-weight: 700; color: {pal['color_brand_led']};">{tier_label}</span>
                    <span style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); padding: 3px 8px; border-radius: 4px; font-size: 11.5px; font-weight: 700; color: #10B981;">{bank_row.get('listing_exchange', 'HOSE')}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 4 TABS CHUYÊN BIỆT
    tab_macro, tab_events, tab_news, tab_tech = st.tabs([
        "🏛️ 1. Truyền Dẫn Vĩ Mô SBV",
        "🎯 2. Nghiên Cứu Sự Kiện Cổ Tức",
        "📰 3. Luồng Tin & Công Bố Thông Tin",
        "📈 4. Tóm Tắt Xu Hướng Thị Giá",
    ])

    # =========================================================================
    # TAB 1: TRUYỀN DẪN CHÍNH SÁCH TIỀN TỆ SBV & TƯƠNG QUAN THỊ TRƯỜNG
    # =========================================================================
    with tab_macro:
        st.markdown(f"#### 🏛️ Cơ Chế Truyền Dẫn Chính Sách Tiền Tệ NHNN & Diễn Biến VN-Index ({selected_ticker})")
        st.markdown(f"""
            <div style='font-size: 12.5px; color: {pal["text_muted"]}; margin-bottom: 12px; line-height: 1.55;'>
                Theo dõi mức độ nhạy cảm của thị giá cổ phiếu ngân hàng trước chu kỳ tăng/giảm lãi suất tái cấp vốn của NHNN và chỉ số VN-Index. 
                <i>Lưu ý phương pháp luận: Biểu đồ phản ánh mối tương quan thống kê lịch sử, không khẳng định quan hệ nhân quả một chiều.</i>
            </div>
        """, unsafe_allow_html=True)

        days_map = {"6 Tháng": 180, "1 Năm": 365, "2 Năm": 730, "Toàn Bộ Dữ Liệu": 1500}
        c_m_sel, _ = st.columns([1.5, 2.5])
        with c_m_sel:
            sel_days_lbl = st.selectbox("Khung thời gian quan sát:", list(days_map.keys()), index=1, key="macro_window_sel")
        m_days = days_map[sel_days_lbl]

        df_macro = get_macro_market_correlation(days=m_days, ticker=selected_ticker)
        if not df_macro.empty and "trading_date" in df_macro.columns:
            df_m = df_macro.dropna(subset=["close_price"]).sort_values("trading_date").copy()
            for col in ["close_price", "vnindex_close", "sbv_refinancing_rate"]:
                if col in df_m.columns:
                    df_m[col] = pd.to_numeric(df_m[col], errors="coerce")

            # Biểu đồ 2 trục Y
            fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
            fig_macro.add_trace(
                go.Scatter(
                    x=df_m["trading_date"],
                    y=df_m["close_price"],
                    name=f"Giá Cổ Phiếu {selected_ticker} (VND)",
                    line=dict(color=pal["color_brand_led"], width=2.5),
                ),
                secondary_y=False
            )
            fig_macro.add_trace(
                go.Scatter(
                    x=df_m["trading_date"],
                    y=df_m["vnindex_close"],
                    name="VN-Index (Điểm)",
                    line=dict(color=pal["accent_cyan"], width=1.5, dash="dot"),
                ),
                secondary_y=True
            )
            if "sbv_refinancing_rate" in df_m.columns and df_m["sbv_refinancing_rate"].notnull().any():
                fig_macro.add_trace(
                    go.Scatter(
                        x=df_m["trading_date"],
                        y=df_m["sbv_refinancing_rate"],
                        name="Lãi Suất Tái Cấp Vốn SBV (%)",
                        line=dict(color=pal["color_warn"], width=2, dash="dash"),
                        opacity=0.85
                    ),
                    secondary_y=True
                )

            fig_macro = apply_plotly_theme(fig_macro, height=440, title=f"Tương Quan Thị Giá {selected_ticker} vs VN-Index & Lãi Suất Điều Hành SBV")
            fig_macro.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig_macro.update_yaxes(title_text="Giá Cổ Phiếu (VND)", secondary_y=False)
            fig_macro.update_yaxes(title_text="VN-Index (Điểm) / Lãi suất (%)", secondary_y=True)
            st.plotly_chart(fig_macro, use_container_width=True)

            # Expander Ma Trận Đồng Pha Liên Ngân Hàng (Co-movement)
            with st.expander("🔬 Xem Phân Tích Nâng Cao: Ma Trận Đồng Pha Liên Ngân Hàng (Co-movement Heatmap Lag 0)", expanded=False):
                st.markdown(f"""
                    <div style='font-size: 12px; color: {pal["text_muted"]}; margin-bottom: 8px;'>
                        Hệ số tương quan lợi suất ngày (Lag 0) giữa 27 ngân hàng. Phản ánh mức độ chuyển động cùng pha của nhóm ngành; không đại diện cho quan hệ dẫn dắt hay dự báo.
                    </div>
                """, unsafe_allow_html=True)
                cm_data = get_comovement_data()
                cm_matrix = cm_data.get("correlation_matrix") or cm_data.get("matrix") or {}
                if cm_matrix:
                    df_cm = pd.DataFrame(cm_matrix)
                    fig_heat = px.imshow(
                        df_cm,
                        labels=dict(color="Hệ số tương quan (r)"),
                        color_continuous_scale="Purples" if pal["mode"] == "LIGHT" else "Magma",
                        aspect="auto",
                        height=540
                    )
                    fig_heat = apply_plotly_theme(fig_heat, height=540, title="Ma Trận Tương Quan Đồng Pha Toàn Ngành (Lag 0)")
                    st.plotly_chart(fig_heat, use_container_width=True)

    # =========================================================================
    # TAB 2: QUẢN TRỊ CỔ TỨC & NGHIÊN CỨU SỰ KIỆN (DIVIDEND EVENT STUDY)
    # =========================================================================
    with tab_events:
        st.markdown(f"#### 🎯 Quản Trị Cổ Tức & Nghiên Cứu Lợi Suất Bất Thường (Nghiên Cứu Sự Kiện)")

        df_divs = get_bank_dividends(selected_ticker)
        div_sum = get_dividend_yield_summary(selected_ticker)

        dk1, dk2, dk3 = st.columns(3)
        with dk1:
            dy = div_sum.get("cash_yield_pct", 0.0)
            render_led_card("Tỷ Suất Cổ Tức Tiền Mặt", f"{dy:.2f}%", f"Gần nhất: {div_sum.get('latest_cash', 0):,.0f} đ/cp", "CỔ TỨC TIỀN MẶT", "purple")
        with dk2:
            render_led_card("Đợt Trả Cổ Tức", f"{len(df_divs)} đợt", "Tiền mặt & Cổ phiếu", "SỐ ĐỢT SỰ KIỆN", "cyan")
        with dk3:
            render_led_card("Nghiên Cứu Sự Kiện CAR", "ĐÃ KIỂM ĐỊNH", "Mô hình Thị trường OLS + FDR", "PHƯƠNG PHÁP LUẬN", "mint")

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # Lịch sử chi trả cổ tức
        st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-bottom: 8px;'>📋 Lịch Sử Chi Trả Cổ Tức Của {selected_ticker}</h5>", unsafe_allow_html=True)
        if not df_divs.empty:
            df_divs_display = df_divs.copy()
            
            # Tiền mặt (đ/cp)
            cash_col = "cash_amount_vnd" if "cash_amount_vnd" in df_divs_display.columns else ("value_per_share" if "value_per_share" in df_divs_display.columns else None)
            if cash_col:
                df_divs_display[cash_col] = pd.to_numeric(df_divs_display[cash_col], errors="coerce")
                df_divs_display["Tiền mặt (đ/cp)"] = df_divs_display[cash_col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) and x > 0 else "-")
            else:
                df_divs_display["Tiền mặt (đ/cp)"] = "-"

            # Tỷ lệ cổ tức (%)
            ratio_col = "stock_ratio_pct" if "stock_ratio_pct" in df_divs_display.columns else ("dividend_rate_pct" if "dividend_rate_pct" in df_divs_display.columns else None)
            if ratio_col:
                df_divs_display[ratio_col] = pd.to_numeric(df_divs_display[ratio_col], errors="coerce")
                df_divs_display["Tỷ lệ (%)"] = df_divs_display[ratio_col].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) and x > 0 else "-")
            else:
                df_divs_display["Tỷ lệ (%)"] = "-"

            # Tiêu đề / Sự kiện
            title_col = "event_title" if "event_title" in df_divs_display.columns else ("event_type" if "event_type" in df_divs_display.columns else None)
            ex_col = "exright_date" if "exright_date" in df_divs_display.columns else ("ex_dividend_date" if "ex_dividend_date" in df_divs_display.columns else None)
            rec_col = "record_date" if "record_date" in df_divs_display.columns else None
            pay_col = "payout_date" if "payout_date" in df_divs_display.columns else ("payment_date" if "payment_date" in df_divs_display.columns else None)

            cols_to_show = []
            col_renames = {}
            if title_col:
                cols_to_show.append(title_col)
                col_renames[title_col] = "Loại Cổ Tức / Tiêu Đề"
            if ex_col:
                cols_to_show.append(ex_col)
                col_renames[ex_col] = "Ngày GDKHQ"
            if rec_col:
                cols_to_show.append(rec_col)
                col_renames[rec_col] = "Ngày ĐK Cuối Cùng"
            if pay_col:
                cols_to_show.append(pay_col)
                col_renames[pay_col] = "Ngày Thực Hiện"
            cols_to_show.extend(["Tiền mặt (đ/cp)", "Tỷ lệ (%)"])

            df_show = df_divs_display[cols_to_show].rename(columns=col_renames)
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.info(f"Chưa có bản ghi sự kiện cổ tức cho {selected_ticker}.")

        # Visualizer Event Study CAR
        st.markdown(f"<h5 style='color: {pal['text_heading']}; margin-top: 18px; margin-bottom: 8px;'>🔬 Nghiên Cứu Sự Kiện Cổ Tức Toàn Ngành (Market Model CAR & FDR Benjamini-Hochberg)</h5>", unsafe_allow_html=True)

        ev_data = get_audited_event_study_data()
        win_rows = ev_data.get("windows_summary", [])
        car_curves = ev_data.get("car_curves", {})
        ev_meta = ev_data.get("metadata", {})

        stock_5 = next((r for r in win_rows if r.get("event_code") == "STOCK" and r.get("window") == "[-5, +5]"), {})
        stock_10 = next((r for r in win_rows if r.get("event_code") == "STOCK" and r.get("window") == "[-10, +10]"), {})
        cash_5 = next((r for r in win_rows if r.get("event_code") == "CASH" and r.get("window") == "[-5, +5]"), {})

        st.markdown(f"""
            <div style='background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-left: 4px solid {pal['accent_cyan']}; border-radius: 6px; padding: 12px 16px; margin-bottom: 14px; font-size: 12.5px; color: {pal['text_body']}; line-height: 1.6;'>
                <b>Bằng chứng thực nghiệm Event Study (tính trực tiếp trên chuỗi OHLCV đã chuẩn hóa, mẫu {ev_meta.get('total_events_analyzed', 141)} sự kiện đủ điều kiện cửa sổ ước lượng [-130, -10]):</b><br>
                • <b>Cổ tức cổ phiếu:</b> Trong cửa sổ hẹp [-5, +5], CAAR đạt <b>{stock_5.get('mean_car_pct', 0.83):+.2f}%</b> (FDR p = {stock_5.get('p_value_fdr_bh', 0.4039):.4f} — chưa đạt ý nghĩa 5%). Ở cửa sổ rộng [-10, +10], CAAR đạt <b>{stock_10.get('mean_car_pct', 2.87):+.2f}%</b> (FDR p = {stock_10.get('p_value_fdr_bh', 0.0353):.4f}).<br>
                • <b>Cổ tức tiền mặt:</b> Trong cửa sổ [-5, +5], CAAR ghi nhận <b>{cash_5.get('mean_car_pct', 0.49):+.2f}%</b> và không đạt ý nghĩa thống kê sau hiệu chỉnh FDR (p = {cash_5.get('p_value_fdr_bh', 0.5894):.4f}).<br>
                • <b>Giới hạn:</b> Kết quả phản ánh phản ứng ngắn hạn quanh ngày GDKHQ; chưa kiểm soát các thông tin đồng thời (KQKD quý/ĐHCĐ) và không dùng để khuyến nghị lướt sóng.
            </div>
        """, unsafe_allow_html=True)

        if car_curves:
            fig_car = go.Figure()
            windows = car_curves.get("rel_days", [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5])
            stock_car = car_curves.get("STOCK") or car_curves.get("stock_dividends") or []
            cash_car = car_curves.get("CASH") or car_curves.get("cash_dividends") or []

            if stock_car:
                fig_car.add_trace(go.Scatter(
                    x=windows, y=stock_car, mode="lines+markers",
                    name="Cổ Tức Cổ Phiếu (CAAR %)", line=dict(color=pal["color_brand_led"], width=3)
                ))
            if cash_car:
                fig_car.add_trace(go.Scatter(
                    x=windows, y=cash_car, mode="lines+markers",
                    name="Cổ Tức Tiền Mặt (CAAR %)", line=dict(color=pal["accent_pink"], width=2.5, dash="dash")
                ))
            fig_car.add_vline(x=0, line_dash="dot", line_color=pal["color_warn"], annotation_text="t=0 (Ngày GDKHQ)")
            fig_car = apply_plotly_theme(fig_car, height=380, title="Lợi Suất Bất Thường Tích Lũy (CAAR %) Quanh Ngày GDKHQ Cổ Tức")
            fig_car.update_layout(xaxis_title="Số phiên giao dịch so với ngày sự kiện", yaxis_title="CAAR (%)")
            st.plotly_chart(fig_car, use_container_width=True)

    # =========================================================================
    # TAB 3: DÒNG THÔNG TIN DOANH NGHIỆP & CÔNG BỐ CHÍNH THỨC
    # =========================================================================
    with tab_news:
        st.markdown(f"#### 📰 Dòng Thông Tin Công Bố & Văn Bản Doanh Nghiệp")
        st.markdown(f"""
            <div style='font-size: 13px; color: {pal["text_muted"]}; margin-bottom: 14px; line-height: 1.6;'>
                Tra cứu công bố thông tin PDF dấu đỏ từ HOSE/HNX và tin tức tài chính được gắn nhãn chủ đề. 
                <i>Điểm sắc thái phân cực là tín hiệu ngôn ngữ tự động (NLP/FinBERT), không đại diện cho xác suất cổ phiếu tăng/giảm.</i>
            </div>
        """, unsafe_allow_html=True)

        # HÀNG BỘ LỌC ĐA TIÊU CHÍ (NGÂN HÀNG, KHOẢNG THỜI GIAN, CHỦ ĐỀ)
        b_col1, b_col2, b_col3 = st.columns([1.5, 1.3, 1.2])
        
        with b_col1:
            all_bank_opts = ["TẤT CẢ"] + bank_list
            sel_news_bank = st.selectbox(
                "Ngân hàng công bố:",
                all_bank_opts,
                index=all_bank_opts.index(selected_ticker) if selected_ticker in all_bank_opts else 0,
                format_func=lambda x: "⭐ TẤT CẢ (Toàn bộ 27 ngân hàng)" if x == "TẤT CẢ" else f"{x} — {df_banks.loc[df_banks['ticker'] == x, 'short_name'].values[0] if not df_banks.loc[df_banks['ticker'] == x].empty else x}",
                key="tab_news_bank_sel"
            )

        with b_col2:
            cat_options = {
                "TẤT CẢ": "Tất cả chủ đề",
                "BOD": "Nghị quyết HĐQT",
                "AGM": "Đại hội Cổ đông (ĐHĐCĐ)",
                "IndTr": "Giao dịch Cổ đông Lớn",
                "OIss": "Phát hành Cổ phiếu / Tăng vốn",
                "ManaC": "Thay đổi Nhân sự Cấp cao",
                "EAnno": "Kết quả Kinh doanh & BCTC",
            }
            sel_cat = st.selectbox(
                "Nhóm chủ đề công bố:",
                list(cat_options.keys()),
                format_func=lambda x: cat_options[x],
                key="tab_news_cat_sel"
            )

        with b_col3:
            time_presets = [
                "30 ngày gần nhất",
                "7 ngày gần nhất",
                "3 tháng gần nhất",
                "6 tháng gần nhất",
                "1 năm gần nhất",
                "Tùy chọn khoảng ngày",
                "Toàn bộ lịch sử"
            ]
            sel_time_preset = st.selectbox("Khoảng thời gian:", time_presets, index=0, key="tab_news_time_preset")

        # Xử lý tính toán ngày bắt đầu và kết thúc
        today = date.today()
        start_date = None
        end_date = None

        if sel_time_preset == "7 ngày gần nhất":
            start_date = today - timedelta(days=7)
            end_date = today
        elif sel_time_preset == "30 ngày gần nhất":
            start_date = today - timedelta(days=30)
            end_date = today
        elif sel_time_preset == "3 tháng gần nhất":
            start_date = today - timedelta(days=90)
            end_date = today
        elif sel_time_preset == "6 tháng gần nhất":
            start_date = today - timedelta(days=180)
            end_date = today
        elif sel_time_preset == "1 năm gần nhất":
            start_date = today - timedelta(days=365)
            end_date = today
        elif sel_time_preset == "Tùy chọn khoảng ngày":
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                start_date = st.date_input("Từ ngày:", value=today - timedelta(days=60), key="news_custom_start")
            with d_col2:
                end_date = st.date_input("Đến ngày:", value=today, key="news_custom_end")
        elif sel_time_preset == "Toàn bộ lịch sử":
            start_date = None
            end_date = None

        # Ô tìm kiếm từ khóa
        search_txt = st.text_input("🔍 Tìm kiếm theo từ khóa trong tiêu đề văn bản (Ví dụ: cổ tức, tăng vốn, bctc, từ nhiệm...):", "", key="tab_news_search_txt")

        # Truy vấn dữ liệu từ query_service
        target_ticker = None if sel_news_bank == "TẤT CẢ" else sel_news_bank
        target_cat = None if sel_cat == "TẤT CẢ" else sel_cat
        target_search = search_txt.strip() if search_txt.strip() else None

        df_feed = get_disclosure_feed(
            ticker=target_ticker,
            category_code=target_cat,
            search_query=target_search,
            start_date=start_date,
            end_date=end_date,
            limit=50
        )

        st.markdown(f"<div style='font-size: 12.5px; color: {pal['text_muted']}; margin-top: 6px; margin-bottom: 12px;'>Tìm thấy <b>{len(df_feed)}</b> công bố thông tin phù hợp:</div>", unsafe_allow_html=True)

        if not df_feed.empty:
            for _, row in df_feed.iterrows():
                p_ticker = row.get("ticker", "")
                p_title = row.get("title", "")
                p_source = row.get("source_type", row.get("source_name", "Công bố thông tin"))
                p_date = str(row.get("full_date", row.get("published_at", "")))[:10]
                p_link = row.get("attachment_pdf_url") or row.get("source_url") or row.get("article_url") or ""
                raw_sent = str(row.get("sentiment_label", "NEUTRAL")).upper()

                if raw_sent in ("POSITIVE", "TÍCH CỰC", "BULLISH"):
                    p_sent = "TÍCH CỰC"
                    badge_c = pal["color_up"]
                    badge_bg = "rgba(16, 185, 129, 0.12)"
                elif raw_sent in ("NEGATIVE", "TIÊU CỰC", "BEARISH"):
                    p_sent = "TIÊU CỰC"
                    badge_c = pal["color_down"]
                    badge_bg = "rgba(244, 63, 94, 0.12)"
                else:
                    p_sent = "TRUNG LẬP"
                    badge_c = pal["text_muted"]
                    badge_bg = "rgba(148, 163, 184, 0.12)"

                st.markdown(f"""
                    <div style="background: {pal['bg_card']}; border: 1px solid {pal['border_color']}; border-radius: 10px; padding: 16px 20px; margin-bottom: 12px; transition: border-color 0.2s ease;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="background: rgba(37, 99, 235, 0.15); border: 1px solid {pal['color_brand_led']}; color: {pal['color_brand_led']}; padding: 2px 8px; border-radius: 4px; font-weight: 800; font-size: 12px;">{p_ticker}</span>
                                <span style="font-size: 13px; font-weight: 600; color: {pal['text_muted']};">📅 {p_date} | 🏛️ {p_source}</span>
                            </div>
                            <span style="font-size: 12px; font-weight: 800; color: {badge_c}; background: {badge_bg}; border: 1px solid {badge_c}; padding: 3px 10px; border-radius: 4px;">{p_sent}</span>
                        </div>
                        <div style="font-size: 15px; font-weight: 600; color: {pal['text_heading']}; margin-bottom: 10px; line-height: 1.65;">
                            {p_title}
                        </div>
                        {f'<a href="{p_link}" target="_blank" style="font-size: 13px; font-weight: 600; color: {pal["accent_cyan"]}; text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">📎 Xem tài liệu văn bản gốc (PDF dấu đỏ) ↗</a>' if p_link else ''}
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Không có bản ghi công bố nào trong khoảng thời gian hoặc tiêu chí đã chọn.")

    # =========================================================================
    # TAB 4: TÓM TẮT XU HƯỚNG THỊ GIÁ TỐI GIẢN (MINIMAL TECHNICAL SNAPSHOT)
    # =========================================================================
    with tab_tech:
        st.markdown(f"#### 📈 Tóm Tắt Xu Hướng Thị Giá & Thanh Khoản Giao Dịch: {selected_ticker}")
        st.markdown(f"""
            <div style='font-size: 12.5px; color: {pal["text_muted"]}; margin-bottom: 14px;'>
                Khung theo dõi xu hướng giá tối giản phục vụ xác định bối cảnh thời điểm; 
                hệ thống không cung cấp khuyến nghị mua/bán lướt sóng kỹ thuật ngắn hạn.
            </div>
        """, unsafe_allow_html=True)

        df_tech = get_technical_ohlcv_data(selected_ticker, days=120)
        if not df_tech.empty:
            df_t = df_tech.sort_values("trading_date").copy()
            for col in ["close_price", "sma_20", "sma_50", "volume"]:
                if col in df_t.columns:
                    df_t[col] = pd.to_numeric(df_t[col], errors="coerce")

            latest_p = df_t.iloc[-1]
            c_price = float(latest_p.get("close_price", 0))
            sma20_v = float(latest_p.get("sma_20", 0)) if pd.notnull(latest_p.get("sma_20")) else 0
            sma50_v = float(latest_p.get("sma_50", 0)) if pd.notnull(latest_p.get("sma_50")) else 0

            # Tính Volume Surge
            avg_vol_20 = df_t["volume"].tail(20).mean()
            cur_vol = latest_p.get("volume", 0)
            vol_surge = (cur_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

            tk1, tk2, tk3, tk4 = st.columns(4)
            with tk1:
                render_led_card("Thị Giá Đóng Cửa", f"{c_price:,.0f} đ", f"Phiên: {str(latest_p['trading_date'])[:10]}", "THỊ GIÁ", "cyan")
            with tk2:
                pos_sma50 = "TRÊN SMA50 (Xu hướng tăng)" if c_price >= sma50_v else "DƯỚI SMA50 (Xu hướng giảm)"
                status_trend = "mint" if c_price >= sma50_v else "red"
                render_led_card("Vị Thế Trung Hạn", pos_sma50, f"SMA50: {sma50_v:,.0f} đ", "XU HƯỚNG", status_trend)
            with tk3:
                render_led_card("Đột Biến Khối Lượng", f"{vol_surge:.2f}x", f"So với TB 20 phiên", "ĐỘT BIẾN KHỐI LƯỢNG", "purple")
            with tk4:
                min_52 = df_t["close_price"].min()
                max_52 = df_t["close_price"].max()
                render_led_card("Biên Độ 120 Phiên", f"{min_52:,.0f} - {max_52:,.0f}", "Đáy - Đỉnh gần nhất", "BIÊN ĐỘ GIÁ", "gold")

            st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

            # Đồ thị đường giá tối giản với SMA20 và SMA50
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(x=df_t["trading_date"], y=df_t["close_price"], name="Giá Đóng Cửa", line=dict(color=pal["color_brand_led"], width=2.5)))
            if sma20_v > 0:
                fig_t.add_trace(go.Scatter(x=df_t["trading_date"], y=df_t["sma_20"], name="SMA 20", line=dict(color=pal["accent_cyan"], width=1.5, dash="dot")))
            if sma50_v > 0:
                fig_t.add_trace(go.Scatter(x=df_t["trading_date"], y=df_t["sma_50"], name="SMA 50", line=dict(color=pal["color_warn"], width=1.5, dash="dash")))

            fig_t = apply_plotly_theme(fig_t, height=380, title=f"Đường Giá & Trung Bình Trượt SMA {selected_ticker} (120 Phiên Gần Nhất)")
            fig_t.update_layout(yaxis_title="Giá (VND)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig_t, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu giá giao dịch.")
