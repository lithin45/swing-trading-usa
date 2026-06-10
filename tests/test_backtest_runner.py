"""BacktestRunner integration tests — uses offline cached OHLCV (no network)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.runner import BacktestRunner, _bar_at, _slice_to
from swing_signals.config_loader import load_secrets, load_settings


def _ohlcv(start: str, n: int = 260, close_start: float = 50.0, slope: float = 0.5) -> pd.DataFrame:
    """Synthetic OHLCV — upward drift so the technical factor fires."""
    idx = pd.bdate_range(start=start, periods=n)
    close = np.array([close_start + i * slope for i in range(n)])
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.full(n, 2_000_000),
        },
        index=idx,
    )


def _build_runner(n_bars: int = 800, slope: float = 0.3) -> BacktestRunner:
    """800 business days from 2020-01-01 covers through ~early 2023, spanning 2022."""
    settings = load_settings()
    secrets = load_secrets()
    bt_cfg = BacktestCfg(
        start="2022-01-01", end="2022-12-31",
        cost_bps=10.0, max_hold_bars=20, warmup_bars=210, equity_start=500.0,
    )
    syms = settings.watchlist.symbols
    ohlcv_all = {s: _ohlcv("2020-01-01", n=n_bars, close_start=50 + i * 5, slope=slope)
                 for i, s in enumerate(syms)}
    index_syms = ["SPY", "QQQ", "IWM"]
    index_ohlcv = {s: _ohlcv("2020-01-01", n=n_bars, close_start=300, slope=slope * 2)
                   for s in index_syms}
    return BacktestRunner(
        settings=settings, bt_cfg=bt_cfg,
        ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv, secrets=secrets,
    )


# ── Lookahead-guard unit tests ─────────────────────────────────────────────

def test_slice_to_excludes_future():
    df = _ohlcv("2023-01-01", n=10)
    asof = date(2023, 1, 5)
    sliced = _slice_to(df, asof)
    for ts in sliced.index:
        d = ts.date()
        assert d <= asof, f"future bar {d} leaked past asof {asof}"


def test_bar_at_returns_correct_row():
    df = _ohlcv("2023-01-02", n=5)
    target = date(2023, 1, 4)
    row = _bar_at(df, target)
    assert row is not None
    assert abs(float(row["close"]) - float(df.loc[df.index[2], "close"])) < 1e-9


def test_bar_at_missing_returns_none():
    df = _ohlcv("2023-01-02", n=3)
    assert _bar_at(df, date(1999, 1, 1)) is None


# ── BacktestRunner integration ─────────────────────────────────────────────

def test_run_produces_result(tmp_path):
    runner = _build_runner()
    start = date(2022, 1, 1)
    end = date(2022, 12, 31)
    result = runner.run(start, end)

    assert result.metrics is not None
    assert result.metrics["n_trades"] >= 0        # may be 0 on first run if no signals fired
    assert len(result.equity_curve) > 0
    assert result.metrics["equity_start"] == pytest.approx(500.0)


def test_no_lookahead_entry_is_next_open():
    """Verify entry_fill is NOT the signal-bar close (would be lookahead)."""
    runner = _build_runner(slope=0.5)
    result = runner.run(date(2022, 1, 1), date(2022, 12, 31))

    if not result.trades:
        pytest.skip("no trades generated — increase slope or date range")

    for trade in result.trades:
        sym = trade.ticker
        df = runner.ohlcv_all.get(sym)
        if df is None:
            continue
        signal_bar = _bar_at(df, trade.signal_date)
        if signal_bar is not None:
            signal_close = float(signal_bar["close"])
            # Entry fill must NOT equal the signal-bar close (that would be lookahead).
            assert trade.entry_fill != pytest.approx(signal_close, rel=1e-4), (
                f"{sym}: entry_fill ({trade.entry_fill}) == signal_close ({signal_close}) — "
                "lookahead detected!"
            )


def test_realized_r_computed_for_all_trades():
    runner = _build_runner()
    result = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    for trade in result.trades:
        assert trade.realized_r is not None
        assert isinstance(trade.realized_r, float)


def test_equity_curve_length_matches_trading_days():
    runner = _build_runner()
    result = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    assert len(result.equity_curve) == len(result.trading_days)


def test_max_drawdown_is_non_positive():
    runner = _build_runner()
    result = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    assert result.metrics["max_drawdown"] <= 0.0


def test_all_exit_reasons_are_valid():
    valid = {"stop", "target", "time_stop", "time_stop_stagnant", "gap_stop", "end_of_range"}
    runner = _build_runner()
    result = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    for trade in result.trades:
        assert trade.exit_reason in valid, f"unexpected exit reason: {trade.exit_reason}"
