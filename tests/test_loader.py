"""DataLoader: cache-first, provider fallback, and fail-loud quality gating."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
from swing_signals.data.retry import TransientDataError

ASOF = date(2024, 1, 5)


def _clean_df(n: int = 250, end: str = "2024-01-05") -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=n)
    base = np.linspace(10, 20, n)
    return pd.DataFrame(
        {"open": base, "high": base + 1, "low": base - 1, "close": base,
         "volume": np.full(n, 1_000_000)},
        index=idx,
    )


class _Fake:
    def __init__(self, name, df=None, fail=False):
        self.name = name
        self._df = df
        self.fail = fail

    def get_ohlcv(self, symbol, start, end):
        if self.fail:
            raise TransientDataError(f"{self.name} boom")
        return self._df


@pytest.fixture
def loader(tmp_path):
    settings = load_settings()
    # point the cache at a temp dir so tests don't touch the real cache
    settings.data.cache_dir = str(tmp_path)
    ldr = DataLoader(settings, load_secrets())
    ldr.cache.dir = tmp_path  # ensure isolation
    ldr.news_providers = []   # never hit live news APIs in unit tests
    return ldr


def test_load_symbol_clean(loader):
    loader.providers = [_Fake("p", _clean_df())]
    sd = loader.load_symbol("AAA", ASOF)
    assert sd.ok and sd.issues == []
    assert sd.ohlcv is not None and len(sd.ohlcv) == 250


def test_load_symbol_short_history_flagged(loader):
    loader.providers = [_Fake("p", _clean_df(n=50))]
    sd = loader.load_symbol("AAA", ASOF)
    assert not sd.ok
    assert any("bars" in i for i in sd.issues)


def test_provider_fallback(loader):
    loader.providers = [_Fake("primary", fail=True), _Fake("backup", _clean_df())]
    sd = loader.load_symbol("AAA", ASOF)
    assert sd.ok  # backup succeeded
    assert sd.ohlcv is not None


def test_all_providers_fail_records_issue(loader):
    loader.providers = [_Fake("primary", fail=True)]
    sd = loader.load_symbol("AAA", ASOF)
    assert not sd.ok
    assert any("fetch failed" in i for i in sd.issues)


def test_cache_then_offline(loader):
    loader.providers = [_Fake("p", _clean_df())]
    loader.load_symbol("AAA", ASOF)  # populates cache
    loader.providers = [_Fake("p", fail=True)]  # network now "down"
    sd = loader.load_symbol("AAA", ASOF, offline=True)  # served from cache
    assert sd.ok and sd.ohlcv is not None


def test_load_watchlist_isolates_failures(loader):
    good = _Fake("g", _clean_df())
    loader.providers = [good]
    result = loader.load_watchlist(["AAA", "BBB"], ASOF)
    assert set(result) == {"AAA", "BBB"}
    assert all(sd.ok for sd in result.values())
