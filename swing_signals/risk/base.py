"""Equity-driven position sizing (file 08) + the risk-gate interface.

``position_size`` is the master sizing equation, valid at any equity level (the
identical logic runs at $500 and $500,000 because it reads current equity). Heat
caps, sector/correlation limits, and drawdown halts arrive in Stage 4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SizeResult:
    shares: float
    risk_pct: float
    risk_dollars: float
    notional: float
    stop_distance: float
    reasons: list[str]


def position_size(
    *,
    equity: float,
    entry: float,
    stop: float,
    risk_pct: float,
    risk_pct_ceiling: float,
    fractional: bool = True,
    conviction_mult: float = 1.0,
) -> SizeResult:
    """Compute share count from risk, rounding DOWN so realized risk <= target.

    Args:
        equity: current account equity (USD).
        entry, stop: entry and stop prices (entry > stop for a long).
        risk_pct: base per-trade risk fraction (e.g. 0.01 for 1%).
        risk_pct_ceiling: hard cap; effective risk is clamped to this.
        fractional: if False, round shares down to a whole number.
        conviction_mult: tier multiplier (e.g. High 1.0 / Medium 0.66 / Low 0.33).

    Returns:
        SizeResult with shares (0 if the trade is not viable) and the reasons.
    """
    reasons: list[str] = []
    stop_distance = entry - stop
    if stop_distance <= 0:
        return SizeResult(0.0, 0.0, 0.0, 0.0, stop_distance, ["invalid stop: entry <= stop"])

    effective_risk = min(risk_pct * conviction_mult, risk_pct_ceiling)
    if effective_risk < risk_pct * conviction_mult:
        reasons.append(f"risk clamped to ceiling {risk_pct_ceiling:.2%}")

    risk_dollars = equity * effective_risk
    raw_shares = risk_dollars / stop_distance
    shares = raw_shares if fractional else math.floor(raw_shares)

    if shares <= 0:
        reasons.append("position rounds to 0 shares at this equity/stop")
    notional = shares * entry
    return SizeResult(
        shares=shares,
        risk_pct=effective_risk,
        risk_dollars=risk_dollars,
        notional=notional,
        stop_distance=stop_distance,
        reasons=reasons,
    )
