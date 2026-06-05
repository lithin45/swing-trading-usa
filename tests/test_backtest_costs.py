"""CostModel: per-side spread, round-trip, entry > open, exit < price."""

from __future__ import annotations

from swing_signals.backtest.costs import CostModel


def test_round_trip_bps():
    m = CostModel(per_side_bps=10.0)
    assert m.round_trip_bps() == 20.0


def test_entry_above_open():
    m = CostModel(per_side_bps=10.0)
    fill = m.fill_long_entry(100.0)
    assert fill > 100.0
    assert abs(fill - 100.10) < 1e-9


def test_exit_below_price():
    m = CostModel(per_side_bps=10.0)
    fill = m.fill_exit(100.0)
    assert fill < 100.0
    assert abs(fill - 99.90) < 1e-9


def test_zero_cost_is_identity():
    m = CostModel(per_side_bps=0.0)
    assert m.fill_long_entry(50.0) == 50.0
    assert m.fill_exit(50.0) == 50.0


def test_round_trip_cost_magnitude():
    """Round-trip on a $100 stock should cost ≈ $0.20 at 10 bps/side."""
    m = CostModel(per_side_bps=10.0)
    entry = m.fill_long_entry(100.0)
    exit_ = m.fill_exit(100.0)  # assume flat trade
    round_trip_cost = entry - exit_
    assert abs(round_trip_cost - 0.20) < 0.001
