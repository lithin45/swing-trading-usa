"""Composite scoring (the transparent core of file 10).

This stage provides the pure, testable composite seam. The surrounding pipeline
— regime/risk gates, ATR entry/stop/target levels, agreement/conflict checks,
conviction tiers, and the full signal record — is implemented in Stage 4 (in
``scoring/gates.py``, ``scoring/levels.py``, and an expanded ``generate_signals``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..factors.base import NEUTRAL

if TYPE_CHECKING:
    from ..factors.base import SubScore


def composite_score(
    subscores: list[SubScore],
    weights: dict[str, float],
) -> tuple[float, dict[str, dict[str, float]]]:
    """Weighted average of factor sub-scores, with full per-factor attribution.

    Sub-scores marked ``ok=False`` (data unavailable) are excluded — never treated
    as neutral — and the weights renormalize over the factors that did compute.

    Returns ``(score, attribution)`` where ``score`` is 0–100 and ``attribution``
    maps factor name → {value, weight, contribution} so every signal can show
    exactly what drove it.
    """
    usable = [s for s in subscores if s.ok and weights.get(s.name, 0) > 0]
    wsum = sum(weights[s.name] for s in usable)
    if wsum <= 0:
        return NEUTRAL, {}

    attribution: dict[str, dict[str, float]] = {}
    score = 0.0
    for s in usable:
        w = weights[s.name] / wsum  # renormalize over usable factors
        contribution = s.value * w
        score += contribution
        attribution[s.name] = {
            "value": round(s.value, 2),
            "weight": round(w, 4),
            "contribution": round(contribution, 2),
        }
    return score, attribution
