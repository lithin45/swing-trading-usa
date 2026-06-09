"""AlpacaBroker — the only module that imports the Alpaca trading SDK.

Wraps alpaca-py's ``TradingClient`` (paper) behind the ``BrokerClient`` Protocol.
With no keys it is a safe no-op: reads return empty, submits raise
``BrokerDisabledError`` (callers check ``enabled`` first). Fractional rules are
enforced here — every order is TIF=DAY and there are no brackets/OCO; exits are
managed by the ``manage`` job. ``alpaca`` is imported lazily so the package
imports without the optional ``broker`` extra.
"""

from __future__ import annotations

import logging

from .base import (
    BrokerAccount,
    BrokerDisabledError,
    BrokerError,
    BrokerOrder,
    BrokerPosition,
)

log = logging.getLogger("swing_signals.broker")


def _f(x) -> float | None:
    return None if x is None else float(x)


def _s(x) -> str:
    """Enum/UUID/str -> plain lowercase string (Alpaca enums carry ``.value``)."""
    return str(getattr(x, "value", x))


class AlpacaBroker:
    name = "alpaca"

    def __init__(
        self, api_key: str | None = None, secret_key: str | None = None, *, paper: bool = True
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.enabled = bool(api_key and secret_key)
        self._trading_client = None
        self._data_client = None

    # -- lazy SDK clients ---------------------------------------------------
    def _trading(self):
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient

            self._trading_client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        return self._trading_client

    def _data(self):
        if self._data_client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            self._data_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        return self._data_client

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise BrokerDisabledError("alpaca broker disabled (no API keys)")

    # -- reads (safe no-ops when disabled) ----------------------------------
    def get_account(self) -> BrokerAccount:
        self._require_enabled()
        a = self._trading().get_account()
        return BrokerAccount(
            equity=_f(a.equity) or 0.0,
            cash=_f(a.cash) or 0.0,
            buying_power=_f(a.buying_power) or 0.0,
            daytrade_count=int(a.daytrade_count or 0),
            account_blocked=bool(a.account_blocked),
            trading_blocked=bool(a.trading_blocked),
        )

    def list_positions(self) -> list[BrokerPosition]:
        if not self.enabled:
            return []
        return [self._map_position(p) for p in self._trading().get_all_positions()]

    def get_position(self, symbol: str) -> BrokerPosition | None:
        if not self.enabled:
            return None
        from alpaca.common.exceptions import APIError

        try:
            return self._map_position(self._trading().get_open_position(symbol))
        except APIError:
            return None  # 404 == no open position

    def list_open_orders(self) -> list[BrokerOrder]:
        if not self.enabled:
            return []
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
        return [self._map_order(o) for o in self._trading().get_orders(filter=req)]

    def get_order_by_id(self, order_id: str) -> BrokerOrder | None:
        if not self.enabled:
            return None
        from alpaca.common.exceptions import APIError

        try:
            return self._map_order(self._trading().get_order_by_id(order_id))
        except APIError:
            return None

    # -- submits (raise when disabled) --------------------------------------
    def submit_limit_buy(
        self, symbol: str, *, qty: float, limit_price: float, client_order_id: str
    ) -> BrokerOrder:
        self._require_enabled()
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest

        return self._submit(LimitOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            limit_price=round(float(limit_price), 2), client_order_id=client_order_id,
        ))

    def submit_market_buy(
        self, symbol: str, *, qty: float, client_order_id: str
    ) -> BrokerOrder:
        self._require_enabled()
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        return self._submit(MarketOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        ))

    def submit_bracket_buy(
        self, symbol: str, *, qty: float, limit_price: float | None, take_profit: float,
        stop_loss: float, client_order_id: str, market: bool = False,
    ) -> BrokerOrder:
        """Whole-share entry with server-side take-profit + stop-loss (OCO bracket, GTC)."""
        self._require_enabled()
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        common = dict(
            symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET, client_order_id=client_order_id,
            take_profit=TakeProfitRequest(limit_price=round(float(take_profit), 2)),
            stop_loss=StopLossRequest(stop_price=round(float(stop_loss), 2)),
        )
        if market or limit_price is None:
            return self._submit(MarketOrderRequest(**common))
        return self._submit(LimitOrderRequest(limit_price=round(float(limit_price), 2), **common))

    def replace_stop(self, order_id: str, *, stop_price: float) -> BrokerOrder | None:
        """Trail a bracket's stop-loss leg to a new (higher) stop. None on failure (non-fatal)."""
        self._require_enabled()
        from alpaca.common.exceptions import APIError
        from alpaca.trading.requests import ReplaceOrderRequest

        try:
            order = self._trading().replace_order_by_id(
                order_id, order_data=ReplaceOrderRequest(stop_price=round(float(stop_price), 2))
            )
            return self._map_order(order)
        except APIError as exc:
            log.info("replace_stop %s no-op: %s", order_id, exc)
            return None

    def submit_sell(
        self, symbol: str, *, qty: float, order_type: str = "market",
        limit_price: float | None = None, stop_price: float | None = None,
        client_order_id: str,
    ) -> BrokerOrder:
        self._require_enabled()
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopOrderRequest,
        )

        common = dict(
            symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        if order_type == "limit":
            if limit_price is None:
                raise BrokerError("limit sell requires limit_price")
            px = round(float(limit_price), 2)
            return self._submit(LimitOrderRequest(limit_price=px, **common))
        if order_type == "stop":
            if stop_price is None:
                raise BrokerError("stop sell requires stop_price")
            px = round(float(stop_price), 2)
            return self._submit(StopOrderRequest(stop_price=px, **common))
        return self._submit(MarketOrderRequest(**common))

    def cancel_order(self, order_id: str) -> None:
        self._require_enabled()
        from alpaca.common.exceptions import APIError

        try:
            self._trading().cancel_order_by_id(order_id)
        except APIError as exc:  # already filled/canceled — not fatal
            log.info("cancel_order %s no-op: %s", order_id, exc)

    def get_latest_price(self, symbol: str) -> float | None:
        if not self.enabled:
            return None
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockLatestTradeRequest

        try:
            req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
            resp = self._data().get_stock_latest_trade(req)
            trade = resp.get(symbol)
            return _f(trade.price) if trade is not None else None
        except Exception as exc:  # noqa: BLE001 - price lookup is best-effort
            log.warning("latest price for %s failed: %s", symbol, exc)
            return None

    # -- mapping helpers ----------------------------------------------------
    def _submit(self, req) -> BrokerOrder:
        from alpaca.common.exceptions import APIError

        try:
            return self._map_order(self._trading().submit_order(order_data=req))
        except APIError as exc:
            raise BrokerError(f"alpaca submit failed: {exc}") from exc

    @staticmethod
    def _map_position(p) -> BrokerPosition:
        return BrokerPosition(
            symbol=p.symbol,
            qty=_f(p.qty) or 0.0,
            avg_entry_price=_f(p.avg_entry_price) or 0.0,
            market_value=_f(p.market_value) or 0.0,
            unrealized_pl=_f(p.unrealized_pl) or 0.0,
            current_price=_f(p.current_price) or 0.0,
        )

    @classmethod
    def _map_order(cls, o, *, with_legs: bool = True) -> BrokerOrder:
        legs: tuple = ()
        if with_legs and getattr(o, "legs", None):
            legs = tuple(cls._map_order(leg, with_legs=False) for leg in o.legs)
        return BrokerOrder(
            id=str(o.id),
            client_order_id=o.client_order_id or "",
            symbol=o.symbol,
            side=_s(o.side),
            type=_s(getattr(o, "order_type", None) or getattr(o, "type", None)),
            status=_s(o.status),
            qty=_f(o.qty),
            notional=_f(o.notional),
            limit_price=_f(o.limit_price),
            stop_price=_f(o.stop_price),
            filled_qty=_f(o.filled_qty) or 0.0,
            filled_avg_price=_f(o.filled_avg_price),
            submitted_at=o.submitted_at,
            filled_at=o.filled_at,
            legs=legs,
        )
