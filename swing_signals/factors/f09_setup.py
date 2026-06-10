"""Factor 09 — Setup / entry confirmation (low-weight pattern timing).

Honest framing: classic chart patterns have only weak peer-reviewed edge as a
standalone signal (Lo, Mamaysky & Wang 2000 found modest one-day informational
value, no tradeable profit rule), so this factor is deliberately LOW-WEIGHT
confirmation, never the profit engine. It rewards a clean, well-timed entry on
top of the momentum core: a fresh breakout on real volume, a held pullback to the
rising EMA20, or a tight volatility-contraction base near the highs.

All inputs come from the shared f01 indicator panel (so the backtest's single
per-symbol panel feeds it for free, and live builds it once). 0-100, 50 = no
setup / neutral, so an absent setup contributes nothing directional.

Components:
  - Breakout proximity: close vs the 20-day Donchian high.
  - Volume confirmation: relative volume (a breakout on volume is more reliable).
  - Pullback quality: a dip to the EMA20 that was recaptured (close above, low near).
  - Volatility contraction: Bollinger bandwidth percentile — a tight, coiled base
    (a light proxy for VCP / flag / cup-with-handle completion).
  - Base proximity: nearness to the 60-day high (the top of a base).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .base import NEUTRAL, Factor, SubScore
from .f01_technical import build_panel
from .registry import register

if TYPE_CHECKING:
    from ..context import RunContext, SymbolData

MIN_BARS = 150  # bandwidth percentile needs ~126 bars + buffer

# Blend weights (sum 1.0) — breakout/base lead, volume/squeeze trim.
_W = {"breakout": 0.30, "base": 0.25, "pullback": 0.20, "volume": 0.15, "squeeze": 0.10}


def _f(row, key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return float("nan")


@register
class SetupFactor(Factor):
    name = "setup"
    requires = ("ohlcv",)

    def compute(self, data: SymbolData, ctx: RunContext) -> SubScore:
        df = data.ohlcv
        if df is None or len(df) < MIN_BARS:
            n = 0 if df is None else len(df)
            return SubScore.unavailable(self.name, f"insufficient bars ({n} < {MIN_BARS})")

        # Backtest passes a precomputed panel row; live builds the panel once.
        row = (
            data.indicators
            if (data.indicators is not None and "high_60" in data.indicators)
            else build_panel(df).iloc[-1]
        )
        close = _f(row, "close")
        low = _f(row, "low")
        atr = _f(row, "atr14")
        ema20 = _f(row, "ema20")
        don20h = _f(row, "don20h")
        rvol = _f(row, "rvol")
        bw_pctile = _f(row, "bw_pctile")
        high_60 = _f(row, "high_60")
        if math.isnan(close) or close <= 0:
            return SubScore.unavailable(self.name, "no close in panel")

        comps: dict[str, float] = {}
        reasons: list[str] = []

        # 1) Breakout proximity vs the 20-day high.
        if not math.isnan(don20h) and not math.isnan(atr) and atr > 0:
            if close > don20h:
                comps["breakout"] = 85.0
                reasons.append("20-day breakout")
            elif close >= don20h - 0.5 * atr:
                comps["breakout"] = 68.0
                reasons.append("coiled at 20-day high")
            else:
                comps["breakout"] = NEUTRAL
        else:
            comps["breakout"] = NEUTRAL

        # 2) Volume confirmation.
        if not math.isnan(rvol):
            if rvol >= 2.0:
                comps["volume"] = 75.0
                reasons.append(f"volume surge {rvol:.1f}x")
            elif rvol >= 1.5:
                comps["volume"] = 63.0
            elif rvol < 0.6:
                comps["volume"] = 42.0
            else:
                comps["volume"] = NEUTRAL
        else:
            comps["volume"] = NEUTRAL

        # 3) Pullback-to-EMA20 quality (held dip).
        if not math.isnan(ema20) and not math.isnan(atr) and atr > 0 and close > ema20:
            gap = (ema20 - low) / atr
            if 0.0 <= gap <= 0.5:
                comps["pullback"] = 80.0
                reasons.append("clean pullback to EMA20, recaptured")
            elif gap <= 1.5:
                comps["pullback"] = 65.0
            else:
                comps["pullback"] = NEUTRAL
        else:
            comps["pullback"] = NEUTRAL

        # 4) Volatility contraction (tight, coiled base).
        if not math.isnan(bw_pctile):
            if bw_pctile <= 0.15:
                comps["squeeze"] = 72.0
                reasons.append("volatility squeeze (tight base)")
            elif bw_pctile <= 0.30:
                comps["squeeze"] = 60.0
            else:
                comps["squeeze"] = NEUTRAL
        else:
            comps["squeeze"] = NEUTRAL

        # 5) Base proximity (nearness to the 60-day high).
        if not math.isnan(high_60) and high_60 > 0:
            nh60 = close / high_60
            if nh60 >= 0.99:
                comps["base"] = 78.0
                reasons.append("at the top of a 60-day base")
            elif nh60 >= 0.95:
                comps["base"] = 64.0
            else:
                comps["base"] = NEUTRAL
        else:
            comps["base"] = NEUTRAL

        score = sum(_W[k] * comps[k] for k in _W)

        return SubScore(
            name=self.name,
            value=round(score, 1),
            reasons=reasons,
            raw={
                "score": round(score, 1),
                "components": {k: round(v, 1) for k, v in comps.items()},
                "close": round(close, 4),
                "don20h": None if math.isnan(don20h) else round(don20h, 4),
                "rvol": None if math.isnan(rvol) else round(rvol, 2),
                "bw_pctile": None if math.isnan(bw_pctile) else round(bw_pctile, 3),
                "high_60": None if math.isnan(high_60) else round(high_60, 4),
            },
        )
