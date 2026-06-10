"""Trade budget (mandate §4): monthly ceiling, cooldown, free passes, DB state, cadence."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import RunContext, SymbolData
from swing_signals.market.base import MarketState
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Signal as SignalRow
from swing_signals.persistence.repository import (
    create_run,
    month_emitted_symbols,
    recent_stop_symbols,
    save_signals,
    upsert_outcome,
    upsert_trade,
)
from swing_signals.scoring.budget import BudgetState, build_budget_state
from swing_signals.scoring.engine import Signal as EngineSignal
from swing_signals.scoring.engine import generate_signals

MONDAY = date(2024, 6, 24)
GREEN = MarketState(name="regime", score=100.0, state="GREEN", multiplier=1.0, veto=False)

_UP = np.linspace(50, 150, 260)


def _ohlcv(path: np.ndarray, vol: float = 1_000_000.0) -> pd.DataFrame:
    n = len(path)
    idx = pd.bdate_range(end="2024-06-24", periods=n)
    return pd.DataFrame(
        {"open": path, "high": path + 0.5, "low": path - 0.5, "close": path,
         "volume": np.full(n, vol)},
        index=idx,
    )


def _sd(symbol: str) -> SymbolData:
    return SymbolData(symbol=symbol, ohlcv=_ohlcv(_UP))


def _ctx():
    s = load_settings()
    s.scoring.max_extension_atr = 0.0  # linear-ramp fixture data trips the no-chase gate
    return RunContext(
        settings=s, secrets=load_secrets(), trading_day=MONDAY, equity=s.account.equity
    )


# ---------------------------------------------------------------------------
# Engine enforcement
# ---------------------------------------------------------------------------

def test_budget_exhausted_defers_all_new_names():
    budget = BudgetState(enabled=True, max_entries_per_month=7, charges_used=7)
    result = generate_signals({"AAA": _sd("AAA")}, _ctx(), GREEN, budget=budget)
    assert result.actionable == []
    deferred = [s for s in result.no_trades if "BUDGET_EXHAUSTED" in s.flags]
    assert len(deferred) == 1
    assert "budget exhausted (7/7" in deferred[0].explanation


def test_budget_caps_todays_new_names_to_remaining():
    budget = BudgetState(enabled=True, max_entries_per_month=7, charges_used=6)
    data = {"AAA": _sd("AAA"), "BBB": _sd("BBB")}
    result = generate_signals(data, _ctx(), GREEN, budget=budget)
    assert len(result.actionable) == 1  # only 1 slot left this month
    assert sum(1 for s in result.no_trades if "BUDGET_EXHAUSTED" in s.flags) == 1


def test_held_name_passes_free_and_does_not_count():
    budget = BudgetState(enabled=True, max_entries_per_month=1, charges_used=1,
                         held_symbols=frozenset({"AAA"}))  # remaining = 0, but held
    result = generate_signals({"AAA": _sd("AAA")}, _ctx(), GREEN, budget=budget)
    assert [s.ticker for s in result.actionable] == ["AAA"]  # re-print, not a NEW entry
    assert budget.entries_this_month == 1


def test_closed_name_reentry_charges_again():
    # The 2018-replay leak: stop out -> cooldown lapses -> re-signal. The name is no
    # longer held, so it must charge a NEW slot; with the month spent it is deferred.
    budget = BudgetState(enabled=True, max_entries_per_month=1, charges_used=1,
                         held_symbols=frozenset())  # AAA traded and CLOSED earlier
    result = generate_signals({"AAA": _sd("AAA")}, _ctx(), GREEN, budget=budget)
    assert result.actionable == []
    assert any("BUDGET_EXHAUSTED" in s.flags for s in result.no_trades)


def test_cooldown_blocks_recently_stopped_name():
    budget = BudgetState(enabled=True, cooldown_blocked=frozenset({"AAA"}))
    result = generate_signals({"AAA": _sd("AAA")}, _ctx(), GREEN, budget=budget)
    assert result.actionable == []
    assert any("COOLDOWN" in s.flags for s in result.no_trades)


def test_no_budget_state_means_no_enforcement():
    result = generate_signals({"AAA": _sd("AAA")}, _ctx(), GREEN, budget=None)
    assert len(result.actionable) == 1
    disabled = BudgetState(enabled=False, cooldown_blocked=frozenset({"AAA"}))
    result = generate_signals({"AAA": _sd("AAA")}, _ctx(), GREEN, budget=disabled)
    assert len(result.actionable) == 1


# ---------------------------------------------------------------------------
# DB-backed state builder
# ---------------------------------------------------------------------------

def _persisted_sig(symbol: str, day: date) -> EngineSignal:
    return EngineSignal(
        ticker=symbol, signal_date=day, direction="LONG",
        conviction_score=80.0, conviction_tier="High",
        entry_zone_high=100.0, stop_price=94.0,
    )


def test_build_budget_state_signal_only_fallback(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/sig.db")
    today = date(2024, 6, 24)
    with session_scope(eng) as s:
        run = create_run(s, run_ts=datetime(2024, 6, 3, 17), trading_day=date(2024, 6, 3),
                         status="success")
        # AAA emitted twice this month (distinct => 1), BBB once last month (excluded),
        # CCC emitted TODAY (excluded — same-day re-runs must stay idempotent).
        save_signals(s, run, [_persisted_sig("AAA", date(2024, 6, 3))],
                     created_at=datetime(2024, 6, 3, 17))
        save_signals(s, run, [_persisted_sig("AAA", date(2024, 6, 10))],
                     created_at=datetime(2024, 6, 10, 17))
        save_signals(s, run, [_persisted_sig("BBB", date(2024, 5, 20))],
                     created_at=datetime(2024, 5, 20, 17))
        save_signals(s, run, [_persisted_sig("CCC", today)],
                     created_at=datetime(2024, 6, 24, 17))
    settings = load_settings()
    settings.broker.enabled = False  # signal-only world: fall back to emitted symbols
    with session_scope(eng) as s:
        assert month_emitted_symbols(s, month_of=today, before_day=today) == {"AAA"}
        state = build_budget_state(settings, s, today)
    assert state.enabled
    assert state.charges_used == 1
    assert state.remaining == settings.budget.max_entries_per_month - 1


def test_build_budget_state_broker_mode_counts_trade_rows(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/sig.db")
    today = date(2024, 6, 24)
    now = datetime(2024, 6, 20, 17)
    settings = load_settings()
    assert settings.broker is not None and settings.broker.enabled
    with session_scope(eng) as s:
        # Two entries this month — incl. a re-entry of the SAME name after a close
        # (two rows, two charges: the leak distinct-symbol counting missed) — plus
        # one row from last month (excluded).
        upsert_trade(s, signal_date=date(2024, 6, 4), symbol="AAA", now=now,
                     status="closed", exit_reason="stopped",
                     exit_date=date(2024, 6, 6))
        upsert_trade(s, signal_date=date(2024, 6, 20), symbol="AAA", now=now,
                     status="open")
        upsert_trade(s, signal_date=date(2024, 5, 7), symbol="BBB", now=now,
                     status="closed", exit_reason="target_hit",
                     exit_date=date(2024, 5, 21))
        state = build_budget_state(settings, s, today)
    assert state.charges_used == 2          # both June rows; May excluded
    assert "AAA" in state.held_symbols      # the open re-entry rides free if re-printed


def test_build_budget_state_cooldown_and_held(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/sig.db")
    today = date(2024, 6, 24)
    now = datetime(2024, 6, 20, 17)
    settings = load_settings()
    cool = settings.budget.cooldown_days
    with session_scope(eng) as s:
        # Stopped recently -> in cooldown; stopped long ago -> free.
        upsert_trade(s, signal_date=date(2024, 6, 18), symbol="STOPD", now=now,
                     status="closed", exit_reason="stopped", exit_date=today - timedelta(days=2))
        upsert_trade(s, signal_date=date(2024, 4, 1), symbol="OLDSTOP", now=now,
                     status="closed", exit_reason="stopped",
                     exit_date=today - timedelta(days=cool + 5))
        # In-flight position -> held (free pass, not charged).
        upsert_trade(s, signal_date=date(2024, 5, 28), symbol="HELD", now=now, status="open")
        # Tracker world: a theoretical outcome stopped recently.
        run = create_run(s, run_ts=now, trading_day=date(2024, 6, 19), status="success")
        save_signals(s, run, [_persisted_sig("TRACKSTOP", date(2024, 6, 19))], created_at=now)
        sig_id = s.scalars(
            select(SignalRow.id).where(SignalRow.symbol == "TRACKSTOP")
        ).one()
        upsert_outcome(s, sig_id, status="stopped", updated_at=now,
                       exit_date=today - timedelta(days=1))
    with session_scope(eng) as s:
        since = today - timedelta(days=cool)
        assert recent_stop_symbols(s, since=since) == {"STOPD", "TRACKSTOP"}
        state = build_budget_state(settings, s, today)
    assert state.cooldown_blocked == frozenset({"STOPD", "TRACKSTOP"})
    assert "HELD" in state.held_symbols
    assert not state.charges_budget("HELD")


# ---------------------------------------------------------------------------
# Earnings gate (engine) + calendar provider
# ---------------------------------------------------------------------------

def test_earnings_soon_vetoes_entry():
    sd = _sd("AAA")
    sd.next_earnings = MONDAY + timedelta(days=2)  # inside the default 3-day window
    result = generate_signals({"AAA": sd}, _ctx(), GREEN)
    assert result.actionable == []
    hit = [s for s in result.no_trades if "EARNINGS_SOON" in s.flags]
    assert len(hit) == 1
    assert "earnings" in hit[0].explanation


def test_earnings_far_away_passes():
    sd = _sd("AAA")
    sd.next_earnings = MONDAY + timedelta(days=10)
    result = generate_signals({"AAA": sd}, _ctx(), GREEN)
    assert len(result.actionable) == 1


def test_earnings_gate_disabled_passes():
    sd = _sd("AAA")
    sd.next_earnings = MONDAY + timedelta(days=1)
    ctx = _ctx()
    ctx.settings.earnings.enabled = False
    result = generate_signals({"AAA": sd}, ctx, GREEN)
    assert len(result.actionable) == 1


def test_earnings_calendar_parses_and_memoizes(monkeypatch):
    from swing_signals.data import earnings as mod

    calls = {"n": 0}

    def fake_http_json(url, *, params=None, headers=None, timeout=20.0):
        calls["n"] += 1
        assert headers and "X-Finnhub-Token" in headers  # key never in the URL
        return {"earningsCalendar": [
            {"symbol": "AAPL", "date": "2024-06-25"},
            {"symbol": "aapl", "date": "2024-06-27"},   # later dup — earliest wins
            {"symbol": "MSFT", "date": "2024-07-30"},   # outside window — dropped
            {"symbol": "", "date": "2024-06-25"},        # malformed — dropped
        ]}

    monkeypatch.setattr("swing_signals.news.base.http_json", fake_http_json)
    cal = mod.EarningsCalendar("k")
    out = cal.upcoming(date(2024, 6, 24), date(2024, 6, 28))
    assert out == {"AAPL": date(2024, 6, 25)}
    assert cal.upcoming(date(2024, 6, 24), date(2024, 6, 28)) == out
    assert calls["n"] == 1  # memoized


def test_earnings_calendar_failure_returns_none(monkeypatch):
    from swing_signals.data import earnings as mod

    def boom(url, **kw):
        raise RuntimeError("api down")

    monkeypatch.setattr("swing_signals.news.base.http_json", boom)
    assert mod.EarningsCalendar("k").upcoming(date(2024, 6, 24), date(2024, 6, 28)) is None
    assert not mod.EarningsCalendar(None).available


def test_manage_earnings_exit_window():
    from swing_signals.broker.manage import _earnings_exit_due

    settings = load_settings()
    today = date(2024, 6, 24)
    near = {"AAA": today + timedelta(days=settings.earnings.veto_days_before)}
    far = {"AAA": today + timedelta(days=settings.earnings.veto_days_before + 1)}
    past = {"AAA": today - timedelta(days=1)}
    assert _earnings_exit_due(settings, near, "AAA", today)
    assert not _earnings_exit_due(settings, far, "AAA", today)
    assert not _earnings_exit_due(settings, past, "AAA", today)   # print already happened
    assert not _earnings_exit_due(settings, None, "AAA", today)   # unscreened
    assert not _earnings_exit_due(settings, near, "BBB", today)   # no print scheduled
