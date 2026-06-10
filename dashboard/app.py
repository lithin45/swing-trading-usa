"""Swing Trading dashboard — Overview (landing page).

Run locally:  streamlit run dashboard/app.py
Deploy:       Streamlit Community Cloud, entrypoint dashboard/app.py (see README).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import streamlit as st

st.set_page_config(page_title="Swing Trading — Paper", page_icon="📈", layout="wide")

from _auth import require_auth  # noqa: E402
from _charts import equity_curve  # noqa: E402
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

acct = load_account()
positions = load_positions()
trades = load_trades()
snaps = load_snapshots()
sigs = load_signals(limit=25)

open_like = (
    trades[trades["status"].isin(["open", "pending_entry", "closing"])]
    if not trades.empty else trades
)
open_only = trades[trades["status"] == "open"] if not trades.empty else trades

# --- status strip: the "is everything OK and what's at risk" answer ------------
c1, c2, c3, c4, c5 = st.columns(5)

# Equity (live Alpaca, falling back to the last persisted snapshot) + day delta.
equity = acct["equity"] if acct else (
    float(snaps.iloc[-1]["equity"]) if not snaps.empty else None
)
delta = None
if not snaps.empty and len(snaps) >= 2 and equity is not None:
    prev = float(snaps.iloc[-2]["equity"])
    delta = equity - prev
c1.metric(
    "Equity" if acct else "Equity (last snapshot)",
    "—" if equity is None else f"${equity:,.0f}",
    delta=None if delta is None else f"{delta:+,.0f}",
)

# Open positions: live broker count, else the tracked-trade view.
n_open = len(positions) if not positions.empty else (0 if open_only.empty else len(open_only))
pend = 0 if open_like.empty else int((open_like["status"] == "pending_entry").sum())
c2.metric("Open positions", n_open, delta=f"{pend} pending" if pend else None,
          delta_color="off")

# Portfolio heat: the sum of open risk fractions vs the configured 10% cap.
heat = 0.0 if open_like.empty else float(open_like["suggested_risk_pct"].fillna(0).sum())
c3.metric("Open heat", f"{heat:.1%}", help="Sum of open risk-at-stop vs the 10% cap")

# Latest regime + signal freshness — a stale date means the daily run is broken.
last_sig_day = None if sigs.empty else sigs.iloc[0]["signal_date"]
regime = "—" if sigs.empty else str(sigs.iloc[0].get("regime_state") or "—")
c4.metric("Market regime", regime)
c5.metric("Last signals", "—" if last_sig_day is None else str(last_sig_day))

if last_sig_day is not None:
    age = int(np.busday_count(last_sig_day, date.today()))
    if age > 2:
        st.warning(
            f"⚠ No signals for {age} business days — check the daily GitHub Actions run "
            "and healthchecks.io before trusting anything below."
        )

if not acct:
    st.caption("Alpaca keys not set — live account hidden; showing persisted history only.")

# --- equity curve with drawdown (tight y-axis; st.line_chart hides real swings) -
st.subheader("Equity curve")
if snaps.empty:
    st.caption("No account snapshots yet — they accrue once `swing-signals manage` runs.")
else:
    st.plotly_chart(equity_curve(snaps), width="stretch")

# --- today's activity: what the bot actually DID this session ------------------
st.subheader("Recent activity")
if trades.empty:
    st.caption("No trades recorded yet.")
else:
    cutoff = date.today() - timedelta(days=5)
    lines: list[str] = []
    for _, t in trades.iterrows():
        sym = t["symbol"]
        if t.get("entry_fill_date") and t["entry_fill_date"] >= cutoff:
            lines.append(f"🟢 **{sym}** filled {t.get('filled_qty') or t.get('qty'):g} sh "
                         f"@ ${t.get('actual_entry') or 0:,.2f} ({t['entry_fill_date']})")
        if t.get("partial_fill_date") and t["partial_fill_date"] >= cutoff:
            lines.append(f"🎯 **{sym}** scaled out {t.get('partial_qty') or 0:g} sh "
                         f"@ ${t.get('partial_fill_price') or 0:,.2f} — stop to breakeven "
                         f"({t['partial_fill_date']})")
        if t.get("exit_date") and t["exit_date"] >= cutoff and t["status"] == "closed":
            r = t.get("realized_r")
            lines.append(f"🔴 **{sym}** closed {t.get('exit_reason') or ''} "
                         f"@ ${t.get('exit_price') or 0:,.2f}"
                         + (f" → **{r:+.2f}R**" if r is not None else "")
                         + f" ({t['exit_date']})")
        if t["status"] == "pending_entry":
            lines.append(f"⏳ **{sym}** limit ${t.get('limit_price') or 0:,.2f} resting "
                         f"(day {int(t.get('pending_days') or 0) + 1} of 3)")
    if lines:
        st.markdown("\n".join(f"- {ln}" for ln in lines[:12]))
    else:
        st.caption("Nothing in the last 5 days.")

# --- today's signals + AI brief -------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.subheader("Latest signals")
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
