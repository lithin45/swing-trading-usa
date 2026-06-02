"""OHLCV normalization (pure) + network-marked live provider pulls."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from swing_signals.data.normalize import OHLCV_COLUMNS, normalize_ohlcv
from swing_signals.data.retry import PermanentDataError


def _yahoo_shaped(n: int = 5) -> pd.DataFrame:
    # yfinance-style: title-cased cols, extra columns, tz-aware index.
    idx = pd.date_range(end="2024-01-05", periods=n, freq="D", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": np.arange(n, dtype=float),
            "High": np.arange(n, dtype=float) + 1,
            "Low": np.arange(n, dtype=float) - 1,
            "Close": np.arange(n, dtype=float),
            "Volume": np.full(n, 1000),
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=idx,
    )


def test_normalize_yahoo_shape():
    out = normalize_ohlcv(_yahoo_shaped())
    assert list(out.columns) == OHLCV_COLUMNS
    assert out.index.tz is None  # tz dropped
    assert out.index.is_monotonic_increasing
    assert out.index.name == "date"


def test_normalize_maps_adj_close():
    df = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Adj Close": [1.5], "Volume": [10]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    out = normalize_ohlcv(df)
    assert "close" in out.columns
    assert out["close"].iloc[0] == 1.5


def test_normalize_missing_column_raises():
    df = pd.DataFrame({"Open": [1.0], "Close": [1.0], "Volume": [10]},
                      index=pd.to_datetime(["2024-01-02"]))
    with pytest.raises(PermanentDataError):
        normalize_ohlcv(df)


def test_normalize_empty_returns_empty():
    out = normalize_ohlcv(pd.DataFrame())
    assert list(out.columns) == OHLCV_COLUMNS
    assert len(out) == 0


def test_normalize_dedupes_and_sorts():
    idx = pd.to_datetime(["2024-01-03", "2024-01-02", "2024-01-03"])
    df = pd.DataFrame(
        {"open": [1, 2, 9], "high": [1, 2, 9], "low": [1, 2, 9],
         "close": [1, 2, 9], "volume": [1, 2, 9]},
        index=idx,
    )
    out = normalize_ohlcv(df)
    assert out.index.is_monotonic_increasing
    assert len(out) == 2  # duplicate date collapsed
    assert out.loc["2024-01-03", "close"] == 9  # keep="last"


@pytest.mark.network
def test_yfinance_live_pull():
    from swing_signals.data.yfinance_provider import YfinanceProvider

    df = YfinanceProvider().get_ohlcv("AAPL", "2024-01-01", "2024-02-01")
    assert not df.empty
    assert list(df.columns) == OHLCV_COLUMNS
    assert df.index.is_monotonic_increasing


@pytest.mark.network
def test_stooq_live_pull():
    import os

    from swing_signals.data.stooq_provider import StooqProvider

    key = os.environ.get("SWING_STOOQ_API_KEY")
    if not key:
        pytest.skip("SWING_STOOQ_API_KEY not set (Stooq bulk CSV now requires a key)")
    df = StooqProvider(api_key=key).get_ohlcv("AAPL", "2024-01-01", "2024-02-01")
    assert not df.empty
    assert list(df.columns) == OHLCV_COLUMNS
