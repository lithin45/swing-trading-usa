"""Broker risk gates: heat / max-positions caps + loss-halt + drawdown circuit breakers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from swing_signals.broker.base import BrokerAccount
from swing_signals.broker.gates import can_open, evaluate_gates
from swing_signals.config_loader import load_settings

TODAY = date(2024, 1, 10)  # a Wednesday


@dataclass
class FakeSnap:
    equity: float
    ts: datetime


@dataclass
class FakeTrade:
    symbol: str
    suggested_risk_pct: float


def _acct(equity: float) -> BrokerAccount:
    return BrokerAccount(equity=equity, cash=equity, buying_power=equity)


def test_clean_state_allows_entry():
    s = load_settings()
    g = evaluate_gates(s, account=_acct(500.0), open_trades=[], snapshots=[], today=TODAY)
    assert not g.halted
    assert g.open_positions == 0
    ok, why = can_open(g, s, risk_pct=0.01)
    assert ok and why is None


def test_max_positions_blocks():
    s = load_settings()
    s.risk.max_positions = 2
    trades = [FakeTrade("AAPL", 0.01), FakeTrade("MSFT", 0.01)]
    g = evaluate_gates(s, account=_acct(500.0), open_trades=trades, snapshots=[], today=TODAY)
    ok, why = can_open(g, s, risk_pct=0.01)
    assert not ok and "max positions" in why


def test_heat_cap_blocks_at_threshold():
    s = load_settings()
    s.risk.portfolio_heat_cap = 0.03
    g = evaluate_gates(
        s, account=_acct(500.0), open_trades=[FakeTrade("AAPL", 0.02)], snapshots=[], today=TODAY
    )
    assert can_open(g, s, risk_pct=0.02)[0] is False  # 0.02 + 0.02 > 0.03
    assert can_open(g, s, risk_pct=0.01)[0] is True   # 0.02 + 0.01 == 0.03 ok


def test_drawdown_hard_halt():
    s = load_settings()
    snaps = [FakeSnap(100.0, datetime(2024, 1, 2, 17))]
    g = evaluate_gates(s, account=_acct(84.0), open_trades=[], snapshots=snaps, today=TODAY)
    assert g.halted and "drawdown" in g.halt_reason  # -16% >= 15% hard halt


def test_drawdown_derisk_band():
    s = load_settings()
    s.risk.daily_loss_halt = s.risk.weekly_loss_halt = s.risk.monthly_loss_halt = 0.99
    snaps = [FakeSnap(100.0, datetime(2024, 1, 2, 17))]
    g = evaluate_gates(s, account=_acct(89.0), open_trades=[], snapshots=snaps, today=TODAY)
    assert not g.halted
    assert g.derisk_multiplier == 0.5  # -11% is in the [10%, 15%) derisk band


def test_daily_loss_halt():
    s = load_settings()
    snaps = [FakeSnap(100.0, datetime(2024, 1, 9, 17))]  # yesterday's close
    g = evaluate_gates(s, account=_acct(96.0), open_trades=[], snapshots=snaps, today=TODAY)
    # -4% day >= 3% daily halt; drawdown is only -4% so it doesn't preempt
    assert g.halted and "daily loss" in g.halt_reason


def test_no_snapshots_no_halt():
    s = load_settings()
    g = evaluate_gates(s, account=_acct(400.0), open_trades=[], snapshots=[], today=TODAY)
    assert not g.halted  # no history -> period baselines skipped, peak == current


def test_broker_blocked_account_halts():
    s = load_settings()
    acct = BrokerAccount(equity=1000.0, cash=1000.0, buying_power=1000.0,
                         trading_blocked=True)
    state = evaluate_gates(s, account=acct, open_trades=[], snapshots=[],
                           today=date(2024, 1, 8))
    assert state.halted
    assert "blocked" in (state.halt_reason or "")
