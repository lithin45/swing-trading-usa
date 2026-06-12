"""Tiingo price provider (optional, key-gated fallback).

A real JSON API with 30+ years of split/dividend-adjusted daily history and —
unlike every other free source in the chain — coverage of many DELISTED
tickers, which makes it the first dent in the survivorship residual (84 dead
union members as of the 2026-06 refill). The free tier caps unique symbols per
month, so it sits BEHIND alpaca/yfinance in ``provider_order``: it only sees
the symbols the primaries fail on, plus targeted recovery jobs.

Key in the ``Authorization: Token`` header, never the URL (exception messages
embed URLs and get logged). Get a key at https://www.tiingo.com/account/api/token
"""

from __future__ import annotations

import logging

import pandas as pd
import requests

from .normalize import normalize_ohlcv
from .retry import PermanentDataError, classify_http, with_retry

log = logging.getLogger("swing_signals.data")


class TiingoProvider:
    name = "tiingo"
    BASE_URL = "https://api.tiingo.com/tiingo/daily"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @with_retry(attempts=3, base=1.0, cap=30.0)
    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.api_key:
            raise PermanentDataError("tiingo: no API key (set SWING_TIINGO_API_KEY)")
        resp = requests.get(
            f"{self.BASE_URL}/{symbol}/prices",
            params={"startDate": start[:10], "endDate": end[:10], "format": "json"},
            headers={"Authorization": f"Token {self.api_key}",
                     "Content-Type": "application/json"},
            timeout=20,
        )
        if resp.status_code == 404:
            raise PermanentDataError(f"tiingo: unknown ticker {symbol}")
        classify_http(resp)
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            raise PermanentDataError(f"tiingo: no data for {symbol}")

        df = pd.DataFrame(rows)
        # Tiingo serves raw AND adjusted fields; keep the adjusted set to match
        # the rest of the chain (alpaca Adjustment.ALL / yfinance auto_adjust).
        needed = {"date", "adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume"}
        if not needed.issubset(df.columns):
            raise PermanentDataError(f"tiingo: unexpected response shape for {symbol}")
        df = df[list(needed)].rename(columns={
            "adjOpen": "open", "adjHigh": "high", "adjLow": "low",
            "adjClose": "close", "adjVolume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
        return normalize_ohlcv(df.set_index("date"))
