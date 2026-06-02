"""Data-quality checks — the "fail safe and loud" gate.

Returns a list of human-readable issues for a symbol's OHLCV. A non-empty list
means the data layer should mark the symbol (``SymbolData.issues``) and the engine
should **skip it and say so** rather than emit a confident signal from bad data.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

REQUIRED_OHLCV_COLS = ("open", "high", "low", "close", "volume")


def check_ohlcv_quality(
    df: pd.DataFrame | None,
    *,
    symbol: str,
    asof: date | None = None,
    min_rows: int = 200,
    max_staleness_days: int = 4,
    required_cols: tuple[str, ...] = REQUIRED_OHLCV_COLS,
) -> list[str]:
    """Return a list of data-quality issues (empty list == clean).

    Checks: data present, required columns present, enough rows for indicator
    warmup (e.g. a 200-DMA), the latest bar not stale, and the latest close
    not NaN.
    """
    issues: list[str] = []

    if df is None or len(df) == 0:
        return [f"{symbol}: no OHLCV data"]

    have = {str(c).lower() for c in df.columns}
    missing = [c for c in required_cols if c not in have]
    if missing:
        issues.append(f"{symbol}: missing column(s) {missing}")

    if len(df) < min_rows:
        issues.append(f"{symbol}: only {len(df)} bars, need >= {min_rows} for warmup")

    # Staleness: business days between the last bar and the as-of date.
    if asof is not None:
        try:
            last = df.index[-1]
            last_date = last.date() if hasattr(last, "date") else date.fromisoformat(str(last)[:10])
            gap = int(np.busday_count(last_date, asof))
            if gap > max_staleness_days:
                issues.append(
                    f"{symbol}: stale data — last bar {last_date} is {gap} "
                    f"business days before {asof} (max {max_staleness_days})"
                )
        except Exception as exc:  # noqa: BLE001 - surface, don't crash the run
            issues.append(f"{symbol}: could not parse last bar date ({exc})")

    # Latest close must be a real number.
    if "close" in have:
        close_col = next(c for c in df.columns if str(c).lower() == "close")
        last_close = df[close_col].iloc[-1]
        if last_close is None or (isinstance(last_close, float) and np.isnan(last_close)):
            issues.append(f"{symbol}: latest close is missing/NaN")

    return issues
