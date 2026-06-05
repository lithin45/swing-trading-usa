"""compute_metrics(): known results on synthetic trade logs."""

from __future__ import annotations

from datetime import date

from swing_signals.backtest.metrics import Trade, compute_metrics


def _trade(r: float, ticker: str = "AAA") -> Trade:
    """Make a synthetic closed Trade with a given realized_r."""
    # Use cost-neutral entries for simplicity (entry and exit are adjusted externally).
    entry = 100.0
    stop = 90.0
    rps = entry - stop  # 10
    exit_price = entry + r * rps
    t = Trade(
        ticker=ticker,
        signal_date=date(2023, 1, 2),
        entry_date=date(2023, 1, 3),
        entry_fill=entry,
        exit_date=date(2023, 1, 10),
        exit_fill=exit_price,
        exit_reason="target" if r > 0 else "stop",
        stop=stop,
        target=entry + 2 * rps,
        risk_per_share=rps,
        shares=1.0,
        bars_held=5,
    )
    return t


def test_expectancy_positive():
    trades = [_trade(2.0), _trade(-1.0), _trade(2.0)]
    eq = [500.0, 510.0, 500.0, 520.0]
    m = compute_metrics(trades, eq, 500.0, 3)
    assert m["expectancy"] == pytest_approx(1.0)
    assert m["win_rate"] > 0.66  # 2/3 = 0.6667 after rounding
    assert m["gates"]["expectancy_positive"]


def test_expectancy_negative():
    trades = [_trade(-1.0), _trade(-1.0)]
    eq = [500.0, 490.0, 480.0]
    m = compute_metrics(trades, eq, 500.0, 2)
    assert m["expectancy"] < 0
    assert not m["gates"]["expectancy_positive"]


def test_profit_factor_2R_strategy():
    # 50% win rate, 2:1 R → profit factor = 1.0
    trades = [_trade(2.0), _trade(-1.0), _trade(2.0), _trade(-1.0)]
    eq = [500.0] * 5
    m = compute_metrics(trades, eq, 500.0, 4)
    assert abs(m["profit_factor"] - 2.0) < 0.01


def test_max_drawdown_is_negative():
    trades = [_trade(-1.0)]
    eq = [500.0, 490.0]
    m = compute_metrics(trades, eq, 500.0, 1)
    assert m["max_drawdown"] < 0


def test_flat_equity_sharpe_zero():
    trades = [_trade(0.0)]
    eq = [500.0] * 252
    m = compute_metrics(trades, eq, 500.0, 252)
    assert abs(m["sharpe"]) < 1e-9


def test_no_trades_returns_empty():
    m = compute_metrics([], [500.0], 500.0, 1)
    assert m["n_trades"] == 0
    assert m["expectancy"] == 0.0
    assert not m["gates"]["expectancy_positive"]


def test_ticker_breakdown_present():
    trades = [_trade(1.0, "AAA"), _trade(-1.0, "BBB"), _trade(2.0, "AAA")]
    eq = [500.0] * 4
    m = compute_metrics(trades, eq, 500.0, 3)
    assert "AAA" in m["ticker_breakdown"]
    assert m["ticker_breakdown"]["AAA"]["n"] == 2


# pytest_approx shim for standalone use
import math  # noqa: E402

def pytest_approx(val: float, rel: float = 1e-6) -> "_Approx":
    return _Approx(val, rel)

class _Approx:
    def __init__(self, expected, rel):
        self.expected = expected
        self.rel = rel
    def __eq__(self, other):
        return math.isclose(other, self.expected, rel_tol=self.rel)
    def __repr__(self):
        return f"≈{self.expected}"
