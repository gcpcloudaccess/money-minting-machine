"""Single consolidated dashboard: index (Nifty 50) + BTC side by side, essentials
only. Two independent, concurrently-active paper portfolios (NSE session-hours
for the index, CoinDCX/CRYPTO_INDIA 24/7 for BTC - see
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
page_header("📊", "Money Minting Machine", "Index (Nifty 50) + BTC — trust-weighted multi-agent Algo, paper trading only")

NO_DECISION_BADGE = '<span class="ic-badge" style="background:#161B27;color:#5B6B84;border:1px solid #2A3140;">NO DECISION YET</span>'

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
index_item = next((i for i in nse_watchlist if i["symbol"] == "^NSEI"), None)
btc_item = next((i for i in crypto_watchlist if i["symbol"] == "BTCINR"), None)

positional = get("/positional/picks", silent=True) or {"picks": []}
picks_by_symbol = {p["symbol"]: p for p in positional.get("picks", [])}

exchange_status = {e["code"]: e["is_open"] for e in app_settings.get("exchanges", [])}


def _fmt_inr_or_uncapped(v) -> str:
    return f"₹{v:,.0f}" if v is not None else "uncapped"


def render_asset_panel(title: str, icon: str, symbol: str, item: dict | None, portfolio: dict) -> None:
    with st.container(border=True):
        st.markdown(f'<div class="ic-panel-title">{icon} {title}</div>', unsafe_allow_html=True)

        price_txt = f"₹{item['price']:,.2f}" if item and item.get("price") else "—"
        verdict = item.get("latest_verdict") if item else None
        conf_txt = f"{item['latest_confidence']:.1f}% confidence" if item and item.get("latest_confidence") is not None else "awaiting first tick"
        badge_html = verdict_badge(verdict) if verdict else NO_DECISION_BADGE

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Live Price", price_txt), unsafe_allow_html=True)
        c2.markdown(
            f'<div class="ic-metric-card"><div class="ic-metric-label">Algo Recommendation</div>'
            f'<div style="margin-top:0.35rem;">{badge_html}</div>'
            f'<div class="ic-metric-delta" style="color:#8B96A8;">{conf_txt}</div></div>',
            unsafe_allow_html=True,
        )
        c3.markdown(metric_card("Total Value", f"₹{portfolio['total_value']:,.2f}", tone=tone_for(portfolio["net_profit"])), unsafe_allow_html=True)
        c4.markdown(
            metric_card("P&L (session)", f"₹{portfolio['net_profit']:,.2f}", delta=f"{portfolio['total_return_pct']:+.2f}%", tone=tone_for(portfolio["net_profit"])),
            unsafe_allow_html=True,
        )

        if item and item.get("used_comex_proxy") and item.get("comex_price"):
            st.caption(f"NSE closed — price shown is a live COMEX {item.get('comex_symbol')} feed proxy (analysis only, not tradable).")

        pick = picks_by_symbol.get(symbol)
        if pick and pick.get("strategy"):
            s = pick["strategy"]
            st.caption(
                f"Options pick: {pick['direction']} · {s['structure_type']} · exp {s['expiry']} · "
                f"max loss {_fmt_inr_or_uncapped(s['max_loss'])} / max profit {_fmt_inr_or_uncapped(s['max_profit'])}"
            )


main_col, side_col = st.columns([2.6, 1], gap="medium")

with main_col:
    p1, p2 = st.columns(2, gap="medium")
    with p1:
        render_asset_panel("Nifty 50 (NSE)", "📈", "^NSEI", index_item, nse_portfolio)
    with p2:
        render_asset_panel("BTC (CoinDCX)", "₿", "BTCINR", btc_item, crypto_portfolio)

    st.divider()

    st.subheader("Open Positions")
    all_positions = [(p, "NSE") for p in nse_portfolio["positions"]] + [(p, "CRYPTO_INDIA") for p in crypto_portfolio["positions"]]
    if all_positions:
        for p, ex in all_positions:
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:700; color:#F8FAFC; font-size:1.05rem;">{p['symbol']}</span>
                        <span class="ic-badge" style="margin-left:0.6rem; background:#0B2A24;color:#2DD4BF;border:1px solid #14B8A6;">{p['side']}</span>
                        <span class="ic-badge" style="margin-left:0.4rem; background:#131B2E;color:#93C5FD;border:1px solid #1E293B;">{ex}</span>
                    </div>
                    <div style="font-family:'JetBrains Mono','SF Mono',monospace; color:#8B96A8;">
                        Qty {p['quantity']:g} @ ₹{p['avg_price']:,.2f}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No open positions.")

    st.write("")
    st.subheader("Recent Trades")
    st.caption("Most recent 15 across both the index and BTC portfolios.")
    all_trades = get("/trades") or []
    recent_trades = list(reversed(all_trades))[:15]
    if recent_trades:
        for t in recent_trades:
            action_color = "#2DD4BF" if t["action"] == "BUY" else "#FB7185"
            ex_tag = t.get("exchange") or "NSE"
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; align-items:center; justify-content:space-between;">
                    <div>
                        <span style="color:#5B6B84; font-size:0.82rem; font-family:'JetBrains Mono','SF Mono',monospace;">{t['timestamp']}</span>
                        <span style="color:{action_color}; font-weight:700; margin-left:0.7rem;">{t['action']}</span>
                        <span style="font-weight:700; color:#F8FAFC; margin-left:0.4rem;">{t['symbol']}</span>
                        <span class="ic-badge" style="margin-left:0.5rem; background:#131B2E;color:#93C5FD;border:1px solid #1E293B;">{ex_tag}</span>
                    </div>
                    <div style="font-family:'JetBrains Mono','SF Mono',monospace; color:#8B96A8; font-size:0.88rem;">
                        Qty {t['quantity']:g} @ ₹{t['price']:,.2f} · costs ₹{t['total_costs']:,.2f}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown('<div class="ic-card">No trades yet.</div>', unsafe_allow_html=True)

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

    st.markdown('<div class="ic-panel-title">Index Options</div>', unsafe_allow_html=True)
    st.caption("Nifty 50 / Bank Nifty positional structure picks (scan is a few minutes — runs the full committee for each).")
    if st.button("Scan Index Options", width="stretch"):
        with st.spinner("Scanning Nifty 50 and Bank Nifty options..."):
            post("/positional/scan")
        st.success("Scan complete.")
        st.rerun()
    if positional.get("scanned_at"):
        st.caption(f"Last scan: {positional['scanned_at']}")

    st.markdown('<div class="ic-panel-title">Market Status</div>', unsafe_allow_html=True)
    st.caption(f"NSE: {'open' if exchange_status.get('NSE') else 'closed'} · CoinDCX: {'open' if exchange_status.get('CRYPTO_INDIA') else 'closed'} (always open)")

    st.markdown('<div class="ic-panel-title">Danger Zone</div>', unsafe_allow_html=True)
    close_choice = st.selectbox("Force close which session?", ["Nifty 50 (NSE)", "BTC (CoinDCX)"], label_visibility="collapsed")
    close_exchange = "NSE" if close_choice.startswith("Nifty") else "CRYPTO_INDIA"
    if st.button("Force Close Session", width="stretch"):
        with st.spinner("Closing session..."):
            post("/session/close", exchange=close_exchange)
        st.success(f"{close_choice} session closed.")
        st.rerun()
