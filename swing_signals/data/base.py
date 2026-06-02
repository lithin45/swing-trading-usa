"""The DataProvider interface.

Providers implement the subset of methods they can serve (e.g. a price provider
implements ``get_ohlcv``; FRED implements ``get_market_context``). Methods a
provider does not support raise ``NotImplementedError`` and the data layer falls
through to the next provider in ``data.provider_order``. Concrete providers land
in Stage 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd

    from ..context import MarketContext


@runtime_checkable
class DataProvider(Protocol):
    """Contract every data source satisfies (each method optional per provider)."""

    name: str

    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Daily split/dividend-adjusted OHLCV for one symbol, indexed by date."""
        ...

    def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Point-in-time fundamentals for one symbol."""
        ...

    def get_news(self, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
        """Recent news items tagged to the symbol."""
        ...

    def get_insider(self, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
        """Insider (Form 4) transactions for the symbol."""
        ...

    def get_short_interest(self, symbol: str) -> dict[str, Any]:
        """Latest short interest / days-to-cover for the symbol."""
        ...

    def get_market_context(self) -> MarketContext:
        """Market-wide series: SPY/QQQ/IWM, VIX/VIX3M, breadth, macro."""
        ...
