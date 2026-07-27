"""Single consolidated dashboard: NSE (Nifty 50 index + gold/silver ETF proxies)
+ BTC side by side, essentials only. Two independent, concurrently-active
paper portfolios (NSE session-hours, CoinDCX/CRYPTO_INDIA 24/7 - see
app/orchestration/session_runner.py) rendered on one page rather than split
across separate tabs. Deliberately omits payoff diagrams, agent-by-agent vote
tables, and conviction-trend charts - those live in the API
(/positional/picks/{symbol}, /decisions/{id}) for anyone who wants to query
them directly, they're just not surfaced in this UI."""

import datetime as dt

import plotly.graph_objects as go
import streamlit as st

from api_client import get, post
from theme import (
    DEFAULT_ACCENT,
    EXCHANGE_ACCENT,
    SYMBOL_ACCENT,
    inject_base_css,
    metric_card,
    page_header,
    panel_header,
    section_title,
    tone_for,
    verdict_badge,
)

st.set_page_config(page_title="Money Minting Machine", page_icon="📊", layout="wide")
inject_base_css()
page_header("📊", "Money Minting Machine", "Index, gold/silver (NSE) + BTC — trust-weighted multi-agent Algo, paper trading only")

app_settings = get("/settings")
tick_status = get("/session/tick-status")

if not app_settings["llm_key_configured"]:
    st.warning(
        f"No LLM API key configured for provider `{app_settings['llm_provider']}`. The Algo still runs "
        "(all indicator/consensus math is independent of the LLM), but reasoning text falls back to "
        "templated summaries instead of LLM-generated narratives. Add a key to `backend/.env` and restart "
        "the backend for full explanations."
    )

nse_portfolio = get("/portfolio", exchange="NSE")
crypto_portfolio = get("/portfolio", exchange="CRYPTO_INDIA")
nse_watchlist = get("/watchlist", exchange="NSE", silent=True) or []
crypto_watchlist = get("/watchlist", exchange="CRYPTO_INDIA", silent=True) or []


def _find(watchlist: list[dict], symbol: str) -> dict | None:
    return next((i for i in watchlist if i["symbol"] == symbol), None)


positional = get("/positional/picks", silent=True) or {"picks": []}
picks_by_symbol = {p["symbol"]: p for p in positional.get("picks", [])}

exchange_status = {e["code"]: e["is_open"] for e in app_settings.get("exchanges", [])}


