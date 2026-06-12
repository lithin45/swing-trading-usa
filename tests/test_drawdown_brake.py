"""Non-absorbing drawdown brake: trailing peak + halt-resume ramp.

The original hard halt was an absorbing state (once -15% from the all-time peak,
no new entries ever again — 2017-19 replay: 306/752 days dead). The brake adds
two config knobs, both defaulting to the original behavior:

- ``risk.drawdown_peak_lookback`` (bars): the high-water mark only looks back
  this far, so an ancient peak cannot anchor the halt forever (0 = all-time).
- ``risk.halt_resume_days`` + ``risk.halt_resume_risk_mult``: after that many
  consecutive halted bars, entries re-open at the reduced size (0 = never).

Backtest (runner.halt_state) and live (broker.gates.evaluate_gates) must agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from swing_signals.backtest.runner import halt_state
from swing_signals.broker.base import BrokerAccount
from swing_signals.broker.gates import evaluate_gates
from swing_signals.config_loader import load_settings

TODAY = date(2024, 1, 10)  # a Wednesday


@dataclass
class FakeSnap:
    equity: float
    ts: datetime


def _acct(equity: float) -> BrokerAccount:
    return BrokerAccount(equity=equity, cash=equity, buying_power=equity)


def _quiet_risk_cfg(**overrides):
    """Risk cfg with period loss-halts neutralized so only the drawdown rules fire."""
    s = load_settings()
    s.risk.daily_loss_halt = s.risk.weekly_loss_halt = s.risk.monthly_loss_halt = 0.99
    for k, v in overrides.items():
        setattr(s.risk, k, v)
    return s.risk


def _flat_curve(n: int, level: float, days_start: date) -> tuple[list[float], list[date]]:
    eq = [level] * n
    days = []
    d = days_start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return eq, days


def test_zero_resume_days_is_absorbing():
    # Peak 100k, then flat at 84k for 30 bars: resume_days=0 (the code default,
    # explicit here since settings.yaml now ships the brake) stays halted forever.
    risk = _quiet_risk_cfg(drawdown_peak_lookback=0, halt_resume_days=0)
    eq, days = _flat_curve(30, 84_000.0, date(2024, 1, 2))
    eq[0] = 100_000.0
    halt, mult, why = halt_state(risk, 100_000.0, eq, days, days[-1] + timedelta(days=1))
    assert halt and mult == 0.0 and why == "drawdown_hard_halt"


def test_resume_after_pause_at_reduced_size():
    risk = _quiet_risk_cfg(halt_resume_days=10, halt_resume_risk_mult=0.25)
    eq, days = _flat_curve(30, 84_000.0, date(2024, 1, 2))
    eq[0] = 100_000.0
    halt, mult, why = halt_state(risk, 100_000.0, eq, days, days[-1] + timedelta(days=1))
    assert not halt and mult == 0.25 and why == "drawdown_halt_resumed"


def test_resume_pause_still_halts_early_in_episode():
    risk = _quiet_risk_cfg(halt_resume_days=10, halt_resume_risk_mult=0.25)
    # Only 5 bars below the line so far -> still inside the pause.
    eq, days = _flat_curve(6, 84_000.0, date(2024, 1, 2))
    eq[0] = 100_000.0
    halt, mult, why = halt_state(risk, 100_000.0, eq, days, days[-1] + timedelta(days=1))
    assert halt and why == "drawdown_hard_halt"


def test_trailing_peak_ages_out_old_high():
    # 100k ancient peak, 60 bars at 84k: with a 40-bar trailing peak the high-water
    # mark decays to 84k -> dd 0 -> no halt at all.
    risk = _quiet_risk_cfg(drawdown_peak_lookback=40)
    eq, days = _flat_curve(60, 84_000.0, date(2024, 1, 2))
    eq[0] = 100_000.0
    halt, mult, why = halt_state(risk, 100_000.0, eq, days, days[-1] + timedelta(days=1))
    assert (halt, mult, why) == (False, 1.0, "")


def test_trailing_peak_still_halts_fresh_crash():
    # Fresh -16% two bars ago is inside any sane lookback -> halts.
    risk = _quiet_risk_cfg(drawdown_peak_lookback=40)
    eq, days = _flat_curve(10, 100_000.0, date(2024, 1, 2))
    eq[-2:] = [84_000.0, 84_000.0]
    halt, mult, why = halt_state(risk, 100_000.0, eq, days, days[-1] + timedelta(days=1))
    assert halt and why == "drawdown_hard_halt"


# ---------------------------------------------------------------------------
# Live gates mirror
# ---------------------------------------------------------------------------

def _snaps(levels: list[float], start: date) -> list[FakeSnap]:
    out, d = [], start
    for v in levels:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(FakeSnap(v, datetime(d.year, d.month, d.day, 17)))
        d += timedelta(days=1)
    return out


def test_gates_zero_resume_days_absorbing():
    s = load_settings()
    s.risk.daily_loss_halt = s.risk.weekly_loss_halt = s.risk.monthly_loss_halt = 0.99
    s.risk.drawdown_peak_lookback = 0
    s.risk.halt_resume_days = 0
    snaps = _snaps([100_000.0] + [84_000.0] * 30, date(2023, 11, 1))
    g = evaluate_gates(s, account=_acct(84_000.0), open_trades=[], snapshots=snaps, today=TODAY)
    assert g.halted and "drawdown" in g.halt_reason


def test_gates_resume_after_pause():
    s = load_settings()
    s.risk.daily_loss_halt = s.risk.weekly_loss_halt = s.risk.monthly_loss_halt = 0.99
    s.risk.halt_resume_days = 10
    s.risk.halt_resume_risk_mult = 0.25
    snaps = _snaps([100_000.0] + [84_000.0] * 30, date(2023, 11, 1))
    g = evaluate_gates(s, account=_acct(84_000.0), open_trades=[], snapshots=snaps, today=TODAY)
    assert not g.halted and g.derisk_multiplier == 0.25


def test_gates_trailing_peak_ages_out():
    s = load_settings()
    s.risk.daily_loss_halt = s.risk.weekly_loss_halt = s.risk.monthly_loss_halt = 0.99
    s.risk.drawdown_peak_lookback = 20
    snaps = _snaps([100_000.0] + [84_000.0] * 40, date(2023, 10, 1))
    g = evaluate_gates(s, account=_acct(84_000.0), open_trades=[], snapshots=snaps, today=TODAY)
    assert not g.halted and g.derisk_multiplier == 1.0


# ---------------------------------------------------------------------------
# Tier size multipliers are config-driven
# ---------------------------------------------------------------------------

def test_tier_mults_default_to_original_stack():
    s = load_settings()
    assert (s.scoring.tier_mult_high, s.scoring.tier_mult_medium, s.scoring.tier_mult_low) == (
        1.0, 0.66, 0.33,
    )


def test_tier_mult_reads_config():
    from swing_signals.scoring.engine import _tier_mult
    s = load_settings()
    s.scoring.tier_mult_medium = 1.0
    assert _tier_mult("Medium", s.scoring) == 1.0
    assert _tier_mult("None", s.scoring) == 0.0
