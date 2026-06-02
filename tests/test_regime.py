"""Regime gate (file 07): bull GREEN, bear veto, fail-safe, VIX effects."""

from __future__ import annotations

import numpy as np
import pandas as pd

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import MarketContext, RunContext
from swing_signals.market.f07_regime import RegimeModule


def _index(path: np.ndarray) -> pd.DataFrame:
    n = len(path)
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    return pd.DataFrame(
        {"open": path, "high": path + 0.5, "low": path - 0.5, "close": path,
         "volume": np.full(n, 1e8)},
        index=idx,
    )


def _ctx(market: MarketContext) -> RunContext:
    return RunContext(settings=load_settings(), secrets=load_secrets(), market=market)


_UP = np.linspace(50, 150, 260)
_DOWN = np.linspace(150, 50, 260)


def test_bull_market_is_green():
    mc = MarketContext(spy=_index(_UP), qqq=_index(_UP), iwm=_index(_UP), vix=13.0)
    st = RegimeModule().compute(_ctx(mc))
    assert st.state == "GREEN"
    assert st.veto is False
    assert st.multiplier > 0.7
    assert st.score > 70


def test_bear_market_vetoes():
    mc = MarketContext(spy=_index(_DOWN), qqq=_index(_DOWN), iwm=_index(_DOWN), vix=28.0)
    st = RegimeModule().compute(_ctx(mc))
    assert st.state == "RED"
    assert st.veto is True
    assert st.multiplier == 0.0


def test_missing_spy_is_failsafe_veto():
    st = RegimeModule().compute(_ctx(MarketContext(spy=None)))
    assert st.state == "RED" and st.veto is True


def test_high_vix_drags_below_green():
    mc = MarketContext(spy=_index(_UP), qqq=_index(_UP), iwm=_index(_UP), vix=35.0)
    st = RegimeModule().compute(_ctx(mc))
    assert st.state != "GREEN"  # strong regime, but panic-level VIX pulls it down


def test_backwardation_lowers_band():
    mc = MarketContext(spy=_index(_UP), qqq=_index(_UP), iwm=_index(_UP), vix=22.0, vix3m=20.0)
    st = RegimeModule().compute(_ctx(mc))
    assert any("backwardation" in r.lower() for r in st.reasons)


def test_degraded_without_vix_still_scores():
    mc = MarketContext(spy=_index(_UP), qqq=_index(_UP), iwm=_index(_UP))  # no VIX
    st = RegimeModule().compute(_ctx(mc))
    assert st.raw["vol_degraded"] is True
    assert st.state in {"GREEN", "YELLOW", "RED"}
