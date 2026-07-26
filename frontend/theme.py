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

# Per-exchange and per-symbol brand colors - purely visual identity (which
# panel/row is which at a glance), kept separate from VERDICT_STYLE/TONE_COLORS
# which carry actual meaning (buy/sell/profit/loss) and shouldn't be muddied
# by a symbol's "brand" color.
EXCHANGE_ACCENT = {"NSE": "#6366F1", "CRYPTO_INDIA": "#F7931A"}  # indigo (equities/index) / bitcoin-orange
SYMBOL_ACCENT = {
    "^NSEI": "#38BDF8",        # sky blue - the index itself
    "GOLDBEES.NS": "#F5B324",  # gold
    "SILVERBEES.NS": "#B8C4D4",  # silver/steel
    "BTCINR": "#F7931A",       # bitcoin orange
}
DEFAULT_ACCENT = "#5B6B84"


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
            background: linear-gradient(135deg, rgba(45,212,191,0.18) 0%, rgba(99,102,241,0.18) 55%, rgba(247,147,26,0.18) 100%);
            border: 1px solid rgba(148,163,184,0.25);
        }
        .ic-page-header-title { font-size: 1.4rem; font-weight: 800; color: #F8FAFC; letter-spacing: -0.01em; }
        .ic-page-header-subtitle { font-size: 0.88rem; color: #8B96A8; margin-top: 0.15rem; }

        /* Two different needs that were wrongly solved with one blanket rule:
           (1) a metric-card ROW (e.g. Total Value / Session P&L) genuinely
           wants its cards stretched to equal height, since one has a delta
           line and the other doesn't. (2) the OUTER NSE/BTC panel row does
           NOT want that - NSE naturally has 3 symbol rows and BTC has 1, so
           forcing them to equal height just leaves a large dead gap under
           the shorter panel instead of aligning anything. A single global
           `align-items: stretch` on every [data-testid="stHorizontalBlock"]
           (Streamlit gives every st.columns() row that same attribute,
           nested or not - there's no way to tell them apart by depth alone
           except structurally) caused exactly that gap. Fix: default to
           flex-start (natural height) everywhere, then re-enable stretch
           only for rows nested inside a bordered st.container() - which is
           precisely the metric-card rows, not the outer panel row that
           contains those bordered containers rather than living inside one. */
        [data-testid="stHorizontalBlock"] { align-items: flex-start; }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] { align-items: stretch; }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { display: flex; flex-direction: column; }
        [data-testid="stColumn"] > div { width: 100%; }

        .ic-metric-card {
            background: linear-gradient(165deg, #101827 0%, #0B1220 100%);
            border: 1px solid #1A2333; border-top: 3px solid var(--accent, #1A2333); border-radius: 14px;
            padding: 0.95rem 1rem; min-height: 100px; height: 100%;
            box-sizing: border-box; display: flex; flex-direction: column; justify-content: flex-start;
            box-shadow: 0 1px 0 0 rgba(255,255,255,0.03) inset;
        }
        .ic-metric-label {
            font-size: 0.72rem; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em;
            white-space: nowrap;
        }
        .ic-metric-value {
            /* clamp() scales the font down as the card narrows, so most values
               shrink to fit on one line. overflow-wrap:break-word is a genuine
               last resort only - it only breaks a word if it can't otherwise
               fit its own line, so a normal-length value never gets chopped.
               (An earlier version also set word-break:break-word, which is
               far more eager to break mid-word - combined with columns that
               were simply too narrow for their content, that chopped ordinary
               values like "23,787.00" into single-digit lines. The real fix
               for that was giving cards more width - see frontend/Home.py's
               2-column-per-row panel layout - not more aggressive wrapping.) */
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace; font-weight: 700;
            font-size: clamp(0.85rem, 1.6vw, 1.45rem);
            color: #F8FAFC; margin-top: 0.28rem; letter-spacing: -0.01em;
            white-space: normal; overflow-wrap: break-word;
            max-width: 100%;
        }
        .ic-metric-delta {
            font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace; font-size: 0.8rem; font-weight: 600;
            margin-top: 0.3rem;
        }

        .ic-badge {
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.24rem 0.7rem; border-radius: 999px; font-size: 0.8rem; font-weight: 700;
            letter-spacing: 0.02em; white-space: nowrap;
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

        /* Main exchange panel headings (NSE / BTC) - deliberately distinct from
           .ic-panel-title above (used for smaller side-panel section labels and
           the Open Positions sub-heading): bigger, heavier weight, and colored
           with the panel's own accent rather than muted grey, so "NSE" / "BTC"
           actually reads as a heading rather than blending into the small-caps
           label styling used everywhere else. */
        .ic-panel-title-main {
            font-size: 1.1rem; font-weight: 800; letter-spacing: -0.01em;
            text-transform: none; margin: 0 0 0.85rem 0;
        }

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


def panel_header(icon: str, title: str, accent: str = DEFAULT_ACCENT) -> str:
    """A panel title with a colored accent bar above it - used to give each
    exchange panel (NSE indigo, BTC bitcoin-orange) a distinct visual
    identity at a glance, beyond just the text label. Larger/bolder/colored
    (.ic-panel-title-main) rather than the small muted-grey uppercase style
    used for side-panel section labels."""
    return (
        f'<div style="height:3px; width:100%; border-radius:3px; margin-bottom:0.85rem; '
        f'background:linear-gradient(90deg, {accent} 0%, {accent}22 100%);"></div>'
        f'<div class="ic-panel-title-main" style="color:{accent};">{icon} {title}</div>'
    )


def section_title(title: str, accent: str = DEFAULT_ACCENT) -> str:
    """A side-panel section title with a small colored dot - quick visual
    scanning cue distinguishing Auto-Trading / Positional Calls / Market
    Status sections from one another."""
    return (
        f'<div class="ic-panel-title" style="display:flex; align-items:center; gap:0.45rem;">'
        f'<span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:{accent}; '
        f'box-shadow:0 0 6px {accent}99;"></span>{title}</div>'
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
