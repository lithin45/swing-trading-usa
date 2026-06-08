"""DB-memoized Claude news scoring for the f02 factor.

``score_news`` is the single entry point the factor calls. It hashes the headline
set into a ``score_key``; a cache hit returns instantly (no API call, no bill), a
miss calls Claude once, then persists the score *and* the raw items (for the
dashboard news panel). Returns None when there's no key or scoring failed, so the
factor excludes itself rather than fabricating a signal.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .client import AnthropicClient
from .prompts import MODEL, PROMPT_VERSION

if TYPE_CHECKING:
    from ..context import RunContext

log = logging.getLogger("swing_signals.ai")


@dataclass(frozen=True)
class NewsScore:
    value: float  # 0-100, 50 = neutral
    catalyst: str
    rationale: str
    items_considered: int
    model: str
    cached: bool
    ok: bool = True


def _reveal(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def _score_key(symbol: str, items: list[dict]) -> str:
    urls = sorted((it.get("url") or it.get("headline") or "") for it in items)
    src = f"{symbol}|{'|'.join(urls)}|{MODEL}|{PROMPT_VERSION}"
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:64]


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


def score_news(symbol: str, items: list[dict], ctx: RunContext) -> NewsScore | None:
    """Return a memoized/fresh Claude news score for ``symbol``, or None to exclude."""
    if not items:
        return None
    api_key = _reveal(ctx.secrets.anthropic_api_key)
    if not api_key:
        return None

    from ..config_loader import resolve_db_url
    from ..persistence import repository as repo
    from ..persistence.db import make_engine, session_scope

    key = _score_key(symbol, items)
    now = datetime.now()

    with session_scope(make_engine(resolve_db_url(ctx.settings, ctx.secrets))) as session:
        cached = repo.get_news_score(session, key)
        if cached is not None:
            return NewsScore(
                value=cached.value, catalyst=cached.catalyst or "none",
                rationale=cached.rationale or "", items_considered=cached.items_considered,
                model=cached.model or MODEL, cached=True,
            )

        out = AnthropicClient(api_key).score_headlines(symbol, items)
        if out is None:
            return None
        value = _clamp(out.score)
        repo.upsert_news_items(session, items, fetched_at=now)
        repo.save_news_score(
            session, score_key=key, symbol=symbol, value=value, created_at=now,
            trading_day=ctx.trading_day, catalyst=out.catalyst, rationale=out.rationale,
            model=MODEL, prompt_version=PROMPT_VERSION, items_considered=len(items),
        )
        return NewsScore(
            value=value, catalyst=out.catalyst, rationale=out.rationale,
            items_considered=len(items), model=MODEL, cached=False,
        )
