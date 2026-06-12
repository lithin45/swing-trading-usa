"""Cost-model stress knobs: defaults are bit-identical to the historical flat
model; multipliers bind only the fills they name (stop exits, market entries)."""

from __future__ import annotations

from swing_signals.backtest.costs import CostModel
from swing_signals.backtest.metrics import compute_metrics


def test_default_multipliers_are_bit_identical():
    cm = CostModel(per_side_bps=10.0)
    assert cm.fill_long_entry(100.0) == 100.0 * 1.001
    assert cm.fill_long_entry(100.0, market=True) == 100.0 * 1.001
    assert cm.fill_exit(100.0) == 100.0 * 0.999
    assert cm.fill_exit(100.0, reason="stop") == 100.0 * 0.999
    assert cm.fill_exit(100.0, reason="gap_stop") == 100.0 * 0.999


def test_stress_multipliers_bind_only_their_fills():
    cm = CostModel(per_side_bps=10.0, stop_exit_mult=2.0, market_entry_mult=3.0)
    assert cm.fill_long_entry(100.0) == 100.0 * 1.001            # limit: unstressed
    assert cm.fill_long_entry(100.0, market=True) == 100.0 * 1.003
    assert cm.fill_exit(100.0, reason="target") == 100.0 * 0.999  # target: unstressed
    assert cm.fill_exit(100.0, reason="time_stop") == 100.0 * 0.999
    assert cm.fill_exit(100.0, reason="stop") == 100.0 * 0.998
    assert cm.fill_exit(100.0, reason="gap_stop") == 100.0 * 0.998


def test_observational_metric_blocks_attach_only_when_supplied():
    # Pre-existing consumers of the metrics dict must see exactly the old shape.
    out = compute_metrics([], [100_000.0], 100_000.0, 0)
    assert "exposure" not in out and "fills" not in out and "rejected_shadow" not in out
    out2 = compute_metrics(
        [], [100_000.0], 100_000.0, 0,
        exposure={"avg_open_positions": 0.0},
        fills={"limit": 0, "market": 0},
        rejected_shadow={"n": 0},
    )
    assert out2["exposure"]["avg_open_positions"] == 0.0
    assert out2["fills"]["limit"] == 0
    assert out2["rejected_shadow"]["n"] == 0
