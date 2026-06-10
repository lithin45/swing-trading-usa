"""Pure exit-decision logic — legacy parity + staged partial/trail/stagnation."""

from __future__ import annotations

from types import SimpleNamespace

from swing_signals.exits import ExitRules, build_rules, decide_exit

LEGACY = ExitRules.legacy(20)
STAGED = ExitRules.staged(
    SimpleNamespace(
        partial_take_frac=0.5, move_stop_to="breakeven",
        stagnation_bars=15, stagnation_min_r=1.0, hard_backstop_bars=60,
    )
)


def _d(rules, **kw):
    base = dict(
        entry_fill=100.0, risk_per_share=5.0, effective_stop=95.0, target_1=110.0,
        partial_done=False, bars_held=1,
        bar_open=101.0, bar_high=102.0, bar_low=99.0, bar_close=101.0, rules=rules,
    )
    base.update(kw)
    return decide_exit(**base)


def test_stop_hit_fills_at_stop():
    a = _d(LEGACY, bar_low=94.0)
    assert a[0].kind == "EXIT_ALL" and a[0].reason == "stop" and a[0].price == 95.0


def test_gap_through_stop_fills_at_open():
    a = _d(LEGACY, bar_open=92.0, bar_low=90.0)
    assert a[0].reason == "gap_stop" and a[0].price == 92.0


def test_stop_checked_before_target():
    # Bar touches both the stop and the target — stop wins.
    a = _d(LEGACY, bar_low=94.0, bar_high=111.0)
    assert a[0].reason == "stop"


def test_legacy_full_exit_at_target():
    a = _d(LEGACY, bar_high=111.0)
    assert len(a) == 1 and a[0].kind == "EXIT_ALL"
    assert a[0].reason == "target" and a[0].price == 110.0


def test_legacy_hard_time_stop():
    a = _d(LEGACY, bars_held=20)
    assert a[0].kind == "EXIT_ALL" and a[0].reason == "time_stop"


def test_staged_scales_partial_and_moves_to_breakeven():
    a = _d(STAGED, bar_high=111.0)
    scale = next(x for x in a if x.kind == "SCALE_OUT")
    move = next(x for x in a if x.kind == "MOVE_STOP")
    assert scale.fraction == 0.5 and scale.price == 110.0
    assert move.price == 100.0  # breakeven = entry_fill


def test_staged_lets_a_working_winner_run():
    # Already scaled, up +2R, 30 bars held, backstop (60) not reached -> ride the trail.
    a = _d(STAGED, partial_done=True, bars_held=30, bar_high=109.0, bar_close=110.0)
    assert a == []


def test_staged_cuts_a_stagnant_trade():
    # Not working (0R < 1R) after 15 bars -> stagnation cut.
    a = _d(STAGED, bars_held=15, bar_high=101.0, bar_close=100.0)
    assert a[0].reason == "time_stop_stagnant"


def test_staged_does_not_cut_a_working_trade_at_stagnation_bars():
    # Up +1.4R at 15 bars -> "working", not cut.
    a = _d(STAGED, bars_held=15, bar_high=108.0, bar_close=107.0)
    assert a == []


def test_staged_hard_backstop_closes_even_a_winner():
    a = _d(STAGED, partial_done=True, bars_held=60, bar_high=109.0, bar_close=108.0)
    assert a[0].kind == "EXIT_ALL" and a[0].reason == "time_stop"


def test_build_rules_selects_mode():
    legacy_settings = SimpleNamespace(exits=SimpleNamespace(mode="legacy"))
    staged_settings = SimpleNamespace(
        exits=SimpleNamespace(
            mode="staged", partial_take_frac=0.5, move_stop_to="breakeven",
            stagnation_bars=15, stagnation_min_r=1.0, hard_backstop_bars=60,
        )
    )
    assert build_rules(legacy_settings, 20).partial_take_frac == 1.0
    assert build_rules(staged_settings, 20).takes_partial is True
    # Missing exits block -> legacy fallback.
    assert build_rules(SimpleNamespace(), 20).partial_take_frac == 1.0
