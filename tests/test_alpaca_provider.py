"""Alpaca price provider: bars.df normalization + key gating (offline, fakes)."""

from __future__ import annotations

import os

import pandas as pd
import pytest

from swing_signals.data.alpaca_provider import AlpacaProvider
from swing_signals.data.normalize import OHLCV_COLUMNS
from swing_signals.data.retry import PermanentDataError


class _FakeBars:
    def __init__(self, df):
        self.df = df


class _FakeClient:
    def __init__(self, df):
        self._df = df
        self.calls = []

    def get_stock_bars(self, req):
        self.calls.append(req)
        return _FakeBars(self._df)


def _alpaca_shaped(n: int = 3) -> pd.DataFrame:
    """A bars.df the SDK returns: MultiIndex (symbol, timestamp), tz-aware, extra cols."""
    ts = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"][:n], utc=True)
    idx = pd.MultiIndex.from_arrays([["AAPL"] * n, ts], names=["symbol", "timestamp"])
    return pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0][:n],
            "high": [2.0, 3.0, 4.0][:n],
            "low": [0.5, 1.5, 2.5][:n],
            "close": [1.5, 2.5, 3.5][:n],
            "volume": [100, 200, 300][:n],
            "trade_count": [1, 1, 1][:n],
            "vwap": [1.0, 2.0, 3.0][:n],
        },
        index=idx,
    )


def test_available_requires_both_keys():
    assert AlpacaProvider("k", "s").available
    assert not AlpacaProvider("k", None).available
    assert not AlpacaProvider(None, None).available


def test_no_keys_raises_permanent():
    with pytest.raises(PermanentDataError):
        AlpacaProvider(None, None).get_ohlcv("AAPL", "2024-01-01", "2024-02-01")


def test_get_ohlcv_normalizes_multiindex():
    p = AlpacaProvider("k", "s")
    p._client = _FakeClient(_alpaca_shaped())  # bypass network
    out = p.get_ohlcv("AAPL", "2024-01-01", "2024-02-01")
    assert list(out.columns) == OHLCV_COLUMNS  # symbol level dropped, OHLCV selected
    assert out.index.tz is None  # tz normalized away
    assert out.index.is_monotonic_increasing
    assert out["close"].iloc[-1] == 3.5


def test_empty_bars_raises():
    p = AlpacaProvider("k", "s")
    p._client = _FakeClient(pd.DataFrame())
    with pytest.raises(PermanentDataError):
        p.get_ohlcv("AAPL", "2024-01-01", "2024-02-01")


@pytest.mark.network
def test_alpaca_live_pull():
    key = os.environ.get("SWING_ALPACA_API_KEY")
    secret = os.environ.get("SWING_ALPACA_SECRET_KEY")
    if not (key and secret):
        pytest.skip("SWING_ALPACA_API_KEY/SECRET_KEY not set")
    df = AlpacaProvider(key, secret).get_ohlcv("AAPL", "2024-01-01", "2024-02-01")
    assert not df.empty
    assert list(df.columns) == OHLCV_COLUMNS
    assert df.index.is_monotonic_increasing
