"""News & sentiment factor (research file 02), powered by Claude.

Scores the entity-level sentiment of recent headlines for the symbol on the
0-100 SubScore scale (50 = neutral). It self-disables to ``ok=False`` whenever
it can't compute — no Anthropic key, no news in the window, or a scoring failure
— so :func:`~swing_signals.scoring.engine.composite_score` excludes it and the
composite is numerically identical to the technical-only result. That makes the
factor safe to register unconditionally: it only ever participates when both a
key and news are present (live runs); the backtest builds SymbolData with
``news=None``, so it stays inert there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..ai.news_scoring import score_news
from .base import Factor, SubScore
from .registry import register

if TYPE_CHECKING:
    from ..context import RunContext, SymbolData


@register
class NewsSentimentFactor(Factor):
    name = "news_sentiment"
    requires = ("news",)

    def compute(self, data: SymbolData, ctx: RunContext) -> SubScore:
        if not ctx.secrets.anthropic_api_key:
            return SubScore.unavailable(self.name, "no Anthropic key — excluded")
        items = data.news
        if not items:
            return SubScore.unavailable(self.name, "no news in window — excluded")

        score = score_news(data.symbol, items, ctx)
        if score is None or not score.ok:
            return SubScore.unavailable(self.name, "news scoring unavailable — excluded")
        return SubScore(
            name=self.name,
            value=score.value,
            reasons=[f"news: {score.catalyst} — {score.rationale}"],
            raw={
                "catalyst": score.catalyst, "items": score.items_considered,
                "model": score.model, "cached": score.cached,
            },
        )
