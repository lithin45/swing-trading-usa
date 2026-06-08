"""Alpaca price provider (preferred when keys are present).

Pulls split/dividend-adjusted daily bars from Alpaca's official market-data API —
far more stable than yfinance (a real API, not screen-scraping), so it sits first
in ``data.provider_order``. The free plan serves the **IEX** feed, which is
adequate for daily OHLCV on the liquid names this system trades; yfinance/Stooq
remain fallbacks for anything Alpaca can't serve (and for deep backtest history).

``alpaca`` is imported lazily so the package still imports without the optional
``broker`` extra installed.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from .normalize import normalize_ohlcv
from .retry import PermanentDataError, TransientDataError, with_retry

log = logging.getLogger("swing_signals.data")


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, api_key: str | None = None, secret_key: str | None = None) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self._client = None  # lazily constructed on first use

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _get_client(self):
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            self._client = StockHistoricalDataClient(self.api_key, self.secret_key)
        return self._client

    @with_retry(attempts=3, base=0.5, cap=8.0)
    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.available:
            raise PermanentDataError(
                "alpaca: no API keys (set SWING_ALPACA_API_KEY / SWING_ALPACA_SECRET_KEY)"
            )
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.fromisoformat(start),
            end=datetime.fromisoformat(end),
            feed=DataFeed.IEX,  # free feed; SIP requires a paid subscription
            adjustment=Adjustment.ALL,  # split + dividend adjusted (matches yfinance auto_adjust)
        )
        try:
            bars = self._get_client().get_stock_bars(req)
        except (TransientDataError, PermanentDataError):
            raise
        except Exception as exc:  # noqa: BLE001 - classify Alpaca's APIError by message
            msg = str(exc)
            if "429" in msg or "rate limit" in msg.lower():
                raise TransientDataError(f"alpaca: {msg}") from exc
            raise PermanentDataError(f"alpaca: {msg}") from exc

        df = getattr(bars, "df", None)
        if df is None or len(df) == 0:
            raise PermanentDataError(f"alpaca: no data for {symbol}")
        # bars.df is a MultiIndex (symbol, timestamp); drop the symbol level to a DatetimeIndex.
        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)
        return normalize_ohlcv(df)
