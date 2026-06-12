"""Coverage guards added 2026-06-10: start-truncated providers + backtest staleness.

The free Alpaca IEX feed silently serves only ~6 years of history from TODAY,
whatever start you ask for. Cached union-merges of such responses carved a
210-day hole into H1-2020, and symbols frozen at the hole's left edge kept
re-signaling at their stale momentum high — eating the entire monthly budget
five months running. Two layers of defense, both tested here:

1. DataLoader prefers the provider whose response actually covers the requested
   start (deep-history fallbacks beat a truncated first provider); a young
   listing (every provider agrees on the late start) is served, not rejected.
2. BacktestRunner mirrors the live ``max_staleness_days`` gate so a frame that
   stops updating becomes a DATA_INTEGRITY skip, never a zombie signal.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader


def _df(start: str, end: str) -> pd.DataFrame:
    idx = pd.bdate_range(start=start, end=end)
    base = np.linspace(10, 20, len(idx))
    return pd.DataFrame(
        {"open": base, "high": base + 1, "low": base - 1, "close": base,
         "volume": np.full(len(idx), 1_000_000)},
        index=idx,
    )


class _Fake:
    def __init__(self, name, df):
        self.name = name
        self._df = df

    def get_ohlcv(self, symbol, start, end):
        return self._df


@pytest.fixture
def loader(tmp_path):
    settings = load_settings()
    settings.data.cache_dir = str(tmp_path)
    ldr = DataLoader(settings, load_secrets())
    ldr.cache.dir = tmp_path
    ldr.news_providers = []
    return ldr


def test_truncated_first_provider_falls_through_to_deeper(loader):
    truncated = _df("2020-07-27", "2021-12-31")   # Alpaca-IEX-style: starts years late
    full = _df("2018-05-11", "2021-12-31")
    loader.providers = [_Fake("alpaca", truncated), _Fake("yfinance", full)]
    df = loader.get_ohlcv("AAA", "2018-05-11", "2021-12-31")
    assert df.index[0] == pd.Timestamp("2018-05-11")


def test_all_providers_truncated_returns_deepest(loader):
    shallow = _df("2020-07-27", "2021-12-31")
    deeper = _df("2019-06-01", "2021-12-31")
    loader.providers = [_Fake("a", shallow), _Fake("b", deeper)]
    df = loader.get_ohlcv("AAA", "2018-05-11", "2021-12-31")
    assert df.index[0] == pd.Timestamp("2019-06-03")  # first business day on/after


def test_young_listing_served_normally(loader):
    # IPO ~2 days after the requested start: inside tolerance, served by provider 1.
    ipo = _df("2018-05-14", "2021-12-31")
    loader.providers = [_Fake("a", ipo)]
    df = loader.get_ohlcv("AAA", "2018-05-11", "2021-12-31")
    assert df.index[0] == pd.Timestamp("2018-05-14")


def test_full_coverage_first_provider_wins(loader):
    full = _df("2018-05-11", "2021-12-31")
    never = _Fake("b", None)  # would blow up if called

    def boom(symbol, start, end):  # pragma: no cover - must not be reached
        raise AssertionError("second provider should not be called")

    never.get_ohlcv = boom
    loader.providers = [_Fake("a", full), never]
    df = loader.get_ohlcv("AAA", "2018-05-11", "2021-12-31")
    assert len(df) == len(full)


# ---------------------------------------------------------------------------
# Backtest staleness parity
# ---------------------------------------------------------------------------

def _stale_runner(frozen_end: str) -> BacktestRunner:
    settings = load_settings()
    secrets = load_secrets()
    bt_cfg = BacktestCfg(
        start="2020-01-01", end="2020-03-31",
        cost_bps=10.0, max_hold_bars=20, warmup_bars=210, equity_start=100_000.0,
    )
    full_idx = pd.bdate_range(start="2019-01-01", end="2020-03-31")
    frozen_idx = pd.bdate_range(start="2019-01-01", end=frozen_end)

    def _mk(idx):
        base = np.linspace(50, 100, len(idx))
        return pd.DataFrame(
            {"open": base, "high": base * 1.01, "low": base * 0.99, "close": base,
             "volume": np.full(len(idx), 2_000_000)},
            index=idx,
        )

    ohlcv_all = {"FROZEN": _mk(frozen_idx), "LIVE": _mk(full_idx)}
    index_ohlcv = {s: _mk(full_idx) for s in ("SPY", "QQQ", "IWM")}
    return BacktestRunner(
        settings=settings, bt_cfg=bt_cfg,
        ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv, secrets=secrets,
    )


def test_frozen_symbol_marked_stale_not_signalable():
    runner = _stale_runner(frozen_end="2020-01-15")
    data = runner._build_symbol_data(date(2020, 2, 14))
    assert not data["FROZEN"].ok
    assert any("stale" in i for i in data["FROZEN"].issues)
    assert data["LIVE"].ok


def test_symbol_within_staleness_window_still_ok():
    runner = _stale_runner(frozen_end="2020-02-12")
    # 2 business days later: inside max_staleness_days (4) -> still tradable.
    data = runner._build_symbol_data(date(2020, 2, 14))
    assert data["FROZEN"].ok


def test_offline_read_trims_to_requested_range(loader):
    full = _df("2013-01-01", "2026-06-01")
    loader.cache.put("AAA", full)
    df = loader.get_ohlcv("AAA", "2020-01-01", "2021-12-31", offline=True)
    assert df.index[0] >= pd.Timestamp("2020-01-01")
    assert df.index[-1] <= pd.Timestamp("2021-12-31")
    assert len(df) < len(full) / 2


def test_offline_read_empty_range_raises(loader):
    import pytest as _pytest

    from swing_signals.data.retry import PermanentDataError
    loader.cache.put("AAA", _df("2013-01-01", "2014-01-01"))
    with _pytest.raises(PermanentDataError):
        loader.get_ohlcv("AAA", "2020-01-01", "2021-12-31", offline=True)
