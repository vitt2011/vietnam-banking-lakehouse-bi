"""
===================================================================================
MODULE: dashboard/common_theme.py
CHỨC NĂNG: HỆ THỐNG THEME ĐÔI (DUAL THEME: LIGHT & DARK MODE) CHUẨN LED NEON VÀ OBSIDIAN NAVY
===================================================================================
Bảng màu tham chiếu chính xác theo mẫu thiết kế chuyên nghiệp (ce671d75.png):
1. DARK MODE (Chế độ mặc định & Trình diễn chuyên nghiệp - Bloomberg / FactSet Style):
   - Nền tổng thể (App Background): #060C22 (Deep Midnight Obsidian Navy)
   - Containers / Cards: #141834 (Dark Indigo Card với viền phát sáng LED)
   - Nền Sidebar: linear-gradient(180deg, #090E23 0%, #060B1C 100%)
   - Viền Card / Phân cách: rgba(138, 43, 226, 0.28) (Viền tím LED phát sáng tinh tế)
   - Nền đồ thị mạng lưới PyVis: #222536 (Khớp chuẩn xác canvas đồ thị ce671d75.png)
   - Đổ bóng: 0 8px 24px rgba(0, 0, 0, 0.70)
   - Typography:
     * Tiêu đề (Headings): #FFFFFF (Trắng tinh khiết cực kỳ sắc nét)
     * Chữ nội dung (Body): #D2D6EE (Bạc ánh tím sáng, độ tương phản cao, dễ đọc)
     * Chữ chú thích (Muted): #8E95BE (Xám lavender dịu mắt)

2. LIGHT MODE (Chế độ Sáng - Hiện đại & Sang trọng):
   - Nền tổng thể: #F3F0FA (Trắng xám ánh tím rất nhạt, dịu mắt khi nhìn lâu)
   - Containers / Cards: #FFFFFF (Trắng tinh khiết, đổ bóng mềm mại)
   - Nền Sidebar: linear-gradient(180deg, #FFFFFF 0%, #F5F0FF 100%)
   - Viền Card / Phân cách: #EBE5F7
   - Typography:
     * Tiêu đề: #10002B (Tím đen cực đậm)
     * Chữ nội dung: #3C096C (Tím than đậm dễ đọc)
     * Chữ chú thích: #9D8189 (Xám ánh tím)
   - Nền đồ thị PyVis: #FAFAFD

3. NHÓM MÀU LED ACCENT & DỮ LIỆU TÀI CHÍNH (Độ bão hòa cao):
   - Tím LED (Primary Brand): #8A2BE2 / #7B2CBF
   - Xanh Cyan Neon (Accent 1): #00D2FF / #4CC9F0
   - Hồng Neon (Accent 2): #FF3366 / #F72585
   - Tăng giá / Tích cực: #00F5D4 (Xanh Mint Neon)
   - Giảm giá / Tiêu cực / Lỗi: #FF006E (Đỏ Hồng Neon)
   - Cảnh báo / Trung lập: #FEE440 (Vàng Chanh Sáng)
===================================================================================
"""

import textwrap
from typing import Dict, Any
import plotly.graph_objects as go
import streamlit as st

PLOTLY_CHART_CONFIG = {"displayModeBar": False}

# FONT CHỮ TOÀN HỆ THỐNG: SEGOE UI CHUẨN XÁC, KHÔNG LỖI TIẾNG VIỆT
FONT_FAMILY = "'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', 'Helvetica Neue', Arial, sans-serif"

# CÁC HẰNG SỐ CỐ ĐỊNH PHỤC VỤ BACKWARD COMPATIBILITY
BG_APP = "#060C22"
BG_CARD = "#141834"
BG_SIDEBAR = "linear-gradient(180deg, #090E23 0%, #060B1C 100%)"

COLOR_BRAND = "#7B2CBF"
COLOR_BRAND_LED = "#8A2BE2"
ACCENT_CYAN = "#00D2FF"
ACCENT_PINK = "#F72585"

TEXT_HEADING = "#FFFFFF"
TEXT_BODY = "#D2D6EE"
TEXT_MUTED = "#8E95BE"

COLOR_UP = "#00F5D4"
COLOR_DOWN = "#FF006E"
COLOR_WARN = "#FEE440"


def get_theme_mode() -> str:
    """
    Trả về trạng thái giao diện hiện tại: 'DARK' hoặc 'LIGHT'.
    Bảo lưu trạng thái qua URL query param (?theme=light/dark) để không bị nhảy lại DARK khi Rerun.
    """
    # 1. Ưu tiên cao nhất: Kiểm tra URL query params (?theme=light hoặc ?theme=dark)
    try:
        if hasattr(st, "query_params") and "theme" in st.query_params:
            param_theme = str(st.query_params["theme"]).strip().upper()
            if param_theme in ("LIGHT", "DARK"):
                st.session_state["theme_mode"] = param_theme
                return param_theme
    except Exception:
        pass

    # 2. Kiểm tra session state
    if "theme_mode" in st.session_state and st.session_state["theme_mode"] in ("LIGHT", "DARK"):
        return st.session_state["theme_mode"]

    # 3. Fallback mặc định: DARK
    st.session_state["theme_mode"] = "DARK"
    return "DARK"


def set_theme_mode(mode: str) -> None:
    """Thiết lập trạng thái giao diện và ghi đè vào URL query params để giữ nguyên khi Rerun."""
    if mode in ("LIGHT", "DARK"):
        st.session_state["theme_mode"] = mode
        try:
            st.query_params["theme"] = mode.lower()
        except Exception:
            pass


def toggle_theme_mode() -> str:
    """Đảo trạng thái giao diện giữa DARK và LIGHT."""
    current = get_theme_mode()
    new_mode = "LIGHT" if current == "DARK" else "DARK"
    st.session_state["theme_mode"] = new_mode
    return new_mode


