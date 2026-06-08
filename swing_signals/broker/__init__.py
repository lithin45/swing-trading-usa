"""Automated paper-trading execution (Stage 8).

Turns persisted signals into Alpaca **paper** orders and self-manages exits. Every
piece is opt-in (``settings.broker.enabled`` + Alpaca keys); with the broker off
or keys absent the package is inert and the system stays signal-only.

Layers:
- ``base``: provider-neutral DTOs + the ``BrokerClient`` Protocol (so logic is
  testable against a fake broker; only ``alpaca_client`` imports the SDK).
- ``alpaca_client``: ``AlpacaBroker`` — the real Alpaca wrapper.
- ``sizing``: fractional ``suggested_shares`` -> an Alpaca order quantity.
- ``gates``: pre-trade risk gates (heat, max positions, loss-halts, drawdown).
- ``entries`` / ``manage``: submit limit-in-zone entries; reconcile + exit.
- ``run``: ``run_trade`` / ``run_manage`` orchestrators the CLI calls.
"""

from __future__ import annotations
