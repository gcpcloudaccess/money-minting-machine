import streamlit as st

from api_client import get
from theme import inject_base_css, metric_card, page_header, verdict_badge, verdict_icon

st.set_page_config(page_title="Committee Meetings", page_icon="🏛️", layout="wide")
inject_base_css()
page_header("🏛️", "Committee Meetings", "Full debate transcript behind every decision: agent votes, critic pushback, and the trust-weighted consensus reasoning")

if st.button("🔄 Refresh"):
    st.rerun()

decisions = get("/decisions", limit=100)

if not decisions:
    st.info("No committee decisions yet. Run a tick from the Dashboard or analyze a symbol in Stock Search.")
    st.stop()

label_by_id = {
    d["id"]: f"[{d['timestamp']}] {d['symbol']} — {d['verdict']} ({d['directional_confidence']:.1f}%)" for d in decisions
}

preselect = st.session_state.pop("selected_decision_id", None)
ids = list(label_by_id.keys())
default_index = ids.index(preselect) if preselect in ids else 0

chosen_id = st.selectbox("Select a decision", ids, index=default_index, format_func=lambda i: label_by_id[i])
decision = next(d for d in decisions if d["id"] == chosen_id)

st.markdown(
    f"""
    <div class="ic-card" style="display:flex; align-items:center; justify-content:space-between; margin-top:0.5rem;">
        <div>
            <span style="font-size:1.4rem; font-weight:700; color:#F1F5F9;">{decision['symbol']}</span>
            <span style="margin-left:0.8rem;">{verdict_badge(decision['verdict'])}</span>
        </div>
        <div style="font-family:'SF Mono','Roboto Mono',monospace; color:#94A3B8; font-size:0.95rem;">
            {decision['directional_confidence']:.1f}% directional confidence
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(f"{decision['timestamp']} · executed={decision['executed']}")

st.subheader("Why the committee reached this verdict")
st.markdown(f'<div class="ic-card">{decision["consensus_reasoning"]}</div>', unsafe_allow_html=True)

st.subheader("Agent Votes & Trust-Weighted Influence")
votes = decision["agent_votes"]
analyst_votes = [v for v in votes if v["agent_type"] == "analyst"]
debate_votes = [v for v in votes if v["agent_type"] == "debate"]
critic_votes = [v for v in votes if v["agent_type"] == "critic"]

tab1, tab2, tab3 = st.tabs(["Analysts", "Debate Agent", "Critics (Debate Loop)"])
with tab1:
    for v in sorted(analyst_votes, key=lambda x: x["weight_used"], reverse=True):
        with st.expander(f"{verdict_icon(v['action'])} {v['agent_name']} — {v['action']} (confidence {v['confidence']:.2f}, weight {v['weight_used']:.3f})"):
            st.write(v["reasoning"])
            for e in v["evidence"]:
                st.markdown(f"- {e}")
with tab2:
    st.caption("Surfaces the strongest contradicting analyst views before the critics weigh in. Low confidence here means the room is genuinely split.")
    for v in debate_votes:
        st.markdown(
            f"""
            <div class="ic-card">
                <div>{verdict_badge(v['action'])} <span style="color:#94A3B8; font-size:0.85rem; margin-left:0.5rem;">synthesis confidence {v['confidence']:.2f} · weight in consensus {v['weight_used']:.3f}</span></div>
                <div style="margin-top:0.6rem; color:#CBD5E1;">{v['reasoning']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
with tab3:
    for v in sorted(critic_votes, key=lambda x: x["weight_used"], reverse=True):
        with st.expander(f"{verdict_icon(v['action'])} {v['agent_name']} — {v['action']} (confidence {v['confidence']:.2f}, weight {v['weight_used']:.3f})"):
            st.write(v["reasoning"])
            for e in v["evidence"]:
                st.markdown(f"- {e}")

st.subheader("Alternative Stocks Considered")
alts = decision["alternatives"].get("alternatives", [])
if alts:
    st.dataframe(alts, width="stretch")
else:
    st.info("No stronger alternative flagged this tick.")

st.subheader("Expected Risk & Return")
err = decision.get("expected_risk_return") or {}
if err.get("scenarios"):
    rc1, rc2, rc3 = st.columns(3)
    rc1.markdown(metric_card("Expected Risk", f"₹{err['expected_risk_inr']:,.2f}", tone="negative"), unsafe_allow_html=True)
    rc2.markdown(metric_card("Expected Return", f"₹{err['expected_return_inr']:,.2f}", tone="positive"), unsafe_allow_html=True)
    rc3.markdown(metric_card("Risk/Reward Ratio", f"{err['risk_reward_ratio']}" if err["risk_reward_ratio"] else "—"), unsafe_allow_html=True)
    st.write("")
    st.dataframe(err["scenarios"], width="stretch")