def render_market_status_bar(exchange_status: dict, tick_status: dict) -> None:
    """Top-of-dashboard strip: NSE/CoinDCX open-closed state plus a tick-
    scheduler health check. Surfaced prominently (above both exchange panels,
    not tucked in the side control panel) because "is the Algo actually
    ticking right now" has been the single most common point of confusion -
    Cloud Run's background scheduler can silently stall (see README's Cloud
    Run CPU-allocation notes) and leave prices/decisions frozen with no
    on-screen indication that anything is wrong. A stale next_run_time (in
    the past by more than a couple of tick intervals) is a real, diagnosable
    symptom, not a cosmetic detail, so it gets its own STALLED state here
    rather than silently showing a wrong "next tick" countdown."""
    nse_open = exchange_status.get("NSE", False)
    crypto_open = exchange_status.get("CRYPTO_INDIA", False)

    stalled = False
    next_run_txt = "—"
    next_run_raw = tick_status.get("next_run_time")
    if next_run_raw:
        try:
            next_run = dt.datetime.fromisoformat(next_run_raw)
            now = dt.datetime.now(next_run.tzinfo) if next_run.tzinfo else dt.datetime.utcnow()
            delta_min = (next_run - now).total_seconds() / 60.0
            stalled = delta_min < -(2 * tick_status.get("tick_minutes", 5))
            next_run_txt = next_run.strftime("%d %b, %H:%M UTC")
        except Exception:
            next_run_txt = next_run_raw

    with st.container(border=True):
        st.markdown(panel_header("🌐", "Market Status", "#38BDF8"), unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.markdown(
            metric_card(
                "NSE (Nifty, Gold, Silver)",
                "OPEN" if nse_open else "CLOSED",
                delta="09:15–15:30 IST, Mon–Fri",
                tone="positive" if nse_open else "muted",
            ),
            unsafe_allow_html=True,
        )
        m2.markdown(
            metric_card("CoinDCX (BTC)", "OPEN" if crypto_open else "CLOSED", delta="24/7", tone="positive" if crypto_open else "muted"),
            unsafe_allow_html=True,
        )
        if tick_status.get("paused"):
            tick_value, tick_tone, tick_delta = "PAUSED", "muted", "resume from the panel on the right"
        elif stalled:
            tick_value, tick_tone, tick_delta = "STALLED", "negative", f"expected {next_run_txt} — hasn't ticked since"
        else:
            tick_value, tick_tone, tick_delta = f"every {tick_status.get('tick_minutes', '—')} min", "positive", f"next: {next_run_txt}"
        m3.markdown(metric_card("Algo Tick Scheduler", tick_value, delta=tick_delta, tone=tick_tone), unsafe_allow_html=True)


render_market_status_bar(exchange_status, tick_status)


def _fmt_inr_or_uncapped(v) -> str:
    return f"₹{v:,.0f}" if v is not None else "uncapped"


def render_exchange_panel(title: str, icon: str, exchange_code: str, symbols: list[tuple[str, str, dict | None]], portfolio: dict) -> None:
    """symbols: list of (display_label, ticker_symbol, watchlist_item_or_None).
    Portfolio Total Value / Session P&L is shared across every symbol in the
    exchange (it's one portfolio, not one per symbol) - shown once at the
    top, then each symbol gets its own compact price + Algo Call row
    underneath. This keeps the row wide enough to never wrap
    character-by-character, however many symbols a given exchange's
    watchlist has (NSE has 3, crypto has 1). Open Positions for this
    exchange render inside the same panel (instead of a separate full-width
    section below) - Streamlit stretches side-by-side columns to equal
    height, so a 1-symbol panel (BTC) would otherwise leave a large dead gap
    under a 3-symbol panel (NSE) for no reason."""
    exchange_accent = EXCHANGE_ACCENT.get(exchange_code, DEFAULT_ACCENT)
    with st.container(border=True):
        st.markdown(panel_header(icon, title, exchange_accent), unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        c1.markdown(metric_card("Total Value", f"₹{portfolio['total_value']:,.2f}", tone=tone_for(portfolio["net_profit"])), unsafe_allow_html=True)
        c2.markdown(
            metric_card("Session P&L", f"₹{portfolio['net_profit']:,.2f}", delta=f"{portfolio['total_return_pct']:+.2f}%", tone=tone_for(portfolio["net_profit"])),
            unsafe_allow_html=True,
        )

        for label, symbol, item in symbols:
            symbol_accent = SYMBOL_ACCENT.get(symbol, DEFAULT_ACCENT)
            price_txt = f"₹{item['price']:,.2f}" if item and item.get("price") else "—"
            verdict = item.get("latest_verdict") if item else None
            conf_txt = f"{item['latest_confidence']:.1f}% confidence" if item and item.get("latest_confidence") is not None else "no tick yet"
            badge_html = verdict_badge(verdict)
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:nowrap; padding:0.65rem 1rem 0.65rem 0.9rem; margin-top:0.6rem; margin-bottom:0; border-left:4px solid {symbol_accent};">
                    <div style="white-space:nowrap;">
                        <span style="font-weight:700; color:#F8FAFC;">{label}</span>
                        <span style="margin-left:0.6rem;">{badge_html}</span>
                    </div>
                    <div style="text-align:right; font-family:'JetBrains Mono','SF Mono',monospace; white-space:nowrap;">
                        <div style="color:#F8FAFC; font-weight:600;">{price_txt}</div>
                        <div style="color:#5B6B84; font-size:0.72rem;">{conf_txt}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Both notes are COMEX-derived, so they're merged into one caption
            # rather than stacked as two near-identical-sounding lines - the
            # "NSE closed, feed proxy" note only exists at all when NSE is
            # shut and this symbol's ANALYSIS feed switched to COMEX; the
            # "Global reference" price (India retail units - real MCX data
            # isn't freely available, see market_data.py) is shown regardless
            # of market hours, so it's always the second half of the line
            # when present.
            ref = item.get("global_reference") if item else None
            closed_note = (
                f"NSE closed — live COMEX {item.get('comex_symbol')} feed proxy for analysis (not tradable)"
                if item and item.get("used_comex_proxy") and item.get("comex_price")
                else None
            )
            ref_note = f"{ref['label']} ₹{ref['value_inr']:,.2f} {ref['unit']} (reference only, not 1:1 comparable)" if ref else None
            if closed_note or ref_note:
                st.caption(f"{label}: " + " · ".join(n for n in (closed_note, ref_note) if n) + ".")

            pick = picks_by_symbol.get(symbol)
            if pick and pick.get("strategy"):
                # Nifty/Bank Nifty: a real options structure (listed NSE index options).
                s = pick["strategy"]
                st.caption(
                    f"{label} options pick: {pick['direction']} · {s['structure_type']} · exp {s['expiry']} · "
                    f"max loss {_fmt_inr_or_uncapped(s['max_loss'])} / max profit {_fmt_inr_or_uncapped(s['max_profit'])}"
                )
            elif pick:
                # Gold/Silver/BTC: no listed options chain to build a structure from,
                # so this is a plain directional positional call instead.
                st.caption(f"{label} positional call: {pick['direction']} · {pick['directional_confidence']:.0f}% conviction")

        st.markdown(section_title("Open Positions", exchange_accent), unsafe_allow_html=True)
        if portfolio["positions"]:
            for p in portfolio["positions"]:
                pos_accent = SYMBOL_ACCENT.get(p["symbol"], exchange_accent)
                st.markdown(
                    f"""
                    <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center; margin-top:0.4rem; margin-bottom:0; border-left:4px solid {pos_accent};">
                        <div>
                            <span style="font-weight:700; color:#F8FAFC;">{p['symbol']}</span>
                            <span class="ic-badge" style="margin-left:0.5rem; background:#0B2A24;color:#2DD4BF;border:1px solid #14B8A6;">{p['side']}</span>
                        </div>
                        <div style="font-family:'JetBrains Mono','SF Mono',monospace; color:#8B96A8; font-size:0.85rem;">
                            Qty {p['quantity']:g} @ ₹{p['avg_price']:,.2f}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                # Positional mode (see backend/app/orchestration/session_runner.py): this
                # position holds until one of these auto-exit levels is hit, or the committee
                # reverses - surfacing both here is the only place a user can see WHY a
                # position might close on its own between visits to the dashboard.
                if p.get("stop_loss") is not None and p.get("target_price") is not None:
                    st.caption(f"Auto-exit: stop ₹{p['stop_loss']:,.2f} · target ₹{p['target_price']:,.2f}")
        else:
            st.caption("No open positions.")


nse_symbols = [
    ("Nifty 50", "^NSEI", _find(nse_watchlist, "^NSEI")),
    ("Gold", "GOLDBEES.NS", _find(nse_watchlist, "GOLDBEES.NS")),
    ("Silver", "SILVERBEES.NS", _find(nse_watchlist, "SILVERBEES.NS")),
]
crypto_symbols = [("BTC", "BTCINR", _find(crypto_watchlist, "BTCINR"))]

main_col, side_col = st.columns([3.2, 1], gap="medium")

with main_col:
    p1, p2 = st.columns(2, gap="medium")
    with p1:
        render_exchange_panel("NSE — Index, Gold, Silver", "📈", "NSE", nse_symbols, nse_portfolio)
    with p2:
        render_exchange_panel("BTC (CoinDCX)", "₿", "CRYPTO_INDIA", crypto_symbols, crypto_portfolio)

# ================================================================== RIGHT: compact control panel
with side_col, st.container(border=True):
    st.markdown(section_title("Auto-Trading", "#2DD4BF"), unsafe_allow_html=True)
    st.caption("Shared across both exchanges — pausing/resuming affects the index and BTC ticks together.")
    if tick_status["paused"]:
        st.markdown(
            '<span class="ic-badge" style="background:#301419;color:#FB7185;border:1px solid #E11D48;">⏸ PAUSED</span>',
            unsafe_allow_html=True,
        )
        if st.button("▶ Resume Auto-Trading", width="stretch", type="primary"):
            post("/session/resume")
            st.success("Auto-trading resumed.")
            st.rerun()
    else:
        st.markdown(
            f'<span class="ic-badge" style="background:#0B2A24;color:#2DD4BF;border:1px solid #14B8A6;">● RUNNING · every {tick_status["tick_minutes"]} min</span>',
            unsafe_allow_html=True,
        )
        if st.button("⏸ Pause (saves LLM tokens)", width="stretch"):
            post("/session/pause")
            st.success("Auto-trading paused.")
            st.rerun()

    rc1, rc2 = st.columns(2)
    with rc1:
        if st.button("Run Tick", width="stretch"):
            with st.spinner("Running Algo tick (index + BTC)..."):
                post("/session/tick")
            st.success("Tick complete.")
            st.rerun()
    with rc2:
        if st.button("Refresh", width="stretch"):
            st.rerun()

    st.markdown(section_title("Positional Calls", "#C4B5FD"), unsafe_allow_html=True)
    st.caption("Multi-day/week calls for Nifty 50, Bank Nifty (with options structures), Gold, Silver and BTC (directional only) — scan takes a few minutes, runs the full committee for each.")
    if st.button("Scan Positional Calls", width="stretch"):
        with st.spinner("Scanning Nifty 50, Bank Nifty, Gold, Silver and BTC..."):
            post("/positional/scan")
        st.success("Scan complete.")
        st.rerun()
    if positional.get("scanned_at"):
        st.caption(f"Last scan: {positional['scanned_at']}")
    # Market Status has its own full-width panel at the top of the dashboard
    # now (render_market_status_bar) - a second copy here would just repeat
    # the same NSE/CoinDCX open-closed state in smaller text for no reason.

# ================================================================== BELOW: candlestick chart for a selected symbol
CHART_OPTIONS = [
    ("Nifty 50", "^NSEI"),
    ("Gold (GOLDBEES)", "GOLDBEES.NS"),
    ("Silver (SILVERBEES)", "SILVERBEES.NS"),
    ("BTC (CoinDCX)", "BTCINR"),
]
with st.container(border=True):
    st.markdown(panel_header("📉", "Price Chart", "#2DD4BF"), unsafe_allow_html=True)
    chart_label = st.selectbox("Script", options=[label for label, _ in CHART_OPTIONS], label_visibility="collapsed")
    chart_symbol = dict(CHART_OPTIONS)[chart_label]
    chart_data = get(f"/market/chart/{chart_symbol}", silent=True)
    if chart_data and chart_data.get("figure"):
        fig = go.Figure(chart_data["figure"])
        fig.update_layout(height=380, margin={"t": 40, "b": 30, "l": 45, "r": 15})
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        if chart_data.get("used_comex_proxy"):
            st.caption(f"NSE closed — showing live COMEX {chart_data.get('source_symbol')} feed as an analysis proxy (not tradable).")
    else:
        st.caption("No bar data available for this symbol right now.")
