"""Exit management + reconciliation — the self-managed stop/target/time engine.

Because Alpaca forbids brackets/OCO on fractional positions, this job is the
exit mechanism. Each run it: (A) syncs pending entry fills -> open; (B) for open
positions ratchets the chandelier trailing stop from fresh OHLCV and exits on
stop / target / time-stop; (C) ages unfilled limits into a market fallback;
(D) syncs exit fills -> closed with realized R / P&L; (E) snapshots the account.

It writes only the ``trades`` table (real fills) — the ``track`` job owns the
theoretical ``outcomes`` table, so the two never clobber each other. A standalone
fractional STOP-DAY order (config ``place_protective_stops``) gives server-side
intraday downside protection between runs (emulated OCO: the loop cancels the
sibling when one side completes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from ..config_loader import resolve_db_url
from ..exits import build_rules, decide_exit
from ..factors import indicators as ind
from .alpaca_client import AlpacaBroker

if TYPE_CHECKING:
    import pandas as pd

    from ..config_loader import Secrets, Settings
    from ..data.loader import DataLoader
    from .base import BrokerClient, BrokerPosition

log = logging.getLogger("swing_signals.broker")


@dataclass
class ManageReport:
    filled_entries: list[str] = field(default_factory=list)
    exits_submitted: list[tuple[str, str]] = field(default_factory=list)  # (symbol, reason)
    closed: list[str] = field(default_factory=list)
    repriced: list[str] = field(default_factory=list)
    fallback_market: list[str] = field(default_factory=list)
    canceled: list[str] = field(default_factory=list)
    protective_placed: list[str] = field(default_factory=list)
    snapshot_equity: float | None = None

    def summary(self) -> str:
        return (
            f"{len(self.filled_entries)} filled, {len(self.exits_submitted)} exiting, "
            f"{len(self.closed)} closed, {len(self.fallback_market)} mkt-fallback, "
            f"{len(self.repriced)} repriced, {len(self.canceled)} canceled"
        )


def _reveal(secret):
    return secret.get_secret_value() if secret is not None else None


def _bars_held(entry_date: date | None, today: date) -> int:
    if entry_date is None:
        return 0
    return max(0, int(np.busday_count(entry_date, today)))


def _chandelier(df: pd.DataFrame, lookback: int, mult: float) -> float | None:
    if df is None or len(df) < lookback:
        return None
    atr_c = float(ind.atr(df["high"], df["low"], df["close"], lookback).iloc[-1])
    hh = float(df["high"].rolling(lookback).max().iloc[-1])
    return round(hh - mult * atr_c, 4)


def reconcile_and_manage(
    settings: Settings,
    secrets: Secrets,
    *,
    today: date,
    broker: BrokerClient | None = None,
    loader: DataLoader | None = None,
    dry_run: bool = False,
    offline: bool = False,
) -> ManageReport:
    """Reconcile fills and manage exits for every in-flight trade. Never raises per-symbol."""
    report = ManageReport()
    bro = settings.broker
    if bro is None or not bro.enabled:
        log.info("broker disabled in config; no management")
        return report
    if broker is None:
        broker = AlpacaBroker(
            _reveal(secrets.alpaca_api_key), _reveal(secrets.alpaca_secret_key), paper=bro.paper
        )
    if not broker.enabled:
        log.info("alpaca broker has no keys; no management")
        return report

    from ..data.loader import DataLoader
    from ..persistence import repository as repo
    from ..persistence.db import make_engine, session_scope

    loader = loader if loader is not None else DataLoader(settings, secrets)
    positions = {p.symbol: p for p in broker.list_positions()}
    now = datetime.now()

    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        for trade in repo.active_trades(session):
            bracket = trade.order_class == "bracket"
            try:
                if trade.status == "pending_entry":
                    if bracket:
                        _sync_pending_bracket(broker, settings, trade, today, now, report, dry_run)
                    else:
                        _sync_pending(broker, settings, trade, today, now, report, dry_run)
                elif trade.status == "open":
                    args = (broker, settings, trade, today, now, positions, loader,
                            report, dry_run, offline)
                    if settings.exits.mode == "staged":
                        _manage_open_staged(*args)
                    elif bracket:
                        _manage_open_bracket(*args)
                    else:
                        _manage_open(*args)
                elif trade.status == "closing":
                    _sync_closing(broker, trade, today, now, report, dry_run)
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the loop
                log.warning("manage %s failed: %s", trade.symbol, exc)

        # --- account equity snapshot for the dashboard curve ---
        if not dry_run:
            acct = broker.get_account()
            open_now = repo.open_trades(session)
            repo.add_account_snapshot(
                session, ts=now, trading_day=today, equity=acct.equity, cash=acct.cash,
                buying_power=acct.buying_power, open_positions=len(positions),
                open_risk_pct=sum(float(t.suggested_risk_pct or 0.0) for t in open_now),
            )
            report.snapshot_equity = acct.equity

    return report


# --- per-status handlers (mutate the attached trade in place) -----------------

def _sync_pending(broker, settings, trade, today, now, report, dry_run) -> None:
    """Pending limit: detect a fill -> open; else age the DAY limit (reprice / fallback)."""
    order = broker.get_order_by_id(trade.entry_order_id) if trade.entry_order_id else None
    bro = settings.broker

    if order is not None and order.is_filled:
        if not dry_run:
            trade.status = "open"
            trade.actual_entry = order.filled_avg_price
            trade.filled_qty = order.filled_qty or trade.qty
            trade.entry_fill_date = today
            if order.filled_avg_price and trade.stop_price is not None:
                trade.risk_per_share = round(order.filled_avg_price - trade.stop_price, 4)
            trade.updated_at = now
        report.filled_entries.append(trade.symbol)
        return

    if order is not None and order.is_open:
        return  # DAY limit still working this session — leave it

    # order is dead (expired/canceled/rejected) or missing -> age it
    pending_days = (trade.pending_days or 0) + 1
    if pending_days >= bro.max_pending_days:
        if bro.market_fallback:
            coid = f"swing-{today:%Y%m%d}-{trade.symbol}-mktfallback"
            if not dry_run:
                o = broker.submit_market_buy(trade.symbol, qty=trade.qty, client_order_id=coid)
                trade.entry_order_id = o.id
                trade.entry_client_order_id = coid
                trade.entry_order_type = "market"
                trade.pending_days = pending_days
                trade.updated_at = now
            report.fallback_market.append(trade.symbol)
        else:
            if not dry_run:
                trade.status = "canceled"
                trade.exit_reason = "unfilled"
                trade.updated_at = now
            report.canceled.append(trade.symbol)
        return

    # not aged out yet -> re-place a fresh DAY limit (the prior one expired)
    if bro.entry_reprice_each_day and trade.limit_price:
        coid = f"swing-{today:%Y%m%d}-{trade.symbol}-entry"
        if not dry_run:
            o = broker.submit_limit_buy(
                trade.symbol, qty=trade.qty, limit_price=trade.limit_price, client_order_id=coid
            )
            trade.entry_order_id = o.id
            trade.entry_client_order_id = coid
            trade.pending_days = pending_days
            trade.updated_at = now
        report.repriced.append(trade.symbol)


def _manage_open(
    broker, settings, trade, today, now, positions, loader, report, dry_run, offline
) -> None:
    """Open position: ratchet the trailing stop, then exit on stop / target / time-stop."""
    pos: BrokerPosition | None = positions.get(trade.symbol)

    # Position vanished while we thought it open -> a protective stop must have filled.
    if pos is None:
        _reconcile_missing_position(broker, trade, today, now, report, dry_run)
        return

    df = _recent_ohlcv(loader, trade.symbol, trade.entry_fill_date, today, offline)
    bro = settings.broker

    # 1) ratchet the chandelier trailing stop (only ever rises)
    eff = trade.effective_stop if trade.effective_stop is not None else trade.stop_price
    chand = _chandelier(df, settings.risk.chandelier_lookback, settings.risk.chandelier_multiple)
    if chand is not None:
        eff = max(eff, chand) if eff is not None else chand
    if eff is not None and not dry_run:
        trade.effective_stop = eff
        trade.chandelier_stop = chand if chand is not None else trade.chandelier_stop

    # 2) exit decision against the latest bar (stop before target, then time-stop)
    reason: str | None = None
    if df is not None and len(df) > 0:
        last = df.iloc[-1]
        low, high = float(last["low"]), float(last["high"])
        if eff is not None and low <= eff:
            reason = "stopped"
        elif trade.target_price is not None and high >= trade.target_price:
            reason = "target_hit"
    if reason is None and _bars_held(trade.entry_fill_date, today) >= bro.max_hold_bars:
        reason = "time_exit"

    if reason is not None:
        coid = f"swing-{today:%Y%m%d}-{trade.symbol}-exit"
        if not dry_run:
            _cancel_protective(broker, trade)  # emulated OCO: drop the resting stop first
            o = broker.submit_sell(
                trade.symbol, qty=pos.qty, order_type="market", client_order_id=coid
            )
            trade.exit_order_id = o.id
            trade.exit_reason = reason
            trade.status = "closing"
            trade.updated_at = now
        report.exits_submitted.append((trade.symbol, reason))
        return

    # 3) not exiting -> keep a standalone STOP-DAY protective order at the effective stop
    if bro.place_protective_stops and eff is not None and not dry_run:
        _refresh_protective_stop(broker, trade, pos, eff, today, now, report)


def _manage_open_staged(
    broker, settings, trade, today, now, positions, loader, report, dry_run, offline
) -> None:
    """Staged exits on a live position: partial at target, breakeven, trail, conditional time-stop.

    The researched ``exits.mode=staged`` behaviour, delegating the *decision* to the
    shared ``decide_exit`` (so live, backtest, and tracker agree). Because Alpaca
    brackets can't scale a partial out, a bracket position is transitioned to a
    self-managed STOP-DAY the first time it's seen here.
    """
    pos: BrokerPosition | None = positions.get(trade.symbol)
    if pos is None:  # position gone -> reconcile which leg/stop filled
        if trade.order_class == "bracket":
            _reconcile_bracket_exit(broker, trade, today, now, report, dry_run)
        else:
            _reconcile_missing_position(broker, trade, today, now, report, dry_run)
        return

    bro = settings.broker

    # Legacy-opened bracket -> cancel the server-side OCO legs and self-manage (once).
    if trade.order_class == "bracket" and (trade.take_profit_order_id or trade.stop_loss_order_id):
        if not dry_run:
            for oid in (trade.take_profit_order_id, trade.stop_loss_order_id):
                if oid:
                    broker.cancel_order(oid)
            trade.take_profit_order_id = None
            trade.stop_loss_order_id = None
            trade.order_class = "simple"
            trade.updated_at = now

    df = _recent_ohlcv(loader, trade.symbol, trade.entry_fill_date, today, offline)
    rules = build_rules(settings, bro.max_hold_bars)
    partial_done = bool(trade.partial_done)
    eff = trade.effective_stop if trade.effective_stop is not None else trade.stop_price

    # Trail the chandelier ONLY after the partial (matches backtest/tracker); stop only rises.
    if partial_done:
        chand = _chandelier(
            df, settings.risk.chandelier_lookback, settings.risk.chandelier_multiple
        )
        if chand is not None and (eff is None or chand > eff):
            eff = chand
            if not dry_run:
                trade.effective_stop = eff
                trade.chandelier_stop = chand

    entry = trade.actual_entry or 0.0
    rps = trade.risk_per_share or 0.0
    if rps <= 0 and entry and trade.stop_price is not None:
        rps = entry - trade.stop_price

    sold_this_cycle = 0.0
    if df is not None and len(df) > 0 and eff is not None and entry > 0 and rps > 0:
        last = df.iloc[-1]
        actions = decide_exit(
            entry_fill=entry, risk_per_share=rps, effective_stop=eff,
            target_1=trade.target_price or (entry + 2.0 * rps),
            partial_done=partial_done, bars_held=_bars_held(trade.entry_fill_date, today),
            bar_open=float(last["open"]), bar_high=float(last["high"]),
            bar_low=float(last["low"]), bar_close=float(last["close"]), rules=rules,
        )
        for act in actions:
            if act.kind == "MOVE_STOP":
                if act.price is not None and (eff is None or act.price > eff):
                    eff = act.price
                    if not dry_run:
                        trade.effective_stop = eff
            elif act.kind == "SCALE_OUT":
                sell_qty = round((act.fraction or 0.0) * pos.qty, 6)
                if sell_qty > 0:
                    coid = f"swing-{today:%Y%m%d}-{trade.symbol}-partial"
                    if not dry_run:
                        _cancel_protective(broker, trade)  # re-placed on the remainder below
                        broker.submit_sell(trade.symbol, qty=sell_qty, order_type="market",
                                           client_order_id=coid)
                        trade.partial_done = True
                        trade.partial_qty = sell_qty
                        trade.partial_fill_price = act.price
                        trade.partial_fill_date = today
                        trade.updated_at = now
                    sold_this_cycle = sell_qty
                    report.exits_submitted.append((trade.symbol, "target_partial"))
            elif act.kind == "EXIT_ALL":
                coid = f"swing-{today:%Y%m%d}-{trade.symbol}-exit"
                if not dry_run:
                    _cancel_protective(broker, trade)
                    o = broker.submit_sell(trade.symbol, qty=pos.qty, order_type="market",
                                           client_order_id=coid)
                    trade.exit_order_id = o.id
                    trade.exit_reason = act.reason
                    trade.status = "closing"
                    trade.updated_at = now
                report.exits_submitted.append((trade.symbol, act.reason))
                return  # fully closing

    # Not exiting -> keep a STOP-DAY protective order on the REMAINING shares.
    remaining = max(0.0, pos.qty - sold_this_cycle)
    if bro.place_protective_stops and eff is not None and remaining > 0 and not dry_run:
        _refresh_protective_stop(broker, trade, pos, eff, today, now, report, qty=remaining)


def _sync_closing(broker, trade, today, now, report, dry_run) -> None:
    """Exit order in flight: on fill, finalize realized R / %-return / P&L."""
    order = broker.get_order_by_id(trade.exit_order_id) if trade.exit_order_id else None
    if order is None:
        return
    if order.is_filled:
        if not dry_run:
            _finalize_closed(trade, order.filled_avg_price, today, trade.exit_reason or "exit", now)
        report.closed.append(trade.symbol)
    elif order.is_dead:
        if not dry_run:  # exit got rejected/canceled -> retry next cycle
            trade.status = "open"
            trade.exit_order_id = None
            trade.updated_at = now


# --- bracket handlers (native server-side stop+target OCO) --------------------

def _bracket_leg_ids(order) -> tuple[str | None, str | None]:
    tp = sl = None
    for leg in getattr(order, "legs", ()) or ():
        if leg.stop_price is not None:
            sl = leg.id
        elif leg.limit_price is not None:
            tp = leg.id
    return tp, sl


def _sync_pending_bracket(broker, settings, trade, today, now, report, dry_run) -> None:
    """GTC bracket entry: fill -> open (capture legs); else age -> market-bracket fallback."""
    order = broker.get_order_by_id(trade.entry_order_id) if trade.entry_order_id else None
    bro = settings.broker

    if order is not None and order.is_filled:
        if not dry_run:
            trade.status = "open"
            trade.actual_entry = order.filled_avg_price
            trade.filled_qty = order.filled_qty or trade.qty
            trade.entry_fill_date = today
            if order.filled_avg_price and trade.stop_price is not None:
                trade.risk_per_share = round(order.filled_avg_price - trade.stop_price, 4)
            tp_id, sl_id = _bracket_leg_ids(order)
            trade.take_profit_order_id = tp_id or trade.take_profit_order_id
            trade.stop_loss_order_id = sl_id or trade.stop_loss_order_id
            trade.updated_at = now
        report.filled_entries.append(trade.symbol)
        return

    # GTC bracket entry doesn't expire; age it by business days since submission.
    aged = _bars_held(trade.pending_since, today)
    if order is not None and order.is_open and aged < bro.max_pending_days:
        return  # still working

    if aged >= bro.max_pending_days:
        if order is not None and order.is_open:
            broker.cancel_order(order.id)  # drop the stale GTC bracket
        if bro.market_fallback and trade.target_price is not None and trade.stop_price is not None:
            coid = f"swing-{today:%Y%m%d}-{trade.symbol}-mktfallback"
            if not dry_run:
                o = broker.submit_bracket_buy(
                    trade.symbol, qty=trade.qty, limit_price=None,
                    take_profit=trade.target_price, stop_loss=trade.stop_price,
                    client_order_id=coid, market=True,
                )
                trade.entry_order_id = o.id
                trade.entry_client_order_id = coid
                trade.entry_order_type = "market"
                trade.updated_at = now
            report.fallback_market.append(trade.symbol)
        elif not dry_run:
            trade.status = "canceled"
            trade.exit_reason = "unfilled"
            trade.updated_at = now
            report.canceled.append(trade.symbol)


def _manage_open_bracket(
    broker, settings, trade, today, now, positions, loader, report, dry_run, offline
) -> None:
    """Open bracketed position: trail the stop leg; time-stop manually; reconcile OCO fills."""
    pos = positions.get(trade.symbol)
    if pos is None:  # a child leg (stop or target) filled — reconcile P&L
        _reconcile_bracket_exit(broker, trade, today, now, report, dry_run)
        return

    df = _recent_ohlcv(loader, trade.symbol, trade.entry_fill_date, today, offline)
    bro = settings.broker

    # 1) ratchet the chandelier and trail the server-side stop leg up to it
    eff = trade.effective_stop if trade.effective_stop is not None else trade.stop_price
    chand = _chandelier(df, settings.risk.chandelier_lookback, settings.risk.chandelier_multiple)
    if chand is not None and (eff is None or chand > eff):
        eff = chand
        if not dry_run:
            trade.effective_stop = eff
            trade.chandelier_stop = chand
            if trade.stop_loss_order_id:
                broker.replace_stop(trade.stop_loss_order_id, stop_price=eff)  # non-fatal

    # 2) time-stop (brackets don't expire): cancel the OCO legs, then market-sell
    if _bars_held(trade.entry_fill_date, today) >= bro.max_hold_bars:
        if not dry_run:
            for oid in (trade.take_profit_order_id, trade.stop_loss_order_id):
                if oid:
                    broker.cancel_order(oid)
            coid = f"swing-{today:%Y%m%d}-{trade.symbol}-exit"
            o = broker.submit_sell(
                trade.symbol, qty=pos.qty, order_type="market", client_order_id=coid
            )
            trade.exit_order_id = o.id
            trade.exit_reason = "time_exit"
            trade.status = "closing"
            trade.updated_at = now
        report.exits_submitted.append((trade.symbol, "time_exit"))


def _reconcile_bracket_exit(broker, trade, today, now, report, dry_run) -> None:
    """Position gone: find which OCO leg filled (stop vs target) and finalize realized P&L."""
    fill_price = None
    reason = "external"
    sl = broker.get_order_by_id(trade.stop_loss_order_id) if trade.stop_loss_order_id else None
    tp = broker.get_order_by_id(trade.take_profit_order_id) if trade.take_profit_order_id else None
    if sl is not None and sl.is_filled:
        fill_price, reason = sl.filled_avg_price, "stopped"
    elif tp is not None and tp.is_filled:
        fill_price, reason = tp.filled_avg_price, "target_hit"
    if not dry_run:
        _finalize_closed(trade, fill_price, today, reason, now)
    report.closed.append(trade.symbol)


# --- helpers ------------------------------------------------------------------

def _recent_ohlcv(loader, symbol, entry_date, today, offline):
    start = ((entry_date or today) - timedelta(days=120)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    try:
        return loader.get_ohlcv(symbol, start, end, offline=offline)
    except Exception as exc:  # noqa: BLE001 - missing data must not break management
        log.warning("manage: no OHLCV for %s (%s)", symbol, exc)
        return None


def _finalize_closed(trade, exit_price, exit_date, reason, now) -> None:
    qty = trade.filled_qty or trade.qty or 0.0
    entry = trade.actual_entry
    trade.status = "closed"
    trade.exit_price = exit_price
    trade.exit_date = exit_date
    trade.exit_reason = reason
    trade.bars_held = _bars_held(trade.entry_fill_date, exit_date)
    if exit_price is not None and entry:
        pq = trade.partial_qty or 0.0
        pf = trade.partial_fill_price
        if trade.partial_done and pq > 0 and pf is not None and qty > 0:
            # Staged scale-out: blend the partial leg (sold at the target) with the
            # remainder (exited now), qty-weighted, so realized R / P&L are one number.
            rem = max(0.0, qty - pq)
            trade.pnl = round(pq * (pf - entry) + rem * (exit_price - entry), 4)
            avg_exit = (pq * pf + rem * exit_price) / qty
            trade.pct_return = round(avg_exit / entry - 1.0, 4)
            if trade.risk_per_share:
                trade.realized_r = round((avg_exit - entry) / trade.risk_per_share, 4)
        else:
            trade.pnl = round((exit_price - entry) * qty, 4)
            trade.pct_return = round(exit_price / entry - 1.0, 4)
            if trade.risk_per_share:
                trade.realized_r = round((exit_price - entry) / trade.risk_per_share, 4)
    trade.updated_at = now


def _reconcile_missing_position(broker, trade, today, now, report, dry_run) -> None:
    """An 'open' trade with no live position: the protective stop (or a manual close) hit."""
    fill_price = None
    if trade.protective_order_id:
        po = broker.get_order_by_id(trade.protective_order_id)
        if po is not None and po.is_filled:
            fill_price = po.filled_avg_price
    reason = "stopped" if fill_price is not None else "external"
    if not dry_run:
        _finalize_closed(trade, fill_price, today, reason, now)
    report.closed.append(trade.symbol)


def _cancel_protective(broker, trade) -> None:
    if trade.protective_order_id:
        broker.cancel_order(trade.protective_order_id)
        trade.protective_order_id = None


def _refresh_protective_stop(broker, trade, pos, eff, today, now, report, *, qty=None) -> None:
    """Re-place a STOP-DAY sell at the current effective stop (DAY orders expire).

    ``qty`` defaults to the whole position; the staged path passes the post-partial
    remainder so the resting stop never tries to sell more shares than are held.
    """
    q = pos.qty if qty is None else qty
    pid = trade.protective_order_id
    existing = broker.get_order_by_id(pid) if pid else None
    if (existing is not None and existing.is_open
            and existing.stop_price == round(eff, 2) and existing.qty == q):
        return  # already protected at this level + size today
    if existing is not None and existing.is_open:
        broker.cancel_order(existing.id)
    coid = f"swing-{today:%Y%m%d}-{trade.symbol}-stop"
    o = broker.submit_sell(
        trade.symbol, qty=q, order_type="stop", stop_price=eff, client_order_id=coid
    )
    trade.protective_order_id = o.id
    trade.updated_at = now
    report.protective_placed.append(trade.symbol)
