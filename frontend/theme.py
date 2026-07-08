"""Shared design system for the Investment Committee frontend: a dark
fintech-terminal palette, verdict color coding (BUY/SELL/HOLD/WAIT/SWITCH),
and reusable card/badge components used across every page."""

import streamlit as st

VERDICT_STYLE = {
    "BUY": {"bg": "#0F2A1C", "fg": "#4ADE80", "border": "#22C55E", "icon": "▲"},
    "SELL": {"bg": "#331414", "fg": "#F87171", "border": "#EF4444", "icon": "▼"},
    "HOLD": {"bg": "#20242C", "fg": "#CBD5E1", "border": "#64748B", "icon": "●"},
    "WAIT": {"bg": "#2E2308", "fg": "#FBBF24", "border": "#F59E0B", "icon": "◐"},
    "SWITCH": {"bg": "#271B3D", "fg": "#C4B5FD", "border": "#A78BFA", "icon": "⇄"},
}
DEFAULT_VERDICT_STYLE = {"bg": "#1B1F2A", "fg": "#94A3B8", "border": "#334155", "icon": "○"}

TONE_COLORS = {"positive": "#22C55E", "negative": "#EF4444", "neutral": "#22D3EE", "muted": "#64748B"}


def inject_base_css() -> None:
    st.markdown(
        """
        <style>
        html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }

        #MainMenu, footer, header[data-testid="stHeader"] { visibility: visible; }
        footer { visibility: hidden; height: 0; }

        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }

        .ic-page-header {
            display: flex; align-items: center; gap: 0.9rem;
            padding: 1.1rem 1.4rem; margin-bottom: 1.4rem;
            background: linear-gradient(135deg, #131B2E 0%, #0F1729 100%);
            border: 1px solid #1E293B; border-radius: 14px;
        }
        .ic-page-header-icon { font-size: 2rem; line-height: 1; }
        .ic-page-header-title { font-size: 1.5rem; font-weight: 700; color: #F1F5F9; letter-spacing: -0.01em; }
        .ic-page-header-subtitle { font-size: 0.92rem; color: #94A3B8; margin-top: 0.15rem; }

        .ic-metric-card {
            background: #131B2E; border: 1px solid #1E293B; border-left: 3px solid var(--accent, #22D3EE);
            border-radius: 10px; padding: 0.85rem 1.1rem; height: 100%;
        }
        .ic-metric-label { font-size: 0.76rem; font-weight: 600; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.04em; }
        .ic-metric-value { font-family: 'SF Mono', 'Roboto Mono', Consolas, monospace; font-size: 1.5rem; font-weight: 700; color: #F1F5F9; margin-top: 0.2rem; }
        .ic-metric-delta { font-family: 'SF Mono', 'Roboto Mono', Consolas, monospace; font-size: 0.85rem; font-weight: 600; margin-top: 0.15rem; }

        .ic-badge {
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.22rem 0.65rem; border-radius: 999px; font-size: 0.82rem; font-weight: 700;
            letter-spacing: 0.02em;
        }

        .ic-card {
            background: #131B2E; border: 1px solid #1E293B; border-radius: 12px;
            padding: 1rem 1.2rem; margin-bottom: 0.8rem;
        }

        .ic-divider { height: 1px; background: #1E293B; margin: 1.1rem 0; border: none; }

        [data-testid="stMetric"] {
            background: #131B2E; border: 1px solid #1E293B; border-radius: 10px; padding: 0.9rem 1rem 0.6rem 1rem;
        }
        [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #94A3B8; }

        .stButton > button {
            border-radius: 8px; font-weight: 600; border: 1px solid #22D3EE33;
        }
        .stButton > button[kind="primary"] { background: #22D3EE; color: #05161A; }

        [data-testid="stExpander"] { background: #10182B; border: 1px solid #1E293B; border-radius: 10px; }

        .stTabs [data-baseweb="tab-list"] { gap: 0.4rem; }
        .stTabs [data-baseweb="tab"] {
            background: #131B2E; border-radius: 8px 8px 0 0; padding: 0.5rem 1rem; color: #94A3B8;
        }
        .stTabs [aria-selected="true"] { color: #22D3EE !important; }
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
