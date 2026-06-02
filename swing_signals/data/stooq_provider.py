"""Stooq price provider (optional free fallback).

Fetches the daily CSV directly (``https://stooq.com/q/d/l/``) — avoids
``pandas_datareader`` (broken on Python 3.12+). As of 2025 Stooq's bulk CSV
download requires a free (captcha-obtained) API key, so this provider is only
usable when ``SWING_STOOQ_API_KEY`` is set; otherwise the loader skips it and
relies on yfinance. Get a key at https://stooq.com/q/d/?s=aapl.us&get_apikey
"""

from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from .normalize import normalize_ohlcv
from .retry import PermanentDataError, classify_http, with_retry

log = logging.getLogger("swing_signals.data")


class StooqProvider:
    name = "stooq"
    BASE_URL = "https://stooq.com/q/d/l/"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @with_retry(attempts=3, base=0.5, cap=8.0)
    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.api_key:
            raise PermanentDataError(
                "stooq: no API key (set SWING_STOOQ_API_KEY); falling back disabled"
            )
        ticker = symbol.lower()
        if "." not in ticker:
            ticker = f"{ticker}.us"  # Stooq US-equity suffix
        params = {
            "s": ticker,
            "i": "d",
            "d1": start.replace("-", ""),
            "d2": end.replace("-", ""),
            "apikey": self.api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=20)
        classify_http(resp)
        text = resp.text or ""
        if "get_apikey" in text or "apikey" in text.split("\n", 1)[0].lower():
            raise PermanentDataError("stooq: API key rejected or required")
        if text.startswith("<") or "No data" in text or not text.strip():
            raise PermanentDataError(f"stooq: no data for {symbol}")
        df = pd.read_csv(io.StringIO(text))
        if "Date" not in df.columns:
            raise PermanentDataError(f"stooq: unexpected response for {symbol}")
        return normalize_ohlcv(df.set_index("Date"))
