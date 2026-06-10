"""Shared data containers passed through the pipeline.

These are the narrow, typed interfaces between layers: the data layer fills
``SymbolData`` / ``MarketContext``; factors and the engine read them via
``RunContext``. ``issues`` lists exist so missing/stale data travels *with* the
data and the engine can fail loud (skip the stock) instead of scoring garbage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid importing heavy deps at package import time
    import pandas as pd

    from .config_loader import Secrets, Settings


@dataclass
class SymbolData:
    """All data for a single watchlist symbol, assembled by the data layer."""

    symbol: str
    ohlcv: pd.DataFrame | None = None
    fundamentals: dict[str, Any] | None = None
    news: list[dict[str, Any]] | None = None
    insider: list[dict[str, Any]] | None = None
    short_interest: dict[str, Any] | None = None
    sector: str | None = None
    # Next confirmed earnings date (live: from the calendar provider; backtest: None —
    # no free point-in-time earnings history). Feeds the engine's EARNINGS_SOON veto.
    next_earnings: date | None = None
    # Precomputed indicator row at the as-of bar — the backtest fast-path sets this
    # so factors read O(1) scalars instead of recomputing indicators every bar.
    indicators: dict[str, Any] | None = None
    issues: list[str] = field(default_factory=list)  # data-quality problems (fail-loud)

    @property
    def ok(self) -> bool:
        """True only if no data-quality issues were recorded."""
        return not self.issues


@dataclass
class MarketContext:
    """Market-wide inputs for the macro (04) and regime (07) modules."""

    spy: pd.DataFrame | None = None
    qqq: pd.DataFrame | None = None
    iwm: pd.DataFrame | None = None
    vix: float | None = None
    vix3m: float | None = None
    breadth: dict[str, Any] | None = None
    macro_series: dict[str, Any] | None = None
    issues: list[str] = field(default_factory=list)


@dataclass
class RunContext:
    """Everything a factor / gate needs for one daily run.

    A single instance is built once per run and passed (read-only by convention)
    to every factor and module so they share the same market view and equity.
    """

    settings: Settings
    secrets: Secrets
    trading_day: date | None = None
    equity: float = 0.0
    market: MarketContext | None = None
    dry_run: bool = False
