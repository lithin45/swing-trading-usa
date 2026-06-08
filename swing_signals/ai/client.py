"""Thin Anthropic wrapper: structured news scoring + free-text brief.

Centralizes the one model id, prompt caching (static rubric in a cache_control
system block), and structured output (messages.parse + a Pydantic schema). All
methods return None when disabled or on API error so callers degrade cleanly.
"""

from __future__ import annotations

import logging

from .prompts import BRIEF_SYSTEM, MODEL, NEWS_RUBRIC, NewsScoreOut

log = logging.getLogger("swing_signals.ai")


class AnthropicClient:
    model = MODEL

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.enabled = bool(api_key)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def score_headlines(self, symbol: str, items: list[dict]) -> NewsScoreOut | None:
        """Entity-level sentiment for ``symbol`` over its headlines, or None on failure."""
        if not self.enabled:
            return None
        lines = []
        for it in items:
            src = it.get("source") or "?"
            head = it.get("headline") or ""
            summ = it.get("summary")
            line = f"- [{src}] {head}"
            if summ:
                line += f" — {str(summ)[:200]}"
            lines.append(line)
        user = (
            f"Ticker: {symbol}\n"
            f"Score the news sentiment toward {symbol} for a swing trader.\n\n"
            f"Headlines:\n" + "\n".join(lines)
        )
        try:
            resp = self._get_client().messages.parse(
                model=self.model,
                max_tokens=1024,
                system=[{
                    "type": "text", "text": NEWS_RUBRIC,
                    "cache_control": {"type": "ephemeral"},  # cached across per-symbol calls
                }],
                messages=[{"role": "user", "content": user}],
                output_format=NewsScoreOut,
            )
            return resp.parsed_output
        except Exception as exc:  # noqa: BLE001 - AI is non-essential; degrade to neutral/exclude
            log.warning("news scoring failed for %s: %s", symbol, exc)
            return None

    def write_brief(self, context_text: str) -> str | None:
        """Plain-English daily brief from a structured-facts block, or None on failure."""
        if not self.enabled:
            return None
        try:
            resp = self._get_client().messages.create(
                model=self.model,
                max_tokens=1024,
                system=[{
                    "type": "text", "text": BRIEF_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": context_text}],
            )
            return "".join(b.text for b in resp.content if b.type == "text").strip() or None
        except Exception as exc:  # noqa: BLE001
            log.warning("brief generation failed: %s", exc)
            return None
