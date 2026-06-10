"""Open positions: where the stop is, what's at risk, and how each trade is doing."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Positions", page_icon="📊", layout="wide")

from _auth import require_auth  # noqa: E402
from _data import load_positions, load_trades  # noqa: E402

require_auth()
st.title("📊 Positions")

positions = load_positions()
trades = load_trades()
live_px = (
    {} if positions.empty else dict(zip(positions["symbol"], positions["current"], strict=False))
)

open_tr = trades[trades["status"] == "open"] if not trades.empty else pd.DataFrame()
pending = trades[trades["status"] == "pending_entry"] if not trades.empty else pd.DataFrame()

# --- the risk picture, one row per open trade -----------------------------------
st.subheader("Open trades — risk view")
if open_tr.empty:
    st.caption("No open trades.")
else:
    rows = []
    for _, t in open_tr.iterrows():
        entry = t.get("actual_entry") or t.get("limit_price") or np.nan
        eff = t.get("effective_stop") or t.get("stop_price") or np.nan
        rps = t.get("risk_per_share") or np.nan
        qty = float(t.get("filled_qty") or t.get("qty") or 0.0)
        partial = bool(t.get("partial_done"))
        remaining = qty - float(t.get("partial_qty") or 0.0) if partial else qty
        cur = live_px.get(t["symbol"])
        unreal_r = (
            round((cur - entry) / rps, 2)
            if cur is not None and np.isfinite(rps) and rps > 0 and np.isfinite(entry)
            else None
        )
        dist_stop = (
            f"{(cur - eff) / cur:+.1%}"
            if cur is not None and np.isfinite(eff) and cur > 0
            else None
        )
        risk_left = (
            round(max(0.0, (cur if cur is not None else entry) - eff) * remaining, 2)
            if np.isfinite(eff) and np.isfinite(entry)
            else None
        )
        bars = (
            int(np.busday_count(t["entry_fill_date"], date.today()))
            if t.get("entry_fill_date") else None
        )
        rows.append({
            "symbol": t["symbol"], "qty left": round(remaining, 4), "entry": entry,
            "now": cur, "unrealized R": unreal_r, "stop (effective)": eff,
            "room to stop": dist_stop, "$ at risk to stop": risk_left,
            "target": t.get("target_price"),
            "partial": "✅ taken" if partial else "—",
            "days held": bars,
        })
    view = pd.DataFrame(rows)
    a, b, c = st.columns(3)
    a.metric("Open trades", len(view))
    total_risk = view["$ at risk to stop"].dropna().sum()
    b.metric("Total $ at risk to stops", f"${total_risk:,.0f}")
    heat = float(open_tr["suggested_risk_pct"].fillna(0).sum())
    c.metric("Heat (at entry)", f"{heat:.1%}")
    st.dataframe(view, width="stretch", hide_index=True)
    if not live_px:
        st.caption("Live prices unavailable (no Alpaca keys) — `now`/`unrealized R` hidden; "
                   "risk shown from entry.")

st.subheader("Pending entries")
if pending.empty:
    st.caption("No resting entry orders.")
else:
    cols = [c for c in [
        "signal_date", "symbol", "limit_price", "qty", "stop_price", "target_price",
        "pending_days",
    ] if c in pending.columns]
    st.dataframe(pending[cols], width="stretch", hide_index=True)

st.subheader("Live positions (Alpaca)")
if positions.empty:
    st.caption("No live positions (or Alpaca keys not set).")
else:
    show = positions.copy()
    show["unrealized_pl"] = show["unrealized_pl"].map(lambda v: f"${v:,.2f}")
    st.dataframe(show, width="stretch", hide_index=True)

st.subheader("All tracked trades")
if trades.empty:
    st.caption("No trades recorded yet.")
else:
    cols = [c for c in [
        "signal_date", "symbol", "status", "qty", "actual_entry", "limit_price",
        "stop_price", "effective_stop", "target_price", "suggested_risk_pct",
    ] if c in trades.columns]
    st.dataframe(trades[cols], width="stretch", hide_index=True)
