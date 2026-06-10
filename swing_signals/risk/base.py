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
    max_notional_pct: float | None = None,
) -> SizeResult:
    """Compute share count from risk, rounding DOWN so realized risk <= target.

    Args:
        equity: current account equity (USD).
        entry, stop: entry and stop prices (entry > stop for a long).
        risk_pct: base per-trade risk fraction (e.g. 0.01 for 1%).
        risk_pct_ceiling: hard cap; effective risk is clamped to this.
        fractional: if False, round shares down to a whole number.
        conviction_mult: tier multiplier (e.g. High 1.0 / Medium 0.66 / Low 0.33).
        max_notional_pct: concentration cap — position value may not exceed this
            fraction of equity. Fixed-fractional risk sizing gives the LARGEST dollar
            exposure to the LOWEST-volatility names (notional/equity = risk/stop%), so
            a calm mega-cap with a tight 2-ATR stop can otherwise absorb half the
            account; this bounds the gap-through-stop tail risk that the stop cannot.

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

    if max_notional_pct is not None and max_notional_pct > 0 and entry > 0:
        notional_cap_shares = (equity * max_notional_pct) / entry
        if raw_shares > notional_cap_shares:
            raw_shares = notional_cap_shares
            reasons.append(f"notional clamped to {max_notional_pct:.0%} of equity")

    shares = raw_shares if fractional else math.floor(raw_shares)

    if shares <= 0:
        reasons.append("position rounds to 0 shares at this equity/stop")
    notional = shares * entry
    # Report the risk actually taken (the notional clamp shrinks it below the target).
    actual_risk_dollars = shares * stop_distance
    actual_risk_pct = actual_risk_dollars / equity if equity > 0 else 0.0
    return SizeResult(
        shares=shares,
        risk_pct=actual_risk_pct,
        risk_dollars=actual_risk_dollars,
        notional=notional,
        stop_distance=stop_distance,
        reasons=reasons,
    )
