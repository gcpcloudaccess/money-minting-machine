"""Shared design system for the Investment Committee frontend: a dark
fintech-terminal palette, verdict color coding (BUY/SELL/HOLD/WAIT/SWITCH),
and reusable card/badge components used across every page."""

import streamlit as st

VERDICT_STYLE = {
    "BUY": {"bg": "#0B2A24", "fg": "#2DD4BF", "border": "#14B8A6", "icon": "▲"},
    "SELL": {"bg": "#301419", "fg": "#FB7185", "border": "#E11D48", "icon": "▼"},
    "HOLD": {"bg": "#1B2130", "fg": "#CBD5E1", "border": "#475569", "icon": "●"},
    "WAIT": {"bg": "#2E2308", "fg": "#FBBF24", "border": "#D97706", "icon": "◐"},
    "SWITCH": {"bg": "#241A38", "fg": "#C4B5FD", "border": "#8B5CF6", "icon": "⇄"},
}
DEFAULT_VERDICT_STYLE = {"bg": "#161B27", "fg": "#8B96A8", "border": "#2A3140", "icon": "○"}

TONE_COLORS = {"positive": "#2DD4BF", "negative": "#FB7185", "neutral": "#38BDF8", "muted": "#64748B"}
ACCENT = "#2DD4BF"


