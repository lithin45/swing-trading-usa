"""Normalize raw provider OHLCV into one canonical shape.

Every price provider returns slightly different columns/index conventions; this
pure function maps them to lowercase ``open/high/low/close/volume`` on a tz-naive,
sorted, de-duplicated DatetimeIndex. Keeping it pure makes providers easy to
unit-test on fixtures without hitting the network.
"""

from __future__ import annotations

import pandas as pd

from .retry import PermanentDataError

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def normalize_ohlcv(df: pd.DataFrame | None) -> pd.DataFrame:
    """Return canonical OHLCV. Raises PermanentDataError if required cols are absent."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]

    # If only an adjusted close is present, use it as close.
    if "close" not in out.columns and "adj close" in out.columns:
        out = out.rename(columns={"adj close": "close"})

    missing = [c for c in OHLCV_COLUMNS if c not in out.columns]
    if missing:
        raise PermanentDataError(
            f"OHLCV missing column(s) {missing}; got {list(out.columns)}"
        )

    out = out[OHLCV_COLUMNS].copy()

    idx = pd.DatetimeIndex(pd.to_datetime(out.index))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    out.index.name = "date"

    out = out[~out.index.duplicated(keep="last")].sort_index()
    for col in OHLCV_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["close"])
