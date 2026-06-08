"""Claude (Anthropic) integration: news scoring + the daily brief.

Powers the f02 news_sentiment factor (entity-level sentiment of headlines) and a
plain-English daily market/portfolio brief for the dashboard. Both degrade to a
no-op when ``SWING_ANTHROPIC_API_KEY`` is absent, and both are DB-memoized so an
idempotent re-run never re-bills the API. ``anthropic`` is imported lazily so the
package imports without the optional ``ai`` extra.
"""

from __future__ import annotations
