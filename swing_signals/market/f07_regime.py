"""Module 07 — Market regime gate (the hard market override).

Minimal-viable version of file 07's master gate: the two pillars file 07 says
capture most of the drawdown-avoidance benefit — **Regime** (SPY/QQQ/IWM vs their
200/50-DMA, slope, ADX) and **Volatility** (VIX level + VIX/VIX3M term structure,
or an SPY ATR% proxy when FRED has no key). Breadth/correlation pillars come later.

Output is a GREEN/YELLOW/RED state + 0–100 score + a position-size multiplier +
a hard ``veto``. Fail-safe by design: if the market data needed to judge the
regime is missing, it returns RED + veto (no new longs) rather than guessing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..factors import indicators as ind
from .base import MarketModule, MarketState

if TYPE_CHECKING:
    import pandas as pd

    from ..context import RunContext

_MIN_BARS = 210


def _above_200dma(df: pd.DataFrame | None) -> bool | None:
    if df is None or len(df) < _MIN_BARS:
        return None
    return float(df["close"].iloc[-1]) > float(ind.sma(df["close"], 200).iloc[-1])


class RegimeModule(MarketModule):
    name = "regime"

    def compute(self, ctx: RunContext) -> MarketState:
        market = ctx.market
        cfg = ctx.settings.regime

        # Fail-safe: can't assess the regime -> no new longs.
        min_bars = max(_MIN_BARS, cfg.spy_ma_days + 10)
        if market is None or market.spy is None or len(market.spy) < min_bars:
            return MarketState(
                name=self.name, score=0.0, state="RED", multiplier=0.0, veto=True,
                reasons=["regime data unavailable (SPY missing/short) — fail-safe veto"],
                raw={"degraded": True},
            )
        spy = market.spy

        close = spy["close"]
        c = float(close.iloc[-1])
        ma_gate_s = ind.sma(close, cfg.spy_ma_days)  # the configured headline gate MA
        ma_gate = float(ma_gate_s.iloc[-1])
        sma200 = float(ind.sma(close, 200).iloc[-1])
        sma200_prev = float(ind.sma(close, 200).iloc[-6])
        sma50 = float(ind.sma(close, 50).iloc[-1])
        rising_200 = sma200 > sma200_prev
        adx_s, plus_di_s, minus_di_s = ind.adx(spy["high"], spy["low"], close, 14)
        adx14 = float(adx_s.iloc[-1])
        trending_up = adx14 > 25 and float(plus_di_s.iloc[-1]) > float(minus_di_s.iloc[-1])

        reasons: list[str] = []

        # --- Regime pillar (0–100) ---
        regime = 0.0
        if c > sma200:
            regime += 35
            reasons.append(f"SPY {c / sma200 - 1:+.1%} vs 200-DMA")
            if rising_200:
                regime += 10
                reasons.append("200-DMA rising")
        else:
            reasons.append(f"SPY {c / sma200 - 1:+.1%} below 200-DMA")
        if c > sma50 and sma50 > sma200:
            regime += 20
            reasons.append("bullish MA stack (price>50>200)")
        qqq_ok = _above_200dma(market.qqq)
        iwm_ok = _above_200dma(market.iwm)
        if qqq_ok:
            regime += 10
            reasons.append("QQQ above 200-DMA")
        if iwm_ok:
            regime += 10
            reasons.append("IWM above 200-DMA")
        if trending_up:
            regime += 15
            reasons.append(f"ADX={adx14:.0f} up-trend")
        regime = max(0.0, min(100.0, regime))

        # --- Volatility pillar (0–100) ---
        vol, vol_degraded = self._volatility_pillar(market, spy, reasons)

        overall = 0.5 * regime + 0.5 * vol

        # --- Hard overrides (each promised by config; all enforced here) ---
        veto = False
        if cfg.require_spy_above_ma and c < ma_gate:
            veto = True
            reasons.append(f"HARD VETO: SPY below its {cfg.spy_ma_days}-DMA")
        elif c < sma200 and not rising_200:
            veto = True
            reasons.append("HARD VETO: SPY below a falling 200-DMA")

        if market.vix is not None and market.vix > cfg.vix_max:
            veto = True
            reasons.append(f"HARD VETO: VIX {market.vix:.1f} > vix_max {cfg.vix_max:.0f}")

        backwardation = (
            market.vix is not None
            and market.vix3m is not None
            and market.vix3m > 0
            and market.vix / market.vix3m > 1.0
        )
        if backwardation and cfg.vix_backwardation_veto:
            overall = max(0.0, overall - 20.0)  # force toward a lower band
            reasons.append("VIX term structure in backwardation — band lowered")

        state, multiplier = self._state_and_multiplier(overall, veto)

        raw = {
            "overall": round(overall, 1),
            "regime_pillar": round(regime, 1),
            "vol_pillar": round(vol, 1),
            "vol_degraded": vol_degraded,
            "spy_close": round(c, 2),
            "spy_ma_gate": round(ma_gate, 2),
            "spy_sma200": round(sma200, 2),
            "spy_sma50": round(sma50, 2),
            "rising_200dma": rising_200,
            "adx": round(adx14, 1),
            "vix": market.vix,
            "vix3m": market.vix3m,
            "backwardation": backwardation,
        }
        return MarketState(
            name=self.name, score=round(overall, 1), state=state,
            multiplier=round(multiplier, 3), veto=veto, reasons=reasons, raw=raw,
        )

    def _volatility_pillar(self, market, spy, reasons: list[str]) -> tuple[float, bool]:
        vix = market.vix
        if vix is not None:
            if vix < 15:
                level = 100.0
            elif vix < 20:
                level = 80.0
            elif vix < 25:
                level = 50.0
            elif vix < 30:
                level = 20.0
            else:
                level = 0.0
            if market.vix3m and market.vix3m > 0:
                ratio = vix / market.vix3m
                term = 100.0 if ratio < 0.95 else (50.0 if ratio <= 1.0 else 0.0)
                score = 0.6 * level + 0.4 * term
            else:
                score = level
            reasons.append(f"VIX={vix:.1f}")
            return score, False

        # Degraded: proxy volatility from SPY's own ATR% (no FRED key).
        atr14 = float(ind.atr(spy["high"], spy["low"], spy["close"], 14).iloc[-1])
        atr_pct = atr14 / float(spy["close"].iloc[-1]) * 100.0
        # ~1%/day daily range = calm (100); ~2.5% = stressed (0).
        score = max(0.0, min(100.0, 100.0 - (atr_pct - 1.0) / 1.5 * 100.0))
        reasons.append(f"VIX n/a — SPY ATR%={atr_pct:.1f}% proxy (no FRED key)")
        return score, True

    @staticmethod
    def _state_and_multiplier(overall: float, veto: bool) -> tuple[str, float]:
        if veto:
            return "RED", 0.0
        if overall >= 70:
            return "GREEN", 0.8 + 0.2 * min(1.0, (overall - 70) / 30)
        if overall >= 40:
            return "YELLOW", 0.3 + 0.3 * ((overall - 40) / 30)
        return "RED", 0.2 * (overall / 40)
