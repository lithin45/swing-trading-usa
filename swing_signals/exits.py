"""Unified exit decision logic — one pure function for all exit call sites.

Live management (``broker.manage``, both the simple and the bracket paths), the
backtest runner, and the signal tracker all delegate the *decision* here so they
can never drift apart. (Previously the four disagreed: live trailed the stop, the
backtest/tracker did not, and live lacked the gap-through-stop branch the others
had.) Each caller still owns *execution* — simulate P&L for the backtest/tracker,
submit real Alpaca orders for ``manage`` — but the *when / at what price* is one
shared function pinned by ``tests/test_exits.py``.

Two behaviours, selected by ``config.exits.mode`` and encoded as ``ExitRules``:

* **legacy** (default) reproduces the original rules — fixed stop, a full exit at
  the 2R target, and a hard time-stop at ``max_hold_bars`` — so turning the module
  on changes nothing until the staged rules are validated.
* **staged** is the researched upgrade — scale a partial out at the first target,
  ratchet the stop to breakeven, then let the remainder ride a volatility
  (chandelier) trail with NO hard time cap; only *stagnant* trades (not yet up
  ``stagnation_min_r`` after ``stagnation_bars``) are time-cut, with a loose
  ``hard_backstop_bars`` so nothing is held forever.

Exit priority (highest first): gap-through stop, stop, first target (scale-out +
breakeven, or a full exit in legacy), hard time backstop, conditional stagnation
time-stop. Trailing the stop is the *caller's* job (it owns the price history);
it passes the already-trailed ``effective_stop`` in. ``chandelier()`` is the
shared trail helper so every caller trails identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class ExitRules:
    """Tunables that distinguish legacy from staged exits."""

    partial_take_frac: float       # fraction sold at the first target (1.0 => full legacy exit)
    move_stop_to_breakeven: bool   # after a partial, ratchet the stop up to entry
    stagnation_bars: int           # cut a not-yet-working trade after this many bars held
    stagnation_min_r: float        # "working" threshold in R (inf => always cut at stagnation_bars)
    hard_backstop_bars: int        # absolute max hold — never carry a position past this

    @property
    def takes_partial(self) -> bool:
        return 0.0 < self.partial_take_frac < 1.0

    @classmethod
    def legacy(cls, max_hold_bars: int) -> ExitRules:
        """Original behaviour: full exit at target, hard time-stop at max_hold_bars."""
        return cls(
            partial_take_frac=1.0,
            move_stop_to_breakeven=False,
            stagnation_bars=max_hold_bars,
            stagnation_min_r=float("inf"),
            hard_backstop_bars=max_hold_bars,
        )

    @classmethod
    def staged(cls, cfg) -> ExitRules:
        """Researched behaviour from the ``exits`` config block."""
        return cls(
            partial_take_frac=float(cfg.partial_take_frac),
            move_stop_to_breakeven=(cfg.move_stop_to == "breakeven"),
            stagnation_bars=int(cfg.stagnation_bars),
            stagnation_min_r=float(cfg.stagnation_min_r),
            hard_backstop_bars=int(cfg.hard_backstop_bars),
        )


def build_rules(settings, max_hold_bars: int) -> ExitRules:
    """Pick legacy or staged rules from settings (falls back to legacy)."""
    ex = getattr(settings, "exits", None)
    if ex is not None and getattr(ex, "mode", "legacy") == "staged":
        return ExitRules.staged(ex)
    return ExitRules.legacy(max_hold_bars)


@dataclass(frozen=True)
class ExitAction:
    """One thing the caller should do this bar.

    kind: ``EXIT_ALL`` (close the whole remaining position), ``SCALE_OUT`` (sell
    ``fraction`` of the ORIGINAL position), or ``MOVE_STOP`` (raise the stop).
    ``price`` is the fill price for EXIT/SCALE, or the new stop level for MOVE_STOP.
    """

    kind: str
    reason: str = ""
    price: float | None = None
    fraction: float | None = None


def decide_exit(
    *,
    entry_fill: float,
    risk_per_share: float,
    effective_stop: float,
    target_1: float,
    partial_done: bool,
    bars_held: int,
    bar_open: float,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    rules: ExitRules,
) -> list[ExitAction]:
    """Decide what to do with one open position on one (complete) bar.

    The caller must have already trailed ``effective_stop`` for this bar. Returns
    an ordered list of actions (usually empty). Stop is always checked before
    target; a gap below the stop fills at the open, not the stop.
    """
    if risk_per_share <= 0:
        return []

    # 1. Gap-through the stop -> fill at the open (worse than the stop).
    if bar_open < effective_stop:
        return [ExitAction("EXIT_ALL", "gap_stop", price=bar_open)]

    # 2. Stop hit intraday.
    if bar_low <= effective_stop:
        return [ExitAction("EXIT_ALL", "stop", price=effective_stop)]

    # 3. First target reached: scale a partial out (staged) or exit fully (legacy).
    if not partial_done and bar_high >= target_1 and rules.partial_take_frac > 0.0:
        if not rules.takes_partial:  # partial_take_frac >= 1.0 -> full exit
            return [ExitAction("EXIT_ALL", "target", price=target_1)]
        actions = [
            ExitAction("SCALE_OUT", "target_partial", price=target_1,
                       fraction=rules.partial_take_frac)
        ]
        if rules.move_stop_to_breakeven:
            actions.append(ExitAction("MOVE_STOP", "breakeven", price=entry_fill))
        return actions

    # 4. Absolute time backstop — never hold past this.
    if bars_held >= rules.hard_backstop_bars:
        return [ExitAction("EXIT_ALL", "time_stop", price=bar_close)]

    # 5. Conditional stagnation time-stop: cut only a not-yet-working, un-scaled
    #    trade. A trade that already hit its target (partial_done) or is up
    #    >= stagnation_min_r is "working" and rides the trail — the let-winners-run
    #    change that replaces the old hard time exit.
    r_now = (bar_close - entry_fill) / risk_per_share
    if (
        not partial_done
        and bars_held >= rules.stagnation_bars
        and r_now < rules.stagnation_min_r
    ):
        return [ExitAction("EXIT_ALL", "time_stop_stagnant", price=bar_close)]

    return []


def chandelier(df: pd.DataFrame | None, lookback: int, mult: float) -> float | None:
    """Chandelier trailing-stop level: HighestHigh(lookback) - mult * ATR(lookback).

    Shared so every caller trails identically. Returns None if there is too little
    history. The caller ratchets it (the effective stop only ever rises).
    """
    if df is None or len(df) < lookback:
        return None
    from .factors import indicators as ind

    atr_c = float(ind.atr(df["high"], df["low"], df["close"], lookback).iloc[-1])
    hh = float(df["high"].rolling(lookback).max().iloc[-1])
    return round(hh - mult * atr_c, 4)
