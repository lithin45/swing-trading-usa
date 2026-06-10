"""Volatility-scaled sizing multiplier."""

from __future__ import annotations

from swing_signals.risk.vol_sizing import vol_scalar


def test_full_size_at_target_vol():
    assert vol_scalar(atr_pct=2.5, vol_target_atr_pct=2.5) == 1.0


def test_high_vol_name_sized_down():
    # ~2x the target vol -> ~half size.
    assert vol_scalar(atr_pct=5.0, vol_target_atr_pct=2.5) == 0.5


def test_low_vol_name_never_upsized():
    # Below target -> would be >1, but capped at scalar_max.
    assert vol_scalar(atr_pct=1.0, vol_target_atr_pct=2.5) == 1.0


def test_floor_applies():
    # Extremely volatile -> clamped to the floor.
    assert vol_scalar(atr_pct=20.0, vol_target_atr_pct=2.5, scalar_min=0.4) == 0.4


def test_stressed_market_scales_everyone_down():
    # At-target name but a stressed market (vol score 0) -> half.
    assert vol_scalar(atr_pct=2.5, vol_target_atr_pct=2.5, market_vol_score=0.0) == 0.5
    # Calm market (score 100) -> unchanged.
    assert vol_scalar(atr_pct=2.5, vol_target_atr_pct=2.5, market_vol_score=100.0) == 1.0


def test_missing_atr_pct_defaults_to_full():
    assert vol_scalar(atr_pct=None, vol_target_atr_pct=2.5) == 1.0
