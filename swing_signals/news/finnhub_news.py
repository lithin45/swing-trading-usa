"""Finnhub company-news provider (free tier: 60 req/min, no card).

``/company-news?symbol=&from=&to=&token=`` returns recent headlines tagged to the
ticker. Free and generous — the default news source.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from .base import NewsItem, http_json

log = logging.getLogger("swing_signals.news")

_URL = "https://finnhub.io/api/v1/company-news"


class FinnhubNews:
    name = "finnhub"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def get_news(self, symbol: str, start: date, end: date) -> list[NewsItem]:
        if not self.api_key:
            return []
        # Key in the header, not the query string: exception messages embed the URL,
        # and those get retried/logged — never give them a secret to carry.
        rows = http_json(
            _URL,
            params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()},
            headers={"X-Finnhub-Token": self.api_key},
        )
        items: list[NewsItem] = []
        for r in rows or []:
            ts = r.get("datetime")
            published = datetime.fromtimestamp(ts) if ts else None
            headline = (r.get("headline") or "").strip()
            url = r.get("url") or ""
            if not headline or not url:
                continue
            items.append(NewsItem(
                symbol=symbol, headline=headline, url=url,
                source=r.get("source") or "finnhub", published_at=published,
                summary=(r.get("summary") or None),
            ))
        return items
