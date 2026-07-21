import plotly.graph_objects as go
import streamlit as st

from api_client import get, post
from theme import inject_base_css, metric_card, page_header, tone_for, verdict_badge

st.set_page_config(page_title="Money Minting Machine", page_icon="📊", layout="wide")
inject_base_css()
page_header("📊", "Money Minting Machine", "Intraday NSE paper trading — explainable, trust-weighted multi-agent consensus")

app_settings = get("/settings")
tick_status = get("/session/tick-status")
portfolio = get("/portfolio")
overall = portfolio["overall"]
status_tone = "positive" if portfolio["status"] == "active" else "muted"

if not app_settings["llm_key_configured"]:
    st.warning(
        f"No LLM API key configured for provider `{app_settings['llm_provider']}`. The committee still runs "
        "(all indicator/consensus math is independent of the LLM), but agent reasoning text will fall back "
        "to templated summaries instead of LLM-generated narratives. Add a key to `backend/.env` and restart "
        "the backend for full explanations."
    )

# ---------------------------------------------------------------- top KPI strip
# Overall Return (across all sessions) is folded in here rather than living in
# its own section further down the page - one KPI strip, no separate block.
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.markdown(metric_card("Status", portfolio["status"].upper(), tone=status_tone), unsafe_allow_html=True)
if app_settings["data_mode"] == "live":
    exchange_delta = "open now" if portfolio["exchange"] == app_settings["currently_open_exchange"] else "closed — will resume next tick"
    exchange_tone = "positive" if portfolio["exchange"] == app_settings["currently_open_exchange"] else "negative"
else:
    exchange_delta = "replay demo — not live"
    exchange_tone = "muted"
k2.markdown(metric_card("Exchange", portfolio["exchange"], delta=exchange_delta, tone=exchange_tone), unsafe_allow_html=True)
k3.markdown(metric_card("Total Value", f"₹{portfolio['total_value']:,.2f}", tone=tone_for(portfolio["net_profit"])), unsafe_allow_html=True)
k4.markdown(
    metric_card("Today's Return", f"₹{portfolio['net_profit']:,.2f}", delta=f"{portfolio['total_return_pct']:+.2f}%", tone=tone_for(portfolio["net_profit"])),
    unsafe_allow_html=True,
)
k5.markdown(
    metric_card("Overall Return", f"₹{overall['net_profit']:,.2f}", delta=f"{overall['return_pct']:+.2f}% · {overall['total_sessions']} sessions", tone=tone_for(overall["net_profit"])),
    unsafe_allow_html=True,
)
k6.markdown(metric_card("Cash", f"₹{portfolio['cash']:,.2f}"), unsafe_allow_html=True)
k7.markdown(metric_card("Open Exposure", f"₹{portfolio['open_positions_value']:,.2f}"), unsafe_allow_html=True)

st.write("")
main_col, side_col = st.columns([2.3, 1], gap="medium")

