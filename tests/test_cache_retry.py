"""Parquet cache round-trip/freshness and retry-wrapper behavior."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from swing_signals.data.cache import OHLCVCache
from swing_signals.data.retry import (
    PermanentDataError,
    TransientDataError,
    with_retry,
)


def _df(n: int = 10, end: str = "2024-01-05") -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame(
        {
            "open": np.arange(n, dtype=float),
            "high": np.arange(n, dtype=float) + 1,
            "low": np.arange(n, dtype=float) - 1,
            "close": np.arange(n, dtype=float),
            "volume": np.full(n, 1000),
        },
        index=idx,
    )


def test_cache_round_trip(tmp_path):
    cache = OHLCVCache(tmp_path)
    df = _df()
    cache.put("AAPL", df)
    got = cache.get("AAPL")
    assert got is not None
    # check_freq=False: real OHLCV has no index freq; bdate_range sets freq='B'
    # which Parquet does not round-trip. Dates and values must still match.
    pd.testing.assert_frame_equal(got, df, check_freq=False)


def test_cache_miss_returns_none(tmp_path):
    assert OHLCVCache(tmp_path).get("NOPE") is None


def test_cache_corrupt_file_returns_none(tmp_path):
    cache = OHLCVCache(tmp_path)
    cache._path("BAD").write_text("not parquet")
    assert cache.get("BAD") is None  # logged + ignored, never raises


def test_fresh_for_recent_and_stale(tmp_path):
    cache = OHLCVCache(tmp_path)
    cache.put("AAPL", _df(end="2024-01-05"))
    assert cache.fresh_for("AAPL", asof=date(2024, 1, 5), max_age_days=4) is not None
    assert cache.fresh_for("AAPL", asof=date(2024, 3, 1), max_age_days=4) is None


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    @with_retry(attempts=3, base=0.001, cap=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientDataError("rate limited")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_does_not_retry_permanent():
    calls = {"n": 0}

    @with_retry(attempts=4, base=0.001, cap=0.01)
    def broken():
        calls["n"] += 1
        raise PermanentDataError("bad symbol")

    with pytest.raises(PermanentDataError):
        broken()
    assert calls["n"] == 1  # failed fast, no retries


def test_cache_put_union_merges_disjoint_ranges(tmp_path):
    """A deep-past fetch must not truncate newer cached bars (and vice versa)."""
    cache = OHLCVCache(tmp_path)
    recent = _df(n=10, end="2024-01-05")
    cache.put("AAPL", recent)
    older = _df(n=10, end="2018-06-29")
    cache.put("AAPL", older)
    got = cache.get("AAPL")
    assert len(got) == 20
    assert got.index.min() == older.index.min()
    assert got.index.max() == recent.index.max()


def test_cache_put_degenerate_frame_never_truncates(tmp_path):
    """A throttled provider's 1-bar response must not gut a multi-year cache."""
    cache = OHLCVCache(tmp_path)
    full = _df(n=500, end="2024-01-05")
    cache.put("SPY", full)
    one_bar = _df(n=1, end="2021-06-15")
    cache.put("SPY", one_bar)
    got = cache.get("SPY")
    assert len(got) == 501  # union: nothing lost, the lone bar added
    assert got.index.max() == full.index.max()
