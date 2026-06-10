"""Volatility-scaled position sizing.

The one robustly evidenced risk technique for momentum (Daniel & Moskowitz 2016;
Barroso & Santa-Clara 2015): scaling exposure to a volatility target roughly
doubles momentum's risk-adjusted return and cuts its crash risk. Here it produces
a multiplier in ``[scalar_min, scalar_max]`` that the scoring engine folds into the
conviction multiplier, so a high-ATR name (or a high-volatility market) is sized
DOWN. It never sizes *up* (caps at scalar_max, default 1.0), so it can only reduce
risk versus the base fixed-fractional size.
"""

from __future__ import annotations


def vol_scalar(
    *,
    atr_pct: float | None,
    vol_target_atr_pct: float,
    market_vol_score: float | None = None,
    scalar_min: float = 0.4,
    scalar_max: float = 1.0,
) -> float:
    """Volatility-target size multiplier.

    Args:
        atr_pct: the name's daily ATR as a percent of price (e.g. 3.0 for 3%/day).
        vol_target_atr_pct: the ATR% that earns full size (size ∝ target / atr_pct).
        market_vol_score: the regime volatility pillar (0-100, 100 = calm); when set,
            a stressed market scales everyone toward half size.
        scalar_min / scalar_max: clamp for the final multiplier.

    Returns:
        A multiplier in [scalar_min, scalar_max]. ~1.0 at the target vol; ~0.5 at
        twice the target vol; floored so size never collapses to zero.
    """
    if atr_pct is None or atr_pct <= 0:
        name_scalar = scalar_max
    else:
        name_scalar = vol_target_atr_pct / atr_pct

    if market_vol_score is not None:
        # 100 (calm) -> 1.0x, 0 (stressed) -> 0.5x.
        market_scalar = 0.5 + 0.5 * max(0.0, min(100.0, market_vol_score)) / 100.0
    else:
        market_scalar = 1.0

    return max(scalar_min, min(scalar_max, name_scalar * market_scalar))
