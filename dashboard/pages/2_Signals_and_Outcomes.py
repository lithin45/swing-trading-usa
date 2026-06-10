"""Signal history + realized paper performance (win rate, expectancy, profit factor)."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Signals & Outcomes", page_icon="🎯", layout="wide")

from _auth import require_auth  # noqa: E402
from _charts import cumulative_r, r_histogram  # noqa: E402
from _data import load_signals, load_trades, trade_stats  # noqa: E402

require_auth()
st.title("🎯 Signals & Outcomes")

trades = load_trades()
stats = trade_stats(trades) if not trades.empty else {"n": 0}

st.subheader("Realized paper performance (closed trades)")
if stats["n"] == 0:
    st.caption("No closed trades yet — stats appear once positions resolve.")
else:
    a, b, c, d, e = st.columns(5)
    a.metric("Closed", stats["n"])
    b.metric("Win rate", f"{stats['win_rate']:.0%}")
    c.metric("Expectancy", f"{stats['expectancy']:.2f} R")
    pf = stats["profit_factor"]
    d.metric("Profit factor", "∞" if pf == float("inf") else f"{pf:.2f}")
    e.metric("Total P&L", f"${stats['total_pnl']:,.2f}")

    closed = trades[trades["status"] == "closed"]
    if "realized_r" in closed and not closed.empty:
        left, right = st.columns(2)
        with left:
            st.caption("R distribution — the asymmetric payoff is the whole strategy: "
                       "many small losses, a few large wins.")
            st.plotly_chart(r_histogram(closed), width="stretch")
        with right:
            st.caption("Cumulative realized R — the expectancy accruing over time.")
            st.plotly_chart(cumulative_r(closed), width="stretch")

        if "exit_reason" in closed:
            st.caption("Exits by reason")
            reason = closed.groupby("exit_reason")["realized_r"].agg(["count", "mean"])
            reason.columns = ["trades", "avg R"]
            st.dataframe(reason.round(2), width="stretch")

st.subheader("All tracked trades")
if not trades.empty:
    cols = [c for c in [
        "signal_date", "symbol", "status", "actual_entry", "exit_price", "exit_reason",
        "realized_r", "pct_return", "pnl", "bars_held",
    ] if c in trades.columns]
    st.dataframe(trades[cols], width="stretch", hide_index=True)

st.subheader("Signal history")
sigs = load_signals(limit=500)
if not sigs.empty:
    cols = [c for c in [
        "signal_date", "symbol", "composite_score", "conviction_tier", "agreement_score",
        "regime_state", "entry_zone_high", "stop_price", "target_price",
    ] if c in sigs.columns]
    st.dataframe(sigs[cols], width="stretch", hide_index=True)
