"""Outcome tracker: exit resolution (stop/target/time/gap/open) + DB integration."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from sqlalchemy import select

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Signal
from swing_signals.persistence.repository import create_run, save_signals
from swing_signals.scoring.engine import Signal as EngineSignal
from swing_signals.tracking.outcomes import resolve_outcome, run_tracker

SIG_DATE = date(2024, 1, 8)  # a Monday


def _ohlcv(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    # rows[0] is the signal-date bar; the entry is rows[1] (next bar's open).
    idx = pd.bdate_range(start="2024-01-08", periods=len(rows))
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows], "high": [r[1] for r in rows],
            "low": [r[2] for r in rows], "close": [r[3] for r in rows],
            "volume": [1e6] * len(rows),
        },
        index=idx,
    )


# ── pure exit resolution (cost_bps=0 for clean numbers; 1R = entry 100 - stop 94 = 6) ──

def test_target_hit():
    df = _ohlcv([(100, 101, 99, 100), (100, 105, 98, 103), (103, 113, 102, 112)])
    r = resolve_outcome(signal_date=SIG_DATE, stop=94, target=112, ohlcv=df, cost_bps=0)
    assert r is not None
    assert r.status == "target_hit"
    assert r.entry_fill == 100.0
    assert r.realized_r == 2.0  # (112 - 100) / 6
    assert r.bars_held == 2
    assert r.exit_date == date(2024, 1, 10)


def test_stopped_intraday():
    df = _ohlcv([(100, 101, 99, 100), (100, 105, 98, 103), (103, 104, 93, 95)])
    r = resolve_outcome(signal_date=SIG_DATE, stop=94, target=112, ohlcv=df, cost_bps=0)
    assert r is not None
    assert r.status == "stopped"
    assert r.realized_r == -1.0  # (94 - 100) / 6
    assert r.mae <= -1.0


def test_gap_through_stop_fills_at_open():
    df = _ohlcv([(100, 101, 99, 100), (100, 105, 98, 103), (92, 93, 90, 91)])
    r = resolve_outcome(signal_date=SIG_DATE, stop=94, target=112, ohlcv=df, cost_bps=0)
    assert r is not None
    assert r.status == "stopped"
    assert r.exit_price == 92.0  # gap fills at the open, worse than the stop
    assert r.realized_r == round((92 - 100) / 6, 4)


def test_time_exit():
    df = _ohlcv([(100, 101, 99, 100), (100, 102, 99, 101), (101, 103, 100, 102)])
    r = resolve_outcome(
        signal_date=SIG_DATE, stop=94, target=120, ohlcv=df, cost_bps=0, max_hold_bars=2
    )
    assert r is not None
    assert r.status == "time_exit"
    assert r.bars_held == 2
    assert r.exit_price == 102.0  # close of the 2nd held bar


def test_still_open_when_no_exit_yet():
    df = _ohlcv([(100, 101, 99, 100), (100, 103, 98, 102)])  # only the entry bar so far
    r = resolve_outcome(signal_date=SIG_DATE, stop=94, target=120, ohlcv=df, cost_bps=0)
    assert r is not None
    assert r.status == "open"
    assert r.realized_r is None
    assert r.bars_held == 1
    assert r.mfe > 0


def test_none_when_not_entered_yet():
    df = _ohlcv([(100, 101, 99, 100)])  # only the signal-date bar, no next bar
    assert resolve_outcome(signal_date=SIG_DATE, stop=94, target=112, ohlcv=df, cost_bps=0) is None


# ── DB integration ───────────────────────────────────────────────────────────

class _FakeLoader:
    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data

    def get_ohlcv(self, symbol, start, end, *, asof=None, offline=False):
        return self._data[symbol]


def _engine_sig(symbol: str) -> EngineSignal:
    return EngineSignal(
        ticker=symbol, signal_date=SIG_DATE, direction="LONG",
        conviction_score=80.0, conviction_tier="High", reference_price=100.0,
        entry_zone_low=99.0, entry_zone_high=100.0, stop_price=94.0, target_price=112.0,
        reward_risk=2.0, atr=3.0, suggested_shares=1.0, suggested_risk_pct=0.01, rank=1,
    )


def test_run_tracker_updates_open_signal(tmp_path):
    settings = load_settings()
    settings.exits.mode = "legacy"  # asserts the legacy full-target-exit outcome
    settings.run.db_url = f"sqlite:///{tmp_path}/t.db"
    eng = make_engine(settings.run.db_url)
    with session_scope(eng) as s:
        run = create_run(s, run_ts=datetime(2024, 1, 8, 17), trading_day=SIG_DATE, status="success")
        save_signals(s, run, [_engine_sig("AAPL")], created_at=datetime(2024, 1, 8, 17))

    fake = _FakeLoader(
        {"AAPL": _ohlcv([(100, 101, 99, 100), (100, 105, 98, 103), (103, 113, 102, 112)])}
    )
    rc = run_tracker(settings, load_secrets(), today=date(2024, 1, 12), offline=True, loader=fake)
    assert rc == 0

    with session_scope(eng) as s:
        sig = s.scalars(select(Signal)).one()
        assert sig.outcome is not None
        assert sig.outcome.status == "target_hit"
        assert sig.outcome.realized_r is not None
