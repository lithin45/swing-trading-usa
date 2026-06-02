"""End-to-end Stage 2 wiring with an injected fake loader (no network)."""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import MarketContext, SymbolData
from swing_signals.main import run

MONDAY = date(2024, 1, 8)


def _clean(symbol: str) -> SymbolData:
    idx = pd.bdate_range(end="2024-01-08", periods=250)
    df = pd.DataFrame(
        {c: np.linspace(10, 20, 250) for c in ["open", "high", "low", "close", "volume"]},
        index=idx,
    )
    return SymbolData(symbol=symbol, ohlcv=df)


class _FakeLoader:
    """Stands in for DataLoader: 2 clean symbols, 1 with a data issue."""

    def load_market_context(self, asof, *, offline=False) -> MarketContext:
        mc = MarketContext(spy=_clean("SPY").ohlcv, vix=14.5)
        return mc

    def load_watchlist(self, symbols, asof, *, offline=False) -> dict[str, SymbolData]:
        out = {}
        for s in symbols:
            sd = _clean(s)
            if s == "BAD":
                sd.issues.append(f"{s}: stale data")
            out[s] = sd
        return out


def test_run_reports_quality_and_skips(caplog):
    settings = load_settings()
    settings.watchlist.symbols = ["AAA", "BBB", "BAD"]
    with caplog.at_level(logging.INFO, logger="swing_signals"):
        rc = run(
            settings=settings,
            secrets=load_secrets(),
            dry_run=True,
            today=MONDAY,
            loader=_FakeLoader(),
        )
    assert rc == 0
    text = caplog.text
    assert "2/3 symbols passed quality gate" in text
    assert "SKIP BAD" in text  # fail-loud reporting


def test_run_no_op_on_holiday():
    settings = load_settings()
    rc = run(settings=settings, secrets=load_secrets(), today=date(2024, 7, 4))
    assert rc == 0  # Independence Day — exits at the calendar gate
