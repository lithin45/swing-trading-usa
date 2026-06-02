"""ATR-based entry/stop/target levels (file 01) — never fixed percentages.

The whole point of file 01's risk logic: stops and targets scale with each name's
own volatility. Entry is a band around the reference price; the stop is k×ATR
below entry; the target is an R-multiple of that volatility-defined risk; the
Chandelier trail hangs off the recent high for managing the exit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..factors import indicators as ind


@dataclass(frozen=True)
class Levels:
    entry_zone_low: float
    entry_zone_high: float
    entry: float           # the reference fill used for sizing/RR (top of the long zone)
    stop: float
    target: float
    risk_per_share: float  # entry - stop (defines 1R)
    reward_risk: float
    stop_distance_atr: float
    chandelier_stop: float | None  # trailing-exit guide (HighestHigh(22) - m*ATR(22))


def compute_levels(
    *,
    ref_price: float,
    atr: float,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    direction: str = "LONG",
    stop_atr_mult: float = 2.0,
    rr_target: float = 2.0,
    chandelier_lookback: int = 22,
    chandelier_mult: float = 3.0,
) -> Levels:
    """Compute the ATR-adaptive entry zone, stop, target, and Chandelier trail."""
    if direction != "LONG":
        raise ValueError("only LONG levels are implemented (long-only v1)")

    # Entry zone: a pullback band just under the reference; size off the top (ref).
    entry = ref_price
    entry_zone_low = ref_price - 0.5 * atr
    entry_zone_high = ref_price

    stop = entry - stop_atr_mult * atr
    risk_per_share = entry - stop
    target = entry + rr_target * risk_per_share
    reward_risk = rr_target  # by construction
    stop_distance_atr = (risk_per_share / atr) if atr > 0 else float("nan")

    chandelier = None
    if len(high) >= chandelier_lookback:
        atr_c = float(ind.atr(high, low, close, chandelier_lookback).iloc[-1])
        hh = float(high.rolling(chandelier_lookback).max().iloc[-1])
        chandelier = hh - chandelier_mult * atr_c

    return Levels(
        entry_zone_low=round(entry_zone_low, 4),
        entry_zone_high=round(entry_zone_high, 4),
        entry=round(entry, 4),
        stop=round(stop, 4),
        target=round(target, 4),
        risk_per_share=round(risk_per_share, 4),
        reward_risk=round(reward_risk, 2),
        stop_distance_atr=round(stop_distance_atr, 2),
        chandelier_stop=round(chandelier, 4) if chandelier is not None else None,
    )
