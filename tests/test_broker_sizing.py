"""Broker sizing: fractional suggested_shares -> a submittable Alpaca qty."""

from __future__ import annotations

from swing_signals.broker.sizing import to_alpaca_order_qty


def test_fractional_qty_passthrough():
    r = to_alpaca_order_qty(suggested_shares=1.732, entry_price=100.0, buying_power=1000.0)
    assert r.ok
    assert r.qty == 1.732
    assert r.notional == 173.2


def test_clamped_to_buying_power():
    # wants 5 sh * $100 = $500 but only $200 buying power (cushion 0.98 -> $196 cap)
    r = to_alpaca_order_qty(suggested_shares=5.0, entry_price=100.0, buying_power=200.0)
    assert r.ok
    assert r.qty == round(196.0 / 100.0, 9)  # 1.96
    assert r.notional <= 196.0 + 1e-6


def test_below_min_skips():
    r = to_alpaca_order_qty(
        suggested_shares=0.005, entry_price=100.0, buying_power=1000.0, min_order_usd=1.0
    )  # 0.005 * 100 = $0.50 < $1.00
    assert not r.ok
    assert "below min" in (r.skipped_reason or "")


def test_whole_share_floor():
    r = to_alpaca_order_qty(
        suggested_shares=2.9, entry_price=50.0, buying_power=1000.0, whole_share_only=True
    )
    assert r.qty == 2.0
    assert r.notional == 100.0


def test_whole_share_rounds_to_zero_skips():
    r = to_alpaca_order_qty(
        suggested_shares=0.4, entry_price=50.0, buying_power=1000.0, whole_share_only=True
    )
    assert not r.ok


def test_no_buying_power_skips():
    assert not to_alpaca_order_qty(
        suggested_shares=1.0, entry_price=50.0, buying_power=0.0
    ).ok


def test_nonpositive_inputs_skip():
    assert not to_alpaca_order_qty(suggested_shares=0.0, entry_price=50.0, buying_power=100.0).ok
    assert not to_alpaca_order_qty(suggested_shares=1.0, entry_price=0.0, buying_power=100.0).ok
