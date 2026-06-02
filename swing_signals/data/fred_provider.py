"""FRED provider — macro series + VIX/VIX3M (research files 04, 07).

Free, official, ToS-clean (needs a free ``SWING_FRED_API_KEY``). Pulls Treasury
yields, the yield curve, credit spreads, and the VIX in one place. Degrades
gracefully: with no key it reports ``available == False`` and the market-context
builder records the gap rather than crashing.
"""

from __future__ import annotations

import logging

import pandas as pd

from .retry import PermanentDataError, with_retry

log = logging.getLogger("swing_signals.data")


class FredProvider:
    name = "fred"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _fred(self):
        if self._client is None:
            from fredapi import Fred

            self._client = Fred(api_key=self.api_key)
        return self._client

    @with_retry(attempts=3, base=0.5, cap=8.0)
    def get_series(self, series_id: str) -> pd.Series:
        if not self.api_key:
            raise PermanentDataError("FRED: no API key (set SWING_FRED_API_KEY)")
        return self._fred().get_series(series_id)

    def get_latest(self, series_id: str) -> float | None:
        """Most recent non-NaN value of a series, or None if empty."""
        series = self.get_series(series_id).dropna()
        return float(series.iloc[-1]) if len(series) else None
