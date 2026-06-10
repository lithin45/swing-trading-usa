"""Market-wide news discovery -> trending tickers (best-effort, key-gated).

Surfaces tickers that are 'in the news' today but aren't already in the index/thematic
universe, so a fresh catalyst mover (an analyst call, a sector headline) gets momentum-
scored alongside everyone else — the evidence-based way to capture news runners is to
let the momentum factor select them once they move, not to chase the headline.

Uses Finnhub's MARKET-WIDE news feed (the company-news endpoints are per-symbol; this
is the general one). Discovery is plain HTTP, no LLM. No key / any failure -> returns
[] and the screen just uses the index + thematic universe. The returned tickers are
only *candidates*: they still must clear liquidity + momentum eligibility to trade.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings

log = logging.getLogger("swing_signals.news")

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _reveal(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def discover_movers(settings: Settings, secrets: Secrets, *, limit: int = 20) -> list[str]:
    """Top tickers by mention in today's general market news (or [] without a key)."""
    key = _reveal(secrets.finnhub_api_key)
    if not key:
        return []
    try:
        import requests

        # Key in the header (not the URL): this exception message is logged below.
        resp = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general"},
            headers={"X-Finnhub-Token": key},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort
        log.warning("finnhub general-news discovery failed: %s", type(exc).__name__)
        return []

    counts: dict[str, int] = {}
    for it in items if isinstance(items, list) else []:
        related = str(it.get("related", "") or "")
        for tok in related.split(","):
            sym = tok.strip().upper()
            if _TICKER_RE.match(sym):
                counts[sym] = counts.get(sym, 0) + 1

    ranked = sorted(counts, key=lambda s: counts[s], reverse=True)[:limit]
    if ranked:
        log.info("news discovery surfaced %d tickers: %s", len(ranked), ", ".join(ranked[:10]))
    return ranked
