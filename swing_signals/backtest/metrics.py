"""Performance metrics (file 11 §6).

``Trade`` records each closed position; ``compute_metrics`` turns a list of Trades
plus a daily equity curve into the full file-11 metric suite.

Design: everything is expressed in **R-multiples** first (realized_r = how many
times the initial risk you made or lost), then in dollar/percentage terms second.
R-multiple thinking (Van Tharp) is the most consistent framework for a system
with variable position sizes and volatility-adaptive stops.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class Trade:
    """One closed swing-trade position."""

    ticker: str
    signal_date: date
    entry_date: date          # bar t+1 (fill date)
    entry_fill: float         # cost-adjusted open price
    exit_date: date
    exit_fill: float          # cost-adjusted exit price
    exit_reason: str          # "stop" | "target" | "time_stop" | "gap_stop"
    stop: float               # initial stop price (ATR-based)
    target: float             # initial target price
    risk_per_share: float     # entry_fill - stop (1R in $)
    shares: float
    bars_held: int

    # Derived fields — computed automatically by the runner
    realized_r: float = 0.0      # (exit_fill - entry_fill) / risk_per_share
    realized_pct: float = 0.0    # (exit_fill / entry_fill) - 1
    pnl_dollars: float = 0.0     # (exit_fill - entry_fill) * shares

    def __post_init__(self) -> None:
        if self.risk_per_share > 0:
            self.realized_r = (self.exit_fill - self.entry_fill) / self.risk_per_share
        if self.entry_fill > 0:
            self.realized_pct = self.exit_fill / self.entry_fill - 1.0
        self.pnl_dollars = (self.exit_fill - self.entry_fill) * self.shares


def compute_metrics(
    trades: list[Trade],
    equity_curve: list[float],      # daily equity, starting at equity_start
    equity_start: float,
    n_trading_days: int,
) -> dict[str, Any]:
    """Return the full file-11 metric suite from a trade log + equity curve."""

    n = len(trades)
    if n == 0:
        return _empty_metrics(equity_start)

    rs = [t.realized_r for t in trades]
    winners = [r for r in rs if r > 0]
    losers = [r for r in rs if r <= 0]

    win_rate = len(winners) / n
    expectancy = sum(rs) / n
    avg_win_r = sum(winners) / len(winners) if winners else 0.0
    avg_loss_r = sum(losers) / len(losers) if losers else 0.0
    profit_factor = (
        sum(winners) / abs(sum(losers))
        if losers and sum(losers) != 0
        else float("inf")
    )

    # Equity-curve statistics.
    eq = equity_curve
    max_dd = _max_drawdown(eq)

    if n_trading_days > 0 and eq[-1] > 0 and equity_start > 0:
        cagr = (eq[-1] / equity_start) ** (252.0 / n_trading_days) - 1.0
    else:
        cagr = 0.0

    # Daily returns from the equity curve.
    daily_rets = [
        (eq[i] / eq[i - 1] - 1.0) if eq[i - 1] > 0 else 0.0
        for i in range(1, len(eq))
    ]
    sharpe = _sharpe(daily_rets)
    sortino = _sortino(daily_rets)
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("inf")

    # Per-ticker breakdown.
    by_ticker: dict[str, list[float]] = {}
    for t in trades:
        by_ticker.setdefault(t.ticker, []).append(t.realized_r)
    ticker_summary = {
        sym: {
            "n": len(rs_),
            "expectancy": round(sum(rs_) / len(rs_), 3),
            "win_rate": round(sum(1 for r in rs_ if r > 0) / len(rs_), 3),
        }
        for sym, rs_ in by_ticker.items()
    }

    return {
        "n_trades": n,
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 4),
        "avg_win_r": round(avg_win_r, 4),
        "avg_loss_r": round(avg_loss_r, 4),
        "profit_factor": round(profit_factor, 4) if math.isfinite(profit_factor) else "∞",
        "max_drawdown": round(max_dd, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4) if math.isfinite(calmar) else "∞",
        "equity_start": round(equity_start, 2),
        "equity_end": round(eq[-1], 2) if eq else equity_start,
        "ticker_breakdown": ticker_summary,
        # Gate thresholds from file 11 (advance only if all pass).
        "gates": {
            "expectancy_positive": expectancy > 0,
            "profit_factor_1_3": profit_factor >= 1.3,
            "calmar_1": calmar >= 1.0 if math.isfinite(calmar) else False,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _max_drawdown(equity: list[float]) -> float:
    """Maximum peak-to-trough decline as a fraction (negative number)."""
    if len(equity) < 2:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _sharpe(daily_rets: list[float], rf: float = 0.0) -> float:
    if len(daily_rets) < 2:
        return 0.0
    n = len(daily_rets)
    mean = sum(daily_rets) / n - rf / 252.0
    var = sum((r - mean) ** 2 for r in daily_rets) / (n - 1)
    std = math.sqrt(var)
    return (mean / std * math.sqrt(252.0)) if std > 0 else 0.0


def _sortino(daily_rets: list[float], rf: float = 0.0) -> float:
    if len(daily_rets) < 2:
        return 0.0
    n = len(daily_rets)
    mean = sum(daily_rets) / n - rf / 252.0
    neg = [r for r in daily_rets if r < 0]
    if not neg:
        return float("inf")
    down_var = sum(r ** 2 for r in neg) / len(neg)
    down_std = math.sqrt(down_var)
    return (mean / down_std * math.sqrt(252.0)) if down_std > 0 else 0.0


def _empty_metrics(equity_start: float) -> dict[str, Any]:
    return {
        "n_trades": 0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "avg_win_r": 0.0,
        "avg_loss_r": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "cagr": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "calmar": 0.0,
        "equity_start": equity_start,
        "equity_end": equity_start,
        "ticker_breakdown": {},
        "gates": {
            "expectancy_positive": False,
            "profit_factor_1_3": False,
            "calmar_1": False,
        },
    }
