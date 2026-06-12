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


def test_assemble_universe_sp500_only_excludes_thematic_and_discovered():
    # The validated universe: every holdout traded point-in-time S&P 500 members
    # only, so the live default must not let theme/news names consume budget slots.
    u = assemble_universe(extra=["ZZZZ"], sp500_only=True)
    assert "AAPL" in u
    assert "IONQ" not in u and "ZZZZ" not in u


def test_settings_universe_choice_is_explicit():
    # Owner decision 2026-06-12: live trades thematic + news-discovered names too.
    # The knob must exist either way, so the validated-universe run is one flag flip.
    assert load_settings().universe.sp500_only is False


def test_screen_sp500_only_never_scans_discovered_movers():
    s = load_settings()
    s.universe.top_n_scan = 5
    s.universe.sp500_only = True   # the validated-universe configuration
    picked = screen(s, load_secrets(), asof=ASOF,
                    loader=_FakeLoader(["NVDA", "IONQ"]), discovered=["IONQ"])
    assert "IONQ" not in picked   # discovered mover excluded from the tradable set


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
    s.scoring.max_extension_atr = 0.0  # the steady _uptrend ramp rides ~3.2 ATR above
    # its EMA20; the screen's mirror of the engine's don't-chase veto is tested below
    picked = screen(s, load_secrets(), asof=ASOF, loader=_FakeLoader(["NVDA", "AMD", "AAPL"]))
    assert "NVDA" in picked
    assert set(picked) <= {"NVDA", "AMD", "AAPL"}   # everything else had no data


def _plateau_uptrend(sym: str, last_close: float = 150.0) -> SymbolData:
    """Year-long uptrend that flattens for the final month, so EMA20 catches up and
    the name is NOT extension-vetoed; a large ``last_close`` adds a blow-off spike
    bar that IS (and that also outranks the plain plateau on momentum)."""
    close = np.concatenate([np.linspace(50, 150, 270), np.full(30, 150.0)])
    close[-1] = last_close
    idx = pd.bdate_range(end="2024-06-28", periods=300)
    df = pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
         "volume": np.full(300, 5_000_000.0)},
        index=idx,
    )
    return SymbolData(symbol=sym, ohlcv=df)


class _MapLoader:
    def __init__(self, frames):
        self.frames = frames

    def load_watchlist(self, symbols, asof, *, offline=False, news=True):
        return {
            s: (self.frames[s] if s in self.frames else SymbolData(symbol=s))
            for s in symbols
        }


def test_screen_mirrors_engine_extension_veto_and_composite_ranking():
    """Parity fix 2026-06-12: an engine-guaranteed rejection must not burn a
    top_n_scan slot, and the top-N cut must use the engine's own ranking key —
    the old 0.6/0.4 blend let a name the engine ranked top-8 miss the candidate
    list entirely (a live decision flip the backtest never sees)."""
    s = load_settings()
    s.universe.top_n_scan = 5
    frames = {"AAPL": _plateau_uptrend("AAPL"), "NVDA": _plateau_uptrend("NVDA", 162.0)}
    loader = _MapLoader(frames)

    s.scoring.max_extension_atr = 0.0   # veto off: the spike name ranks first
    assert screen(s, load_secrets(), asof=ASOF, loader=loader)[0] == "NVDA"

    s.scoring.max_extension_atr = 3.0   # veto on: the engine would reject NVDA anyway
    picked = screen(s, load_secrets(), asof=ASOF, loader=loader)
    assert picked == ["AAPL"]           # the extended name burned no candidate slot


def test_engine_rank_ties_break_alphabetically_not_by_input_order():
    """Parity fix 2026-06-12: conviction ties (scores round to 0.1) must rank the
    same names regardless of dict insertion order — the backtest loads symbols
    sorted while live candidates arrive in screen-rank order, and order-dependent
    ties flipped real selections at the max-positions boundary."""
    s = load_settings()
    s.risk.max_positions = 1
    s.scoring.max_extension_atr = 0.0
    ctx = RunContext(settings=s, secrets=load_secrets(), trading_day=ASOF, equity=s.account.equity)
    data = {"ZZZ": _uptrend("ZZZ"), "AAA": _uptrend("AAA")}  # identical frames, ZZZ first
    res = generate_signals(data, ctx, GREEN)
    assert [sig.ticker for sig in res.actionable] == ["AAA"]
    assert any(
        sig.ticker == "ZZZ" and "CAPPED_MAX_POSITIONS" in sig.flags for sig in res.no_trades
    )


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
