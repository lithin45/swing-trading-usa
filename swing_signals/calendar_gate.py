"""NYSE trading-day gate (Step 0 of every run).

Decides whether today is a trading day before doing any work, so the cloud
scheduler can fire generously (e.g. every weekday in UTC) while the app stays
correct. Backed by ``pandas_market_calendars`` (NYSE holidays + early closes).
"""

from __future__ import annotations

import functools
from datetime import date

import pandas_market_calendars as mcal

_CALENDAR = "NYSE"


@functools.lru_cache(maxsize=1)
def _nyse():
    return mcal.get_calendar(_CALENDAR)


def is_trading_day(d: date) -> bool:
    """True if ``d`` is a regular NYSE trading day (holiday- and weekend-aware)."""
    iso = d.isoformat()
    return len(_nyse().valid_days(start_date=iso, end_date=iso)) > 0


def is_early_close(d: date) -> bool:
    """True if ``d`` is a NYSE half-day (early close), e.g. the day before July 4."""
    if not is_trading_day(d):
        return False
    cal = _nyse()
    iso = d.isoformat()
    schedule = cal.schedule(start_date=iso, end_date=iso)
    if schedule.empty:
        return False
    return not cal.early_closes(schedule).empty


def is_holiday_aware() -> bool:
    """Whether the gate accounts for market holidays. True since Stage 2."""
    return True
