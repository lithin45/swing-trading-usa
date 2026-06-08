"""AlpacaBroker disabled-mode contract: reads no-op, submits raise (no network)."""

from __future__ import annotations

import pytest

from swing_signals.broker.alpaca_client import AlpacaBroker
from swing_signals.broker.base import BrokerClient, BrokerDisabledError


def test_disabled_reads_are_safe_noops():
    b = AlpacaBroker(None, None)
    assert not b.enabled
    assert isinstance(b, BrokerClient)  # satisfies the Protocol
    assert b.list_positions() == []
    assert b.list_open_orders() == []
    assert b.get_position("AAPL") is None
    assert b.get_order_by_id("x") is None
    assert b.get_latest_price("AAPL") is None


def test_disabled_submits_raise():
    b = AlpacaBroker(None, None)
    with pytest.raises(BrokerDisabledError):
        b.get_account()
    with pytest.raises(BrokerDisabledError):
        b.submit_market_buy("AAPL", qty=1.0, client_order_id="c")
    with pytest.raises(BrokerDisabledError):
        b.submit_limit_buy("AAPL", qty=1.0, limit_price=100.0, client_order_id="c")
    with pytest.raises(BrokerDisabledError):
        b.submit_sell("AAPL", qty=1.0, client_order_id="c")


def test_enabled_flag_requires_both_keys():
    assert AlpacaBroker("k", "s").enabled
    assert not AlpacaBroker("k", None).enabled
    assert not AlpacaBroker(None, "s").enabled
