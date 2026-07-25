"""Positional Picks: the ranked "best positional options pick" dashboard tab
(see docs/POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md) - screens the whole
positional universe (Settings.positional_universe, wider than the 3-symbol
intraday watchlist), ranks candidates by trust-weighted directional
conviction, and shows the actual options structure (strikes/expiry/max
loss/payoff) the Strategy Architect built for the top pick, not just a
BUY/SELL label."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import get, post
from theme import inject_base_css, page_header, tone_for, verdict_badge

st.set_page_config(page_title="Positional Picks — Money Minting Machine", page_icon="🎯", layout="wide")
inject_base_css()
page_header("🎯", "Positional Picks", "Ranked multi-week options candidates — trust-weighted committee, screened across the full positional universe")

universe_info = get("/positional/universe")
picks_data = get("/positional/picks")

top_bar1, top_bar2, top_bar3 = st.columns([2, 1, 1])
with top_bar1:
    if picks_data and picks_data.get("scanned_at"):
        st.caption(f"Last scan: {picks_data['scanned_at']} · {len(picks_data['picks'])} candidates · universe size {len(universe_info['universe']) if universe_info else '—'}")
    else:
        st.caption("No scan has been run yet.")
with top_bar3:
    run_scan = st.button("Run Positional Scan", type="primary", use_container_width=True)

if run_scan:
    with st.spinner(f"Running the full committee across {len(universe_info['universe']) if universe_info else 'the'} positional universe — this evaluates ~19 agents per symbol and can take several minutes..."):
        scan_result = post("/positional/scan")
    st.success(f"Scan complete — {scan_result['scan_size']} candidates evaluated.")
    picks_data = {"scan_id": None, "scanned_at": "just now", "picks": scan_result["picks"]}

picks = (picks_data or {}).get("picks", [])

if not picks:
    st.info("No positional picks yet. Click **Run Positional Scan** above to evaluate the positional universe (configured in `.env` as `POSITIONAL_UNIVERSE`).")
    st.stop()

# ---------------------------------------------------------------- ranked table
st.markdown('<div class="ic-panel-title">Ranked candidates</div>', unsafe_allow_html=True)

rows = []
for p in picks:
    strat = p.get("strategy")
    legs_txt = "—"
    if strat and strat.get("legs"):
        legs_txt = " / ".join(f"{l['action']} {l['option_type']} {l['strike']:g}" for l in strat["legs"])
    rows.append({
        "Symbol": p["symbol"],
        "Direction": p["direction"],
        "Conviction %": round(p["directional_confidence"], 1),
        "Structure": (strat["structure_type"].replace("_", " ") if strat else "—"),
        "Legs": legs_txt,
        "Expiry": strat["expiry"] if strat else "—",
        "Max Loss (₹/sh)": strat["max_loss"] if strat else None,
        "Max Profit (₹/sh)": strat["max_profit"] if strat and strat["max_profit"] is not None else ("uncapped" if strat else None),
        "IV Rank": p.get("iv_rank"),
        "Days to Catalyst": p.get("days_to_next_catalyst"),
        "Next Catalyst": p.get("next_catalyst_label") or "—",
    })

df = pd.DataFrame(rows)
st.dataframe(
    df, use_container_width=True, hide_index=True,
    column_config={
        "Conviction %": st.column_config.ProgressColumn("Conviction %", min_value=0, max_value=100, format="%.1f%%"),
    },
)

st.markdown('<hr class="ic-divider" />', unsafe_allow_html=True)

# ---------------------------------------------------------------- drill-down
st.markdown('<div class="ic-panel-title">Pick drill-down</div>', unsafe_allow_html=True)

symbols = [p["symbol"] for p in picks]
selected_symbol = st.selectbox("Symbol", symbols, index=0, label_visibility="collapsed")

detail = get(f"/positional/picks/{selected_symbol}", silent=True)

if detail is None:
    st.warning("No detail available for this symbol yet.")
    st.stop()

d1, d2, d3, d4 = st.columns(4)
d1.metric("Verdict", detail["direction"])
d2.metric("Directional confidence", f"{detail['directional_confidence']:.1f}%")
d3.metric("IV Rank", f"{detail['iv_rank']:.0f}" if detail.get("iv_rank") is not None else "—")
d4.metric("Next catalyst", f"{detail['days_to_next_catalyst']}d" if detail.get("days_to_next_catalyst") is not None else "—", help=detail.get("next_catalyst_label"))

st.markdown(verdict_badge(detail["direction"]), unsafe_allow_html=True)
st.write(detail["consensus_reasoning"])

strat = detail.get("strategy")
left, right = st.columns([1.3, 1])

with left:
    st.markdown('<div class="ic-panel-title">Payoff at expiry</div>', unsafe_allow_html=True)
    if strat and strat.get("payoff_points"):
        points = strat["payoff_points"]
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"width": 2.5, "color": "#2DD4BF"}, fill="tozeroy", fillcolor="rgba(45, 212, 191, 0.12)"))
        fig.add_hline(y=0, line_color="#475569", line_width=1)
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#8B96A8", "family": "Inter, Segoe UI, sans-serif"},
            xaxis={"title": "Underlying price at expiry (₹)", "gridcolor": "#1A2333"},
            yaxis={"title": "P&L per share (₹)", "gridcolor": "#1A2333"},
            margin={"t": 20, "b": 40, "l": 50, "r": 20}, height=340,
        )
        st.plotly_chart(fig, use_container_width=True)
        max_profit_txt = "uncapped" if strat["max_profit"] is None else f"₹{strat['max_profit']:.2f}/sh"
        breakeven_txt = ", ".join(f"₹{b:,.0f}" for b in strat["breakeven"]) if strat["breakeven"] else "—"
        st.caption(
            f"**{strat['structure_type'].replace('_', ' ').title()}** · expiry {strat['expiry']} · "
            f"max loss ₹{strat['max_loss']:.2f}/sh · max profit {max_profit_txt} · "
            f"breakeven {breakeven_txt}. "
            "Figures are per share — multiply by NSE lot size for actual contract P&L."
        )
        st.caption(strat.get("rationale", ""))
    elif detail["direction"] in ("BUY", "SELL"):
        st.info("Directional pick, but no options chain was available this scan to build a structure (NSE unreachable, or symbol not in F&O).")
    else:
        st.caption("No trade — verdict is HOLD/WAIT.")

with right:
    st.markdown('<div class="ic-panel-title">Conviction trend</div>', unsafe_allow_html=True)
    trend = detail.get("conviction_trend", [])
    if len(trend) >= 2:
        tdf = pd.DataFrame(trend)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=tdf["timestamp"], y=tdf["directional_confidence"], mode="lines+markers", line={"color": "#2DD4BF", "width": 2}))
        fig2.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#8B96A8", "family": "Inter, Segoe UI, sans-serif"},
            xaxis={"title": "Scan", "gridcolor": "#1A2333"}, yaxis={"title": "Directional confidence %", "gridcolor": "#1A2333"},
            margin={"t": 20, "b": 40, "l": 50, "r": 20}, height=340,
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.caption("Run more scans over time to build a conviction trend for this symbol.")

st.markdown('<div class="ic-panel-title">Agent vote breakdown</div>', unsafe_allow_html=True)
votes = detail.get("agent_votes", [])
details_by_name = {d["agent_name"]: d for d in detail.get("agent_details", [])}
if votes:
    vote_rows = []
    for v in votes:
        weight_info = details_by_name.get(v["agent_name"], {})
        vote_rows.append({
            "Agent": v["agent_name"],
            "Type": v["agent_type"],
            "Action": v["action"],
            "Confidence": v["confidence"],
            "Weight": weight_info.get("weight"),
            "Trust": weight_info.get("trust_score"),
            "Relevance": weight_info.get("expertise_relevance"),
        })
    vdf = pd.DataFrame(vote_rows).sort_values("Weight", ascending=False, na_position="last")
    st.dataframe(vdf, use_container_width=True, hide_index=True)

    with st.expander("Full agent reasoning"):
        for v in votes:
            st.markdown(f"**{v['agent_name']}** — {verdict_badge(v['action'])}", unsafe_allow_html=True)
            st.caption(v["reasoning"])
else:
    st.caption("No agent vote detail available.")
