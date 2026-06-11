"""Overfitting controls: PSR/DSR math, CSCV PBO, trial ledger, halt replay, bar guard."""

from __future__ import annotations

import math
import random
from datetime import date

import pytest

from swing_signals.backtest.overfitting import (
    cscv_pbo,
    deflated_sharpe,
    expected_max_sharpe,
    norm_cdf,
    norm_ppf,
    probabilistic_sharpe,
)
from swing_signals.backtest.trials import Trial, append_trial, ledger_counts, load_trials

# ---------------------------------------------------------------------------
# Normal CDF / PPF
# ---------------------------------------------------------------------------

def test_norm_ppf_matches_known_quantiles():
    assert norm_ppf(0.5) == pytest.approx(0.0, abs=1e-9)
    assert norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-4)
    assert norm_ppf(0.025) == pytest.approx(-1.959964, abs=1e-4)
    assert norm_ppf(0.99) == pytest.approx(2.326348, abs=1e-4)
    # round-trips through the CDF
    for p in (0.001, 0.1, 0.42, 0.9, 0.9999):
        assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-7)


def test_norm_ppf_rejects_bounds():
    for bad in (0.0, 1.0, -0.1, 1.1):
        with pytest.raises(ValueError):
            norm_ppf(bad)


# ---------------------------------------------------------------------------
# PSR / expected max / DSR
# ---------------------------------------------------------------------------

def test_psr_normal_returns_reduce_to_textbook_form():
    # With skew 0 / kurt 3 the denominator is sqrt(1 + SR^2/2); check vs direct formula.
    sr, t = 0.1, 253
    expected = norm_cdf(sr * math.sqrt(t - 1) / math.sqrt(1 + sr * sr / 2))
    assert probabilistic_sharpe(sr, 0.0, t, 0.0, 3.0) == pytest.approx(expected, abs=1e-12)
    # Positive SR over a long track => high confidence vs zero.
    assert probabilistic_sharpe(0.1, 0.0, 2520, 0.0, 3.0) > 0.99


def test_psr_punishes_bad_moments():
    base = probabilistic_sharpe(0.1, 0.0, 253, skew=0.0, kurt=3.0)
    skewed = probabilistic_sharpe(0.1, 0.0, 253, skew=-1.5, kurt=8.0)
    assert skewed < base  # left tail + fat tails => less confidence, never more


def test_expected_max_sharpe_grows_with_trials_and_variance():
    assert expected_max_sharpe(1, 0.01) == 0.0  # one trial = no selection
    e10 = expected_max_sharpe(10, 0.01)
    e100 = expected_max_sharpe(100, 0.01)
    assert 0 < e10 < e100
    assert expected_max_sharpe(10, 0.04) == pytest.approx(2 * e10, rel=1e-9)  # ∝ √var
    # Hand check: N=10, var=0.01 → ≈ 0.1·(0.4228·1.2816 + 0.5772·1.7892) ≈ 0.157
    assert e10 == pytest.approx(0.157, abs=0.005)


def test_deflated_sharpe_deflates():
    rng = random.Random(7)
    # ~0.08/period true SR over 500 obs
    rets = [0.0008 + rng.gauss(0, 0.01) for _ in range(500)]
    one = deflated_sharpe(rets, n_trials=1, var_sr_trials=0.0)
    many = deflated_sharpe(rets, n_trials=50, var_sr_trials=0.005)
    assert one.dsr == pytest.approx(one.psr_vs_zero)  # no selection => no deflation
    assert many.sr_benchmark > 0
    assert many.dsr < one.dsr  # 50 trials must cost confidence


# ---------------------------------------------------------------------------
# CSCV PBO
# ---------------------------------------------------------------------------

def test_pbo_low_for_genuine_persistent_skill():
    rng = random.Random(3)
    t, n = 240, 8
    matrix = []
    for _ in range(t):
        row = [rng.gauss(0.0, 0.01) for _ in range(n)]
        row[0] += 0.004  # trial 0 has real edge in EVERY period
        matrix.append(row)
    res = cscv_pbo(matrix, n_blocks=8)
    assert res.n_splits == 70  # C(8,4)
    assert res.pbo < 0.2


def test_pbo_high_for_pure_inversion():
    # Two trials, anti-symmetric by half: the IS winner is ALWAYS the OOS loser.
    t = 80
    matrix = []
    for i in range(t):
        a = 0.01 if i < t // 2 else -0.01
        matrix.append([a, -a])
    # Use 2 blocks => 2 splits, each picks the IS winner that loses OOS.
    res = cscv_pbo(matrix, n_blocks=2)
    assert res.pbo == 1.0


def test_pbo_near_half_for_noise():
    rng = random.Random(11)
    matrix = [[rng.gauss(0, 0.01) for _ in range(10)] for _ in range(240)]
    res = cscv_pbo(matrix, n_blocks=8)
    assert 0.2 <= res.pbo <= 0.8  # skill-less => no systematic OOS persistence


def test_pbo_input_validation():
    with pytest.raises(ValueError):
        cscv_pbo([], n_blocks=8)
    with pytest.raises(ValueError):
        cscv_pbo([[0.01]], n_blocks=2)          # one trial
    with pytest.raises(ValueError):
        cscv_pbo([[0.01, 0.0]] * 50, n_blocks=7)  # odd blocks


# ---------------------------------------------------------------------------
# Trial ledger
# ---------------------------------------------------------------------------

