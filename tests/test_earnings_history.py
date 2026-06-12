"""Earnings-date backfill: AV parsing, quota stop, table lookups, runner plumbing."""

from __future__ import annotations

from datetime import date

import pytest

from swing_signals.data.earnings_history import (
    EarningsHistory,
    fetch_av_earnings,
    load_state,
    save_symbol,
)
from swing_signals.data.retry import TransientDataError


def _patch_http(monkeypatch, payload):
    import swing_signals.news.base as nb

    monkeypatch.setattr(nb, "http_json", lambda url, **kw: payload)


def test_fetch_parses_reported_dates(monkeypatch):
    _patch_http(monkeypatch, {
        "symbol": "TGT",
        "quarterlyEarnings": [
            {"fiscalDateEnding": "2024-01-31", "reportedDate": "2024-03-05"},
            {"fiscalDateEnding": "2023-10-31", "reportedDate": "2023-11-15"},
            {"fiscalDateEnding": "bad", "reportedDate": ""},          # skipped
            {"fiscalDateEnding": "2023-07-31", "reportedDate": "2023-08-16"},
        ],
    })
    dates = fetch_av_earnings("TGT", "k")
    assert dates == [date(2023, 8, 16), date(2023, 11, 15), date(2024, 3, 5)]


def test_fetch_shapeless_returns_none_for_retry(monkeypatch):
    # AV's flaky mode: {} for symbols it knows perfectly well (seen live: ACN).
    _patch_http(monkeypatch, {})
    assert fetch_av_earnings("ACN", "k") is None


def test_fetch_shaped_but_dateless_is_terminal_empty(monkeypatch):
    _patch_http(monkeypatch, {"symbol": "YHOO", "annualEarnings": [], "quarterlyEarnings": []})
    assert fetch_av_earnings("YHOO", "k") == []


def test_retry_escalates_to_empty_after_max(tmp_path):
    from swing_signals.data.earnings_history import MAX_RETRIES

    dp, sp = tmp_path / "dates.csv", tmp_path / "state.csv"
    for i in range(MAX_RETRIES):
        save_symbol("ACN", None, dates_path=dp, state_path=sp)
        expected = "retry" if i < MAX_RETRIES - 1 else "empty"
        assert load_state(sp)["ACN"]["status"] == expected
    # a later successful fetch still wins
    save_symbol("ACN", [date(2024, 3, 5)], dates_path=dp, state_path=sp)
    assert load_state(sp)["ACN"]["status"] == "ok"


def test_fetch_quota_notice_raises_transient(monkeypatch):
    _patch_http(monkeypatch, {"Information": "25 requests per day limit reached"})
    with pytest.raises(TransientDataError, match="quota"):
        fetch_av_earnings("TGT", "k")


def test_fetch_sanitizes_key_in_errors(monkeypatch):
    import swing_signals.news.base as nb

    def boom(url, **kw):
        raise RuntimeError("http error at url?apikey=SECRETKEY123")

    monkeypatch.setattr(nb, "http_json", boom)
    with pytest.raises(TransientDataError) as ei:
        fetch_av_earnings("TGT", "SECRETKEY123")
    assert "SECRETKEY123" not in str(ei.value)


def test_next_after_lookup():
    h = EarningsHistory({"TGT": [date(2020, 3, 3), date(2020, 5, 20), date(2020, 8, 19)]})
    assert h.next_after("TGT", date(2020, 5, 1)) == date(2020, 5, 20)
    assert h.next_after("TGT", date(2020, 5, 20)) == date(2020, 5, 20)  # print day itself
    assert h.next_after("TGT", date(2020, 9, 1)) is None
    assert h.next_after("ZZZ", date(2020, 5, 1)) is None


def test_save_and_load_round_trip(tmp_path):
    dp, sp = tmp_path / "dates.csv", tmp_path / "state.csv"
    save_symbol("TGT", [date(2024, 3, 5), date(2023, 11, 15)], dates_path=dp, state_path=sp)
    save_symbol("YHOO", [], dates_path=dp, state_path=sp)

    h = EarningsHistory.load(dp)
    assert h is not None and "TGT" in h and "YHOO" not in h
    assert h.next_after("TGT", date(2024, 1, 1)) == date(2024, 3, 5)

    state = load_state(sp)
    assert state["TGT"]["status"] == "ok" and state["TGT"]["n_quarters"] == "2"
    assert state["YHOO"]["status"] == "empty"  # never re-fetched


def test_runner_sets_next_earnings(tmp_path):
    import numpy as np
    import pandas as pd

    from swing_signals.backtest.config import BacktestCfg
    from swing_signals.backtest.runner import BacktestRunner
    from swing_signals.config_loader import load_secrets, load_settings

    idx = pd.bdate_range(start="2019-01-01", end="2020-03-31")
    base = np.linspace(50, 100, len(idx))
    df = pd.DataFrame(
        {"open": base, "high": base * 1.01, "low": base * 0.99, "close": base,
         "volume": np.full(len(idx), 2_000_000)},
        index=idx,
    )
    runner = BacktestRunner(
        settings=load_settings(),
        bt_cfg=BacktestCfg(start="2020-01-01", end="2020-03-31", cost_bps=10.0,
                           max_hold_bars=20, warmup_bars=210, equity_start=100_000.0),
        ohlcv_all={"AAA": df},
        index_ohlcv={s: df for s in ("SPY", "QQQ", "IWM")},
        secrets=load_secrets(),
        earnings_history=EarningsHistory({"AAA": [date(2020, 2, 18)]}),
    )
    data = runner._build_symbol_data(date(2020, 2, 14))
    assert data["AAA"].next_earnings == date(2020, 2, 18)  # engine veto sees the print
    data = runner._build_symbol_data(date(2020, 2, 17))
    assert data["AAA"].next_earnings == date(2020, 2, 18)  # 1 day out: inside veto window
    data = runner._build_symbol_data(date(2020, 2, 24))
    assert data["AAA"].next_earnings is None  # print passed, nothing scheduled
