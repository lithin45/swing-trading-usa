"""Factor 01 — Technical (trend/momentum core).

Implements the file-01 rulebook as a single 0–100 sub-score: compute each
component sub-score (rows 1–21 of file 01), drop the neutral (==50) ones that
didn't fire, then take an evidence-tier-weighted average (Tier-1 ×3, Tier-2 ×2,
Tier-3 ×1). Higher = more bullish; 50 = neutral. Every firing component returns
a human-readable reason, and all indicator values land in ``raw`` for attribution.

Deviation from file 01 noted inline: the ADX component (row 14) is made
*directional* via +DI/–DI so a strong downtrend scores low rather than neutral —
correct behavior for a directional sub-score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import indicators as ind
from .base import NEUTRAL, Factor, SubScore
from .registry import register

if TYPE_CHECKING:
    from ..context import RunContext, SymbolData

# Evidence-tier weights (file 01: "T1 ×3, T2 ×2, T3 ×1").
T1, T2, T3 = 3.0, 2.0, 1.0
MIN_BARS = 210  # need ~200 for SMA200 + 126 for momentum/bandwidth + buffer


@dataclass
class _Component:
    name: str
    score: float
    weight: float
    reason: str | None  # set when the component meaningfully fired


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


@register
class TechnicalFactor(Factor):
    name = "technical"
    requires = ("ohlcv",)

    def compute(self, data: SymbolData, ctx: RunContext) -> SubScore:
        df = data.ohlcv
        if df is None or len(df) < MIN_BARS:
            n = 0 if df is None else len(df)
            return SubScore.unavailable(self.name, f"insufficient bars ({n} < {MIN_BARS})")

        close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
        c = float(close.iloc[-1])
        last_low = float(low.iloc[-1])

        sma200 = float(ind.sma(close, 200).iloc[-1])
        sma50 = float(ind.sma(close, 50).iloc[-1])
        ema20 = float(ind.ema(close, 20).iloc[-1])
        ema50 = float(ind.ema(close, 50).iloc[-1])
        atr14 = float(ind.atr(high, low, close, 14).iloc[-1])
        rsi14 = float(ind.rsi(close, 14).iloc[-1])
        rsi2 = float(ind.rsi(close, 2).iloc[-1])
        adx14_s, plus_di_s, minus_di_s = ind.adx(high, low, close, 14)
        adx14 = float(adx14_s.iloc[-1])
        plus_di = float(plus_di_s.iloc[-1])
        minus_di = float(minus_di_s.iloc[-1])
        don20h = float(ind.donchian_high(high, 20).iloc[-1])
        don10l = float(ind.donchian_low(low, 10).iloc[-1])
        _mid, bb_upper_s, _lower, bandwidth_s, _pctb = ind.bollinger(close, 20, 2.0)
        bb_upper = float(bb_upper_s.iloc[-1])
        bw_now = float(bandwidth_s.iloc[-1])
        bw_window = bandwidth_s.dropna().iloc[-126:]
        bw_pctile = float((bw_window <= bw_now).mean()) if len(bw_window) else 1.0
        rvol_now = float(ind.rvol(volume, 20).iloc[-1])
        obv_s = ind.obv(close, volume)
        obv_now = float(obv_s.iloc[-1])
        obv_ema = float(ind.ema(obv_s, 20).iloc[-1])
        obv_rising = float(obv_s.iloc[-1]) > float(obv_s.iloc[-2])
        mom6 = c / float(close.iloc[-127]) - 1.0  # 126 trading days

        # Core trend inputs must be finite, else the symbol lacks enough clean history.
        if any(math.isnan(x) for x in (sma200, ema50, atr14, mom6)):
            return SubScore.unavailable(self.name, "core indicators NaN (insufficient/dirty data)")

        comps: list[_Component] = []
        # `s` (component score) and `r` (its reason, None when it doesn't fire)
        # are rebound in each block below; declare once so the type is stable.
        s: float
        r: str | None

        # 1. Long-term trend filter vs SMA200 (T1)
        if c >= 1.02 * sma200:
            s, r = 100.0, f"price {c / sma200 - 1:+.1%} vs 200-DMA (strong uptrend)"
        elif c >= sma200:
            s, r = 70.0, f"price {c / sma200 - 1:+.1%} above 200-DMA"
        elif c <= 0.98 * sma200:
            s, r = 0.0, f"price {c / sma200 - 1:+.1%} below 200-DMA (downtrend)"
        else:
            s, r = 30.0, f"price {c / sma200 - 1:+.1%} just below 200-DMA"
        comps.append(_Component("trend200", s, T1, r))

        # 2. Intermediate stacked EMAs (T1)
        if c > ema20 > ema50:
            s, r = 100.0, "EMAs stacked bullishly (C>EMA20>EMA50)"
        elif c > ema50:
            s, r = 60.0, "price above EMA50"
        else:
            s, r = 20.0, "price below EMA50"
        comps.append(_Component("stacked_ema", s, T1, r))

        # 3. Time-series momentum, 6-month (T1)
        s = _clip(50.0 + 1000.0 * mom6)
        comps.append(_Component("momentum6m", s, T1, f"6-month momentum {mom6:+.1%}"))

        # 5. Pullback-to-EMA20 quality (T2) — bullish dip recaptured
        if c > ema20 and atr14 > 0:
            gap = (ema20 - last_low) / atr14
            if 0.0 <= gap <= 0.5:
                s, r = 100.0, "clean pullback to rising EMA20, recaptured"
            elif 0.5 < gap <= 1.5:
                s, r = _clip(100.0 * (1.0 - (gap - 0.5) / 1.0)), "pullback to EMA20 (extended)"
            else:
                s, r = NEUTRAL, None
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("pullback_ema20", s, T2, r))

        # 6. Donchian 20-day breakout (T2)
        if not math.isnan(don20h) and c > don20h:
            s, r = 100.0, "20-day high breakout"
        elif not math.isnan(don20h) and c >= don20h - atr14:
            s, r = 60.0, "within 1 ATR of 20-day high"
        elif not math.isnan(don10l) and c < don10l:
            s, r = 0.0, "broke below 10-day low"
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("donchian_breakout", s, T2, r))

        # 7. Bollinger squeeze + breakout (T2)
        squeeze = bw_pctile <= 0.20
        if squeeze and not math.isnan(bb_upper) and c > bb_upper:
            s, r = 100.0, "squeeze breakout above upper band"
        elif squeeze:
            s, r = 60.0, "volatility squeeze (coiling)"
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("bollinger_squeeze", s, T2, r))

        # 9. RSI(2) oversold mean-reversion, only in uptrends (T2)
        if c > sma200:
            if rsi2 < 5:
                s, r = 100.0, f"RSI(2)={rsi2:.0f} deeply oversold in uptrend"
            elif rsi2 < 10:
                s, r = 85.0, f"RSI(2)={rsi2:.0f} oversold dip in uptrend"
            elif rsi2 < 20:
                s, r = 60.0, f"RSI(2)={rsi2:.0f} mild dip in uptrend"
            else:
                s, r = NEUTRAL, None
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("rsi2_oversold", s, T2, r))

        # 10. RSI(14) momentum confirmation (T3)
        s = _clip((rsi14 - 30.0) * 2.0)
        comps.append(_Component("rsi14_momentum", s, T3, f"RSI(14)={rsi14:.0f}"))

        # 14. ADX trend-strength gate — made DIRECTIONAL via +DI/-DI (T2)
        if not math.isnan(adx14) and adx14 > 25:
            up = plus_di > minus_di
            if adx14 > 30:
                s = 100.0 if up else 0.0
            else:
                s = 80.0 if up else 20.0
            r = f"ADX={adx14:.0f} {'up' if up else 'down'}-trend"
        elif not math.isnan(adx14) and adx14 < 20:
            s, r = NEUTRAL, None  # no trend -> neutral (don't penalize)
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("adx_gate", s, T2, r))

        # 15. Relative-volume confirmation (T2)
        if not math.isnan(rvol_now):
            s = _clip(min(rvol_now, 3.0) / 3.0 * 100.0)
            r = f"RVOL={rvol_now:.1f}x" if rvol_now >= 1.5 else None
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("rvol_confirm", s, T2, r))

        # 16. OBV trend confirmation (T3)
        if not math.isnan(obv_ema):
            if obv_now > obv_ema and obv_rising:
                s, r = 75.0, "OBV rising above its EMA (accumulation)"
            elif obv_now < obv_ema:
                s, r = 25.0, "OBV below its EMA (distribution)"
            else:
                s, r = NEUTRAL, None
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("obv_trend", s, T3, r))

        # 21. Golden/death cross state (T2)
        if not math.isnan(sma50):
            if sma50 > sma200:
                s, r = 70.0, "golden-cross state (SMA50>SMA200)"
            else:
                s, r = 30.0, "death-cross state (SMA50<SMA200)"
        else:
            s, r = NEUTRAL, None
        comps.append(_Component("golden_cross", s, T2, r))

        # --- combine: drop neutral contributors, evidence-tier-weighted average ---
        firing = [c_ for c_ in comps if abs(c_.score - NEUTRAL) > 1e-9]
        wsum = sum(c_.weight for c_ in firing)
        if wsum <= 0:
            score = NEUTRAL
        else:
            score = sum(c_.score * c_.weight for c_ in firing) / wsum

        reasons = [c_.reason for c_ in firing if c_.reason]
        raw = {
            "score": round(score, 1),
            "close": round(c, 4),
            "sma200": round(sma200, 4),
            "sma50": round(sma50, 4),
            "ema20": round(ema20, 4),
            "ema50": round(ema50, 4),
            "atr14": round(atr14, 4),
            "rsi14": round(rsi14, 2),
            "rsi2": round(rsi2, 2),
            "adx14": round(adx14, 2),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
            "donchian20_high": round(don20h, 4) if not math.isnan(don20h) else None,
            "bandwidth_pctile": round(bw_pctile, 3),
            "rvol": round(rvol_now, 2) if not math.isnan(rvol_now) else None,
            "mom6m": round(mom6, 4),
            "components": {c_.name: {"score": round(c_.score, 1), "weight": c_.weight}
                          for c_ in comps},
            "dropped_neutral": [c_.name for c_ in comps if c_ not in firing],
        }
        return SubScore(name=self.name, value=round(score, 1), reasons=reasons, raw=raw)
