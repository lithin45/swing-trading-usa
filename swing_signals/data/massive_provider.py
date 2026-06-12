"""Massive (formerly Polygon.io) price provider — last-resort LIVE fallback.

Institutional-grade API; the free tier serves 2 years of daily aggregates at
5 requests/minute, and a hard 403 for anything deeper — which makes it
self-limiting to the live path (lookback ~400 days) while deep backtest
refills fall through to providers with full history.

ADJUSTMENT CAVEAT, stated loudly: ``adjusted=true`` here means SPLIT-adjusted
only. The rest of the chain (alpaca ALL / yfinance auto_adjust / tiingo adj*)
is split+dividend adjusted, so Massive bars diverge from chain convention by
the dividend back-adjustment (~1-2%/yr on older bars in the window). That is
acceptable for a LAST-RESORT fallback — the alternative is no data at all,
the same philosophy as the stale-cache fallback — but this provider must stay
BEHIND the total-return sources in ``provider_order`` and must never be the
source of long backtest history (the 2-year 403 enforces that structurally).

Standout future use (not yet wired): the grouped-daily endpoint returns the
ENTIRE US market's daily bars in one call (verified: 12,262 tickers) — the
550-symbol daily cache refresh could become a single request per session.
"""

from __future__ import annotations

import logging

import pandas as pd
import requests

from .normalize import normalize_ohlcv
from .retry import PermanentDataError, TransientDataError, classify_http, with_retry

log = logging.getLogger("swing_signals.data")


class MassiveProvider:
    name = "massive"
    BASE_URL = "https://api.polygon.io"  # legacy domain still canonical post-rebrand

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @with_retry(attempts=3, base=2.0, cap=30.0)
    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        if not self.api_key:
            raise PermanentDataError("massive: no API key (set SWING_MASSIVE_API_KEY)")
        resp = requests.get(
            f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/range/1/day/{start[:10]}/{end[:10]}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        if resp.status_code == 403:
            # Free tier: requests beyond the 2-year window are refused outright.
            raise PermanentDataError(
                f"massive: plan does not cover [{start[:10]}, {end[:10]}] for {symbol}"
            )
        if resp.status_code == 429:
            raise TransientDataError("massive: rate limited (free tier is 5 req/min)")
        classify_http(resp)
        payload = resp.json()
        rows = payload.get("results") or []
        if not rows:
            raise PermanentDataError(f"massive: no data for {symbol}")

        df = pd.DataFrame(rows)
        if not {"t", "o", "h", "l", "c", "v"}.issubset(df.columns):
            raise PermanentDataError(f"massive: unexpected response shape for {symbol}")
        df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                                "c": "close", "v": "volume"})
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
        return normalize_ohlcv(df.set_index("date")[
            ["open", "high", "low", "close", "volume"]
        ])
