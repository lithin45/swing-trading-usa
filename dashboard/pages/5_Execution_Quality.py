"""Execution quality — live fills vs the model the backtests assume.

The validated edge (+0.19R at best) is small enough that execution drag could
erase it: this page is go/no-go #6's evidence surface. Entry/exit slippage vs
the 10 bps cost model, live-vs-shadow R deltas, the limit fill rate, monthly
entry cadence, and the broker risk-gate audit trail (which caps actually bound).
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Execution Quality", page_icon="🧾", layout="wide")

from _auth import require_auth  # noqa: E402
from _data import load_broker_rejections, load_reconciliation  # noqa: E402

require_auth()
st.title("🧾 Execution Quality")
st.caption(
    "Paper-trading is an execution-fidelity test, not an expectancy test "
    "(≤7 entries/month cannot statistically resolve a +0.1R edge): what it CAN "
    "prove is whether fills, slippage, and cadence match the backtest's assumptions."
)

rows, summary = load_reconciliation()

st.subheader("Live vs model (closed trades)")
if summary["n_closed"] == 0:
    st.caption("No closed trades reconciled yet — metrics appear once positions resolve.")
else:
    a, b, c, d, e = st.columns(5)
    a.metric("Closed & reconciled", summary["n_closed"])
    fill = summary["limit_fill_rate"]
    b.metric(
        "Limit fill rate",
        f"{fill:.0%}" if fill is not None else "n/a",
        help=f"{summary['n_limit_filled']}/{summary['n_limit_submitted']} decided limit "
             "submissions filled AT the limit (market fallbacks and cancels count as misses).",
    )
    slip = summary["avg_entry_slippage_bps"]
    c.metric(
        "Entry slippage (bps)",
        f"{slip:+.1f}" if slip is not None else "n/a",
        help="Fill vs the submitted limit; the cost model assumes 10 bps/side.",
    )
    xslip = summary["avg_exit_slippage_bps"]
    d.metric(
        "Exit slippage (bps)",
        f"{xslip:+.1f}" if xslip is not None else "n/a",
        help="Exit fill vs the planned stop/target level; positive = exited better.",
    )
    rd = summary["mean_r_delta"]
    e.metric(
        "Live − shadow R (mean)",
        f"{rd:+.3f}" if rd is not None else "n/a",
        help=f"Total live {summary['total_live_r']} R vs shadow "
             f"{summary['total_shadow_r']} R on the market-at-next-open reference model.",
    )

    st.subheader("Per-trade reconciliation")
    st.dataframe(rows, width="stretch", hide_index=True)

if summary["monthly_entries"]:
    st.subheader("Entry cadence (submissions per month — budget ceiling is 7)")
    st.bar_chart(summary["monthly_entries"])

st.subheader("Broker risk-gate decisions")
st.caption(
    "Every live entry blocked by the deployed gates (halt, max positions, heat cap, "
    "sector cap, gross exposure, sizing) — the audit trail of the risk machinery."
)
rejections = load_broker_rejections()
if rejections.empty:
    st.caption("No gate rejections recorded yet.")
else:
    st.dataframe(rejections, width="stretch", hide_index=True)
