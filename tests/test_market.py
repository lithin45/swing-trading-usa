"""FRED provider graceful-degradation + market-context assembly (fail-soft)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from swing_signals.data.fred_provider import FredProvider
from swing_signals.data.market import build_market_context
from swing_signals.data.retry import PermanentDataError

FRED_SERIES = {"vix": "VIXCLS", "vix3m": "VXVCLS", "t10y2y": "T10Y2Y"}


def _ohlcv(sym: str, start: str, end: str) -> pd.DataFrame:
    idx = pd.bdate_range(end="2024-01-05", periods=20)
    return pd.DataFrame({c: np.arange(20.0) for c in
                         ["open", "high", "low", "close", "volume"]}, index=idx)


class _FakeFred:
    """Duck-types the bits build_market_context uses."""

    available = True
    _values = {"VIXCLS": 14.2, "VXVCLS": 16.0, "T10Y2Y": 0.35}

    def get_latest(self, series_id: str):
        return self._values[series_id]


def test_fred_no_key_unavailable_and_raises():
    fred = FredProvider(api_key=None)
    assert fred.available is False
    with pytest.raises(PermanentDataError):
        fred.get_series("VIXCLS")


def test_fred_get_latest_with_injected_client():
    fred = FredProvider(api_key="dummy")

    class _Client:
        def get_series(self, sid):
            return pd.Series([1.0, np.nan, 3.5])

    fred._client = _Client()
    assert fred.get_latest("ANY") == 3.5  # last non-NaN


def test_build_market_context_happy():
    mc = build_market_context(
        get_ohlcv=_ohlcv,
        fred=_FakeFred(),
        index_symbols=["SPY", "QQQ", "IWM"],
        fred_series=FRED_SERIES,
        lookback_days=60,
        asof=date(2024, 1, 5),
    )
    assert mc.spy is not None and mc.qqq is not None and mc.iwm is not None
    assert mc.vix == 14.2
    assert mc.vix3m == 16.0
    assert mc.macro_series == {"t10y2y": 0.35}
    assert mc.issues == []


def test_build_market_context_fred_unavailable_records_issue():
    mc = build_market_context(
        get_ohlcv=_ohlcv,
        fred=None,
        index_symbols=["SPY"],
        fred_series=FRED_SERIES,
        lookback_days=60,
        asof=date(2024, 1, 5),
    )
    assert mc.vix is None
    assert any("FRED unavailable" in i for i in mc.issues)


def test_build_market_context_index_failure_is_isolated():
    def _bad_ohlcv(sym, start, end):
        if sym == "QQQ":
            raise RuntimeError("boom")
        return _ohlcv(sym, start, end)

    mc = build_market_context(
        get_ohlcv=_bad_ohlcv,
        fred=_FakeFred(),
        index_symbols=["SPY", "QQQ"],
        fred_series=FRED_SERIES,
        lookback_days=60,
        asof=date(2024, 1, 5),
    )
    assert mc.spy is not None  # SPY still loaded
    assert mc.qqq is None
    assert any("QQQ" in i for i in mc.issues)