def get_theme_palette() -> Dict[str, str]:
    """
    Bảng màu Chuẩn Định Chế Tài Chính (Institutional-grade Palette)
    - Tách biệt hoàn toàn Màu Thương Hiệu (Cobalt/Royal Blue) khỏi màu Trần/Sàn của TTCK Việt Nam.
    - Đảm bảo tỷ lệ tương phản WCAG 2.1 AA (>= 4.5:1) ở cả Light và Dark Mode.
    """
    mode = get_theme_mode()
    if mode == "DARK":
        res = {
            "mode": "DARK",
            "bg_app": "#0B0F19",          # Institutional Deep Obsidian Slate
            "bg_card": "#111827",         # Dark Slate Card
            "bg_card_glass": "rgba(17, 24, 39, 0.92)",
            "bg_subtle": "rgba(30, 41, 59, 0.70)",
            "bg_sidebar": "linear-gradient(180deg, #0F172A 0%, #0B0F19 100%)",
            "text_heading": "#F8FAFC",    # Trắng sắc nét (Contrast 17.5:1)
            "text_body": "#E2E8F0",       # Xám bạc sáng (Contrast 14.1:1)
            "text_muted": "#94A3B8",      # Slate dịu mắt (Contrast 6.4:1 - Đạt WCAG AA)
            "chart_tick": "#CBD5E1",      # Bạc sáng rõ nét trên nền tối
            "chart_title": "#F8FAFC",     # Trắng sáng tiêu đề đồ thị
            "chart_bar_peer": "#334155",  # Cột so sánh bạn bè (Slate 700)
            "border_color": "rgba(59, 130, 246, 0.24)", # Viền Royal Blue tinh tế
            "border_glass": "rgba(59, 130, 246, 0.35)",
            "grid_color": "#1E293B",
            "plot_bg": "#0F172A",
            "color_brand": "#3B82F6",     # Institutional Royal Blue
            "color_brand_led": "#60A5FA",
            "accent_cyan": "#0284C7",     # Ocean Blue
            "accent_pink": "#EC4899",
            # Bộ màu ngữ nghĩa TTCK Việt Nam (Tối ưu tương phản Dark Mode)
            "color_ceiling": "#A855F7",   # Tím trần
            "color_up": "#10B981",        # Xanh lá tăng giá (Emerald)
            "color_warn": "#F59E0B",      # Vàng tham chiếu / Cảnh báo (Amber)
            "color_down": "#F43F5E",      # Đỏ giảm giá (Rose Red)
            "color_floor": "#06B6D4",     # Xanh lơ sàn
            "shadow_color": "rgba(0, 0, 0, 0.60)",
            "graph_bg": "#1E293B",
            "hero_bg": "linear-gradient(90deg, #1E293B 0%, #0F172A 100%)",
            "hero_border": "1px solid rgba(59, 130, 246, 0.35)",
            "hero_shadow": "0 8px 24px rgba(0, 0, 0, 0.50)",
        }
    else:
        res = {
            "mode": "LIGHT",
            "bg_app": "#F8FAFC",          # Cool Alabaster White
            "bg_card": "#FFFFFF",         # Trắng tinh khiết
            "bg_card_glass": "rgba(255, 255, 255, 0.95)",
            "bg_subtle": "#F1F5F9",
            "bg_sidebar": "linear-gradient(180deg, #FFFFFF 0%, #F1F5F9 100%)",
            "text_heading": "#0F172A",    # Slate cực đậm (Contrast 17.8:1)
            "text_body": "#1E293B",       # Slate đậm (Contrast 13.5:1)
            "text_muted": "#334155",      # Slate 700 đậm đà (Contrast 9.5:1 - Cực rõ)
            "chart_tick": "#0F172A",      # Slate 900 - Chữ trục đồ thị đen đậm rõ nét 100%
            "chart_title": "#0F172A",     # Slate 900 - Tiêu đề trục và đồ thị
            "chart_bar_peer": "#94A3B8",  # Cột so sánh bạn bè (Slate 400 - Tương phản rõ trên nền trắng)
            "border_color": "#E2E8F0",
            "border_glass": "rgba(226, 232, 240, 0.95)",
            "grid_color": "#E2E8F0",
            "plot_bg": "#FFFFFF",
            "color_brand": "#2563EB",     # Institutional Cobalt Blue
            "color_brand_led": "#1D4ED8",
            "accent_cyan": "#0369A1",
            "accent_pink": "#DB2777",
            # Bộ màu ngữ nghĩa TTCK Việt Nam (Tối ưu tương phản Light Mode - Không bị tàng hình!)
            "color_ceiling": "#7E22CE",   # Tím đậm trần
            "color_up": "#059669",        # Xanh Emerald đậm (Contrast 4.8:1 trên trắng)
            "color_warn": "#D97706",      # Cam vàng đậm (Contrast 4.6:1 trên trắng)
            "color_down": "#DC2626",      # Đỏ đậm
            "color_floor": "#0891B2",     # Xanh lơ đậm sàn
            "shadow_color": "rgba(15, 23, 42, 0.06)",
            "graph_bg": "#F8FAFC",
            "hero_bg": "#FFFFFF",
            "hero_border": "1px solid #E2E8F0",
            "hero_shadow": "0 4px 16px rgba(15, 23, 42, 0.05)",
        }
    # Thêm aliases linh hoạt tránh KeyError
    res["card_bg"] = res["bg_card"]
    res["border"] = res["border_color"]
    res["brand"] = res["color_brand"]
    res["brand_led"] = res["color_brand_led"]
    return res


