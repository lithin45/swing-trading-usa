"""Alpha Vantage NEWS_SENTIMENT provider (free: 25 req/day, 5/min).

Returns headlines *with* a per-ticker sentiment score, which we carry through as
``sentiment_hint`` to give Claude a free prior. The daily cap is tiny, so callers
must cache hard (the DB news cache does this).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from .base import NewsItem, http_json

log = logging.getLogger("swing_signals.news")

_URL = "https://www.alphavantage.co/query"


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S")  # e.g. 20240115T093000
    except ValueError:
        return None


class AlphaVantageNews:
    name = "alphavantage"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def get_news(self, symbol: str, start: date, end: date) -> list[NewsItem]:
        if not self.api_key:
            return []
        data = http_json(_URL, params={
            "function": "NEWS_SENTIMENT", "tickers": symbol, "limit": 50,
            "time_from": f"{start.isoformat().replace('-', '')}T0000",
            "apikey": self.api_key,
        })
        feed = (data or {}).get("feed") or []
        items: list[NewsItem] = []
        for r in feed:
            headline = (r.get("title") or "").strip()
            url = r.get("url") or ""
            if not headline or not url:
                continue
            hint = None
            for ts_obj in r.get("ticker_sentiment") or []:
                if ts_obj.get("ticker") == symbol:
                    try:
                        hint = float(ts_obj.get("ticker_sentiment_score"))
                    except (TypeError, ValueError):
                        hint = None
                    break
            items.append(NewsItem(
                symbol=symbol, headline=headline, url=url,
                source=r.get("source") or "alphavantage",
                published_at=_parse_ts(r.get("time_published")),
                summary=(r.get("summary") or None), sentiment_hint=hint,
            ))
        return items
