"""Monthly trade-budget state — the prime directive's enforcement input (mandate §4).

The ceiling is **≤ N new entries per calendar month, hard, never a quota**. An
"entry" is a **new position submission**: re-prints of a name that is currently
held or pending ride free (the screen re-emits a still-strong winner daily and
the broker skips it as held — that is not a new entry), but a name that closed
and signals again later in the month charges a NEW slot. Distinct-symbol
counting was tried first and failed exactly there: 2018 replay showed months
with 7 "entries" charged but 11 positions opened via stop → cooldown → re-entry.

The engine itself stays stateless: callers build a :class:`BudgetState` from
their own world (live: the trades/signals/outcomes tables; backtest: simulated
counters) and pass it to ``generate_signals``. Both paths therefore enforce the
identical policy, and the backtest's cadence histogram is an honest preview of
live behavior.

Idempotency: in broker mode charges come from ``trades`` rows — a same-day
re-run sees its own earlier submissions as held (free pass) and the remaining
budget already debited, so it re-emits the same set. In signal-only mode
charges fall back to distinct symbols emitted on earlier days (an
approximation, documented), which is likewise re-run stable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..config_loader import Settings

log = logging.getLogger("swing_signals.budget")


@dataclass(frozen=True)
class BudgetState:
    """Everything the engine needs to enforce the monthly ceiling + cooldown.

    ``charges_used`` is how many entry slots this calendar month has consumed.
    ``held_symbols`` are in-flight positions/pending orders: their re-emissions
    pass the budget gate free — a re-print of a held name is not a NEW entry.
    Anything not held charges a slot, including a re-entry of a name that
    already traded and closed earlier in the month.
    """

    enabled: bool = False
    max_entries_per_month: int = 7
    charges_used: int = 0                           # entry slots consumed this month
    held_symbols: frozenset[str] = frozenset()      # in-flight; re-prints free
    cooldown_blocked: frozenset[str] = frozenset()  # symbols in post-stop cooldown

    @property
    def entries_this_month(self) -> int:
        return self.charges_used

    @property
    def remaining(self) -> int:
        return max(0, self.max_entries_per_month - self.charges_used)

    def charges_budget(self, ticker: str) -> bool:
        """True if emitting ``ticker`` today would consume a NEW budget slot."""
        return ticker not in self.held_symbols


def month_start(d: date) -> date:
    return d.replace(day=1)


def build_budget_state(settings: Settings, session: Session, today: date) -> BudgetState:
    """Build live budget state from the DB (entry charges + recent stop-outs).

    Broker mode counts ``trades`` rows created this month — each row is one real
    entry submission (re-entry after a close = a new row = a new charge; today's
    own rows are counted, and their symbols are simultaneously held, so a
    same-day re-run is stable). Signal-only mode falls back to distinct symbols
    emitted on earlier days — an approximation that undercounts a same-month
    re-entry, accepted because no positions exist in that mode to count exactly.

    Cooldown reads both real paper trades and tracked signal outcomes, so the
    signal-only and broker modes get the same protection.
    """
    from ..persistence.repository import (
        active_trade_symbols,
        month_emitted_symbols,
        month_entry_charges,
        recent_stop_symbols,
    )

    cfg = settings.budget
    if not cfg.enabled:
        return BudgetState(enabled=False)
    broker_mode = settings.broker is not None and settings.broker.enabled
    if broker_mode:
        charges = month_entry_charges(session, month_of=today)
    else:
        charges = len(month_emitted_symbols(session, month_of=today, before_day=today))
    # In-flight trade symbols ride free: a held name re-emitting is not a NEW entry.
    held = frozenset(active_trade_symbols(session))
    blocked: frozenset[str] = frozenset()
    if cfg.cooldown_days > 0:
        since = today - timedelta(days=cfg.cooldown_days)
        blocked = frozenset(recent_stop_symbols(session, since=since))
    state = BudgetState(
        enabled=True,
        max_entries_per_month=cfg.max_entries_per_month,
        charges_used=charges,
        held_symbols=held,
        cooldown_blocked=blocked,
    )
    log.info(
        "budget: %d/%d entries used this month (%d remaining)%s",
        state.entries_this_month, state.max_entries_per_month, state.remaining,
        f"; cooldown: {', '.join(sorted(blocked))}" if blocked else "",
    )
    return state
