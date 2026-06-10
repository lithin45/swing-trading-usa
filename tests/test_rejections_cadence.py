"""Rejection persistence (audit trail) + cadence distribution metrics."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from swing_signals.backtest.metrics import Trade, compute_metrics
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Rejection
from swing_signals.persistence.repository import create_run, save_rejections
from swing_signals.scoring.engine import Signal as EngineSignal

DAY = date(2024, 1, 8)
TS = datetime(2024, 1, 8, 17, 0, 0)


def _reject(symbol: str, *, flags: list[str], score: float = 69.8) -> EngineSignal:
    return EngineSignal(
        ticker=symbol, signal_date=DAY, direction="NO-TRADE",
        conviction_score=score, conviction_tier="None",
        regime_state="GREEN", agreement_score=0.8, flags=flags,
        reasons=["near miss"], explanation=f"{symbol}: no-trade — test",
    )


def test_rejections_persist_and_are_idempotent(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/sig.db")
    rejs = [
        _reject("NEAR", flags=[]),
        _reject("BUDG", flags=["BUDGET_EXHAUSTED"]),
        _reject("COOL", flags=["COOLDOWN"]),
    ]
    with session_scope(eng) as s:
        run = create_run(s, run_ts=TS, trading_day=DAY, status="success")
        assert save_rejections(s, run, rejs, created_at=TS) == 3
        assert save_rejections(s, run, rejs, created_at=TS) == 0  # same-day re-run no-op

    with session_scope(eng) as s:
        rows = list(s.scalars(select(Rejection).order_by(Rejection.symbol)))
        assert [r.symbol for r in rows] == ["BUDG", "COOL", "NEAR"]
        budg = rows[0]
        assert "BUDGET_EXHAUSTED" in (budg.flags or "")
        near = rows[2]
        assert near.composite_score == 69.8  # the near-miss is now queryable


def _trade(symbol: str, entry: date, exit_: date, r: float) -> Trade:
    return Trade(
        ticker=symbol, signal_date=entry, entry_date=entry, entry_fill=100.0,
        exit_date=exit_, exit_fill=100.0 + 6.0 * r, exit_reason="target",
        stop=94.0, target=112.0, risk_per_share=6.0, shares=10.0, bars_held=5,
    )


def test_cadence_block_in_metrics():
    trades = [
        _trade("A", date(2024, 1, 5), date(2024, 1, 20), 1.0),
        _trade("B", date(2024, 1, 9), date(2024, 1, 25), -0.5),
        _trade("C", date(2024, 2, 6), date(2024, 2, 15), 2.0),
    ]
    m = compute_metrics(
        trades, [100_000.0, 101_000.0], 100_000.0, 40,
        entries_by_month={"2024-01": 8, "2024-02": 3},
        budget_cap=7,
    )
    cad = m["cadence"]
    assert cad["entries_by_month"] == {"2024-01": 8, "2024-02": 3}
    assert cad["fills_by_month"] == {"2024-01": 2, "2024-02": 1}
    assert cad["entries_per_month_max"] == 8
    assert cad["budget_cap"] == 7
    assert cad["months_over_cap"] == 1  # the hot month is visible, not averaged away


def test_cadence_present_even_with_no_trades():
    m = compute_metrics([], [100_000.0], 100_000.0, 0,
                        entries_by_month={}, budget_cap=7)
    assert m["cadence"]["entries_by_month"] == {}
    assert m["cadence"]["months_over_cap"] == 0
