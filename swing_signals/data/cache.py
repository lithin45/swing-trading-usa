"""Parquet OHLCV cache — makes daily runs idempotent and resilient to outages.

A re-run on the same day reads cached bars instead of re-pulling, and an
``--offline`` run reads cache only. ``fresh_for`` enables cache-first loading
(skip the network when the cached last bar is recent enough).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("swing_signals.data")


class OHLCVCache:
    """Per-symbol Parquet cache of adjusted daily OHLCV (DatetimeIndex preserved)."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        safe = symbol.upper().replace("/", "_").replace("\\", "_")
        return self.dir / f"ohlcv_{safe}.parquet"

    def get(self, symbol: str) -> pd.DataFrame | None:
        """Return cached OHLCV for ``symbol`` (None if absent or unreadable)."""
        p = self._path(symbol)
        if not p.exists():
            return None
        try:
            return pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001 - a corrupt cache must not crash a run
            log.warning("cache read failed for %s (%s); ignoring cached copy", symbol, exc)
            return None

    def put(self, symbol: str, df: pd.DataFrame | None) -> None:
        """UNION-merge new bars into the cached frame — the cache never loses bars.

        Daily runs fetch ~400 days, backtests fetch deep past windows, and a
        throttled provider can return a degenerate partial frame; a plain
        overwrite (or a prepend-only merge) lets any of those truncate a
        multi-year cache. The union keeps every disjoint range ever cached; new
        bars win on overlapping dates (re-fetches carry fresher adjusted prices).
        """
        if df is None or len(df) == 0:
            return
        try:
            old = self.get(symbol)
            if old is not None and len(old) > 0:
                df = pd.concat([old, df]).sort_index()
                df = df[~df.index.duplicated(keep="last")]
            df.to_parquet(self._path(symbol))
        except Exception as exc:  # noqa: BLE001 - caching is best-effort
            log.warning("cache write failed for %s (%s)", symbol, exc)

    def fresh_for(
        self, symbol: str, asof: date, max_age_days: int
    ) -> pd.DataFrame | None:
        """Cached df if its last bar is within ``max_age_days`` business days of ``asof``."""
        df = self.get(symbol)
        if df is None or len(df) == 0:
            return None
        try:
            last = df.index[-1]
            last_date = last.date() if hasattr(last, "date") else date.fromisoformat(str(last)[:10])
            gap = int(np.busday_count(last_date, asof))
        except Exception as exc:  # noqa: BLE001
            log.warning("cache freshness check failed for %s (%s)", symbol, exc)
            return None
        return df if 0 <= gap <= max_age_days else None
