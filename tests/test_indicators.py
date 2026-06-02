"""Indicator correctness: exact small cases + properties."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swing_signals.factors import indicators as ind


def test_sma_exact():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert ind.sma(s, 2).iloc[-1] == 3.5


def test_ema_constant_series():
    s = pd.Series([5.0] * 30)
    assert abs(ind.ema(s, 10).iloc[-1] - 5.0) < 1e-9


def test_rsi_all_up_near_100():
    s = pd.Series(np.arange(1, 60, dtype=float))
    assert ind.rsi(s, 14).iloc[-1] > 99


def test_rsi_all_down_near_0():
    s = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert ind.rsi(s, 14).iloc[-1] < 1


def test_rsi_flat_is_neutral():
    s = pd.Series([10.0] * 40)
    assert abs(ind.rsi(s, 14).iloc[-1] - 50.0) < 1e-9


def test_atr_constant_range():
    n = 60
    high = pd.Series(np.full(n, 11.0))
    low = pd.Series(np.full(n, 9.0))
    close = pd.Series(np.full(n, 10.0))
    # TR each bar = 2 (high-low); no gaps -> ATR converges to 2.
    assert abs(ind.atr(high, low, close, 14).iloc[-1] - 2.0) < 1e-6


def test_adx_rises_in_trend():
    n = 120
    close = pd.Series(np.linspace(10, 60, n))
    high = close + 0.5
    low = close - 0.5
    adx, plus_di, minus_di = ind.adx(high, low, close, 14)
    assert adx.iloc[-1] > 25  # strong, sustained trend
    assert plus_di.iloc[-1] > minus_di.iloc[-1]  # upward


def test_donchian_high_prior_only():
    high = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    # prior-2 high at the last bar = max(high[-3], high[-2]) = max(3,4) = 4
    assert ind.donchian_high(high, 2).iloc[-1] == 4.0


def test_bollinger_percent_b_in_band():
    close = pd.Series(np.linspace(10, 11, 40))
    _mid, _u, _l, bw, pctb = ind.bollinger(close, 20, 2.0)
    assert 0.0 <= pctb.iloc[-1] <= 1.0
    assert bw.iloc[-1] > 0


def test_rvol_doubles_on_double_volume():
    vol = pd.Series([100.0] * 19 + [200.0])
    assert abs(ind.rvol(vol, 20).iloc[-1] - (200.0 / 105.0)) < 1e-6


def test_obv_rises_on_up_days():
    close = pd.Series([1.0, 2.0, 3.0, 4.0])
    vol = pd.Series([10.0, 10.0, 10.0, 10.0])
    out = ind.obv(close, vol)
    assert out.iloc[-1] == 30.0  # three up days * 10
