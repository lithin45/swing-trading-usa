"""Swing Trading dashboard — Overview (landing page).

Run locally:  streamlit run dashboard/app.py
Deploy:       Streamlit Community Cloud, entrypoint dashboard/app.py (see README).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

st.set_page_config(page_title="Swing Trading — Paper", page_icon="📈", layout="wide")

from _auth import require_auth  # noqa: E402
from _data import (  # noqa: E402
    load_account,
    load_brief,
    load_positions,
    load_signals,
    load_snapshots,
    load_trades,
)

require_auth()

st.title("📈 Swing Trading — Paper Account")
st.caption("Automated Alpaca paper trading · decision support, not financial advice")

# --- live account snapshot ---
acct = load_account()
positions = load_positions()
trades = load_trades()
open_trades = (
    trades[trades["status"].isin(["open", "pending_entry", "closing"])]
    if not trades.empty else trades
)

c1, c2, c3, c4 = st.columns(4)
if acct:
    c1.metric("Equity", f"${acct['equity']:,.2f}")
    c2.metric("Cash", f"${acct['cash']:,.2f}")
    c3.metric("Buying power", f"${acct['buying_power']:,.2f}")
else:
    c1.info("Alpaca keys not set — live account hidden. Add them in Streamlit secrets.")
c4.metric("Open positions", 0 if positions.empty else len(positions))

# --- equity curve ---
st.subheader("Equity curve")
snaps = load_snapshots()
if snaps.empty:
    st.caption("No account snapshots yet — they accrue once `swing-signals manage` runs.")
else:
    st.line_chart(snaps.set_index("ts")["equity"], height=260)

# --- today's signals + regime ---
left, right = st.columns([3, 2])
with left:
    st.subheader("Latest signals")
    sigs = load_signals(limit=25)
    if sigs.empty:
        st.caption("No signals recorded yet.")
    else:
        cols = [c for c in [
            "signal_date", "symbol", "composite_score", "conviction_tier", "regime_state",
            "entry_zone_high", "stop_price", "target_price", "suggested_shares",
        ] if c in sigs.columns]
        st.dataframe(sigs[cols], width="stretch", hide_index=True)

with right:
    st.subheader("AI brief")
    brief = load_brief(date.today())
    if brief:
        st.write(brief)
    else:
        st.caption("No brief yet today (the daily run writes it when an Anthropic key is set).")

    if not open_trades.empty and "regime_state" in load_signals(limit=1).columns:
        latest = load_signals(limit=1)
        if not latest.empty:
            st.metric("Market regime", str(latest.iloc[0].get("regime_state", "—")))
