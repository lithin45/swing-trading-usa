"""NYSE calendar gate: holidays, weekends, half-days."""

from __future__ import annotations

from datetime import date

from swing_signals.calendar_gate import is_early_close, is_holiday_aware, is_trading_day


def test_is_holiday_aware():
    assert is_holiday_aware() is True


def test_normal_weekday_is_trading():
    assert is_trading_day(date(2024, 1, 8))  # a Monday


def test_weekend_is_not_trading():
    assert not is_trading_day(date(2024, 1, 6))  # Saturday
    assert not is_trading_day(date(2024, 1, 7))  # Sunday


def test_holidays_are_not_trading():
    assert not is_trading_day(date(2024, 1, 1))  # New Year's Day
    assert not is_trading_day(date(2024, 7, 4))  # Independence Day
    assert not is_trading_day(date(2024, 12, 25))  # Christmas


def test_july_3_2024_is_early_close():
    # The day before a weekday July 4 is a NYSE half-day.
    assert is_trading_day(date(2024, 7, 3))
    assert is_early_close(date(2024, 7, 3))


def test_regular_day_is_not_early_close():
    assert not is_early_close(date(2024, 1, 8))


def test_holiday_is_not_early_close():
    assert not is_early_close(date(2024, 7, 4))
