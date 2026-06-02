"""Assemble the daily MarketContext (indices + VIX/VIX3M + macro).

Composes a price source (for SPY/QQQ/IWM OHLCV → regime/breadth) with FRED (for
VIX, VIX3M, yields, credit spreads). Every fetch is wrapped so a single failure
records an issue on the context instead of crashing the run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd

from ..context import MarketContext
from .fred_provider import FredProvider

log = logging.getLogger("swing_signals.data")

# attribute on MarketContext -> the index symbol that fills it
_INDEX_ATTR = {"SPY": "spy", "QQQ": "qqq", "IWM": "iwm"}


def build_market_context(
    *,
    get_ohlcv: Callable[[str, str, str], pd.DataFrame],
    fred: FredProvider | None,
    index_symbols: list[str],
    fred_series: dict[str, str],
    lookback_days: int,
    asof: date,
) -> MarketContext:
    mc = MarketContext()
    start = (asof - timedelta(days=lookback_days)).isoformat()
    end = (asof + timedelta(days=1)).isoformat()

    for sym in index_symbols:
        attr = _INDEX_ATTR.get(sym.upper())
        try:
            df = get_ohlcv(sym, start, end)
            if attr:
                setattr(mc, attr, df)
        except Exception as exc:  # noqa: BLE001 - record, don't crash
            mc.issues.append(f"index {sym}: {exc}")

    if fred is not None and fred.available:
        vix_id = fred_series.get("vix")
        vix3m_id = fred_series.get("vix3m")
        if vix_id:
            try:
                mc.vix = fred.get_latest(vix_id)
            except Exception as exc:  # noqa: BLE001
                mc.issues.append(f"VIX ({vix_id}): {exc}")
        if vix3m_id:
            try:
                mc.vix3m = fred.get_latest(vix3m_id)
            except Exception as exc:  # noqa: BLE001
                mc.issues.append(f"VIX3M ({vix3m_id}): {exc}")
        macro: dict[str, float | None] = {}
        for key, series_id in fred_series.items():
            if key in ("vix", "vix3m"):
                continue
            try:
                macro[key] = fred.get_latest(series_id)
            except Exception as exc:  # noqa: BLE001
                mc.issues.append(f"macro {key} ({series_id}): {exc}")
        mc.macro_series = macro
    else:
        mc.issues.append("FRED unavailable (no SWING_FRED_API_KEY) — VIX/macro missing")

    return mc
