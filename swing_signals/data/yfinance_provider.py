"""yfinance price provider (primary, free).

Pulls split/dividend-adjusted daily OHLCV from Yahoo Finance. Unofficial and
brittle by nature (scrapes Yahoo) — hence the retry wrapper, the cache, and the
Stooq fallback in the loader. yfinance is imported lazily so the package imports
without the optional ``data`` extra installed.
"""

from __future__ import annotations

import logging

import pandas as pd

from .normalize import normalize_ohlcv
from .retry import PermanentDataError, with_retry

log = logging.getLogger("swing_signals.data")


class YfinanceProvider:
    name = "yfinance"

    @with_retry(attempts=3, base=0.5, cap=8.0)
    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        import yfinance as yf

        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if df is None or df.empty:
            raise PermanentDataError(f"yfinance: no data for {symbol}")
        return normalize_ohlcv(df)
