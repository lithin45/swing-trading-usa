"""NYSE trading-day gate.

Step 0 of every run: decide whether today is a trading day before doing any work,
so the cloud scheduler can fire generously (e.g. every weekday) while the app
stays correct.

NOTE: Stage 1 ships a *placeholder* weekday check that is NOT holiday- or
half-day-aware. Stage 2 replaces ``is_trading_day`` with ``pandas_market_calendars``
(NYSE holidays + early closes). The signature is stable so nothing downstream
changes.
"""

from __future__ import annotations

from datetime import date


def is_trading_day(d: date) -> bool:
    """PLACEHOLDER: weekday check only (Mon–Fri). Not holiday-aware yet.

    Stage 2 swaps in the real NYSE calendar via pandas_market_calendars.
    """
    return d.weekday() < 5  # 0=Mon .. 4=Fri


def is_holiday_aware() -> bool:
    """Whether the gate currently accounts for market holidays. False until Stage 2."""
    return False
