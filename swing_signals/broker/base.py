"""Broker abstraction: provider-neutral DTOs + the ``BrokerClient`` Protocol.

The entry/exit/gating logic depends only on these thin dataclasses — never on the
``alpaca`` SDK — so the trade engine is unit-tested against a fake broker and the
real Alpaca client (``alpaca_client``) is the only place the SDK is imported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class BrokerError(Exception):
    """A broker call failed (auth, rate limit, rejected order)."""


class BrokerDisabledError(BrokerError):
    """A submit was attempted while the broker is disabled (no keys / not enabled)."""


@dataclass(frozen=True)
class BrokerAccount:
    equity: float
    cash: float
    buying_power: float
    daytrade_count: int = 0
    account_blocked: bool = False
    trading_blocked: bool = False


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    unrealized_pl: float
    current_price: float


# Alpaca order statuses grouped into the three states our logic cares about.
_OPEN_STATUSES = frozenset(
    {"new", "accepted", "pending_new", "partially_filled", "held",
     "accepted_for_bidding", "pending_replace", "replaced", "calculated"}
)
_DEAD_STATUSES = frozenset(
    {"canceled", "expired", "rejected", "done_for_day", "stopped", "suspended"}
)


@dataclass(frozen=True)
class BrokerOrder:
    id: str
    client_order_id: str
    symbol: str
    side: str  # buy | sell
    type: str  # market | limit | stop | stop_limit
    status: str
    qty: float | None
    notional: float | None
    limit_price: float | None
    stop_price: float | None
    filled_qty: float
    filled_avg_price: float | None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None

    @property
    def is_filled(self) -> bool:
        return self.status == "filled"

    @property
    def is_open(self) -> bool:
        return self.status in _OPEN_STATUSES

    @property
    def is_dead(self) -> bool:
        return self.status in _DEAD_STATUSES


@runtime_checkable
class BrokerClient(Protocol):
    """The contract entries/manage/gates depend on (the fake broker in tests matches it)."""

    name: str
    enabled: bool

    def get_account(self) -> BrokerAccount: ...
    def list_positions(self) -> list[BrokerPosition]: ...
    def get_position(self, symbol: str) -> BrokerPosition | None: ...
    def list_open_orders(self) -> list[BrokerOrder]: ...
    def get_order_by_id(self, order_id: str) -> BrokerOrder | None: ...
    def submit_limit_buy(
        self, symbol: str, *, qty: float, limit_price: float, client_order_id: str
    ) -> BrokerOrder: ...
    def submit_market_buy(
        self, symbol: str, *, qty: float, client_order_id: str
    ) -> BrokerOrder: ...
    def submit_sell(
        self, symbol: str, *, qty: float, order_type: str = "market",
        limit_price: float | None = None, stop_price: float | None = None,
        client_order_id: str,
    ) -> BrokerOrder: ...
    def cancel_order(self, order_id: str) -> None: ...
    def get_latest_price(self, symbol: str) -> float | None: ...
