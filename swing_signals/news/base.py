"""News types + a tiny HTTP helper shared by the providers.

A ``NewsItem`` is one headline tagged to a ticker. ``http_json`` centralizes the
GET + status-classification + JSON parse so tests can monkeypatch one function
instead of stubbing ``requests`` per provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    headline: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str | None = None
    sentiment_hint: float | None = None  # provider's own score (e.g. Alpha Vantage), if any

    def as_dict(self) -> dict[str, Any]:
        """In-memory payload for SymbolData.news (keeps ``published_at`` as a datetime)."""
        return {
            "symbol": self.symbol,
            "headline": self.headline,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "summary": self.summary,
            "sentiment_hint": self.sentiment_hint,
        }


@runtime_checkable
class NewsProvider(Protocol):
    """A keyed source of headlines for one ticker over a date window."""

    name: str

    @property
    def available(self) -> bool: ...

    def get_news(self, symbol: str, start: date, end: date) -> list[NewsItem]: ...


def http_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> Any:
    """GET ``url`` and return parsed JSON, raising the data-layer error taxonomy on bad status."""
    import requests

    from ..data.retry import classify_http

    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    classify_http(resp)
    return resp.json()