def test_ledger_round_trip_and_duplicate_guard(tmp_path):
    path = tmp_path / "trials.jsonl"
    t1 = Trial(id="t1", date="2026-06-10", window="2022..2024", universe="sp500-pit",
               config="base", purpose="selection", source="test", expectancy_r=-0.1)
    t2 = Trial(id="t2", date="2026-06-10", window="2025..2026", universe="sp500-pit",
               config="combo", purpose="validation", source="test", sharpe_daily=0.05)
    append_trial(t1, path)
    append_trial(t2, path)
    loaded = load_trials(path)
    assert [t.id for t in loaded] == ["t1", "t2"]
    assert loaded[0].expectancy_r == -0.1
    counts = ledger_counts(loaded)
    assert counts["selection"] == 1 and counts["validation"] == 1 and counts["all"] == 2
    with pytest.raises(ValueError):
        append_trial(t1, path)  # duplicate id must not inflate N


def test_seeded_ledger_loads_and_counts():
    trials = load_trials()  # the committed docs/validation/trials.jsonl
    counts = ledger_counts(trials)
    assert counts["selection"] >= 9    # round 1 (7) + round 2 (2)
    assert counts["validation"] >= 5   # 4 holdout looks + the 2017-19 window
    assert len({t.id for t in trials}) == len(trials)  # ids unique


def test_trial_rejects_bad_purpose():
    with pytest.raises(ValueError):
        Trial(id="x", date="d", window="w", universe="u", config="c",
              purpose="tuning", source="s")


# ---------------------------------------------------------------------------
# Loss-halt replay
# ---------------------------------------------------------------------------

def _risk_cfg():
    from swing_signals.config_loader import load_settings
    return load_settings().risk  # 3%/6%/10% halts, 10% derisk, 15% hard halt


def test_halt_state_daily_loss_halts():
    from swing_signals.backtest.runner import halt_state
    days = [date(2024, 6, d) for d in (3, 4, 5)]
    eq = [100_000.0, 100_500.0, 96_000.0]  # -4.5% yesterday vs the day before
    halt, mult, why = halt_state(_risk_cfg(), 100_000.0, eq, days, date(2024, 6, 6))
    assert halt and why == "daily_loss_halt"


def test_halt_state_monthly_loss_halts():
    from swing_signals.backtest.runner import halt_state
    # Slow bleed: ~0.6%/day over 18 sessions never trips daily (3%) or weekly (6%)
    # but passes -10% on the month.
    days, eq = [], []
    v = 100_000.0
    d = date(2024, 5, 31)
    days.append(d)
    eq.append(v)
    cur = date(2024, 6, 3)
    while len(days) < 19:
        if cur.weekday() < 5:
            v *= 0.994
            days.append(cur)
            eq.append(v)
        cur = date.fromordinal(cur.toordinal() + 1)
    halt, mult, why = halt_state(_risk_cfg(), 100_000.0, eq, days, cur)
    assert halt and why == "monthly_loss_halt"


def test_halt_state_drawdown_derisk_halves_size():
    from swing_signals.backtest.runner import halt_state
    # Rally to a 115k peak then bleed ≤2%/day, ≤5.1%/week, monthly still positive —
    # ONLY the -10% drawdown-from-peak rule fires (-11.7%), and it derisks, not halts.
    days = [date(2024, 5, 31)] + [
        date(2024, 6, d) for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17, 18)
    ]
    eq = [100_000.0, 106_000.0, 112_000.0, 115_000.0, 112_800.0, 110_600.0,
          109_000.0, 107_800.0, 106_500.0, 105_600.0, 105_000.0, 103_000.0, 101_500.0]
    halt, mult, why = halt_state(_risk_cfg(), 100_000.0, eq, days, date(2024, 6, 19))
    assert not halt and mult == 0.5 and why == "drawdown_derisk"


def test_halt_state_quiet_curve_no_halt():
    from swing_signals.backtest.runner import halt_state
    days = [date(2024, 6, d) for d in (3, 4, 5)]
    eq = [100_000.0, 100_400.0, 100_900.0]
    halt, mult, why = halt_state(_risk_cfg(), 100_000.0, eq, days, date(2024, 6, 6))
    assert (halt, mult, why) == (False, 1.0, "")


# ---------------------------------------------------------------------------
# Bar-finality guard
# ---------------------------------------------------------------------------

def test_session_still_open_midday(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from swing_signals import main as main_mod

    et = ZoneInfo("America/New_York")
    monday = date(2024, 6, 24)
    monkeypatch.setattr(main_mod, "_now_eastern",
                        lambda: datetime(2024, 6, 24, 13, 30, tzinfo=et))
    assert main_mod.session_still_open(monday) is True
    monkeypatch.setattr(main_mod, "_now_eastern",
                        lambda: datetime(2024, 6, 24, 16, 5, tzinfo=et))
    assert main_mod.session_still_open(monday) is False
    # Running for a PAST date is always final, whatever the clock says.
    monkeypatch.setattr(main_mod, "_now_eastern",
                        lambda: datetime(2024, 6, 25, 10, 0, tzinfo=et))
    assert main_mod.session_still_open(monday) is False


def test_run_refuses_partial_bar(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from swing_signals import main as main_mod
    from swing_signals.config_loader import load_secrets, load_settings

    et = ZoneInfo("America/New_York")
    monkeypatch.setattr(main_mod, "_now_eastern",
                        lambda: datetime(2024, 6, 24, 11, 0, tzinfo=et))
    rc = main_mod.run(settings=load_settings(), secrets=load_secrets(),
                      dry_run=True, today=date(2024, 6, 24))
    assert rc == 2  # refused before touching any data
