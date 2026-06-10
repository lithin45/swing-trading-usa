"""Pre-trade risk gates over *live* account state, reusing the existing RiskCfg.

The scoring engine already enforces per-trade sizing and a portfolio-heat cap at
signal time; this re-checks the same limits against the broker's actual open
positions/equity before submitting, and adds the account-level circuit breakers
from research file 08: daily/weekly/monthly loss-halts and drawdown derisk/halt.
Exits are never gated — only new entries. Inputs are duck-typed (``.equity``,
``.suggested_risk_pct``, ``.ts``) so the logic unit-tests with plain fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config_loader import Settings
    from .base import BrokerAccount


@dataclass
class GateState:
    halted: bool = False
    halt_reason: str | None = None
    open_positions: int = 0
    open_heat_pct: float = 0.0
    sector_counts: dict[str, int] = field(default_factory=dict)
    derisk_multiplier: float = 1.0  # 0.5 when in a drawdown-derisk band


def _baseline_before(snapshots: list, cutoff: date) -> float | None:
    """Equity at the most recent snapshot strictly before ``cutoff`` (a period's open)."""
    prior = [s for s in snapshots if s.ts.date() < cutoff]
    return float(prior[-1].equity) if prior else None


def _period_loss(snapshots: list, current_equity: float, cutoff: date) -> float | None:
    base = _baseline_before(snapshots, cutoff)
    if not base or base <= 0:
        return None
    return (base - current_equity) / base  # positive == a loss


def evaluate_gates(
    settings: Settings,
    *,
    account: BrokerAccount,
    open_trades: list,
    snapshots: list,
    today: date,
    sector_of: dict[str, str] | None = None,
) -> GateState:
    """Compute global halt state + current heat/positions for the entry loop."""
    risk = settings.risk
    equity = float(account.equity)

    sector_counts: dict[str, int] = {}
    if sector_of:
        for t in open_trades:
            sec = sector_of.get(t.symbol)
            if sec:
                sector_counts[sec] = sector_counts.get(sec, 0) + 1

    state = GateState(
        open_positions=len(open_trades),
        open_heat_pct=sum(float(t.suggested_risk_pct or 0.0) for t in open_trades),
        sector_counts=sector_counts,
    )

    # --- broker-side circuit breaker: a blocked account can't trade anyway ---
    if account.trading_blocked or account.account_blocked:
        return _halt(state, "account/trading blocked at the broker")

    # --- drawdown from peak equity (peak over snapshot history + now) ---
    equities = [float(s.equity) for s in snapshots] + [equity]
    peak = max(equities) if equities else equity
    if peak > 0:
        dd = (peak - equity) / peak
        if dd >= risk.drawdown_hard_halt:
            return _halt(state, f"drawdown {dd:.1%} >= hard halt {risk.drawdown_hard_halt:.0%}")
        if dd >= risk.drawdown_derisk:
            state.derisk_multiplier = 0.5

    # --- daily / weekly / monthly loss-halts (vs the period's opening equity) ---
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    for label, cutoff, threshold in (
        ("daily", today, risk.daily_loss_halt),
        ("weekly", start_of_week, risk.weekly_loss_halt),
        ("monthly", start_of_month, risk.monthly_loss_halt),
    ):
        loss = _period_loss(snapshots, equity, cutoff)
        if loss is not None and loss >= threshold:
            return _halt(state, f"{label} loss {loss:.1%} >= halt {threshold:.0%}")

    return state


def _halt(state: GateState, reason: str) -> GateState:
    state.halted = True
    state.halt_reason = reason
    return state


def can_open(
    gate: GateState,
    settings: Settings,
    *,
    risk_pct: float,
    sector: str | None = None,
) -> tuple[bool, str | None]:
    """May a new entry with ``risk_pct`` be opened given the current gate state?"""
    risk = settings.risk
    if gate.halted:
        return False, gate.halt_reason
    if gate.open_positions >= risk.max_positions:
        return False, f"max positions reached ({risk.max_positions})"
    if gate.open_heat_pct + risk_pct > risk.portfolio_heat_cap + 1e-9:
        return False, f"portfolio heat cap reached ({risk.portfolio_heat_cap:.0%})"
    if sector is not None and gate.sector_counts.get(sector, 0) >= risk.max_per_sector:
        return False, f"max per sector reached for {sector} ({risk.max_per_sector})"
    return True, None
