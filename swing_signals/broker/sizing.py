"""Translate the engine's fractional ``suggested_shares`` into an Alpaca order qty.

The scoring engine already did the risk math (``risk/base.py:position_size``) and
stored a fractional share count sized off *configured* equity. Here we only adapt
that to a submittable Alpaca quantity: honor whole-share mode, clamp to *live*
buying power (configured equity drifts from the paper account), and skip orders
below Alpaca's fractional minimum. Alpaca accepts fractional ``qty`` to 9 dp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderQty:
    qty: float | None
    notional: float | None
    skipped_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.skipped_reason is None and bool(self.qty)


def to_alpaca_order_qty(
    *,
    suggested_shares: float,
    entry_price: float,
    buying_power: float,
    min_order_usd: float = 1.0,
    whole_share_only: bool = False,
    buying_power_cushion: float = 0.98,
) -> OrderQty:
    """Return a submittable ``qty`` (+ its notional), or a skip reason.

    Clamps to ``buying_power * cushion`` so Alpaca never rejects for insufficient funds, then
    enforces the ``min_order_usd`` floor. ``whole_share_only`` floors to an integer count.
    """
    if suggested_shares <= 0 or entry_price <= 0:
        return OrderQty(None, None, "non-positive size or price")

    shares = math.floor(suggested_shares) if whole_share_only else suggested_shares
    if shares <= 0:
        return OrderQty(None, None, "rounds to 0 whole shares at this equity/price")

    max_notional = buying_power * buying_power_cushion
    if max_notional <= 0:
        return OrderQty(None, None, "no buying power")

    notional = shares * entry_price
    if notional > max_notional:  # engine sized off configured equity; clamp to live funds
        shares = max_notional / entry_price
        if whole_share_only:
            shares = math.floor(shares)
        if shares <= 0:
            return OrderQty(None, None, "buying power below one share")
        notional = shares * entry_price

    if notional < min_order_usd:
        return OrderQty(None, None, f"notional ${notional:.2f} below min ${min_order_usd:.2f}")

    return OrderQty(qty=float(round(shares, 9)), notional=round(notional, 2))
