"""Single consolidated dashboard: NSE (Nifty 50 index + gold/silver ETF proxies)
+ BTC side by side, essentials only. Two independent, concurrently-active
paper portfolios (NSE session-hours, CoinDCX/CRYPTO_INDIA 24/7 - see
app/orchestration/session_runner.py) rendered on one page rather than split
across separate tabs. Deliberately omits payoff diagrams, agent-by-agent vote
tables, and conviction-trend charts - those live in the API
(/positional/picks/{symbol}, /decisions/{id}) for anyone who wants to query
them directly, they're just not surfaced in this UI."""

import streamlit as st

from api_client import get, post
from theme import inject_base_css, metric_card, page_header, tone_for, verdict_badge

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


def _fmt_inr_or_uncapped(v) -> str:
    return f"₹{v:,.0f}" if v is not None else "uncapped"


def render_exchange_panel(title: str, icon: str, symbols: list[tuple[str, dict | None]], portfolio: dict) -> None:
    """symbols: list of (display_label, watchlist_item_or_None). Portfolio
    Total Value / Session P&L is shared across every symbol in the exchange
    (it's one portfolio, not one per symbol) - shown once at the top, then
    each symbol gets its own compact price + Algo Call row underneath. This
    keeps the row wide enough to never wrap character-by-character, however
    many symbols a given exchange's watchlist has (NSE has 3, crypto has 1).
    Open Positions for this exchange render inside the same panel (instead of
    a separate full-width section below) - Streamlit stretches side-by-side
    columns to equal height, so a 1-symbol panel (BTC) would otherwise leave
    a large dead gap under a 3-symbol panel (NSE) for no reason."""
    with st.container(border=True):
        st.markdown(f'<div class="ic-panel-title">{icon} {title}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        c1.markdown(metric_card("Total Value", f"₹{portfolio['total_value']:,.2f}", tone=tone_for(portfolio["net_profit"])), unsafe_allow_html=True)
        c2.markdown(
            metric_card("Session P&L", f"₹{portfolio['net_profit']:,.2f}", delta=f"{portfolio['total_return_pct']:+.2f}%", tone=tone_for(portfolio["net_profit"])),
            unsafe_allow_html=True,
        )

        for label, item in symbols:
            price_txt = f"₹{item['price']:,.2f}" if item and item.get("price") else "—"
            verdict = item.get("latest_verdict") if item else None
            conf_txt = f"{item['latest_confidence']:.1f}% confidence" if item and item.get("latest_confidence") is not None else "no tick yet"
            badge_html = verdict_badge(verdict)
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:nowrap; padding:0.65rem 1rem; margin-top:0.6rem; margin-bottom:0;">
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
            if item and item.get("used_comex_proxy") and item.get("comex_price"):
                st.caption(f"{label}: NSE closed — live COMEX {item.get('comex_symbol')} feed proxy (analysis only, not tradable).")

            pick = picks_by_symbol.get(item["symbol"]) if item else None
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

        st.markdown('<div class="ic-panel-title">Open Positions</div>', unsafe_allow_html=True)
        if portfolio["positions"]:
            for p in portfolio["positions"]:
                st.markdown(
                    f"""
                    <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center; margin-top:0.4rem; margin-bottom:0;">
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
        else:
            st.caption("No open positions.")


nse_symbols = [
    ("Nifty 50", _find(nse_watchlist, "^NSEI")),
    ("Gold", _find(nse_watchlist, "GOLDBEES.NS")),
    ("Silver", _find(nse_watchlist, "SILVERBEES.NS")),
]
crypto_symbols = [("BTC", _find(crypto_watchlist, "BTCINR"))]

main_col, side_col = st.columns([3.2, 1], gap="medium")

with main_col:
    p1, p2 = st.columns(2, gap="medium")
    with p1:
        render_exchange_panel("NSE — Index, Gold, Silver", "📈", nse_symbols, nse_portfolio)
    with p2:
        render_exchange_panel("BTC (CoinDCX)", "₿", crypto_symbols, crypto_portfolio)

# ================================================================== RIGHT: compact control panel
with side_col, st.container(border=True):
    st.markdown('<div class="ic-panel-title">Auto-Trading</div>', unsafe_allow_html=True)
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

    st.markdown('<div class="ic-panel-title">Positional Calls</div>', unsafe_allow_html=True)
    st.caption("Multi-day/week calls for Nifty 50, Bank Nifty (with options structures), Gold, Silver and BTC (directional only) — scan takes a few minutes, runs the full committee for each.")
    if st.button("Scan Positional Calls", width="stretch"):
        with st.spinner("Scanning Nifty 50, Bank Nifty, Gold, Silver and BTC..."):
            post("/positional/scan")
        st.success("Scan complete.")
        st.rerun()
    if positional.get("scanned_at"):
        st.caption(f"Last scan: {positional['scanned_at']}")

    st.markdown('<div class="ic-panel-title">Market Status</div>', unsafe_allow_html=True)
    st.caption(f"NSE: {'open' if exchange_status.get('NSE') else 'closed'} · CoinDCX: {'open' if exchange_status.get('CRYPTO_INDIA') else 'closed'} (always open)")
