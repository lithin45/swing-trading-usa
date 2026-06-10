"""Factor 08 — Momentum / relative strength (the core edge).

The most-replicated edge in the academic literature (Jegadeesh-Titman 1993;
George-Hwang 2004 "52-week high"; Moskowitz-Ooi-Pedersen time-series momentum).
It is price-based and pattern-agnostic, so it captures strong trending / news-
driven names (AI, quantum, semis) that never print a clean chart pattern — the
case the old pattern-first engine on a 10-name list could not see.

All components are ABSOLUTE / per-symbol, so the factor satisfies the per-symbol
``Factor.compute`` contract; the cross-sectional "pick the strongest" is the
scoring engine's existing rank-and-cap step (it sorts actionable signals by
conviction and caps to max_positions/heat), so a heavy momentum weight makes the
engine select the strongest names without any cross-sectional hook.

Components (0-100, 50 = neutral), blended with 52-week-high distance dominant:
  - 52-week-high distance (George-Hwang): ``close / max(high, 252)``. Best-evidenced.
  - 12-1 momentum (Jegadeesh-Titman): trailing 12-month return skipping the most
    recent ~month (21 bars) to dodge short-term reversal.
  - 6-month ROC: medium-horizon confirmation (same metric as f01's ``mom6``).
  - Trend backbone: ``close > SMA200`` and ``SMA50 > SMA200``.

It also exposes ``raw["eligible"]`` — a hard long-eligibility flag the engine
vetoes on (confirmed uptrend + positive 12-1 + within range of the 52-week high),
which makes the strategy long-only-into-strength and drives selectivity.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from . import indicators as ind
from .base import Factor, SubScore
from .registry import register

if TYPE_CHECKING:
    import pandas as pd

    from ..context import RunContext, SymbolData

MIN_BARS = 260  # ~252 for the 52-week high + the 12-1 (252-bar) shift, plus a buffer
ELIGIBLE_NH = 0.75  # long-eligible only within 25% of the 52-week high

# Component blend (sums to 1), 52-week-high distance dominant. Module-level so
# research scripts can run pre-registered ranking variants (e.g. 12-1-dominant)
# without forking the factor; production behavior is unchanged unless edited here.
W_NH, W_121, W_TREND, W_ROC = 0.40, 0.30, 0.20, 0.10


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _metrics(df: pd.DataFrame) -> dict[str, float]:
    """Momentum inputs computed directly from OHLCV (the live path).

    Mirrors the columns ``f01_technical.build_panel`` adds, so the backtest
    fast-path (reading the precomputed panel row) is numerically identical.
    """
    close = df["close"]
    return {
        "close": float(close.iloc[-1]),
        "sma200": float(ind.sma(close, 200).iloc[-1]),
        "sma50": float(ind.sma(close, 50).iloc[-1]),
        "high_252": float(df["high"].rolling(252).max().iloc[-1]),
        "mom_12_1": float(close.shift(21).iloc[-1] / close.shift(252).iloc[-1] - 1.0),
        "mom6": float(close.iloc[-1] / close.shift(126).iloc[-1] - 1.0),
    }


@register
class MomentumFactor(Factor):
    name = "momentum"
    requires = ("ohlcv",)

    def compute(self, data: SymbolData, ctx: RunContext) -> SubScore:
        df = data.ohlcv
        if df is None or len(df) < MIN_BARS:
            n = 0 if df is None else len(df)
            return SubScore.unavailable(self.name, f"insufficient bars ({n} < {MIN_BARS})")

        # Backtest passes a precomputed panel row (O(1)); live computes directly.
        # Identical values either way (build_panel uses the same causal formulas).
        ind_row = data.indicators
        if ind_row is not None and "high_252" in ind_row:
            close = float(ind_row["close"])
            sma200 = float(ind_row["sma200"])
            sma50 = float(ind_row["sma50"])
            high_252 = float(ind_row["high_252"])
            mom_12_1 = float(ind_row["mom_12_1"])
            mom6 = float(ind_row["mom6"])
        else:
            m = _metrics(df)
            close, sma200, sma50 = m["close"], m["sma200"], m["sma50"]
            high_252, mom_12_1, mom6 = m["high_252"], m["mom_12_1"], m["mom6"]

        if any(math.isnan(x) for x in (sma200, sma50, high_252, mom_12_1)) or high_252 <= 0:
            return SubScore.unavailable(self.name, "core momentum inputs NaN (insufficient/dirty)")

        nh = close / high_252  # nearness to the 52-week high, in (0, 1]

        # --- component sub-scores (0-100) ---
        s_nh = _clip(100.0 * (nh - 0.5) / 0.5)   # at-high -> 100, 25% off -> 50, half -> 0
        s_121 = _clip(50.0 + 125.0 * mom_12_1)   # +40% 12-1 -> 100
        s_roc = _clip(50.0 + 200.0 * mom6)       # +25% 6-mo -> 100
        stacked = close > sma200 and sma50 > sma200
        if stacked:
            s_trend = 100.0
        elif close > sma200:
            s_trend = 65.0
        elif close > sma50:
            s_trend = 40.0
        else:
            s_trend = 15.0

        score = W_NH * s_nh + W_121 * s_121 + W_TREND * s_trend + W_ROC * s_roc
        eligible = bool(stacked and mom_12_1 > 0.0 and nh >= ELIGIBLE_NH)

        reasons: list[str] = []
        reasons.append(
            "at/near 52-week high" if nh >= 0.98 else f"{(1.0 - nh) * 100:.0f}% below 52-week high"
        )
        reasons.append(f"12-1 momentum {mom_12_1:+.0%}")
        reasons.append(
            "uptrend (price>50DMA>200DMA)" if stacked
            else ("above 200-DMA" if close > sma200 else "below 200-DMA")
        )
        if not eligible:
            reasons.append("not long-eligible (needs uptrend + positive 12-1 near highs)")

        return SubScore(
            name=self.name,
            value=round(score, 1),
            reasons=reasons,
            raw={
                "score": round(score, 1),
                "eligible": eligible,
                "nearness_52w_high": round(nh, 4),
                "mom_12_1": round(mom_12_1, 4),
                "mom6": round(mom6, 4),
                "close": round(close, 4),
                "sma200": round(sma200, 4),
                "sma50": round(sma50, 4),
                "high_252": round(high_252, 4),
                "components": {
                    "nearness_52w": round(s_nh, 1),
                    "mom_12_1": round(s_121, 1),
                    "trend": round(s_trend, 1),
                    "roc_6m": round(s_roc, 1),
                },
            },
        )
