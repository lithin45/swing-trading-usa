"""Position sizing (file 08): equity-driven, rounds down, respects the ceiling."""

from __future__ import annotations

from swing_signals.risk.base import position_size


def test_500_account_fractional_example():
    # File 08 worked example: E=$500, 1% risk, entry 50, stop 47 -> $5 / $3 = 1.67 shares.
    r = position_size(
        equity=500, entry=50, stop=47, risk_pct=0.01, risk_pct_ceiling=0.02, fractional=True
    )
    assert round(r.shares, 2) == 1.67
    assert abs(r.risk_dollars - 5.0) < 1e-9
    assert abs(r.stop_distance - 3.0) < 1e-9


def test_whole_shares_round_down():
    r = position_size(
        equity=500, entry=50, stop=47, risk_pct=0.01, risk_pct_ceiling=0.02, fractional=False
    )
    assert r.shares == 1  # floor(1.67)


def test_invalid_stop_returns_zero():
    r = position_size(equity=500, entry=50, stop=50, risk_pct=0.01, risk_pct_ceiling=0.02)
    assert r.shares == 0


def test_conviction_clamped_to_ceiling():
    # High-conviction 3x would be 3% but the 2% ceiling binds.
    r = position_size(
        equity=1000,
        entry=100,
        stop=90,
        risk_pct=0.01,
        risk_pct_ceiling=0.02,
        conviction_mult=3.0,
    )
    assert abs(r.risk_pct - 0.02) < 1e-9


def test_notional_cap_clamps_low_vol_name():
    # 1% risk with a 2% stop wants $50k (half the account); the 20% cap bounds it.
    r = position_size(
        equity=100_000.0, entry=100.0, stop=98.0, risk_pct=0.01, risk_pct_ceiling=0.02,
        max_notional_pct=0.20,
    )
    assert r.shares == 200.0
    assert r.notional == 20_000.0
    assert abs(r.risk_pct - 0.004) < 1e-12  # actual risk taken, post-clamp
    assert any("notional" in why for why in r.reasons)


def test_notional_cap_no_op_when_under_cap():
    r = position_size(
        equity=100_000.0, entry=100.0, stop=90.0, risk_pct=0.01, risk_pct_ceiling=0.02,
        max_notional_pct=0.20,
    )
    assert r.shares == 100.0  # $1000 risk / $10 stop
    assert r.notional == 10_000.0
    assert abs(r.risk_pct - 0.01) < 1e-12
