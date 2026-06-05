"""Module 04 — Macro risk-on/off modifier (a position-size multiplier, never a veto).

File 04's thesis: the macro layer answers "how aggressive should I be right now",
not "what should I buy". It scales position size and stands down in stress; it
never picks stocks and never hard-vetoes (that is the regime gate's job, file 07).

Minimal-viable version of file 04's composite: a level-based blend of the free,
daily inputs the data layer already pulls from FRED — VIX level, VIX/VIX3M term
structure, high-yield credit spread (HY OAS), and the 2s10s yield curve — mapped
to a 0–100 risk-on score and then to a size multiplier in (0, 1]. A faithful
z-scored-over-252-days version (file 04 §"Building your composite") needs rolling
FRED *history*, which the latest-value data layer doesn't keep yet; the level
thresholds here come straight from file 04's "Practical thresholds summary".

Fail-soft by design: with no macro data (no FRED key, or backtest), it returns a
NEUTRAL 1.0× — macro simply has no effect rather than penalizing on missing data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import MarketModule, MarketState

if TYPE_CHECKING:
    from ..context import RunContext


def _vix_score(v: float) -> float:
    """VIX level → 0–100 (lower VIX = more risk-on). File 04: <18 risk-on, >25 risk-off."""
    if v < 15:
        return 100.0
    if v < 18:
        return 80.0
    if v < 20:
        return 60.0
    if v < 25:
        return 40.0
    if v < 30:
        return 20.0
    return 0.0


def _credit_score(oas_bps: float) -> float:
    """HY OAS (bps) → 0–100 (tighter = risk-on). File 04: <350 risk-on, >500 risk-off."""
    if oas_bps < 300:
        return 100.0
    if oas_bps < 350:
        return 85.0
    if oas_bps < 450:
        return 60.0
    if oas_bps < 550:
        return 35.0
    if oas_bps < 700:
        return 15.0
    return 0.0


def _curve_score(t10y2y: float) -> float:
    """2s10s (T10Y2Y, in %) → 0–100. A positive/steep curve is risk-on; inverted is risk-off."""
    if t10y2y >= 1.0:
        return 85.0
    if t10y2y >= 0.5:
        return 75.0
    if t10y2y >= 0.0:
        return 60.0
    if t10y2y >= -0.5:
        return 40.0
    return 20.0


class MacroModule(MarketModule):
    name = "macro"

    def compute(self, ctx: RunContext) -> MarketState:
        market = ctx.market
        cfg = ctx.settings.macro

        if market is None:
            return self._degraded("no market context")

        vix = market.vix
        vix3m = market.vix3m
        macro = market.macro_series or {}
        hy_oas = macro.get("hy_oas")
        t10y2y = macro.get("t10y2y")

        # (score, weight, reason) for each input we actually have — weights from
        # file 04 §158, renormalized over the available subset.
        parts: list[tuple[float, float, str]] = []
        if vix is not None:
            parts.append((_vix_score(vix), 0.30, f"VIX={vix:.1f}"))
            if vix3m and vix3m > 0:
                ratio = vix / vix3m
                term = 100.0 if ratio < 0.95 else (50.0 if ratio <= 1.0 else 0.0)
                parts.append((term, 0.15, f"VIX/VIX3M={ratio:.2f}"))
        if hy_oas is not None:
            parts.append((_credit_score(hy_oas), 0.30, f"HY OAS={hy_oas:.0f}bps"))
        if t10y2y is not None:
            parts.append((_curve_score(t10y2y), 0.25, f"2s10s={t10y2y:+.2f}"))

        if not parts:
            return self._degraded("no FRED macro series (no SWING_FRED_API_KEY?)")

        wsum = sum(w for _, w, _ in parts)
        score = sum(s * w for s, w, _ in parts) / wsum
        reasons = [r for _, _, r in parts]

        # Hard overlay (file 04 §168/§217): VIX backwardation or HY OAS > 500 bps
        # forces the score one band lower regardless of the blend.
        backwardation = (
            vix is not None and vix3m is not None and vix3m > 0 and vix / vix3m > 1.0
        )
        credit_stress = hy_oas is not None and hy_oas > 500.0
        if backwardation or credit_stress:
            score = max(0.0, score - 20.0)
            reasons.append("risk-off overlay (VIX backwardation / HY OAS>500)")

        state, multiplier = self._state_and_multiplier(score, cfg)
        raw = {
            "score": round(score, 1),
            "vix": vix,
            "vix3m": vix3m,
            "hy_oas": hy_oas,
            "t10y2y": t10y2y,
            "backwardation": backwardation,
            "credit_stress": credit_stress,
            "inputs_used": [r for _, _, r in parts],
        }
        return MarketState(
            name=self.name, score=round(score, 1), state=state,
            multiplier=round(multiplier, 3), veto=False, reasons=reasons, raw=raw,
        )

    @staticmethod
    def _degraded(why: str) -> MarketState:
        """No macro data → NEUTRAL 1.0× (macro never penalizes on missing data)."""
        return MarketState(
            name="macro", score=50.0, state="NEUTRAL", multiplier=1.0, veto=False,
            reasons=[f"macro neutral — {why}"], raw={"degraded": True},
        )

    @staticmethod
    def _state_and_multiplier(score: float, cfg) -> tuple[str, float]:
        on, off = cfg.risk_on_threshold, cfg.risk_off_threshold
        if score >= on:
            return "RISK_ON", 1.0
        if score <= off:
            # 0..off → 0.3..0.6 (cut size in risk-off, file 04 §165)
            return "RISK_OFF", 0.3 + 0.3 * (score / off if off > 0 else 1.0)
        # neutral band off..on → 0.6..1.0
        span = on - off
        return "NEUTRAL", 0.6 + 0.4 * ((score - off) / span if span > 0 else 1.0)
