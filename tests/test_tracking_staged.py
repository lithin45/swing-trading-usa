"""Staged-exit integration through the tracker's resolve_outcome."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from swing_signals.exits import ExitRules
from swing_signals.tracking.outcomes import resolve_outcome

SIG_DATE = date(2024, 1, 8)

_STAGED = ExitRules.staged(
    SimpleNamespace(
        partial_take_frac=0.5, move_stop_to="breakeven",
        stagnation_bars=15, stagnation_min_r=1.0, hard_backstop_bars=60,
    )
)


def _ohlcv(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.bdate_range(start="2024-01-08", periods=len(rows))
    return pd.DataFrame(
        {"open": [r[0] for r in rows], "high": [r[1] for r in rows],
         "low": [r[2] for r in rows], "close": [r[3] for r in rows],
         "volume": [1e6] * len(rows)},
        index=idx,
    )


def test_staged_matches_legacy_on_immediate_stop():
    # Entry bar drops to the stop: no partial, no trail -> identical either way.
    df = _ohlcv([(100, 101, 99, 100), (100, 100, 93, 95)])
    legacy = resolve_outcome(signal_date=SIG_DATE, stop=95.0, target=120.0, ohlcv=df)
    staged = resolve_outcome(signal_date=SIG_DATE, stop=95.0, target=120.0, ohlcv=df,
                             rules=_STAGED, trail=True)
    assert legacy.status == staged.status == "stopped"
    assert legacy.realized_r == staged.realized_r


def test_staged_takes_partial_then_gives_back_remainder():
    # Rise through the +2R target (partial + breakeven), then a pullback closes the rest.
    df = _ohlcv([
        (100, 101, 99, 100),     # signal bar
        (100, 106, 99, 105),     # entry open=100; below target
        (106, 112, 105, 111),    # high >= target 110 -> partial @110, stop -> breakeven
        (100, 101, 98, 99),      # opens below breakeven -> remainder exits near breakeven
    ])
    legacy = resolve_outcome(signal_date=SIG_DATE, stop=95.0, target=110.0, ohlcv=df)
    staged = resolve_outcome(signal_date=SIG_DATE, stop=95.0, target=110.0, ohlcv=df,
                             rules=_STAGED, trail=True)
    assert legacy.status == "target_hit"
    assert legacy.realized_r >= 1.8                 # legacy takes the full +2R
    # Staged banks half at +2R, the remainder gives back -> blended R well below the full target.
    assert staged.realized_r is not None
    assert staged.realized_r < legacy.realized_r
