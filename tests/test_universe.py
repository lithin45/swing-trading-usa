"""Universe screener: membership, thematic map, the funnel, and the sector cap."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import RunContext, SymbolData
from swing_signals.market.base import MarketState
from swing_signals.scoring.engine import generate_signals
from swing_signals.universe.membership import sp500
from swing_signals.universe.screen import assemble_universe, resolve_universe, screen
from swing_signals.universe.thematic import sector_map, thematic_symbols, themes

ASOF = date(2024, 6, 28)
GREEN = MarketState(name="regime", score=100.0, state="GREEN", multiplier=1.0, veto=False)


def _uptrend(sym: str) -> SymbolData:
    close = np.linspace(50, 150, 300)
    idx = pd.bdate_range(end="2024-06-28", periods=300)
    df = pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
         "volume": np.full(300, 5_000_000.0)},
        index=idx,
    )
    return SymbolData(symbol=sym, ohlcv=df)


def test_sp500_loads():
    m = sp500()
    assert len(m) > 400
    assert "AAPL" in m and m["AAPL"]  # has a GICS sector


def test_thematic_handles_on_ticker_not_coerced_to_bool():
    assert "ON" in themes()["semis"]      # quoted; not YAML-coerced to a bool
    assert "IONQ" in thematic_symbols()   # non-S&P quantum name present


def test_sector_map_theme_overrides_gics():
    m = sector_map()
    assert m["ON"] == "semis"        # theme overrides the GICS sector
    assert m["IONQ"] == "quantum"    # non-S&P thematic name
    assert m.get("AAPL")             # S&P name keeps its GICS sector


def test_assemble_universe_unions_sources():
    u = assemble_universe(extra=["ZZZZ"])
    assert "AAPL" in u and "IONQ" in u and "ZZZZ" in u


def test_resolve_universe_static_passthrough():
    s = load_settings()
    s.watchlist.source = "static"
    out = resolve_universe(s, load_secrets(), loader=None, asof=ASOF)
    assert out == s.watchlist.symbols


class _FakeLoader:
    def __init__(self, eligible):
        self.eligible = set(eligible)

    def load_watchlist(self, symbols, asof, *, offline=False, news=True):
        return {
            s: (_uptrend(s) if s in self.eligible else SymbolData(symbol=s)) for s in symbols
        }


def test_screen_picks_only_eligible_liquid_names():
    s = load_settings()
    s.universe.top_n_scan = 5
    picked = screen(s, load_secrets(), asof=ASOF, loader=_FakeLoader(["NVDA", "AMD", "AAPL"]))
    assert "NVDA" in picked
    assert set(picked) <= {"NVDA", "AMD", "AAPL"}   # everything else had no data


def test_engine_caps_correlated_sector():
    s = load_settings()
    s.risk.max_per_sector = 1
    s.risk.max_positions = 10
    s.scoring.max_extension_atr = 0.0  # gate under test elsewhere
    ctx = RunContext(settings=s, secrets=load_secrets(), trading_day=ASOF, equity=s.account.equity)
    data = {}
    for sym, sec in [("AAA", "semis"), ("BBB", "semis"), ("CCC", "energy")]:
        sd = _uptrend(sym)
        sd.sector = sec
        data[sym] = sd
    res = generate_signals(data, ctx, GREEN)
    chosen_sectors = [data[sig.ticker].sector for sig in res.actionable]
    assert chosen_sectors.count("semis") <= 1               # correlation cap held
    assert any("CAPPED_SECTOR" in sig.flags for sig in res.no_trades)