def inject_base_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

        html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }

        #MainMenu, footer, header[data-testid="stHeader"] { visibility: visible; }
        footer { visibility: hidden; height: 0; }
        header[data-testid="stHeader"] { background: transparent; }

        [data-testid="stAppViewContainer"] {
            background: radial-gradient(1100px 620px at 14% -8%, #0E1626 0%, rgba(14,22,38,0) 60%),
                        linear-gradient(180deg, #070B14 0%, #05070D 100%);
        }
        [data-testid="stSidebar"] {
            background: #060A13; border-right: 1px solid #141B2B;
        }
        [data-testid="stSidebar"] * { color: #93A1B7 !important; }
        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: rgba(45, 212, 191, 0.10) !important; border-radius: 8px;
        }
        [data-testid="stSidebarNav"] a[aria-current="page"] span { color: #2DD4BF !important; font-weight: 700; }

        .block-container { padding-top: 1.7rem; padding-bottom: 3rem; max-width: 1280px; }

        .ic-page-header {
            display: flex; align-items: center; gap: 1rem;
            padding: 1.15rem 1.5rem; margin-bottom: 1.5rem;
            background: linear-gradient(135deg, #101827 0%, #0A0F1C 100%);
            border: 1px solid #1A2333; border-radius: 16px;
            box-shadow: 0 1px 0 0 rgba(255,255,255,0.03) inset;
        }
        .ic-page-header-icon {
            font-size: 1.5rem; line-height: 1; width: 46px; height: 46px; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center; border-radius: 12px;
            background: rgba(45, 212, 191, 0.10); border: 1px solid rgba(45, 212, 191, 0.25);
        }
        .ic-page-header-title { font-size: 1.4rem; font-weight: 800; color: #F8FAFC; letter-spacing: -0.01em; }
        .ic-page-header-subtitle { font-size: 0.88rem; color: #8B96A8; margin-top: 0.15rem; }

        /* Streamlit doesn't stretch sibling columns to equal height by default,
           so cards with a delta line ended up taller than ones without - making
           the value line land at a different vertical position per card. Force
           the row to stretch, and give every card a shared min-height baseline
           (a row grows past it together if one card's content genuinely needs
           more room, e.g. a long wrapped delta message). */
        [data-testid="stHorizontalBlock"] { align-items: stretch; }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { display: flex; flex-direction: column; }
        [data-testid="stColumn"] > div { width: 100%; }

        .ic-metric-card {
            background: linear-gradient(165deg, #101827 0%, #0B1220 100%);
            border: 1px solid #1A2333; border-radius: 14px;
            padding: 0.95rem 1.15rem; min-height: 100px; height: 100%;
            box-sizing: border-box; display: flex; flex-direction: column; justify-content: flex-start;
            box-shadow: 0 1px 0 0 rgba(255,255,255,0.03) inset;
        }
        .ic-metric-label {
            font-size: 0.72rem; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em;
        }
        .ic-metric-value {
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace; font-size: 1.45rem; font-weight: 700;
            color: #F8FAFC; margin-top: 0.28rem; letter-spacing: -0.01em;
        }
        .ic-metric-delta {
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace; font-size: 0.8rem; font-weight: 600;
            margin-top: 0.3rem;
        }

        .ic-badge {
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.24rem 0.7rem; border-radius: 999px; font-size: 0.8rem; font-weight: 700;
            letter-spacing: 0.02em;
        }

        .ic-card {
            background: #0D1420; border: 1px solid #1A2333; border-radius: 14px;
            padding: 1rem 1.25rem; margin-bottom: 0.8rem;
            box-shadow: 0 1px 0 0 rgba(255,255,255,0.03) inset;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            background: linear-gradient(180deg, #0F1626 0%, #0A0F1C 100%) !important;
            border: 1px solid #1A2333 !important; border-radius: 16px !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { gap: 0.5rem; }
        .ic-panel-title {
            font-size: 0.75rem; font-weight: 700; color: #5B6B84; text-transform: uppercase;
            letter-spacing: 0.08em; margin: 1.1rem 0 0.6rem 0;
        }
        .ic-panel-title:first-child { margin-top: 0; }

        .ic-divider { height: 1px; background: #1A2333; margin: 1.15rem 0; border: none; }

        [data-testid="stMetric"] {
            background: #0D1420; border: 1px solid #1A2333; border-radius: 12px; padding: 0.9rem 1rem 0.6rem 1rem;
        }
        [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #8B96A8; }

        .stButton > button {
            border-radius: 10px; font-weight: 600; border: 1px solid #1A2333; background: #101827; color: #CBD5E1;
            transition: border-color 0.15s ease;
        }
        .stButton > button:hover { border-color: #2DD4BF66; color: #F8FAFC; }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #2DD4BF 0%, #14B8A6 100%); color: #04231F; border: none;
            box-shadow: 0 4px 16px -4px rgba(45, 212, 191, 0.45);
        }
        .stButton > button[kind="primary"]:hover { filter: brightness(1.06); }
        .stDownloadButton > button { border-radius: 10px; font-weight: 600; }

        [data-testid="stExpander"] { background: #0D1420; border: 1px solid #1A2333; border-radius: 12px; }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.25rem; background: #0B1220; border: 1px solid #1A2333; border-radius: 12px; padding: 0.3rem;
        }
        .stTabs [data-baseweb="tab"] {
            background: transparent; border-radius: 8px; padding: 0.5rem 1.1rem; color: #64748B; font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background: rgba(45, 212, 191, 0.12) !important; color: #2DD4BF !important;
        }
        .stTabs [data-baseweb="tab-highlight"] { display: none; }
        .stTabs [data-baseweb="tab-border"] { display: none; }

        [data-testid="stMetricValue"], .ic-mono { font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace; }

        .ic-selectbox-label, [data-testid="stWidgetLabel"] p { color: #8B96A8 !important; font-size: 0.82rem; }

        [data-testid="stAlert"] { border-radius: 12px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def verdict_badge(verdict: str | None) -> str:
    s = VERDICT_STYLE.get(verdict, DEFAULT_VERDICT_STYLE)
    label = verdict or "NO DECISION"
    return f'<span class="ic-badge" style="background:{s["bg"]};color:{s["fg"]};border:1px solid {s["border"]}">{s["icon"]} {label}</span>'


def verdict_icon(verdict: str | None) -> str:
    return VERDICT_STYLE.get(verdict, DEFAULT_VERDICT_STYLE)["icon"]


def page_header(icon: str, title: str, subtitle: str | None = None) -> None:
    subtitle_html = f'<div class="ic-page-header-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="ic-page-header">
            <div class="ic-page-header-icon">{icon}</div>
            <div>
                <div class="ic-page-header-title">{title}</div>
                {subtitle_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, delta: str | None = None, tone: str = "neutral") -> str:
    color = TONE_COLORS.get(tone, TONE_COLORS["neutral"])
    delta_html = f'<div class="ic-metric-delta" style="color:{color}">{delta}</div>' if delta else ""
    return (
        f'<div class="ic-metric-card" style="--accent:{color}">'
        f'<div class="ic-metric-label">{label}</div>'
        f'<div class="ic-metric-value">{value}</div>'
        f"{delta_html}</div>"
    )


def tone_for(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"