# ================================================================== LEFT: single flat page
with main_col:
    watchlist = app_settings["watchlist"]
    held_symbols = [p["symbol"] for p in portfolio["positions"]]
    default_symbol = held_symbols[0] if held_symbols else (watchlist[0] if watchlist else "^NSEI")
    chart_options = list(dict.fromkeys([*held_symbols, *watchlist]))
    hc1, hc2 = st.columns([1, 3])
    with hc1:
        chart_symbol = st.selectbox("Symbol", chart_options or [default_symbol], index=0, label_visibility="collapsed")
    chart_data = get(f"/market/chart/{chart_symbol}", silent=True)
    if chart_data:
        st.plotly_chart(go.Figure(chart_data["figure"]), width="stretch", config={"displayModeBar": False})
        if chart_data.get("used_comex_proxy"):
            st.info(
                f"NSE is currently closed — this chart is reading live COMEX futures "
                f"(`{chart_data.get('source_symbol')}`) as an analysis-feed proxy for {chart_symbol}. "
                "No trade can execute on this feed until NSE reopens; P&L always uses the real NSE price."
            )
    else:
        st.markdown('<div class="ic-card">No chart data available for this symbol right now.</div>', unsafe_allow_html=True)

    st.divider()

    # -------------------------------------------------------------- session summary
    f1, f2, f3, f4 = st.columns(4)
    f1.markdown(metric_card("Final Portfolio Value", f"₹{portfolio['total_value']:,.2f}", tone=tone_for(portfolio["net_profit"])), unsafe_allow_html=True)
    f2.markdown(
        metric_card("Net Profit / Loss", f"₹{portfolio['net_profit']:,.2f}", delta="after brokerage, taxes & trading costs", tone=tone_for(portfolio["net_profit"])),
        unsafe_allow_html=True,
    )
    f3.markdown(metric_card("Total Return", f"{portfolio['total_return_pct']:+.1f}%", tone=tone_for(portfolio["total_return_pct"])), unsafe_allow_html=True)
    f4.markdown(
        metric_card("Win Rate", f"{portfolio['win_rate_pct']:.0f}%", delta=f"{portfolio['winning_trades_count']} of {portfolio['closed_trades_count']} trades" if portfolio["closed_trades_count"] else "no closed trades yet"),
        unsafe_allow_html=True,
    )

    st.write("")
    st.subheader("Committee Recommendations")
    st.caption("Latest verdict from the multi-agent committee for each watchlisted symbol.")
    recommendations = get("/watchlist", silent=True) or []
    no_decision_badge = '<span class="ic-badge" style="background:#161B27;color:#5B6B84;border:1px solid #2A3140;">NO DECISION YET</span>'
    if recommendations:
        for item in recommendations:
            verdict = item.get("latest_verdict")
            badge_html = verdict_badge(verdict) if verdict else no_decision_badge
            conf_txt = f"{item['latest_confidence']:.1f}% directional confidence" if item.get("latest_confidence") is not None else "awaiting first tick"
            ts_txt = item.get("latest_timestamp") or ""
            price_txt = f"₹{item['price']:,.2f}" if item.get("price") else "—"
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:700; color:#F8FAFC; font-size:1.05rem;">{item['symbol']}</span>
                        <span style="margin-left:0.6rem;">{badge_html}</span>
                    </div>
                    <div style="font-family:'JetBrains Mono','SF Mono',monospace; color:#8B96A8; font-size:0.85rem; text-align:right;">
                        {price_txt} · {conf_txt}<br><span style="font-size:0.72rem; color:#5B6B84;">{ts_txt}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if item.get("used_comex_proxy") and item.get("comex_price"):
                st.caption(f"NSE closed — analysis fed by COMEX {item.get('comex_symbol')} at {item['comex_price']:.2f} (feed only, not tradable).")
            if item.get("latest_decision_id"):
                decision = get(f"/decisions/{item['latest_decision_id']}", silent=True)
                if decision and decision.get("consensus_reasoning"):
                    with st.expander(f"Why the committee's latest call on {item['symbol']}" + (f" ({verdict})" if verdict else "")):
                        st.write(decision["consensus_reasoning"])
    else:
        st.info("No recommendations yet — run a tick to get the committee's first read.")

    st.divider()

    # -------------------------------------------------------------- Positions & Trades
    st.subheader("Positions & Trades")
    st.markdown("**Open Positions**")
    if portfolio["positions"]:
        for p in portfolio["positions"]:
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:700; color:#F8FAFC; font-size:1.05rem;">{p['symbol']}</span>
                        <span class="ic-badge" style="margin-left:0.6rem; background:#0B2A24;color:#2DD4BF;border:1px solid #14B8A6;">{p['side']}</span>
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
    st.markdown("**Trade History (all sessions)**")
    st.caption("Retained and appended across every session rollover, not reset when a new session starts.")
    trades = get("/trades") or []
    recent_trades = list(reversed(trades))[-20:]  # chronological, most recent 20
    if recent_trades:
        for t in recent_trades:
            action_color = "#2DD4BF" if t["action"] == "BUY" else "#FB7185"
            st.markdown(
                f"""
                <div class="ic-card" style="display:flex; align-items:center; justify-content:space-between;">
                    <div>
                        <span style="color:#5B6B84; font-size:0.82rem; font-family:'JetBrains Mono','SF Mono',monospace;">{t['timestamp']}</span>
                        <span style="color:{action_color}; font-weight:700; margin-left:0.7rem;">{t['action']}</span>
                        <span style="font-weight:700; color:#F8FAFC; margin-left:0.4rem;">{t['symbol']}</span>
                    </div>
                    <div style="font-family:'JetBrains Mono','SF Mono',monospace; color:#8B96A8; font-size:0.88rem;">
                        Qty {t['quantity']:g} @ ₹{t['price']:,.2f} · costs ₹{t['total_costs']:,.2f}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if t.get("reasoning"):
                verdict_txt = f"{t['verdict']} · {t['directional_confidence']:.1f}% directional confidence" if t.get("verdict") else ""
                with st.expander(f"Why the committee made this {t['action']} call" + (f" ({verdict_txt})" if verdict_txt else "")):
                    st.write(t["reasoning"])
    else:
        st.markdown('<div class="ic-card">No trades yet this session.</div>', unsafe_allow_html=True)

# ================================================================== RIGHT: session control panel
with side_col, st.container(border=True):
    st.markdown('<div class="ic-panel-title">Auto-Trading</div>', unsafe_allow_html=True)
    if tick_status["paused"]:
        st.markdown(
            '<span class="ic-badge" style="background:#301419;color:#FB7185;border:1px solid #E11D48;">⏸ PAUSED</span>',
            unsafe_allow_html=True,
        )
        st.caption("The committee will not run on its own until resumed.")
        if st.button("▶ Resume Auto-Trading", width="stretch", type="primary"):
            post("/session/resume")
            st.success("Auto-trading resumed.")
            st.rerun()
    else:
        st.markdown(
            f'<span class="ic-badge" style="background:#0B2A24;color:#2DD4BF;border:1px solid #14B8A6;">● RUNNING · every {tick_status["tick_minutes"]} min</span>',
            unsafe_allow_html=True,
        )
        st.caption("Ticks fire automatically on schedule.")
        if st.button("⏸ Pause (saves LLM tokens)", width="stretch"):
            post("/session/pause")
            st.success("Auto-trading paused.")
            st.rerun()

    rc1, rc2 = st.columns(2)
    with rc1:
        if st.button("Run Tick", width="stretch"):
            with st.spinner("Running committee tick..."):
                post("/session/tick")
            st.success("Tick complete.")
            st.rerun()
    with rc2:
        if st.button("Refresh", width="stretch"):
            st.rerun()

    st.markdown('<div class="ic-panel-title">Watchlist Pulse</div>', unsafe_allow_html=True)
    pulse = get("/watchlist", silent=True) or []
    pulse_rows = ""
    no_verdict_badge = '<span class="ic-badge" style="background:#161B27;color:#5B6B84;border:1px solid #2A3140;">—</span>'
    for item in pulse:
        price_txt = f"₹{item['price']:.2f}" if item["price"] else "—"
        badge_html = verdict_badge(item["latest_verdict"]) if item["latest_verdict"] else no_verdict_badge
        pulse_rows += (
            '<div style="display:flex; justify-content:space-between; align-items:center; padding:0.35rem 0;">'
            f'<span style="color:#F8FAFC; font-weight:600; font-size:0.85rem;">{item["symbol"].replace(".NS", "")}</span>'
            f'{badge_html}'
            f'<span class="ic-mono" style="color:#8B96A8; font-size:0.8rem;">{price_txt}</span>'
            "</div>"
        )
        if item.get("used_comex_proxy") and item.get("comex_price"):
            pulse_rows += (
                '<div style="display:flex; justify-content:flex-end; padding:0 0 0.35rem 0;">'
                f'<span class="ic-mono" style="color:#93C5FD; font-size:0.72rem;">'
                f'COMEX {item.get("comex_symbol")} feed: {item["comex_price"]:.2f} (analysis only, NSE closed)</span>'
                "</div>"
            )
    if pulse_rows:
        st.markdown(pulse_rows, unsafe_allow_html=True)
    else:
        st.caption("No watchlist data yet.")

    with st.expander("Session Info"):
        st.caption(f"Starting capital ₹{app_settings['starting_capital_inr']:,.0f} · leverage {app_settings['leverage']:.0f}× (no margin) · tick every {app_settings['tick_minutes']} min · data mode {app_settings['data_mode'].upper()}")
        st.caption(f"LLM provider: {app_settings['llm_provider']} ({'configured' if app_settings['llm_key_configured'] else 'not configured — templated reasoning only'})")
        st.markdown(
            " ".join(f'<span class="ic-badge" style="background:#131B2E;color:#93C5FD;border:1px solid #1E293B">{s}</span>' for s in app_settings["watchlist"]),
            unsafe_allow_html=True,
        )

    st.markdown('<div class="ic-panel-title">Danger Zone</div>', unsafe_allow_html=True)
    if st.button("Force Close Session", width="stretch"):
        with st.spinner("Closing session..."):
            post("/session/close")
        st.success("Session closed.")
        st.rerun()
