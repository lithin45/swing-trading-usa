"""Live-vs-shadow reconciliation — the authoritative slippage measure.

The outcome tracker grades signals on a market-at-next-open reference model, while
live entries are limit-at-zone-top with a 3-session age-out and market fallback, so
raw outcome-vs-trade deltas conflate entry-model mismatch with genuine execution
slippage. This module separates them: for every closed paper trade it joins the
``trades`` row (actual fills) to the theoretical ``outcomes`` row for the same
signal and computes

- **entry slippage**: the fill vs the submitted limit (bps; positive = paid more),
  plus the excess over the cost model's assumed ``MODEL_ENTRY_COST_BPS``;
- **exit slippage**: the exit fill vs the planned level for the exit reason
  (stop / target; bps, positive = exited better than planned);
- **live-minus-shadow R** per trade and in aggregate;
- **limit fill rate**: of decided limit submissions, the share filled at the limit
  (market-fallback fills and unfilled cancels count as misses);
- **monthly entry cadence**: entry submissions per calendar month.

``reconcile`` is session-in/report-out so it unit-tests on SQLite and feeds the
dashboard; ``run_reconcile`` is the CLI-shaped wrapper the ``track`` job can call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.models import Outcome, Signal, Trade

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings

log = logging.getLogger("swing_signals.tracking")

# Entry cost the shadow/backtest model already assumes per side. Fill quality is
# reported raw (vs the submitted limit) and as excess over this assumption.
MODEL_ENTRY_COST_BPS = 10.0


@dataclass(frozen=True)
class TradeReconciliation:
    """One closed paper trade joined to its theoretical outcome."""

    signal_date: date
    symbol: str
    entry_order_type: str | None
    limit_price: float | None
    actual_entry: float | None
    entry_slippage_bps: float | None        # fill vs submitted limit; + = paid more
    entry_excess_vs_model_bps: float | None  # entry_slippage_bps - MODEL_ENTRY_COST_BPS
    entry_vs_shadow_bps: float | None        # fill vs next-open reference (outcomes.slippage)
    exit_reason: str | None
    exit_price: float | None
    planned_exit_level: float | None
    exit_slippage_bps: float | None          # fill vs planned level; + = exited better
    live_r: float | None
    shadow_r: float | None
    r_delta: float | None                    # live_r - shadow_r


@dataclass(frozen=True)
class ReconciliationReport:
    rows: list[TradeReconciliation]
    n_closed: int
    n_limit_submitted: int          # decided limit submissions (filled, fallback, canceled)
    n_limit_filled: int             # filled AT the limit
    limit_fill_rate: float | None
    avg_entry_slippage_bps: float | None
    avg_exit_slippage_bps: float | None
    mean_r_delta: float | None
    total_live_r: float | None
    total_shadow_r: float | None
    monthly_entries: dict[str, int]  # 'YYYY-MM' -> entry submissions

    def summary(self) -> dict:
        return {
            "n_closed": self.n_closed,
            "n_limit_submitted": self.n_limit_submitted,
            "n_limit_filled": self.n_limit_filled,
            "limit_fill_rate": self.limit_fill_rate,
            "avg_entry_slippage_bps": self.avg_entry_slippage_bps,
            "avg_exit_slippage_bps": self.avg_exit_slippage_bps,
            "mean_r_delta": self.mean_r_delta,
            "total_live_r": self.total_live_r,
            "total_shadow_r": self.total_shadow_r,
            "monthly_entries": self.monthly_entries,
        }


def _bps(price: float | None, reference: float | None) -> float | None:
    if price is None or not reference or reference <= 0:
        return None
    return round((price / reference - 1.0) * 1e4, 2)


def _planned_exit_level(trade: Trade) -> float | None:
    if trade.exit_reason == "stopped":
        return trade.effective_stop or trade.stop_price
    if trade.exit_reason == "target_hit":
        return trade.target_price
    return None  # time/cancel exits have no planned price level


def _outcome_for(session: Session, trade: Trade) -> Outcome | None:
    sig_id = trade.signal_id
    if sig_id is None:
        sig_id = session.scalar(
            select(Signal.id).where(
                Signal.signal_date == trade.signal_date, Signal.symbol == trade.symbol
            )
        )
    if sig_id is None:
        return None
    return session.scalar(select(Outcome).where(Outcome.signal_id == sig_id))


def _began_as_limit(trade: Trade) -> bool:
    """Did this entry start life as a limit order? (Fallbacks rewrite the type to
    'market' and the client id to '...-mktfallback'; adopted positions never had one.)"""
    if trade.entry_order_type == "limit":
        return True
    return (
        trade.entry_order_type == "market"
        and (trade.entry_client_order_id or "").endswith("-mktfallback")
    )


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def reconcile(session: Session) -> ReconciliationReport:
    """Join every closed trade to its theoretical outcome and aggregate the deltas."""
    all_trades = list(session.scalars(select(Trade).order_by(Trade.signal_date)))
    rows: list[TradeReconciliation] = []
    for trade in all_trades:
        if trade.status != "closed":
            continue
        outcome = _outcome_for(session, trade)
        entry_slip = _bps(trade.actual_entry, trade.limit_price)
        level = _planned_exit_level(trade)
        shadow_r = outcome.realized_r if outcome is not None else None
        live_r = trade.realized_r
        rows.append(TradeReconciliation(
            signal_date=trade.signal_date,
            symbol=trade.symbol,
            entry_order_type=trade.entry_order_type,
            limit_price=trade.limit_price,
            actual_entry=trade.actual_entry,
            entry_slippage_bps=entry_slip,
            entry_excess_vs_model_bps=(
                round(entry_slip - MODEL_ENTRY_COST_BPS, 2) if entry_slip is not None else None
            ),
            entry_vs_shadow_bps=(
                round(outcome.slippage * 1e4, 2)
                if outcome is not None and outcome.slippage is not None else None
            ),
            exit_reason=trade.exit_reason,
            exit_price=trade.exit_price,
            planned_exit_level=level,
            exit_slippage_bps=_bps(trade.exit_price, level),
            live_r=live_r,
            shadow_r=shadow_r,
            r_delta=(
                round(live_r - shadow_r, 4)
                if live_r is not None and shadow_r is not None else None
            ),
        ))

    decided_limit = [
        t for t in all_trades if t.status != "pending_entry" and _began_as_limit(t)
    ]
    filled_at_limit = [
        t for t in decided_limit
        if t.entry_order_type == "limit" and t.actual_entry is not None
    ]

    monthly: dict[str, int] = {}
    for t in all_trades:  # every row is one entry submission (canceled still charged)
        key = f"{t.signal_date:%Y-%m}"
        monthly[key] = monthly.get(key, 0) + 1

    entry_slips = [r.entry_slippage_bps for r in rows if r.entry_slippage_bps is not None]
    exit_slips = [r.exit_slippage_bps for r in rows if r.exit_slippage_bps is not None]
    r_deltas = [r.r_delta for r in rows if r.r_delta is not None]
    live_rs = [r.live_r for r in rows if r.live_r is not None]
    shadow_rs = [r.shadow_r for r in rows if r.shadow_r is not None]

    return ReconciliationReport(
        rows=rows,
        n_closed=len(rows),
        n_limit_submitted=len(decided_limit),
        n_limit_filled=len(filled_at_limit),
        limit_fill_rate=(
            round(len(filled_at_limit) / len(decided_limit), 4) if decided_limit else None
        ),
        avg_entry_slippage_bps=_mean(entry_slips),
        avg_exit_slippage_bps=_mean(exit_slips),
        mean_r_delta=_mean(r_deltas),
        total_live_r=round(sum(live_rs), 4) if live_rs else None,
        total_shadow_r=round(sum(shadow_rs), 4) if shadow_rs else None,
        monthly_entries=dict(sorted(monthly.items())),
    )


def run_reconcile(settings: Settings, secrets: Secrets) -> int:
    """Open the configured DB, reconcile, and log the aggregates. Returns exit code."""
    from ..config_loader import resolve_db_url
    from ..persistence.db import make_engine, session_scope

    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        report = reconcile(session)

    fill = report.limit_fill_rate
    log.info(
        "reconcile: %d closed trade(s); limit fill rate %s (%d/%d); "
        "entry slip %s bps vs limit (model assumes %.0f); exit slip %s bps; "
        "live-shadow R delta %s (live %s vs shadow %s)",
        report.n_closed,
        f"{fill:.0%}" if fill is not None else "n/a",
        report.n_limit_filled, report.n_limit_submitted,
        report.avg_entry_slippage_bps, MODEL_ENTRY_COST_BPS,
        report.avg_exit_slippage_bps,
        report.mean_r_delta, report.total_live_r, report.total_shadow_r,
    )
    if report.monthly_entries:
        log.info("reconcile: entry cadence %s", report.monthly_entries)
    return 0
