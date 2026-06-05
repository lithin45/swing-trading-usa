"""Persistence (file 12): run/signal logging, idempotency, outcome upsert."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from swing_signals.config_loader import load_settings
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Run, Signal
from swing_signals.persistence.repository import (
    create_run,
    open_signals,
    persist_daily_run,
    save_signals,
    upsert_outcome,
)
from swing_signals.scoring.engine import Signal as EngineSignal

DAY = date(2024, 1, 8)
TS = datetime(2024, 1, 8, 17, 0, 0)


def _sig(symbol: str, *, score: float = 78.0, rank: int = 1) -> EngineSignal:
    return EngineSignal(
        ticker=symbol, signal_date=DAY, direction="LONG",
        conviction_score=score, conviction_tier="High",
        reference_price=100.0, atr=3.0,
        entry_zone_low=99.0, entry_zone_high=100.0,
        stop_price=94.0, stop_distance_atr=2.0, target_price=112.0, reward_risk=2.0,
        suggested_risk_pct=0.01, suggested_shares=1.5, chandelier_stop=95.0,
        regime_state="GREEN", rank=rank,
        factor_contributions={"technical": {"value": score, "weight": 1.0}},
        agreement_score=1.0, flags=[],
    )


def _engine(tmp_path):
    return make_engine(f"sqlite:///{tmp_path}/signals.db")


def test_save_and_round_trip(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        run = create_run(s, run_ts=TS, trading_day=DAY, status="success", data_provider="yfinance")
        n = save_signals(s, run, [_sig("AAPL"), _sig("MSFT", rank=2)], created_at=TS)
        assert n == 2
        assert run.n_signals == 2

    with session_scope(eng) as s:
        rows = list(s.scalars(select(Signal).order_by(Signal.rank)))
        assert [r.symbol for r in rows] == ["AAPL", "MSFT"]
        aapl = rows[0]
        assert aapl.composite_score == 78.0
        assert aapl.stop_price == 94.0
        assert aapl.risk_per_share == 6.0  # entry 100 - stop 94 = 1R
        assert aapl.direction == "long"
        assert "technical" in (aapl.factor_scores or "")


def test_idempotent_rerun(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        run = create_run(s, run_ts=TS, trading_day=DAY, status="success")
        assert save_signals(s, run, [_sig("AAPL")], created_at=TS) == 1
    with session_scope(eng) as s:
        run = create_run(s, run_ts=TS, trading_day=DAY, status="success")
        assert save_signals(s, run, [_sig("AAPL")], created_at=TS) == 0  # already present
    with session_scope(eng) as s:
        assert len(list(s.scalars(select(Signal)))) == 1


def test_outcome_upsert_and_open_signals(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        run = create_run(s, run_ts=TS, trading_day=DAY, status="success")
        save_signals(s, run, [_sig("AAPL")], created_at=TS)

    with session_scope(eng) as s:
        opens = open_signals(s)
        assert len(opens) == 1  # no outcome yet
        upsert_outcome(s, opens[0].id, status="open", updated_at=TS)

    with session_scope(eng) as s:
        opens = open_signals(s)
        assert len(opens) == 1  # outcome exists but still 'open'
        upsert_outcome(
            s, opens[0].id, status="stopped", updated_at=TS,
            exit_price=94.0, realized_r=-1.0, bars_held=3,
        )

    with session_scope(eng) as s:
        assert open_signals(s) == []  # resolved
        sig = s.scalars(select(Signal)).one()
        assert sig.outcome.status == "stopped"
        assert sig.outcome.realized_r == -1.0


def test_persist_daily_run_via_settings(tmp_path):
    settings = load_settings()
    settings.run.db_url = f"sqlite:///{tmp_path}/run.db"
    n = persist_daily_run(settings, DAY, [_sig("AAPL"), _sig("NVDA", rank=2)])
    assert n == 2

    eng = make_engine(settings.run.db_url)
    with session_scope(eng) as s:
        runs = list(s.scalars(select(Run)))
        assert len(runs) == 1
        assert runs[0].n_signals == 2
        assert runs[0].config_hash  # auditability: which config produced these
