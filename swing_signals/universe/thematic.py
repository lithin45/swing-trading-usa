"""Curated thematic universe (``config/thematic.yaml``) + the symbol -> sector map.

The thematic lists add liquid momentum leaders the S&P scan misses (quantum names
especially). A symbol's theme doubles as a COARSE sector for the correlation cap —
so a basket of semis counts as one crowded bet, not five independent ones.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .membership import sp500

_THEMATIC_YAML = Path(__file__).resolve().parent.parent.parent / "config" / "thematic.yaml"


@lru_cache(maxsize=1)
def themes() -> dict[str, list[str]]:
    """``theme -> [symbols]`` (empty if the YAML is absent)."""
    if not _THEMATIC_YAML.exists():
        return {}
    raw = yaml.safe_load(_THEMATIC_YAML.read_text(encoding="utf-8")) or {}
    out: dict[str, list[str]] = {}
    for theme, syms in (raw.get("themes") or {}).items():
        # str(s): defend against YAML coercing a ticker to a non-string (e.g. ON -> bool).
        out[str(theme)] = [str(s).strip().upper() for s in (syms or []) if str(s).strip()]
    return out


@lru_cache(maxsize=1)
def thematic_symbols() -> frozenset[str]:
    return frozenset(s for syms in themes().values() for s in syms)


@lru_cache(maxsize=1)
def sector_map() -> dict[str, str]:
    """``symbol -> sector`` for the correlation cap: a theme overrides the GICS sector.

    Theme membership is a tighter correlation cluster than a broad GICS sector (all
    'semis' move together more than all 'Information Technology'), so it takes priority.
    """
    m: dict[str, str] = dict(sp500())  # GICS sectors first
    for theme, syms in themes().items():
        for s in syms:
            m[s] = theme  # theme wins
    return m
