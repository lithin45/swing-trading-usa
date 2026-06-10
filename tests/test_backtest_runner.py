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


# ── Portfolio realism: caps, cash, limit-entry mechanics ───────────────────

def _mini_runner(ohlcv_all, *, equity=100_000.0, max_positions=8, heat_cap=0.10,
                 entry_type="limit", market_fallback=True, exits_mode=None):
    settings = load_settings()
    settings.risk.max_positions = max_positions
    settings.risk.portfolio_heat_cap = heat_cap
    settings.broker.entry_order_type = entry_type
    settings.broker.market_fallback = market_fallback
    if exits_mode is not None:
        settings.exits.mode = exits_mode
    bt_cfg = BacktestCfg(
        start="2022-01-01", end="2022-12-31",
        cost_bps=0.0, max_hold_bars=20, warmup_bars=210, equity_start=equity,
    )
    index_ohlcv = {s: _ohlcv("2020-01-01", n=800, close_start=300, slope=0.6)
                   for s in ["SPY", "QQQ", "IWM"]}
    return BacktestRunner(settings=settings, bt_cfg=bt_cfg,
                          ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv,
                          secrets=load_secrets())


def test_max_positions_binds_across_days():
    """Open positions accumulated over many days never exceed risk.max_positions."""
    settings = load_settings()
    syms = settings.watchlist.symbols
    ohlcv_all = {s: _ohlcv("2020-01-01", n=800, close_start=50 + i * 5, slope=0.3)
                 for i, s in enumerate(syms)}
    runner = _mini_runner(ohlcv_all, max_positions=2)
    res = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    assert len(res.trades) > 2  # the cap forces turnover, not a single static pair
    # Reconstruct concurrent holdings from the trade ledger.
    events = []
    for t in res.trades:
        events.append((t.entry_date, 1))
        events.append((t.exit_date, -1))
    concurrent = 0
    peak = 0
    for _, delta in sorted(events, key=lambda e: (e[0], -e[1])):
        concurrent += delta
        peak = max(peak, concurrent)
    assert peak <= 2, f"held {peak} concurrent positions with max_positions=2"


def test_cash_constraint_no_leverage():
    """Sum of simultaneously-open entry notional stays near the equity high-water.

    The old runner debited nothing at entry, so dozens of concurrent full-size
    positions could ride on the same dollars; with cash accounting each fill is
    clamped to what is actually available.
    """
    settings = load_settings()
    syms = settings.watchlist.symbols
    ohlcv_all = {s: _ohlcv("2020-01-01", n=800, close_start=50 + i * 5, slope=0.3)
                 for i, s in enumerate(syms)}
    runner = _mini_runner(ohlcv_all, equity=10_000.0, exits_mode="legacy")
    res = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    peak_equity = max(res.equity_curve)
    days = pd.date_range("2022-01-01", "2022-12-31", freq="B").date
    for d in days:
        open_notional = sum(
            t.entry_fill * t.shares for t in res.trades
            if t.entry_date <= d < t.exit_date
        )
        # 5% slack: cash freed by underwater exits can be redeployed at the
        # high-water while older positions still carry their entry notional.
        assert open_notional <= peak_equity * 1.05 + 1e-6


def test_limit_entry_fills_only_when_touched():
    """A breakaway gap-and-go above the limit must NOT fill (the live limit wouldn't)."""
    idx = pd.bdate_range(start="2020-01-01", periods=800)
    n = len(idx)
    close = np.array([50 + i * 0.30 for i in range(n)])
    df = pd.DataFrame({
        "open": close * 0.999, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": np.full(n, 2_000_000),
    }, index=idx)
    # From bar 600 on: every day gaps up and never trades back to the prior close
    # (low is 3% ABOVE it), so a limit resting at the signal close cannot fill.
    closes = list(close)
    for i in range(600, n):
        prev = closes[i - 1]
        closes[i] = prev * 1.05
        df.iloc[i, df.columns.get_loc("open")] = prev * 1.04
        df.iloc[i, df.columns.get_loc("low")] = prev * 1.03
        df.iloc[i, df.columns.get_loc("close")] = closes[i]
        df.iloc[i, df.columns.get_loc("high")] = closes[i] * 1.01

    runner = _mini_runner({"AAPL": df}, market_fallback=False)
    res = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    gap_start = idx[600].date()
    assert all(t.entry_date < gap_start for t in res.trades), (
        "limit entries filled inside the runaway-gap regime where low never touched the limit"
    )
    assert res.n_unfilled > 0  # the aged-out orders are counted, not silently dropped


def test_universe_asof_filter_blocks_pre_membership_entries():
    """A name that joined the index mid-window must not trade before its join date."""
    join_day = date(2022, 7, 1)
    df = _ohlcv("2020-01-01", n=800, close_start=50, slope=0.3)
    runner = _mini_runner({"AAPL": df})
    runner.universe_asof = lambda d: frozenset({"AAPL"}) if d >= join_day else frozenset()
    res = runner.run(date(2022, 1, 1), date(2022, 12, 31))
    assert res.trades, "expected trades after the join date"
    assert all(t.signal_date >= join_day for t in res.trades)


def test_vix_series_hard_veto_blocks_all_entries():
    """Historical VIX above vix_max must veto every entry; calm VIX must not."""
    df = _ohlcv("2020-01-01", n=800, close_start=50, slope=0.3)
    idx = pd.bdate_range(start="2020-01-01", periods=800)

    stressed = _mini_runner({"AAPL": df})
    stressed._vix = pd.Series(35.0, index=idx)  # > vix_max 28 every day
    res_stressed = stressed.run(date(2022, 1, 1), date(2022, 12, 31))
    assert res_stressed.trades == []

    calm = _mini_runner({"AAPL": df})
    calm._vix = pd.Series(12.0, index=idx)
    res_calm = calm.run(date(2022, 1, 1), date(2022, 12, 31))
    assert len(res_calm.trades) > 0