def apply_global_theme():
    """Áp dụng bộ CSS theme toàn cục phản ứng động theo trạng thái LIGHT / DARK."""
    pal = get_theme_palette()
    is_light = (pal["mode"] == "LIGHT")
    
    # Chuẩn bị các giá trị CSS động tránh lỗi lồng nhau trong f-string
    sec_btn_hover_color = "#1D4ED8" if is_light else "#FFFFFF"
    sec_btn_hover_bg = "#EFF6FF" if is_light else "rgba(59, 130, 246, 0.22)"
    
    radio_hover_css = (
        "background-color: #F8FAFC !important; border-color: #2563EB !important; color: #1D4ED8 !important; transform: translateX(2px);"
        if is_light else
        "border-color: #60A5FA !important; color: #FFFFFF !important; transform: translateX(2px);"
    )
    radio_checked_css = (
        "background: #EFF6FF !important; background-color: #EFF6FF !important; border: 1.5px solid #2563EB !important; box-shadow: 0 2px 10px rgba(37, 99, 235, 0.18) !important; color: #1D4ED8 !important; font-weight: 700 !important;"
        if is_light else
        "background: rgba(59, 130, 246, 0.25) !important; background-color: rgba(59, 130, 246, 0.25) !important; border: 1.5px solid #3B82F6 !important; box-shadow: 0 0 14px rgba(59, 130, 246, 0.40) !important; color: #FFFFFF !important; font-weight: 700 !important;"
    )
    
    slider_thumb_bg = "#FFFFFF" if is_light else "radial-gradient(circle, #FFFFFF 30%, #3B82F6 100%)"
    slider_thumb_border = "2.5px solid #2563EB" if is_light else "2px solid #FFFFFF"
    slider_thumb_shadow = "0 2px 8px rgba(37, 99, 235, 0.35)" if is_light else "0 0 14px rgba(59, 130, 246, 0.95)"
    
    dropdown_opt_active_bg = "#EFF6FF" if is_light else "rgba(59, 130, 246, 0.25)"
    dropdown_opt_active_color = "#1D4ED8" if is_light else "#FFFFFF"
    
    tag_bg = "#EFF6FF" if is_light else "#1E293B"
    tag_border = "#BFDBFE" if is_light else "rgba(59, 130, 246, 0.4)"
    tag_color = "#1D4ED8" if is_light else "#93C5FD"
    
    expander_hover_bg = "#EFF6FF" if is_light else "rgba(59, 130, 246, 0.15)"
    # Glide Data Grid renders on <canvas> using Streamlit's base="dark" config palette;
    # in Light Mode, invert + hue-rotate turns the dark table surface into a crisp light table.
    dataframe_filter = (
        "filter: invert(0.95) hue-rotate(180deg) saturate(1.12) contrast(1.04) !important;"
        if is_light else
        "filter: none !important;"
    )

    # Cấu hình Segmented Control Tabs (Nút bấm chuyển tab nổi 3D)
    tab_list_bg = "#F1F5F9" if is_light else "rgba(15, 23, 42, 0.75)"
    tab_list_border = "#CBD5E1" if is_light else "rgba(59, 130, 246, 0.28)"
    tab_btn_bg = "#FFFFFF" if is_light else "rgba(30, 41, 59, 0.85)"
    tab_btn_border = "#CBD5E1" if is_light else "rgba(255, 255, 255, 0.12)"
    tab_btn_color = "#334155" if is_light else "#E2E8F0"
    tab_btn_hover_bg = "#EFF6FF" if is_light else "rgba(59, 130, 246, 0.20)"
    tab_btn_hover_border = "#2563EB" if is_light else "#60A5FA"
    tab_btn_hover_color = "#1D4ED8" if is_light else "#FFFFFF"
    
    tab_active_bg = "linear-gradient(135deg, #1D4ED8 0%, #2563EB 100%)" if is_light else "linear-gradient(135deg, #1E40AF 0%, #2563EB 50%, #3B82F6 100%)"
    tab_active_border = "#1D4ED8" if is_light else "#60A5FA"
    tab_active_shadow = "0 3px 12px rgba(37, 99, 235, 0.35)" if is_light else "0 3px 14px rgba(59, 130, 246, 0.50)"

    nav_active_bg = "linear-gradient(90deg, rgba(37, 99, 235, 0.12) 0%, rgba(37, 99, 235, 0.04) 100%)" if is_light else "linear-gradient(90deg, rgba(59, 130, 246, 0.22) 0%, rgba(59, 130, 246, 0.08) 100%)"
    nav_active_border = "#2563EB" if is_light else "#60A5FA"
    nav_active_color = "#1D4ED8" if is_light else "#93C5FD"
    nav_tile_shadow = "0 1px 3px rgba(15, 23, 42, 0.08)" if is_light else "0 2px 6px rgba(0, 0, 0, 0.45)"
    nav_hover_shadow = "0 4px 16px rgba(37, 99, 235, 0.16)" if is_light else "0 4px 18px rgba(59, 130, 246, 0.35)"
    nav_active_shadow = "0 3px 12px rgba(37, 99, 235, 0.22)" if is_light else "0 3px 14px rgba(59, 130, 246, 0.40)"

    css = f"""
    <style>
        /* 1. CSS VARIABLES DÙNG CHUNG */
        :root {{
            --bg-app: {pal["bg_app"]};
            --bg-card: {pal["bg_card"]};
            --bg-card-glass: {pal["bg_card_glass"]};
            --text-heading: {pal["text_heading"]};
            --text-body: {pal["text_body"]};
            --text-muted: {pal["text_muted"]};
            --border-color: {pal["border_color"]};
            --border-glass: {pal["border_glass"]};
            --color-brand: {pal["color_brand"]};
            --color-brand-led: {pal["color_brand_led"]};
            --accent-cyan: {pal["accent_cyan"]};
            --accent-pink: {pal["accent_pink"]};
            --shadow-color: {pal["shadow_color"]};
        }}

        /* KEYFRAME ANIMATIONS DÀNH CHO WORKSTATION CHUYÊN NGHIỆP */
        @keyframes pulseGlow {{
            0% {{
                transform: scale(0.95);
                opacity: 0.65;
            }}
            50% {{
                transform: scale(1.2);
                opacity: 1;
            }}
            100% {{
                transform: scale(0.95);
                opacity: 0.65;
            }}
        }}

        @keyframes cardReveal {{
            from {{
                opacity: 0.88;
                transform: translateY(6px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        @keyframes subtleShimmer {{
            0% {{ background-position: -150% 0; }}
            100% {{ background-position: 150% 0; }}
        }}

        /* 2. NỀN & FONT TOÀN BỘ ỨNG DỤNG - KHÔNG LÀM HỎNG ICON CỦA STREAMLIT */
        html, body, .stApp, p, label, input, select, textarea, h1, h2, h3, h4, h5, h6 {{
            font-family: {FONT_FAMILY};
        }}

        /* BẢO TOÀN BIỂU TƯỢNG VÀ MŨI TÊN STREAMLIT */
        [data-testid="stIcon"], 
        [data-testid="stSidebarCollapseButton"] *,
        [data-testid="stExpandSidebarButton"] *,
        [data-testid="collapsedControl"] *,
        button[kind="headerNoPadding"] *,
        [class*="material-symbols"], 
        [class*="material-icons"], 
        button span[class*="material"],
        span[class*="material"] {{
            font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
            font-feature-settings: 'liga' 1;
            text-rendering: optimizeLegibility;
        }}

        html, body, .stApp, [data-testid="stApp"],
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > .main,
        [data-testid="stMain"], .stMain,
        [data-testid="stBottom"], [data-testid="stBottomBlockContainer"] {{
            background: var(--bg-app) !important;
            background-color: var(--bg-app) !important;
            color: var(--text-body) !important;
            transition: background-color 0.25s ease, color 0.25s ease;
        }}

        /* STREAMLIT TOP HEADER */
        header[data-testid="stHeader"],
        [data-testid="stHeader"],
        .stAppHeader {{
            background: var(--bg-app) !important;
            background-color: var(--bg-app) !important;
            border-bottom: 1px solid var(--border-color) !important;
            height: 3.75rem !important;
            z-index: 99 !important;
            color: var(--text-heading) !important;
        }}

        [data-testid="stHeader"] button,
        [data-testid="stHeader"] svg,
        [data-testid="stToolbar"] button,
        [data-testid="stToolbar"] svg,
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapseButton"] *,
        [data-testid="stSidebarCollapseButton"] span,
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stExpandSidebarButton"],
        [data-testid="stExpandSidebarButton"] *,
        [data-testid="stExpandSidebarButton"] span,
        [data-testid="stExpandSidebarButton"] svg {{
            color: var(--text-heading) !important;
            fill: var(--text-heading) !important;
            opacity: 1 !important;
            visibility: visible !important;
        }}

        /* ẨN NÚT DEPLOY CỦA STREAMLIT COMMUNITY CLOUD TRÊN HỆ THỐNG NỘI BỘ */
        .stDeployButton,
        [data-testid="stDeployButton"],
        .stAppDeployButton,
        [data-testid="stAppDeployButton"] {{
            display: none !important;
        }}

        footer {{visibility: hidden;}}

        .block-container,
        [data-testid="stMainBlockContainer"] {{
            padding-top: 4.5rem !important;
            padding-bottom: 2.5rem !important;
            padding-left: 1.75rem !important;
            padding-right: 1.75rem !important;
        }}

        /* 3. SIDEBAR TOÀN DIỆN: ĐỒNG BỘ 100% NỀN CẢ LIGHT VÀ DARK MODE, KHÔNG ĐÈ NỘI DUNG */
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarContent"],
        [data-testid="stSidebarUserContent"],
        .stSidebar,
        .stSidebar > div:first-child {{
            background: {pal["bg_sidebar"]} !important;
            background-color: {pal["bg_app"]} !important;
            color: var(--text-body) !important;
        }}

        section[data-testid="stSidebar"] {{
            border-right: 1px solid var(--border-color) !important;
            box-shadow: 4px 0 24px var(--shadow-color) !important;
        }}

        section[data-testid="stSidebar"][data-collapsed="false"] {{
            min-width: 260px;
            max-width: 320px;
        }}

        /* KHI SIDEBAR ĐÓNG: CHO PHÉP THU GỌN HOÀN TOÀN VỀ 0, KHÔNG ĐỂ LẠI KHOẢNG TRẮNG */
        section[data-testid="stSidebar"][data-collapsed="true"],
        section[data-testid="stSidebar"][aria-expanded="false"] {{
            min-width: 0 !important;
            width: 0 !important;
            border-right: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stSidebar"] h1, 
        [data-testid="stSidebar"] h2, 
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4 {{
            color: var(--text-heading) !important;
            font-weight: 700 !important;
        }}

        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] label p,
        [data-testid="stSidebar"] .stMarkdown p {{
            color: var(--text-heading) !important;
            font-weight: 600 !important;
        }}

        /* 4. TYPOGRAPHY TIÊU ĐỀ & NỘI DUNG */
        h1, h2, h3, h4, h5, h6,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h4,
        [data-testid="stMarkdownContainer"] h5,
        [data-testid="stMarkdownContainer"] h6,
        [data-testid="stHeadingWithActionElements"] * {{
            color: var(--text-heading) !important;
            font-weight: 700 !important;
            letter-spacing: -0.3px;
        }}

        .stApp p, .stApp label, .stMarkdown, .stText,
        [data-testid="stMain"] p, [data-testid="stMain"] li,
        [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
            color: var(--text-body);
            line-height: 1.68 !important;
            font-size: 13.5px;
        }}

        [data-testid="stCheckbox"] label,
        [data-testid="stCheckbox"] p,
        [data-testid="stToggle"] label,
        [data-testid="stToggle"] p {{
            color: var(--text-heading) !important;
        }}

        /* ĐỊNH DẠNG CÔNG THỨC TOÁN HỌC (KATEX & CODE SPAN) */
        code {{
            background: rgba(59, 130, 246, 0.12) !important;
            color: var(--color-brand) !important;
            border: 1px solid rgba(59, 130, 246, 0.25) !important;
            padding: 2px 6px !important;
            border-radius: 4px !important;
            font-weight: 600 !important;
            font-family: 'Consolas', 'Monaco', monospace !important;
        }}

        .katex, .katex-display {{
            color: var(--text-heading) !important;
        }}
        .katex-display {{
            margin: 10px 0 14px 0 !important;
            padding: 8px 16px !important;
            background: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 10px !important;
            box-shadow: 0 2px 6px var(--shadow-color) !important;
        }}

        /* 5. HERO BANNERS & CARD CONTAINERS */
        .hero-banner {{
            background: {pal["hero_bg"]} !important;
            padding: 22px 28px !important;
            border-radius: 14px !important;
            border: {pal["hero_border"]} !important;
            box-shadow: {pal["hero_shadow"]} !important;
            margin-bottom: 20px !important;
            border-left: 5px solid var(--color-brand-led) !important;
        }}

        .hero-banner h1, .hero-banner h2 {{
            color: var(--text-heading) !important;
            margin: 0 0 6px 0 !important;
            font-size: 22px !important;
            font-weight: 800 !important;
        }}

        .hero-banner p {{
            color: var(--text-muted) !important;
            margin: 0 !important;
            font-size: 13.5px !important;
            line-height: 1.6 !important;
        }}

        /* 6. NÚT BẤM (BUTTONS) */
        .stButton > button,
        .stButton > button p,
        .stButton > button span,
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-primary"] p,
        [data-testid="stBaseButton-primary"] span {{
            color: #FFFFFF !important;
        }}

        .stButton > button,
        [data-testid="stBaseButton-primary"] {{
            background: linear-gradient(135deg, var(--color-brand) 0%, var(--color-brand-led) 100%) !important;
            font-weight: 700 !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            padding: 9px 20px !important;
            box-shadow: 0 4px 14px var(--shadow-color) !important;
            transition: all 0.2s ease-in-out !important;
        }}

        [data-testid="stSidebar"] .stButton > button {{
            padding: 7px 10px !important;
            font-size: 13px !important;
            white-space: nowrap !important;
            min-width: 0 !important;
        }}

        .stButton > button:hover,
        [data-testid="stBaseButton-primary"]:hover {{
            background: linear-gradient(135deg, var(--color-brand) 0%, var(--color-brand-led) 100%) !important;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
            transform: translateY(-1px);
            color: #FFFFFF !important;
            border-color: rgba(255, 255, 255, 0.3) !important;
        }}

        .stButton > button[kind="secondary"],
        .stButton > button[kind="secondary"] p,
        .stButton > button[kind="secondary"] span,
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-secondary"] p,
        [data-testid="stBaseButton-secondary"] span {{
            color: var(--text-heading) !important;
        }}

        .stButton > button[kind="secondary"],
        [data-testid="stBaseButton-secondary"] {{
            background: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: none !important;
        }}

        .stButton > button[kind="secondary"]:hover,
        .stButton > button[kind="secondary"]:hover p,
        .stButton > button[kind="secondary"]:hover span,
        [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stBaseButton-secondary"]:hover p,
        [data-testid="stBaseButton-secondary"]:hover span {{
            color: {sec_btn_hover_color} !important;
        }}

        .stButton > button[kind="secondary"]:hover,
        [data-testid="stBaseButton-secondary"]:hover {{
            border-color: var(--color-brand-led) !important;
            background: {sec_btn_hover_bg} !important;
        }}

        /* 7. RADIO SELECTION & MENU NAVIGATION (LINEAR / STRIPE MODERN STYLE) */
        div.stRadio > div {{
            gap: 6px !important;
        }}

        /* ẨN HOÀN TOÀN LABEL TIÊU ĐỀ CỦA ST.RADIO */
        div[data-testid="stRadio"] > label,
        div[data-testid="stRadio"] [data-testid="stWidgetLabel"],
        div.stRadio > label {{
            display: none !important;
            width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0 !important;
            visibility: hidden !important;
            position: absolute !important;
            pointer-events: none !important;
        }}

        /* TRIỆT TIÊU HOÀN TOÀN CÁC VÒNG TRÒN / CHẤM ĐEN RADIO MẶC ĐỊNH TRONG SIDEBAR */
        section[data-testid="stSidebar"] div[data-testid="stRadio"] label > div > div:first-child:not([data-testid="stMarkdownContainer"]),
        section[data-testid="stSidebar"] div[data-testid="stRadio"] [class*="e1dm8mpf4"],
        section[data-testid="stSidebar"] div[data-testid="stRadio"] [data-baseweb="radio"] > div:first-child,
        section[data-testid="stSidebar"] div.stRadio [data-baseweb="radio"] > div:first-child,
        section[data-testid="stSidebar"] div[data-testid="stRadio"] input[type="radio"],
        section[data-testid="stSidebar"] div.stRadio input[type="radio"],
        section[data-testid="stSidebar"] div[data-testid="stRadio"] svg,
        section[data-testid="stSidebar"] div.stRadio svg {{
            display: none !important;
            width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            opacity: 0 !important;
            visibility: hidden !important;
            position: absolute !important;
            pointer-events: none !important;
        }}

        /* BẢO ĐẢM CONTAINER TEXT CỦA RADIO VÀ CHECKBOX LUÔN HIỂN THỊ ĐẦY ĐỦ */
        div[data-testid="stRadio"] [data-testid="stMarkdownContainer"],
        div.stRadio [data-testid="stMarkdownContainer"],
        div[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] {{
            display: block !important;
            width: 100% !important;
            opacity: 1 !important;
            visibility: visible !important;
        }}

        div[data-testid="stRadio"] div[data-testid="stMarkdownContainer"] p,
        div.stRadio div[data-testid="stMarkdownContainer"] p {{
            display: block !important;
            margin: 0 !important;
            padding: 0 !important;
            font-size: 12.5px !important;
            line-height: 1.35 !important;
            color: inherit !important;
            white-space: normal !important;
            word-break: break-word !important;
            overflow: visible !important;
        }}

        div[data-testid="stCheckbox"] div[data-testid="stMarkdownContainer"] p {{
            margin: 0 !important;
            padding: 0 !important;
            font-size: 13px !important;
            line-height: 1.4 !important;
            color: inherit !important;
            white-space: nowrap !important;
            overflow: visible !important;
        }}

        /* ----------------------------------------------------------------- */
        /* NÚT THẺ PHÂN HỆ NAVIGATION DẠNG Ô BẤM (INTERACTIVE TILES & SLIDE) */
        /* ----------------------------------------------------------------- */
        section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] {{
            gap: 6px !important;
            display: flex !important;
            flex-direction: column !important;
        }}

        section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label,
        div[data-testid="stRadio"] div[role="radiogroup"] > label,
        div.stRadio div[role="radiogroup"] > label,
        div[data-testid="stRadio"] [role="radiogroup"] > label {{
            background: var(--bg-card) !important;
            padding: 9px 12px !important;
            margin-bottom: 2px !important;
            border-radius: 8px !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: {nav_tile_shadow} !important;
            color: var(--text-body) !important;
            font-weight: 600 !important;
            font-size: 12.5px !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            cursor: pointer !important;
            border-left: 3.5px solid transparent !important;
            display: flex !important;
            align-items: center !important;
            position: relative !important;
            user-select: none !important;
            overflow: hidden !important;
        }}

        section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:hover,
        div[data-testid="stRadio"] div[role="radiogroup"] > label:hover,
        div.stRadio div[role="radiogroup"] > label:hover {{
            background: {tab_btn_hover_bg} !important;
            border-color: {nav_active_border} !important;
            border-left: 3.5px solid {nav_active_border} !important;
            color: {nav_active_color} !important;
            transform: translateX(4px) scale(1.005) !important;
            box-shadow: {nav_hover_shadow} !important;
        }}

        section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked),
        div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked),
        div.stRadio div[role="radiogroup"] > label:has(input:checked) {{
            background: {nav_active_bg} !important;
            border-color: {nav_active_border} !important;
            border-left: 4.5px solid {nav_active_border} !important;
            color: {nav_active_color} !important;
            font-weight: 700 !important;
            transform: translateX(3px) !important;
            box-shadow: {nav_active_shadow} !important;
        }}

        /* LED Indicator trên thẻ phân hệ đang active */
        section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked)::after {{
            content: "●";
            position: absolute;
            right: 12px;
            font-size: 11px;
            color: {nav_active_border};
            filter: drop-shadow(0 0 5px {nav_active_border});
            animation: pulseGlow 1.8s infinite;
        }}

        section[data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:active,
        div[data-testid="stRadio"] div[role="radiogroup"] > label:active {{
            transform: scale(0.98) !important;
        }}

        div[data-testid="stRadio"] div[data-testid="stMarkdownContainer"] p,
        div.stRadio div[data-testid="stMarkdownContainer"] p {{
            margin: 0 !important;
            padding: 0 !important;
            font-size: 13px !important;
            line-height: 1.4 !important;
            color: inherit !important;
            font-weight: inherit !important;
        }}

        /* 8. SLIDER */
        div[data-baseweb="slider"] div[role="slider"] {{
            background: {slider_thumb_bg} !important;
            border: {slider_thumb_border} !important;
            box-shadow: {slider_thumb_shadow} !important;
            width: 20px !important;
            height: 20px !important;
            cursor: pointer !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}

        div[data-baseweb="slider"] div[role="slider"]:hover {{
            transform: scale(1.25);
            box-shadow: 0 0 16px var(--color-brand-led) !important;
        }}

        div[data-baseweb="slider"] div[data-testid="stSliderTickBar"] {{
            background: var(--color-brand) !important;
        }}

        [data-testid="stSlider"] div,
        [data-testid="stSlider"] p,
        [data-testid="stSliderTickBarMin"],
        [data-testid="stSliderTickBarMax"] {{
            color: var(--text-body) !important;
        }}

        /* 9. INPUTS, SELECTBOX, MULTISELECT, SEARCH & DROPDOWNS (STREAMLIT 1.66 EMOTION + BASEWEB) */
        div[data-testid="stSelectbox"],
        div.stSelectbox,
        div[data-testid="stMultiSelect"],
        div.stMultiSelect {{
            background: transparent !important;
            background-color: transparent !important;
        }}

        /* Hộp điều khiển Selectbox Streamlit 1.66 (e1oobldh0) & BaseWeb Containers - TRIỆT TIÊU Ô ĐEN TRÊN NỀN SÁNG */
        div[data-testid="stSelectbox"] [class*="e1oobldh0"],
        div.stSelectbox [class*="e1oobldh0"],
        div[data-testid="stSelectbox"] > div:last-child,
        div.stSelectbox > div:last-child,
        div[data-testid="stSelectbox"] > div:not([data-testid="stWidgetLabel"]),
        div[data-testid="stMultiSelect"] > div:last-child,
        div[data-baseweb="select"],
        div[data-baseweb="select"] > div,
        div[data-baseweb="select"] > div > div,
        div[data-testid="stTextInputRootElement"],
        div[data-testid="stNumberInputRootElement"],
        div[data-testid="stTextAreaRootElement"],
        div[class*="e1bh1cux0"],
        div[class*="e1gm8nhx0"],
        div[data-baseweb="input"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"] {{
            background-color: var(--bg-card) !important;
            background: var(--bg-card) !important;
            border-radius: 10px !important;
            border: 1px solid var(--border-color) !important;
            color: var(--text-heading) !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
        }}

        /* Trạng thái Hover & Focus của Selectbox & Inputs */
        div[data-testid="stSelectbox"] [class*="e1oobldh0"]:hover,
        div[data-testid="stSelectbox"] [class*="e1oobldh0"]:focus-within,
        div[data-testid="stSelectbox"] > div:last-child:hover,
        div[data-testid="stSelectbox"] > div:last-child:focus-within,
        div[data-baseweb="select"]:hover > div,
        div[data-baseweb="select"]:focus-within > div,
        div[data-testid="stTextInputRootElement"]:hover,
        div[data-testid="stTextInputRootElement"]:focus-within,
        div[class*="e1bh1cux0"]:hover,
        div[class*="e1bh1cux0"]:focus-within,
        div[class*="e1gm8nhx0"]:hover,
        div[class*="e1gm8nhx0"]:focus-within {{
            border-color: var(--color-brand) !important;
            box-shadow: 0 0 0 1.5px var(--color-brand) !important;
        }}

        /* Giá trị Text, Input và Spans bên trong */
        div[data-testid="stSelectbox"] [class*="e1oobldh1"],
        div.stSelectbox [class*="e1oobldh1"],
        div[data-testid="stSelectbox"] input,
        div.stSelectbox input,
        div[data-baseweb="select"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] [role="combobox"],
        div[data-testid="stTextInput"] input,
        div.stTextInput input,
        input[data-testid="stTextInputField"],
        div[data-testid="stTextInputRootElement"] input,
        div[class*="e1bh1cux0"] input,
        div[class*="e1gm8nhx0"] input,
        div[data-baseweb="input"] input,
        input[type="text"],
        input[type="search"],
        input[type="number"],
        textarea {{
            color: var(--text-heading) !important;
            background-color: transparent !important;
            background: transparent !important;
            -webkit-text-fill-color: var(--text-heading) !important;
            font-size: 13.5px !important;
            font-weight: 600 !important;
        }}

        /* Biểu tượng Mũi tên Dropdown Chevron */
        div[data-testid="stSelectbox"] [class*="e1oobldh2"] svg,
        div[data-testid="stSelectbox"] svg,
        div.stSelectbox svg,
        div[data-baseweb="select"] svg,
        div[data-testid="stTextInputRootElement"] svg,
        div[data-testid="stTextInput"] svg {{
            fill: var(--text-heading) !important;
            color: var(--text-heading) !important;
        }}

        /* Biểu tượng Clear Icon */
        div[data-testid="stSelectbox"] [class*="e1oobldh3"] svg {{
            fill: var(--text-muted) !important;
        }}

        input::placeholder,
        textarea::placeholder {{
            color: var(--text-muted) !important;
            -webkit-text-fill-color: var(--text-muted) !important;
        }}

        label[data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] {{
            color: var(--text-heading) !important;
            font-weight: 600 !important;
            font-size: 13px !important;
        }}

        /* BẢNG MENU VÀ DROPDOWN POPOVER (STREAMLIT 1.66: e1oobldh4, e1oobldh5 + BASEWEB) */
        div[class*="e1oobldh4"],
        ul[class*="e1oobldh5"],
        div[data-testid="stSelectboxVirtualDropdown"],
        ul[data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] > div,
        div[data-baseweb="menu"],
        ul[role="menu"],
        div[role="menu"],
        ul[role="listbox"],
        [data-testid="stMainMenuPopover"] {{
            background-color: var(--bg-card) !important;
            background: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            box-shadow: 0 10px 32px var(--shadow-color) !important;
            padding: 6px !important;
        }}

        ul[class*="e1oobldh5"] {{
            padding: 4px !important;
        }}

        /* Các mục lựa chọn trong dropdown */
        li[class*="e1oobldh7"],
        li[class*="e1oobldh7"] > div,
        div[class*="e1oobldh8"],
        li[role="option"],
        div[role="option"],
        ul[role="listbox"] li,
        div[data-baseweb="menu"] li,
        div[data-testid="stSelectboxVirtualDropdown"] li {{
            background: transparent !important;
            background-color: transparent !important;
            color: var(--text-body) !important;
            -webkit-text-fill-color: var(--text-body) !important;
            border-radius: 6px !important;
            padding: 8px 12px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            transition: background 0.15s ease, color 0.15s ease !important;
        }}

        /* Hiệu ứng Hover và Selected trong dropdown menu */
        li[class*="e1oobldh7"]:hover,
        li[class*="e1oobldh7"]:hover div[class*="e1oobldh8"],
        li[class*="e1oobldh7"][aria-selected="true"],
        li[class*="e1oobldh7"][aria-selected="true"] div[class*="e1oobldh8"],
        li[role="option"]:hover,
        li[role="option"][aria-selected="true"],
        ul[role="listbox"] li:hover,
        ul[role="listbox"] li[aria-selected="true"],
        div[data-baseweb="menu"] li:hover {{
            background: {dropdown_opt_active_bg} !important;
            background-color: {dropdown_opt_active_bg} !important;
            color: {dropdown_opt_active_color} !important;
            -webkit-text-fill-color: {dropdown_opt_active_color} !important;
            font-weight: 700 !important;
        }}

        /* MULTISELECT TAGS */
        div[data-baseweb="tag"] {{
            background-color: {tag_bg} !important;
            border: 1px solid {tag_border} !important;
            border-radius: 6px !important;
        }}
        div[data-baseweb="tag"] span {{
            color: {tag_color} !important;
            font-weight: 600 !important;
        }}
        div[data-baseweb="tag"] svg {{
            fill: {tag_color} !important;
        }}

        /* TABS PHÂN HỆ & GÓC NHÌN (SEGMENTED CONTROL CHUẨN STRIPE / BLOOMBERG) */
        div[data-testid="stTabs"] {{
            background: transparent !important;
            margin-top: 6px !important;
            margin-bottom: 16px !important;
            width: 100% !important;
        }}
        /* Khung viền bọc hàng nút Tabs (tự động co giãn & xuống dòng gọn gàng nếu hẹp, không bị cắt chữ) */
        div[data-testid="stTabs"] div[role="tablist"],
        div[data-baseweb="tab-list"] {{
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 4px !important;
            background: {tab_list_bg} !important;
            border: 1px solid {tab_list_border} !important;
            border-radius: 10px !important;
            padding: 4px !important;
            width: 100% !important;
            max-width: 100% !important;
            box-shadow: 0 1px 3px var(--shadow-color) !important;
            align-items: center !important;
            overflow-x: visible !important;
            scrollbar-width: none !important;
        }}
        div[data-testid="stTabs"] div[role="tablist"]::-webkit-scrollbar,
        div[data-baseweb="tab-list"]::-webkit-scrollbar {{
            display: none !important;
        }}
        /* Từng nút Tab bấm được - Sizing tự nhiên theo nội dung, không đè chữ */
        div[data-testid="stTabs"] div[role="tab"],
        div[data-testid="stTabs"] div[data-testid="stTab"],
        button[data-baseweb="tab"] {{
            flex: 0 0 auto !important;
            background: transparent !important;
            border: none !important;
            border-radius: 7px !important;
            color: {tab_btn_color} !important;
            font-weight: 600 !important;
            font-size: 12.5px !important;
            padding: 7px 12px !important;
            cursor: pointer !important;
            box-shadow: none !important;
            transition: all 0.18s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            user-select: none !important;
            white-space: nowrap !important;
            text-align: center !important;
        }}
        div[data-testid="stTabs"] div[role="tab"] p,
        div[data-testid="stTabs"] div[role="tab"] span,
        button[data-baseweb="tab"] p,
        button[data-baseweb="tab"] span {{
            font-size: 13px !important;
            font-weight: 600 !important;
            color: inherit !important;
            margin: 0 !important;
            white-space: nowrap !important;
        }}
        /* Hiệu ứng rê chuột (Hover) */
        div[data-testid="stTabs"] div[role="tab"]:hover,
        button[data-baseweb="tab"]:hover {{
            background: {tab_btn_hover_bg} !important;
            color: {tab_btn_hover_color} !important;
            transform: none !important;
        }}
        /* Nút Tab đang kích hoạt (Active) */
        div[data-testid="stTabs"] div[role="tab"][aria-selected="true"],
        button[data-baseweb="tab"][aria-selected="true"] {{
            background: {tab_active_bg} !important;
            border: none !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            box-shadow: {tab_active_shadow} !important;
            transform: none !important;
        }}
        div[data-testid="stTabs"] div[role="tab"][aria-selected="true"] p,
        div[data-testid="stTabs"] div[role="tab"][aria-selected="true"] span,
        button[data-baseweb="tab"][aria-selected="true"] p,
        button[data-baseweb="tab"][aria-selected="true"] span {{
            color: #FFFFFF !important;
            font-weight: 700 !important;
        }}
        /* Triệt tiêu hoàn toàn thanh gạch chân và nút cuộn mũi tên đè lên tabs */
        div[data-testid="stTabs"] .react-aria-SelectionIndicator,
        div[data-baseweb="tab-highlight"],
        div[data-baseweb="tab-border"],
        div[data-testid="stTabs"] button[aria-label*="Scroll"],
        div[data-testid="stTabs"] button[aria-label*="scroll"],
        button[aria-label*="Scroll tabs right"],
        button[aria-label*="Scroll tabs left"],
        button[aria-label*="Scroll tabs"],
        button[aria-label*="scroll"],
        div[data-baseweb="tabs"] button[aria-label*="Scroll"],
        div[data-baseweb="tab-list"] > button:not([role="tab"]),
        div[data-testid="stTabs"] button:not([role="tab"]) {{
            display: none !important;
            width: 0 !important;
            height: 0 !important;
            opacity: 0 !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }}

        /* METRICS SỐ LIỆU & KPI HUDS CÓ HIỆU ỨNG TƯƠNG TÁC THẺ */
        div[data-testid="stMetric"] {{
            background-color: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            padding: 14px 18px !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
            animation: cardReveal 0.25s ease-out !important;
        }}
        div[data-testid="stMetric"]:hover {{
            transform: translateY(-3px) scale(1.01) !important;
            box-shadow: 0 8px 24px var(--shadow-color) !important;
            border-color: var(--color-brand) !important;
        }}

        /* KHUNG ĐỒ THỊ CHUẨN TƯƠNG TÁC WORKSTATION */
        div[data-testid="stPlotlyChart"],
        div[data-testid="stPlotlyChart"] > div {{
            max-width: 100% !important;
            width: 100% !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
        }}
        div[data-testid="stPlotlyChart"] {{
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            padding: 6px !important;
            background: var(--bg-card) !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            transition: border-color 0.22s ease, box-shadow 0.22s ease !important;
        }}
        div[data-testid="stPlotlyChart"]:hover {{
            border-color: rgba(37, 99, 235, 0.35) !important;
            box-shadow: 0 6px 20px var(--shadow-color) !important;
        }}
        div[data-testid="stMetricLabel"] p {{
            color: var(--text-muted) !important;
            font-size: 12.5px !important;
            font-weight: 600 !important;
        }}
        div[data-testid="stMetricValue"] div {{
            color: var(--text-heading) !important;
            font-weight: 800 !important;
            font-size: 24px !important;
        }}

        /* THÔNG BÁO ALERTS */
        div[data-testid="stAlert"],
        div[data-testid="stAlertContainer"],
        div[role="alert"] {{
            background-color: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 10px !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            color: var(--text-body) !important;
        }}
        div[data-testid="stAlert"] p,
        div[data-testid="stAlertContainer"] p,
        div[role="alert"] p {{
            color: var(--text-body) !important;
            font-size: 13px !important;
        }}

        /* ĐỒNG BỘ CHIỀU CAO BẰNG NHAU CHO CÁC THẺ KPI (LED CARDS) */
        [data-testid="stHorizontalBlock"]:has(.led-card) {{
            align-items: stretch !important;
            margin-bottom: 14px !important;
        }}
        [data-testid="stHorizontalBlock"]:has(.led-card) > [data-testid="stColumn"] {{
            display: flex !important;
            flex-direction: column !important;
        }}
        [data-testid="stColumn"]:has(.led-card) > div,
        [data-testid="stColumn"]:has(.led-card) [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stColumn"]:has(.led-card) [data-testid="stVerticalBlockBorderWrapper"] > div,
        [data-testid="stColumn"]:has(.led-card) [data-testid="stVerticalBlock"],
        [data-testid="stColumn"]:has(.led-card) [data-testid="stElementContainer"]:has(.led-card),
        [data-testid="stColumn"]:has(.led-card) [data-testid="stMarkdown"]:has(.led-card),
        [data-testid="stColumn"]:has(.led-card) [data-testid="stMarkdownContainer"]:has(.led-card) {{
            flex: 1 1 auto !important;
            display: flex !important;
            flex-direction: column !important;
            height: 100% !important;
        }}
        .led-card {{
            flex: 1 1 auto !important;
            height: 100% !important;
            min-height: 158px !important;
            margin-bottom: 0 !important;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-sizing: border-box;
        }}
        [data-testid="stElementContainer"]:has([data-vq-theme]),
        [data-testid="stHtml"]:has([data-vq-theme]) {{
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }}

        /* POPOVER NÚT GIAO DIỆN & POPUP NỘI DUNG */
        div[data-testid="stPopoverBody"],
        [data-testid="stPopoverBody"] {{
            background-color: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 32px var(--shadow-color) !important;
            color: var(--text-body) !important;
            padding: 12px 14px !important;
        }}

        div[data-testid="stPopover"] > button {{
            background: var(--bg-card) !important;
            color: var(--text-heading) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 10px !important;
            font-size: 18px !important;
            font-weight: 700 !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            padding: 6px 14px !important;
            transition: all 0.2s ease !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}

        div[data-testid="stPopover"] > button:hover {{
            border-color: var(--color-brand) !important;
            color: var(--color-brand) !important;
            box-shadow: 0 0 14px var(--shadow-color) !important;
            transform: scale(1.02);
        }}

        /* STYLING EXPANDER TRONG POPOVER VÀ TOÀN TRANG */
        div[data-testid="stExpander"],
        details[data-testid="stExpander"] {{
            background-color: var(--bg-card) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 10px !important;
            color: var(--text-heading) !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            margin-bottom: 8px !important;
        }}

        div[data-testid="stExpander"] summary,
        details[data-testid="stExpander"] summary {{
            background-color: var(--bg-card) !important;
            color: var(--text-heading) !important;
            font-weight: 600 !important;
            font-size: 13.5px !important;
            padding: 10px 14px !important;
            border-radius: 8px !important;
        }}

        div[data-testid="stExpander"] summary p,
        details[data-testid="stExpander"] summary p,
        div[data-testid="stExpander"] summary span,
        details[data-testid="stExpander"] summary span {{
            color: var(--text-heading) !important;
            font-weight: 600 !important;
        }}

        div[data-testid="stExpander"] summary:hover,
        details[data-testid="stExpander"] summary:hover {{
            color: var(--color-brand) !important;
            background-color: {expander_hover_bg} !important;
        }}

        div[data-testid="stExpander"] summary svg,
        details[data-testid="stExpander"] summary svg {{
            fill: var(--color-brand) !important;
            color: var(--color-brand) !important;
        }}

        div[data-testid="stExpanderDetails"] {{
            border-top: 1px solid var(--border-color) !important;
            padding: 10px 12px !important;
            background: transparent !important;
        }}

        /* 10. BẢNG DỮ LIỆU (DATAFRAME) TỰ ĐỘNG THÍCH ỨNG SÁNG / TỐI */
        [data-testid="stDataFrame"],
        div.stDataFrame {{
            border-radius: 10px !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
            overflow: hidden !important;
            {dataframe_filter}
        }}
    </style>
    """
    clean_css = textwrap.dedent(css).strip()
    # Prepend a zero-height hidden theme marker so st.html mounts in the persistent main
    # delta tree instead of Streamlit's ephemeral _event_dg (which drops <style> on reruns).
    marker = f'<div data-vq-theme="{pal["mode"]}" style="display:none !important;height:0;margin:0;padding:0;"></div>'
    if hasattr(st, "html"):
        st.html(f"{marker}\n{clean_css}")
    else:
        st.markdown(clean_css, unsafe_allow_html=True)


