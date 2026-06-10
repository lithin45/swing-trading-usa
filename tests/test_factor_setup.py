"""Factor 09 (setup): confirmation scoring, data guards, panel parity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swing_signals.context import SymbolData
from swing_signals.factors import register_builtins
from swing_signals.factors.f01_technical import build_panel
from swing_signals.factors.f09_setup import MIN_BARS, SetupFactor


def _ohlcv(close: np.ndarray, vol: np.ndarray | float = 1_000_000.0) -> pd.DataFrame:
    n = len(close)
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    volume = np.full(n, vol) if np.isscalar(vol) else vol
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": volume},
        index=idx,
    )


def _sd(close, vol=1_000_000.0) -> SymbolData:
    return SymbolData(symbol="TEST", ohlcv=_ohlcv(np.asarray(close, dtype=float), vol))


def test_breakout_uptrend_scores_above_neutral():
    ss = SetupFactor().compute(_sd(np.linspace(50, 150, 260)), ctx=None)
    assert ss.ok
    assert ss.value > 55  # fresh highs near the base top => confirmation


def test_downtrend_is_roughly_neutral():
    ss = SetupFactor().compute(_sd(np.linspace(150, 50, 260)), ctx=None)
    assert ss.ok
    assert 45.0 <= ss.value <= 58.0  # no setup => near neutral, not penalising hard


def test_insufficient_data_is_unavailable():
    ss = SetupFactor().compute(_sd(np.linspace(50, 60, 100)), ctx=None)
    assert not ss.ok
    assert "insufficient" in ss.reasons[0]


def test_missing_ohlcv_is_unavailable():
    ss = SetupFactor().compute(SymbolData(symbol="TEST", ohlcv=None), ctx=None)
    assert not ss.ok


def test_registered_as_builtin():
    assert "setup" in register_builtins()


def test_precomputed_panel_matches_recompute():
    n = 320
    t = np.arange(n)
    close = 50.0 + 0.2 * t + 5.0 * np.sin(t / 9.0)
    df = _ohlcv(close)
    panel = build_panel(df)
    factor = SetupFactor()

    checked = 0
    for i in range(MIN_BARS, n, 11):
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
