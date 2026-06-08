"""Fan out to the available news providers, dedupe, and truncate.

Skips any provider without a key, unions their items, drops duplicates (by URL
then normalized headline), sorts newest-first, and caps the count to bound Claude
token usage. Network failures from one provider never sink the others.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from .alphavantage_news import AlphaVantageNews
from .base import NewsItem, NewsProvider
from .finnhub_news import FinnhubNews
from .sec_edgar import SecEdgarNews

if TYPE_CHECKING:
    from ..config_loader import Secrets

log = logging.getLogger("swing_signals.news")

NEWS_LOOKBACK_DAYS = 7
MAX_ITEMS = 15


def _reveal(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def build_providers(secrets: Secrets) -> list[NewsProvider]:
    """Instantiate the providers whose keys are present (order = source priority)."""
    providers: list[NewsProvider] = [
        FinnhubNews(_reveal(secrets.finnhub_api_key)),
        AlphaVantageNews(_reveal(secrets.alphavantage_api_key)),
        SecEdgarNews(secrets.sec_edgar_user_agent),
    ]
    return [p for p in providers if p.available]


def _key(item: NewsItem) -> str:
    return item.url.strip().lower() or item.headline.strip().lower()


def fetch_news(
    symbol: str,
    asof: date,
    *,
    providers: list[NewsProvider],
    lookback_days: int = NEWS_LOOKBACK_DAYS,
    max_items: int = MAX_ITEMS,
) -> list[NewsItem]:
    """Return up to ``max_items`` recent, deduped NewsItems for ``symbol``."""
    start = asof - timedelta(days=lookback_days)
    seen: set[str] = set()
    out: list[NewsItem] = []
    for provider in providers:
        try:
            items = provider.get_news(symbol, start, asof)
        except Exception as exc:  # noqa: BLE001 - one provider down must not sink the rest
            log.warning("news provider %s failed for %s: %s", provider.name, symbol, exc)
            continue
        for it in items:
            k = _key(it)
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(it)
    out.sort(key=lambda i: i.published_at or datetime.min, reverse=True)
    return out[:max_items]
