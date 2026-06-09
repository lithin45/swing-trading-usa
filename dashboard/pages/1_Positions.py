"""Open positions + their managed stop/target/R, and pending entries."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Positions", page_icon="📊", layout="wide")

from _auth import require_auth  # noqa: E402
from _data import load_positions, load_trades  # noqa: E402

require_auth()
st.title("📊 Positions")

positions = load_positions()
trades = load_trades()

st.subheader("Live positions (Alpaca)")
if positions.empty:
    st.caption("No live positions (or Alpaca keys not set).")
else:
    show = positions.copy()
    show["unrealized_pl"] = show["unrealized_pl"].map(lambda v: f"${v:,.2f}")
    st.dataframe(show, width="stretch", hide_index=True)

st.subheader("Tracked trades")
if trades.empty:
    st.caption("No trades recorded yet.")
else:
    open_like = trades[trades["status"].isin(["open", "pending_entry", "closing"])]
    cols = [c for c in [
        "signal_date", "symbol", "status", "qty", "actual_entry", "limit_price",
        "stop_price", "effective_stop", "target_price", "suggested_risk_pct",
    ] if c in trades.columns]
    st.dataframe((open_like if not open_like.empty else trades)[cols],
                 width="stretch", hide_index=True)
