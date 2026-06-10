"""Factor 08 (momentum): direction, eligibility gate, data guards, panel parity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swing_signals.context import SymbolData
from swing_signals.factors import register_builtins
from swing_signals.factors.f01_technical import build_panel
from swing_signals.factors.f08_momentum import MIN_BARS, MomentumFactor


def _ohlcv(close: np.ndarray, vol: float = 2_000_000.0) -> pd.DataFrame:
    n = len(close)
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
         "volume": np.full(n, vol)},
        index=idx,
    )


def _sd(close) -> SymbolData:
    return SymbolData(symbol="TEST", ohlcv=_ohlcv(np.asarray(close, dtype=float)))


def test_uptrend_eligible_and_bullish():
    ss = MomentumFactor().compute(_sd(np.linspace(50, 150, 300)), ctx=None)
    assert ss.ok
    assert ss.value > 70
    assert ss.raw["eligible"] is True
    assert ss.raw["nearness_52w_high"] > 0.95


def test_downtrend_not_eligible():
    ss = MomentumFactor().compute(_sd(np.linspace(150, 50, 300)), ctx=None)
    assert ss.ok
    assert ss.value < 40
    assert ss.raw["eligible"] is False


def test_far_below_52w_high_not_eligible():
    # Rise to 150, then pull back ~30% to 105 — too far off the high to be eligible.
    path = np.concatenate([np.linspace(50, 150, 250), np.linspace(150, 105, 50)])
    ss = MomentumFactor().compute(_sd(path), ctx=None)
    assert ss.ok
    assert ss.raw["nearness_52w_high"] < 0.75
    assert ss.raw["eligible"] is False


def test_insufficient_data_is_unavailable():
    ss = MomentumFactor().compute(_sd(np.linspace(50, 60, 100)), ctx=None)
    assert not ss.ok
    assert "insufficient" in ss.reasons[0]


def test_missing_ohlcv_is_unavailable():
    ss = MomentumFactor().compute(SymbolData(symbol="TEST", ohlcv=None), ctx=None)
    assert not ss.ok


def test_registered_as_builtin():
    assert "momentum" in register_builtins()


def test_precomputed_panel_matches_recompute():
    """The backtest fast-path (panel row) must EXACTLY equal a live recompute."""
    n = 400
    t = np.arange(n)
    close = 50.0 + 0.2 * t + 5.0 * np.sin(t / 9.0)  # trend + deterministic wiggle
    df = _ohlcv(close)
    panel = build_panel(df)
    factor = MomentumFactor()

    checked = 0
    for i in range(MIN_BARS, n, 13):
        sliced = df.iloc[: i + 1]
        recompute = factor.compute(SymbolData(symbol="X", ohlcv=sliced), ctx=None)
        precomputed = factor.compute(
            SymbolData(symbol="X", ohlcv=sliced, indicators=panel.iloc[i].to_dict()), ctx=None,
        )
        assert recompute.ok and precomputed.ok
        assert precomputed.value == recompute.value, (
            f"bar {i}: {precomputed.value} != {recompute.value}"
        )
        checked += 1
    assert checked >= 5
