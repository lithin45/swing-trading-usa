"""Daily AI brief — generated once per trading day, stored for the dashboard.

``generate_brief`` builds a structured-facts block from the run, calls Claude
once, and upserts the result keyed on ``trading_day`` (so a same-day re-run is
free and the dashboard reads it without needing an Anthropic key). Best-effort:
returns None and writes nothing when there's no key or generation failed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from .client import AnthropicClient
from .prompts import MODEL

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings

log = logging.getLogger("swing_signals.ai")


def _reveal(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def build_facts(*, today, regime, macro, result) -> str:
    """Render the structured facts block Claude turns into prose."""
    lines = [f"Date: {today}"]
    if regime is not None:
        lines.append(
            f"Regime: {regime.state} (score {regime.score}, size x{regime.multiplier}, "
            f"veto={regime.veto})"
        )
    if macro is not None:
        lines.append(f"Macro: {macro.state} (score {macro.score}, size x{macro.multiplier})")

    actionable = getattr(result, "actionable", []) or []
    lines.append(f"\nSignals fired today: {len(actionable)}")
    for s in actionable[:8]:
        lines.append(
            f"- {s.ticker}: conviction {s.conviction_score} ({s.conviction_tier}), "
            f"entry {s.entry_zone_low}-{s.entry_zone_high}, stop {s.stop_price}, "
            f"target {s.target_price} | {'; '.join(s.reasons[:3])}"
        )
    if not actionable:
        lines.append("- (none qualified — gates/conviction not met)")
    return "\n".join(lines)


def generate_brief(
    settings: Settings,
    secrets: Secrets,
    *,
    today: date,
    regime=None,
    macro=None,
    result=None,
    force: bool = False,
) -> str | None:
    """Generate (or reuse today's) brief and persist it. Returns the text or None."""
    api_key = _reveal(secrets.anthropic_api_key)
    if not api_key:
        return None

    from ..config_loader import resolve_db_url
    from ..persistence import repository as repo
    from ..persistence.db import make_engine, session_scope

    now = datetime.now()
    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        existing = repo.get_brief(session, today)
        if existing is not None and not force:
            return existing.text

        facts = build_facts(today=today, regime=regime, macro=macro, result=result)
        text = AnthropicClient(api_key).write_brief(facts)
        if not text:
            return None
        repo.upsert_brief(session, trading_day=today, text=text, created_at=now, model=MODEL)
        return text
