"""Scoring engine: gates, sizing, ranking, transparency."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import RunContext, SymbolData
from swing_signals.market.base import MarketState
from swing_signals.scoring.engine import generate_signals

MONDAY = date(2024, 6, 24)
GREEN = MarketState(name="regime", score=100.0, state="GREEN", multiplier=1.0, veto=False)
VETO = MarketState(name="regime", score=0.0, state="RED", multiplier=0.0, veto=True)


def _ohlcv(path: np.ndarray, vol: float = 1_000_000.0) -> pd.DataFrame:
    n = len(path)
    idx = pd.bdate_range(end="2024-06-24", periods=n)
    return pd.DataFrame(
        {"open": path, "high": path + 0.5, "low": path - 0.5, "close": path,
         "volume": np.full(n, vol)},
        index=idx,
    )


def _sd(symbol, path, vol=1_000_000.0):
    return SymbolData(symbol=symbol, ohlcv=_ohlcv(path, vol))


def _ctx():
    s = load_settings()
    s.scoring.max_extension_atr = 0.0  # gate under test elsewhere; linear-ramp data trips it
    return RunContext(
        settings=s, secrets=load_secrets(), trading_day=MONDAY, equity=s.account.equity
    )


_UP = np.linspace(50, 150, 260)
_DOWN = np.linspace(150, 50, 260)


def test_bullish_symbol_produces_long_signal():
    data = {"AAA": _sd("AAA", _UP)}
    result = generate_signals(data, _ctx(), GREEN)
    assert len(result.actionable) == 1
    sig = result.actionable[0]
    assert sig.direction == "LONG"
    assert sig.rank == 1
    assert sig.stop_price < sig.reference_price < sig.target_price
    assert sig.suggested_shares > 0
    assert sig.factor_contributions  # transparent attribution
    assert sig.reasons


def test_regime_veto_blocks_all():
    data = {"AAA": _sd("AAA", _UP)}
    result = generate_signals(data, _ctx(), VETO)
    assert result.actionable == []
    assert any("REGIME_VETO" in s.flags for s in result.no_trades)


def test_bad_data_is_no_trade():
    sd = SymbolData(symbol="BAD", ohlcv=None)
    sd.issues.append("BAD: no OHLCV data")
    result = generate_signals({"BAD": sd}, _ctx(), GREEN)
    assert result.actionable == []
    assert "DATA_INTEGRITY" in result.no_trades[0].flags


def test_downtrend_below_conviction_threshold():
    result = generate_signals({"AAA": _sd("AAA", _DOWN)}, _ctx(), GREEN)
    assert result.actionable == []
    assert result.no_trades  # rejected on conviction


def test_illiquid_is_no_trade():
    # price < $5 fails the liquidity floor regardless of score
    result = generate_signals({"PNY": _sd("PNY", np.linspace(2, 4, 260))}, _ctx(), GREEN)
    assert result.actionable == []
    assert any("LIQUIDITY_FAIL" in s.flags for s in result.no_trades)


def test_ranking_and_max_positions_cap():
    s = load_settings()
    s.risk.max_positions = 3
    s.scoring.max_extension_atr = 0.0  # gate under test elsewhere
    ctx = RunContext(
        settings=s, secrets=load_secrets(), trading_day=MONDAY, equity=s.account.equity
    )
    data = {f"S{i}": _sd(f"S{i}", _UP + i) for i in range(6)}
    result = generate_signals(data, ctx, GREEN)
    assert len(result.actionable) == 3  # capped
    ranks = [sig.rank for sig in result.actionable]
    assert ranks == [1, 2, 3]
    assert any("CAPPED_MAX_POSITIONS" in s.flags for s in result.no_trades)


def test_extension_gate_vetoes_blowoff_entries():
    """max_extension_atr blocks names too far above the 20-EMA; 0 disables it."""
    import numpy as np
    import pandas as pd

    from swing_signals.config_loader import load_secrets, load_settings
    from swing_signals.context import RunContext, SymbolData
    from swing_signals.market.base import MarketState
    from swing_signals.scoring.engine import generate_signals

    # Long steady uptrend, then a vertical blow-off: close ends far above EMA20.
    n = 320
    idx = pd.bdate_range(end="2024-06-28", periods=n)
    close = np.array([50 + 0.2 * i for i in range(n)])
    close[-10:] = close[-11] * np.linspace(1.05, 1.45, 10)  # +45% in 10 bars
    df = pd.DataFrame({
        "open": close * 0.995, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, 5_000_000),
    }, index=idx)
    sd = SymbolData(symbol="HYPE", ohlcv=df)
    regime = MarketState(name="regime", score=90.0, state="GREEN", multiplier=1.0,
                         veto=False, reasons=[], raw={})

    s = load_settings()
    s.scoring.max_extension_atr = 3.0
    ctx = RunContext(settings=s, secrets=load_secrets(), trading_day=idx[-1].date(),
                     equity=s.account.equity)
    res = generate_signals({"HYPE": sd}, ctx, regime)
    gated = [x for x in res.no_trades if "EXTENSION" in x.flags]
    assert gated and not res.actionable

    s2 = load_settings()
    s2.scoring.max_extension_atr = 0.0  # disabled -> the same setup passes the gate
    ctx2 = RunContext(settings=s2, secrets=load_secrets(), trading_day=idx[-1].date(),
                      equity=s2.account.equity)
    res2 = generate_signals({"HYPE": sd}, ctx2, regime)
    assert not any("EXTENSION" in x.flags for x in res2.no_trades)
