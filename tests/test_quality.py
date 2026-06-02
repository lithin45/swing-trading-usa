"""Data-quality gate: clean data passes; bad/stale/short data is flagged loudly."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from swing_signals.data.quality import check_ohlcv_quality


def _df(n: int = 250, end: str = "2024-01-05") -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame(
        {
            "open": np.linspace(10, 20, n),
            "high": np.linspace(10, 21, n),
            "low": np.linspace(9, 19, n),
            "close": np.linspace(10, 20, n),
            "volume": np.full(n, 1_000_000),
        },
        index=idx,
    )


def test_clean_passes():
    issues = check_ohlcv_quality(
        _df(), symbol="AAA", asof=date(2024, 1, 5), min_rows=200, max_staleness_days=4
    )
    assert issues == []


def test_none_flagged():
    assert check_ohlcv_quality(None, symbol="AAA", asof=date(2024, 1, 5))


def test_too_few_rows_flagged():
    issues = check_ohlcv_quality(_df(n=50), symbol="AAA", asof=date(2024, 1, 5), min_rows=200)
    assert any("bars" in i for i in issues)


def test_stale_flagged():
    issues = check_ohlcv_quality(
        _df(end="2023-12-01"), symbol="AAA", asof=date(2024, 1, 5), max_staleness_days=4
    )
    assert any("stale" in i for i in issues)


def test_missing_column_flagged():
    issues = check_ohlcv_quality(
        _df().drop(columns=["volume"]), symbol="AAA", asof=date(2024, 1, 5)
    )
    assert any("missing column" in i for i in issues)
