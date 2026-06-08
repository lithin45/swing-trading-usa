"""Free-tier news ingestion for the news_sentiment (f02) factor + dashboard.

Network-only here: providers fetch raw items, ``aggregate.fetch_news`` dedupes and
truncates them to a token-bounded list. Claude scoring and DB caching live in the
``ai`` package (so this layer has no DB/LLM dependency and is easy to unit-test).
"""

from __future__ import annotations
