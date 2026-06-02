"""Factor 01 (technical): direction sanity, data guards, registration."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swing_signals.context import SymbolData
from swing_signals.factors import register_builtins
from swing_signals.factors.f01_technical import MIN_BARS, TechnicalFactor


def _ohlcv(close_path: np.ndarray, *, vol: float = 1_000_000.0) -> pd.DataFrame:
    n = len(close_path)
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    return pd.DataFrame(
        {
            "open": close_path,
            "high": close_path + 0.5,
            "low": close_path - 0.5,
            "close": close_path,
            "volume": np.full(n, vol),
        },
        index=idx,
    )


def _sd(close_path: np.ndarray) -> SymbolData:
    return SymbolData(symbol="TEST", ohlcv=_ohlcv(close_path))


def test_uptrend_scores_bullish():
    close = np.linspace(50, 150, 260)
    ss = TechnicalFactor().compute(_sd(close), ctx=None)
    assert ss.ok
    assert ss.value > 60
    assert ss.reasons  # explains why it fired
    assert ss.raw["sma200"] < ss.raw["close"]


def test_downtrend_scores_bearish():
    close = np.linspace(150, 50, 260)
    ss = TechnicalFactor().compute(_sd(close), ctx=None)
    assert ss.ok
    assert ss.value < 40


def test_insufficient_data_is_unavailable():
    close = np.linspace(50, 60, 100)  # < MIN_BARS
    ss = TechnicalFactor().compute(_sd(close), ctx=None)
    assert not ss.ok
    assert "insufficient" in ss.reasons[0]
    assert len(close) < MIN_BARS


def test_missing_ohlcv_is_unavailable():
    ss = TechnicalFactor().compute(SymbolData(symbol="TEST", ohlcv=None), ctx=None)
    assert not ss.ok


def test_score_in_range_and_attribution_present():
    close = np.linspace(80, 120, 260)
    ss = TechnicalFactor().compute(_sd(close), ctx=None)
    assert 0.0 <= ss.value <= 100.0
    assert "components" in ss.raw
    assert "trend200" in ss.raw["components"]


def test_registered_as_builtin():
    assert "technical" in register_builtins()
