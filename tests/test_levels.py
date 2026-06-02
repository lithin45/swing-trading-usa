"""ATR level math (file 01): entry zone, stop, target, Chandelier."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swing_signals.scoring.levels import compute_levels


def _series(n=60, val=100.0):
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    high = pd.Series(np.full(n, val + 1), index=idx)
    low = pd.Series(np.full(n, val - 1), index=idx)
    close = pd.Series(np.full(n, val), index=idx)
    return high, low, close


def test_levels_basic_math():
    high, low, close = _series(val=100.0)
    lv = compute_levels(
        ref_price=100.0, atr=2.0, high=high, low=low, close=close,
        stop_atr_mult=2.0, rr_target=2.0,
    )
    assert lv.entry == 100.0
    assert lv.entry_zone_low == 99.0  # ref - 0.5*ATR
    assert lv.stop == 96.0            # ref - 2*ATR
    assert lv.risk_per_share == 4.0
    assert lv.target == 108.0         # entry + 2*risk
    assert lv.reward_risk == 2.0
    assert lv.stop_distance_atr == 2.0


def test_chandelier_present_with_enough_bars():
    high, low, close = _series(n=60, val=100.0)
    lv = compute_levels(
        ref_price=100.0, atr=2.0, high=high, low=low, close=close,
        chandelier_lookback=22, chandelier_mult=3.0,
    )
    assert lv.chandelier_stop is not None
    # HighestHigh(22)=101, ATR(22)=2 -> 101 - 3*2 = 95
    assert abs(lv.chandelier_stop - 95.0) < 1e-6
