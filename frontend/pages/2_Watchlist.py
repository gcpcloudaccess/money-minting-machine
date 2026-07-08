import streamlit as st

from api_client import get
from theme import inject_base_css, page_header, verdict_badge

st.set_page_config(page_title="Watchlist", page_icon="👀", layout="wide")
inject_base_css()
page_header("👀", "Watchlist", "Latest committee signal per symbol — updates as session ticks run")

if st.button("🔄 Refresh"):
    st.rerun()

watchlist = get("/watchlist")

st.write("")
cols = st.columns(4)
for i, item in enumerate(watchlist):
    conf_txt = f"{item['latest_confidence']:.1f}% directional confidence" if item["latest_confidence"] is not None else "No decision yet"
    price_txt = f"₹{item['price']:.2f}" if item["price"] else "—"
    with cols[i % 4]:
        st.markdown(
            f"""
            <div class="ic-card" style="min-height:132px">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <span style="font-weight:700; color:#F1F5F9; font-size:1.05rem;">{item['symbol']}</span>
                    <span style="font-family:'SF Mono','Roboto Mono',monospace; color:#94A3B8; font-size:0.9rem;">{price_txt}</span>
                </div>
                <div style="margin-top:0.7rem;">{verdict_badge(item['latest_verdict'])}</div>
                <div style="margin-top:0.5rem; font-size:0.8rem; color:#64748B;">{conf_txt}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown('<hr class="ic-divider">', unsafe_allow_html=True)
st.subheader("Jump to a decision's full committee transcript")
options = {f"{item['symbol']} — {item['latest_verdict'] or 'No decision'}": item["latest_decision_id"] for item in watchlist if item["latest_decision_id"]}
if options:
    choice = st.selectbox("Select", list(options.keys()))
    if st.button("View in Committee Meetings", type="primary"):
        st.session_state["selected_decision_id"] = options[choice]
        st.switch_page("pages/4_Committee_Meetings.py")
else:
    st.info("No decisions recorded yet. Run a tick from the Dashboard or analyze a symbol in Stock Search.")