def render_hero_banner(title: str, subtitle: str, icon: str = ""):
    """Hiển thị Header Hero Banner tiêu chuẩn, tự động thích ứng với Light / Dark mode."""
    pal = get_theme_palette()
    display_title = f"{icon} {title}" if icon else title
    html = f"""
    <div class="hero-banner">
        <h2>{display_title}</h2>
        <p>{subtitle}</p>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_top_theme_switcher():
    """
    Hiển thị cụm nút chuyển đổi giao diện 'LIGHT / DARK MODE' trực quan ở góc trên bên phải
    với hiệu ứng LED glow tương ứng theo theme hiện tại.
    """
    current_mode = get_theme_mode()
    is_dark = (current_mode == "DARK")

    col_l, col_d = st.columns(2)
    with col_l:
        if st.button("☀️ SÁNG", key="top_theme_light", type="secondary" if is_dark else "primary", use_container_width=True, help="Chuyển sang giao diện Sáng"):
            if is_dark:
                set_theme_mode("LIGHT")
                st.rerun()
    with col_d:
        if st.button("🌙 TỐI", key="top_theme_dark", type="primary" if is_dark else "secondary", use_container_width=True, help="Chuyển sang giao diện Tối (Bloomberg/FactSet Style)"):
            if not is_dark:
                set_theme_mode("DARK")
                st.rerun()


def apply_plotly_theme(fig: go.Figure, height: int = 420, title: str = None) -> go.Figure:
    """
    Chuẩn hóa giao diện Plotly Charts thích ứng động Light / Dark Mode với độ tương phản cao:
    - Ép template 'plotly_white' / 'plotly_dark' để tránh Streamlit Dark config ghi đè trục/chú giải.
    - Text trục (tickfont) và tiêu đề trục (title_font), legend, colorbar đều tương phản rõ nét.
    """
    pal = get_theme_palette()
    is_light = (pal["mode"] == "LIGHT")

    fig.update_layout(
        template="plotly_white" if is_light else "plotly_dark",
        paper_bgcolor=pal["bg_card"],
        plot_bgcolor=pal["plot_bg"],
        font=dict(color=pal["chart_tick"], family="Segoe UI, Roboto, Helvetica, Arial, sans-serif", size=12),
        height=height,
        margin=dict(l=55, r=32, t=78 if title else 36, b=70),
        hoverlabel=dict(
            namelength=-1,
            bgcolor=pal["bg_card"],
            bordercolor=pal["color_brand_led"],
            font=dict(color=pal["text_heading"], size=12, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif")
        ),
        legend=dict(
            bgcolor=pal["bg_card_glass"],
            bordercolor=pal["border_color"],
            borderwidth=1,
            font=dict(color=pal["chart_tick"], size=12, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
            title=dict(font=dict(color=pal["chart_title"], size=12.5, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif")),
        ),
        coloraxis_colorbar=dict(
            title=dict(font=dict(color=pal["chart_title"], size=12, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif")),
            tickfont=dict(color=pal["chart_tick"], size=11.5, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=pal["grid_color"],
        gridwidth=1,
        zerolinecolor=pal["border_color"],
        tickfont=dict(color=pal["chart_tick"], size=12, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
        title_font=dict(color=pal["chart_title"], size=13, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=pal["grid_color"],
        gridwidth=1,
        zerolinecolor=pal["border_color"],
        tickfont=dict(color=pal["chart_tick"], size=12, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
        title_font=dict(color=pal["chart_title"], size=13, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
    )
    for trace in fig.data:
        if hasattr(trace, "colorbar") and getattr(trace, "colorbar", None) is not None:
            trace.update(
                colorbar=dict(
                    title=dict(font=dict(color=pal["chart_title"], size=12)),
                    tickfont=dict(color=pal["chart_tick"], size=11.5),
                )
            )
    if getattr(fig.layout, "polar", None) is not None and len(fig.layout.polar.to_plotly_json()) > 0:
        fig.update_layout(
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(gridcolor=pal["grid_color"], tickfont=dict(color=pal["chart_tick"], size=11)),
                angularaxis=dict(gridcolor=pal["grid_color"], tickfont=dict(color=pal["chart_title"], size=12)),
            )
        )
    if title:
        fig.update_layout(
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(color=pal["chart_title"], size=14.5, family="Segoe UI, Roboto, Helvetica, Arial, sans-serif"),
                x=0.02,
                xanchor="left",
                y=0.97,
                yanchor="top"
            )
        )
    return fig


def render_led_card(title: str, value: str, subtext: str = "", badge: str = "", status: str = "cyan", **kwargs):
    """
    Hiển thị khối thẻ số liệu phong cách LED Card cao cấp chuẩn xác theo Image ce671d75.png:
    - status: 'purple', 'cyan', 'pink', 'mint', 'gold', 'red', 'blue'
    - Tự động chuẩn hóa các alias như 'up', 'down', 'green', 'warning', 'brand', 'neutral'.
    """
    # Xử lý trường hợp caller gọi với 4 tham số không có badge mà truyền status vào vị trí thứ 4
    # hoặc truyền nhầm tên màu (warn, mint, pink, cyan...) vào badge
    known_statuses = {
        "cyan", "purple", "pink", "mint", "gold", "red", "blue", "brand", 
        "warning", "warn", "danger", "yellow", "orange", "emerald", "up", "down", "green", "neutral"
    }
    if str(badge).lower() in known_statuses:
        if status == "cyan" and "status" not in kwargs:
            status = str(badge).lower()
        badge = ""

    if "accent" in kwargs:
        status = str(kwargs["accent"])

    # Chuẩn hóa aliases
    st_clean = str(status).strip().lower()
    mapping = {
        "up": "mint",
        "green": "mint",
        "positive": "mint",
        "bullish": "mint",
        "emerald": "mint",
        "down": "red",
        "negative": "red",
        "bearish": "red",
        "danger": "red",
        "brand": "purple",
        "warning": "gold",
        "warn": "gold",
        "neutral": "gold",
        "yellow": "gold",
        "orange": "gold",
    }
    status = mapping.get(st_clean, st_clean)

    # TỰ ĐỘNG DỊCH TOÀN BỘ CÁC BADGE TIẾNG ANH LAI CĂNG SANG TIẾNG VIỆT CHUYÊN NGÀNH
    badge_trans = {
        "POOLED OLS": "HỒI QUY POOLED OLS",
        "SAMPLE SIZE": "DUNG LƯỢNG MẪU",
        "CONVERGENCE": "HỘI TỤ GIÁ TRỊ",
        "UNDERVALUED": "ĐỊNH GIÁ THẤP",
        "MEDIAN P/B": "TRUNG VỊ P/B",
        "MEDIAN ROE": "TRUNG VỊ ROE",
        "LEADER": "DẪN ĐẦU ROE",
        "BEST YIELD": "LỢI SUẤT TỐT NHẤT",
        "DIVIDEND YIELD": "CỔ TỨC TIỀN MẶT",
        "EVENT COUNT": "SỐ ĐỢT SỰ KIỆN",
        "METHODOLOGY": "PHƯƠNG PHÁP LUẬN",
        "PRICE": "THỊ GIÁ",
        "TREND": "XU HƯỚNG",
        "VOLUME SURGE": "ĐỘT BIẾN KHỐI LƯỢNG",
        "VOLUME": "KHỐI LƯỢNG KHỚP LỆNH",
        "TURNOVER": "GIÁ TRỊ GIAO DỊCH",
        "SURGE": "ĐỘT BIẾN",
        "RANGE": "BIÊN ĐỘ GIÁ",
        "DWH COVERAGE": "ĐỘ PHỦ KHO",
        "FINANCIAL RATIOS": "CHỈ SỐ TÀI CHÍNH",
        "CLEAN OHLCV": "DỮ LIỆU GIÁ SẠCH",
        "INTERMARKET": "LIÊN THỊ TRƯỜNG",
        "CAPITAL": "AN TOÀN VỐN",
        "ASSET QUALITY": "CHẤT LƯỢNG TÀI SẢN",
        "PROVISIONS": "DỰ PHÒNG RỦI RO",
        "EFFICIENCY": "HIỆU QUẢ HOẠT ĐỘNG",
        "FUNDING": "NGUỒN VỐN RẺ",
        "LOANS": "CHO VAY KHÁCH HÀNG",
        "DEPOSITS": "TIỀN GỬI KHÁCH HÀNG",
        "LIQUIDITY GAP": "KHOẢNG CÁCH THANH KHOẢN",
        "ANALYTICAL": "LDR PHÂN TÍCH",
        "REVENUE": "TỔNG THU NHẬP",
        "CORE PPOP": "LỢI NHUẬN CỐT LÕI",
        "CREDIT COST": "CHI PHÍ TÍN DỤNG",
        "BOTTOM LINE": "LỢI NHUẬN RÒNG",
        "OWNERSHIP": "CƠ CẤU SỞ HỮU",
        "MANAGEMENT": "BAN ĐIỀU HÀNH",
        "SUBSIDIARIES": "CÔNG TY CON",
        "ATTACHMENTS": "TỆP ĐÍNH KÈM",
        "BULLISH": "TÍCH CỰC",
        "BEARISH": "TIÊU CỰC",
        "NEUTRAL": "TRUNG LẬP",
        "UNIVERSE": "TOÀN BỘ NGÀNH",
        "GOLDEN": "TÍN HIỆU GOLDEN CROSS",
        "SECULAR": "XU HƯỚNG DÀI HẠN",
        "STRAT RET": "LỢI NHUẬN CHIẾN LƯỢC",
        "BUY & HOLD": "MUA & NẮM GIỮ",
        "ALPHA": "ALPHA THẶNG DƯ",
        "DRAWDOWN": "SỤT GIẢM TỐI ĐA",
        "SHARPE": "HỆ SỐ SHARPE",
        "WIN RATE": "TỶ LỆ THẮNG",
        "BOD / BOM": "BAN ĐIỀU HÀNH & HĐQT",
        "CƠ CẤU VỐN": "CƠ CẤU SỞ HỮU",
    }
    if badge and str(badge).upper() in badge_trans:
        badge = badge_trans[str(badge).upper()]

    pal = get_theme_palette()
    mode = get_theme_mode()

    if mode == "DARK":
        card_styles = {
            "blue": {
                "bg": "linear-gradient(145deg, #131E35 0%, #0F172A 100%)",
                "border": "rgba(59, 130, 246, 0.35)",
                "top": "#3B82F6",
                "badge_bg": "rgba(59, 130, 246, 0.20)",
                "badge_border": "rgba(59, 130, 246, 0.50)",
                "badge_color": "#60A5FA",
                "val_color": "#F8FAFC",
            },
            "cyan": {
                "bg": "linear-gradient(145deg, #0E2536 0%, #0B1926 100%)",
                "border": "rgba(2, 132, 199, 0.35)",
                "top": "#0284C7",
                "badge_bg": "rgba(2, 132, 199, 0.20)",
                "badge_border": "rgba(2, 132, 199, 0.50)",
                "badge_color": "#38BDF8",
                "val_color": "#38BDF8",
            },
            "purple": {
                "bg": "linear-gradient(145deg, #1C1936 0%, #131124 100%)",
                "border": "rgba(168, 85, 247, 0.35)",
                "top": "#A855F7",
                "badge_bg": "rgba(168, 85, 247, 0.20)",
                "badge_border": "rgba(168, 85, 247, 0.50)",
                "badge_color": "#C084FC",
                "val_color": "#C084FC",
            },
            "pink": {
                "bg": "linear-gradient(145deg, #241424 0%, #180D18 100%)",
                "border": "rgba(236, 72, 153, 0.35)",
                "top": "#EC4899",
                "badge_bg": "rgba(236, 72, 153, 0.20)",
                "badge_border": "rgba(236, 72, 153, 0.50)",
                "badge_color": "#F472B6",
                "val_color": "#F472B6",
            },
            "mint": {
                "bg": "linear-gradient(145deg, #0F2922 0%, #0A1C17 100%)",
                "border": "rgba(16, 185, 129, 0.35)",
                "top": "#10B981",
                "badge_bg": "rgba(16, 185, 129, 0.20)",
                "badge_border": "rgba(16, 185, 129, 0.50)",
                "badge_color": "#34D399",
                "val_color": "#10B981",
            },
            "gold": {
                "bg": "linear-gradient(145deg, #261F10 0%, #1A150A 100%)",
                "border": "rgba(245, 158, 11, 0.35)",
                "top": "#F59E0B",
                "badge_bg": "rgba(245, 158, 11, 0.20)",
                "badge_border": "rgba(245, 158, 11, 0.50)",
                "badge_color": "#FBBF24",
                "val_color": "#F59E0B",
            },
            "red": {
                "bg": "linear-gradient(145deg, #261217 0%, #1A0B0F 100%)",
                "border": "rgba(244, 63, 94, 0.35)",
                "top": "#F43F5E",
                "badge_bg": "rgba(244, 63, 94, 0.20)",
                "badge_border": "rgba(244, 63, 94, 0.50)",
                "badge_color": "#FB7185",
                "val_color": "#F43F5E",
            },
        }
    else:
        # Light Mode: Tối ưu độ tương phản WCAG 2.1 AA (chữ đậm trên nền trắng, không tàng hình!)
        card_styles = {
            "blue": {
                "bg": "#FFFFFF", "border": "#E2E8F0", "top": "#2563EB",
                "badge_bg": "rgba(37, 99, 235, 0.08)",
                "badge_border": "rgba(37, 99, 235, 0.30)", "badge_color": "#2563EB",
                "val_color": "#1E40AF",
            },
            "cyan": {
                "bg": "#FFFFFF", "border": "#E0F2FE", "top": "#0284C7",
                "badge_bg": "rgba(2, 132, 199, 0.08)",
                "badge_border": "rgba(2, 132, 199, 0.30)", "badge_color": "#0284C7",
                "val_color": "#0369A1",
            },
            "purple": {
                "bg": "#FFFFFF", "border": "#F3E8FF", "top": "#7E22CE",
                "badge_bg": "rgba(126, 34, 206, 0.08)",
                "badge_border": "rgba(126, 34, 206, 0.30)", "badge_color": "#7E22CE",
                "val_color": "#6B21A8",
            },
            "pink": {
                "bg": "#FFFFFF", "border": "#FCE7F3", "top": "#DB2777",
                "badge_bg": "rgba(219, 39, 119, 0.08)",
                "badge_border": "rgba(219, 39, 119, 0.30)", "badge_color": "#DB2777",
                "val_color": "#BE185D",
            },
            "mint": {
                "bg": "#FFFFFF", "border": "#D1FAE5", "top": "#059669",
                "badge_bg": "rgba(5, 150, 105, 0.08)",
                "badge_border": "rgba(5, 150, 105, 0.30)", "badge_color": "#059669",
                "val_color": "#047857", # Emerald đậm rõ nét trên nền trắng
            },
            "gold": {
                "bg": "#FFFFFF", "border": "#FEF3C7", "top": "#D97706",
                "badge_bg": "rgba(217, 119, 6, 0.08)",
                "badge_border": "rgba(217, 119, 6, 0.30)", "badge_color": "#D97706",
                "val_color": "#B45309", # Amber đậm tương phản cao
            },
            "red": {
                "bg": "#FFFFFF", "border": "#FEE2E2", "top": "#DC2626",
                "badge_bg": "rgba(220, 38, 38, 0.08)",
                "badge_border": "rgba(220, 38, 38, 0.30)", "badge_color": "#DC2626",
                "val_color": "#B91C1C", # Đỏ đậm
            },
        }

    st_cfg = card_styles.get(status, card_styles["cyan"])
    badge_html = f'<span style="background-color: {st_cfg["badge_bg"]}; color: {st_cfg["badge_color"]}; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; border: 1px solid {st_cfg["badge_border"]}; letter-spacing: 0.4px; white-space: nowrap; flex-shrink: 0;">{badge}</span>' if badge else ""

    card_html = (
        f'<div class="led-card" style="background: {st_cfg["bg"]}; border-radius: 12px; padding: 15px 16px; '
        f'border: 1px solid {st_cfg["border"]}; box-shadow: 0 6px 20px {pal["shadow_color"]}; '
        f'border-top: 3.5px solid {st_cfg["top"]}; transition: all 0.2s ease;">'
        f'<div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 4px 6px; margin-bottom: 8px;">'
        f'<span style="color: {pal["text_muted"]}; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; line-height: 1.3;">{title}</span>'
        f'{badge_html}'
        f'</div>'
        f'<div style="color: {st_cfg["val_color"]}; font-size: clamp(20px, 1.8vw, 25px); font-weight: 800; letter-spacing: -0.4px; margin-bottom: 6px; line-height: 1.25;">{value}</div>'
        f'<div style="color: {pal["text_muted"]}; font-size: 12.5px; line-height: 1.55;">{subtext}</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)
