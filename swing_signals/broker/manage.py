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
from ..exits import ExitAction, build_rules, chandelier, decide_exit
from ..factors import indicators as ind
from .alpaca_client import AlpacaBroker

if TYPE_CHECKING:
    import pandas as pd

    from ..config_loader import Secrets, Settings
    from ..data.loader import DataLoader
    from .base import BrokerClient, BrokerOrder, BrokerPosition

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
    orphans_adopted: list[str] = field(default_factory=list)      # live position, no trade row
    orphan_orders_canceled: list[str] = field(default_factory=list)
    snapshot_equity: float | None = None

    def summary(self) -> str:
        base = (
            f"{len(self.filled_entries)} filled, {len(self.exits_submitted)} exiting, "
            f"{len(self.closed)} closed, {len(self.fallback_market)} mkt-fallback, "
            f"{len(self.repriced)} repriced, {len(self.canceled)} canceled"
        )
        if self.orphans_adopted or self.orphan_orders_canceled:
            base += (
                f", {len(self.orphans_adopted)} orphans adopted, "
                f"{len(self.orphan_orders_canceled)} orphan orders canceled"
            )
        return base


def _reveal(secret):
    return secret.get_secret_value() if secret is not None else None


def _fetch_earnings(settings: Settings, secrets: Secrets, today: date) -> dict[str, date] | None:
    """Upcoming prints for the earnings-exit check (one bulk call; None = unscreened)."""
    ecfg = getattr(settings, "earnings", None)
    if ecfg is None or not ecfg.enabled or not ecfg.exit_before_earnings:
        return None
    from ..data.earnings import EarningsCalendar

    cal = EarningsCalendar(_reveal(secrets.finnhub_api_key))
    if not cal.available:
        return None  # the signal run already warns loudly about the missing key
    dates = cal.upcoming(today, today + timedelta(days=ecfg.veto_days_before + 4))
    if dates is None:
        log.warning("manage: earnings calendar unavailable — no earnings exits this run")
    return dates


def _earnings_exit_due(
    settings: Settings, earnings: dict[str, date] | None, symbol: str, today: date
) -> bool:
    """True when ``symbol`` prints within the veto window — exit before the gap risk."""
    if earnings is None:
        return False
    ed = earnings.get(symbol)
    if ed is None:
        return False
    ecfg = settings.earnings
    return 0 <= (ed - today).days <= ecfg.veto_days_before


def _bars_held(entry_date: date | None, today: date) -> int:
    if entry_date is None:
        return 0
    return max(0, int(np.busday_count(entry_date, today)))


def _bar_age_busdays(df: pd.DataFrame | None, today: date) -> int | None:
    """Business days between the last bar and ``today`` (None = no data at all)."""
    if df is None or len(df) == 0:
        return None
    last = df.index[-1]
    last_day = last.date() if hasattr(last, "date") else last
    return int(np.busday_count(last_day, today))


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
    earnings = _fetch_earnings(settings, secrets, today)

    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        worklist = repo.active_trades(session)
        for trade in worklist:
            bracket = trade.order_class == "bracket"
            try:
                if trade.status == "pending_entry":
                    if bracket:
                        _sync_pending_bracket(broker, settings, trade, today, now, report, dry_run)
                    else:
                        _sync_pending(broker, settings, trade, today, now, report, dry_run)
                elif trade.status == "open":
                    args = (broker, settings, trade, today, now, positions, loader,
                            report, dry_run, offline, earnings)
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

        # --- orphan sweep: live broker state the DB doesn't know about. A crash
        # between order submission and the end-of-run commit leaves Alpaca holding
        # orders/positions with no trade row — nothing above would ever manage them.
        # `known` comes from the run-START worklist: a trade closed within this run is
        # no longer "active" but its position/settling sell is ours, not an orphan.
        known = {t.symbol for t in worklist}
        _sweep_orphans(broker, settings, loader, session, repo, known=known,
                       positions=positions, today=today, now=now, report=report,
                       dry_run=dry_run, offline=offline)

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


def _sweep_orphans(
    broker, settings, loader, session, repo, *, known, positions,
    today, now, report, dry_run, offline
) -> None:
    """Adopt unknown live positions under a synthesized stop; cancel unknown swing-* buys.

    An adopted position gets the strategy's default initial stop (entry − k·ATR) so the
    normal manage loop protects and exits it from the next run onward. Unknown resting
    swing-* buy orders would fill into exactly such unmanaged positions, so they are
    canceled. Both paths are loud — they only ever exist after a mid-run crash.
    ``known``/``positions`` are the run-start views, so trades this run just closed
    (no longer "active") are still recognized as ours.
    """
    try:
        open_orders = broker.list_open_orders()
    except Exception as exc:  # noqa: BLE001 - sweep is best-effort, never kills the run
        log.warning("orphan sweep skipped (broker read failed: %s)", exc)
        return

    for sym, pos in positions.items():
        if sym in known or pos.qty <= 0:
            continue
        report.orphans_adopted.append(sym)
        log.warning(
            "%s: live position (%.4f sh @ %.2f) has no trade row — adopting under a "
            "synthesized %.1f-ATR stop", sym, pos.qty, pos.avg_entry_price,
            settings.risk.atr_stop_multiple,
        )
        if dry_run:
            continue
        df = _recent_ohlcv(loader, sym, None, today, offline)
        stop = None
        if df is not None and len(df) > settings.risk.atr_period:
            atr_now = float(
                ind.atr(df["high"], df["low"], df["close"], settings.risk.atr_period).iloc[-1]
            )
            if np.isfinite(atr_now) and atr_now > 0:
                stop = round(pos.avg_entry_price - settings.risk.atr_stop_multiple * atr_now, 2)
        repo.upsert_trade(
            session, signal_date=today, symbol=sym, now=now,
            status="open", order_class="simple", entry_order_type="adopted",
            qty=pos.qty, filled_qty=pos.qty, actual_entry=pos.avg_entry_price,
            entry_fill_date=today, stop_price=stop, effective_stop=stop,
            risk_per_share=(
                round(pos.avg_entry_price - stop, 4) if stop is not None else None
            ),
        )

    for order in open_orders:
        if (
            order.side == "buy"
            and order.client_order_id.startswith("swing-")
            and order.symbol not in known
        ):
            report.orphan_orders_canceled.append(order.symbol)
            log.warning(
                "%s: open %s buy (coid %s) has no trade row — canceling",
                order.symbol, order.type, order.client_order_id,
            )
            if not dry_run:
                broker.cancel_order(order.id)


# --- per-status handlers (mutate the attached trade in place) -----------------

def _mark_open(trade, order, today, now, *, re_anchor: bool = False) -> None:
    """Entry (fully or partially) filled -> the trade is open on the filled shares.

    With ``re_anchor`` (the self-managed path only — bracket legs rest server-side at
    fixed prices), a fill that deviates from the planned entry re-bases the stop and
    target to the SAME dollar distances off the actual fill. Without this, a market
    fallback that fills well above the aged limit carries a stop far wider than the
    sized risk and a reward:risk far under the configured target.
    """
    trade.status = "open"
    trade.actual_entry = order.filled_avg_price
    trade.filled_qty = order.filled_qty or trade.qty
    trade.entry_fill_date = today
    fill = order.filled_avg_price
    ref = trade.limit_price
    if (
        re_anchor and fill and ref and trade.stop_price is not None
        and abs(fill - ref) / ref > 0.001  # ignore sub-0.1% price improvement
    ):
        dist = ref - trade.stop_price
        if dist > 0:
            trade.stop_price = round(fill - dist, 4)
            if trade.target_price is not None and trade.target_price > ref:
                trade.target_price = round(fill + (trade.target_price - ref), 4)
            trade.effective_stop = trade.stop_price  # nothing trailed while pending
    if fill and trade.stop_price is not None:
        trade.risk_per_share = round(fill - trade.stop_price, 4)
    trade.updated_at = now


def _sync_pending(broker, settings, trade, today, now, report, dry_run) -> None:
    """Pending limit: detect a fill -> open; else age the DAY limit (reprice / fallback)."""
    order = broker.get_order_by_id(trade.entry_order_id) if trade.entry_order_id else None
    bro = settings.broker

    if order is not None and order.is_filled:
        if not dry_run:
            _mark_open(trade, order, today, now, re_anchor=True)
        report.filled_entries.append(trade.symbol)
        return

    if order is not None and order.is_open:
        return  # DAY limit still working this session — leave it

    # The order died (expired/canceled) but may have PARTIALLY filled first. Those
    # shares are real: a full-size re-order would double up, and unadopted they'd sit
    # with no stop. Adopt the partial as the position and stop chasing the rest.
    if order is not None and order.is_dead and order.filled_qty > 0:
        if not dry_run:
            _mark_open(trade, order, today, now, re_anchor=True)
        log.warning(
            "%s: entry filled partially (%.4f of %.4f sh) before dying — adopting the "
            "partial as the position", trade.symbol, order.filled_qty, trade.qty or 0.0,
        )
        report.filled_entries.append(trade.symbol)
        return

    # order is dead with no fill, or missing -> age it
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
    broker, settings, trade, today, now, positions, loader, report, dry_run, offline,
    earnings: dict[str, date] | None = None,
) -> None:
    """Open position: exit on stop / target / time-stop / earnings, then ratchet the trail.

    The exit decision tests the bar against the stop as it stood BEFORE this bar —
    that is where the resting protective order actually was all session — and only
    afterwards ratchets the chandelier for the next session, so a level computed
    from today's bar can never claim today's low (mirrors the backtest's shift(1)).
    """
    pos: BrokerPosition | None = positions.get(trade.symbol)

    # Position vanished while we thought it open -> a protective stop must have filled.
    if pos is None:
        _reconcile_missing_position(broker, trade, today, now, report, dry_run)
        return

    df = _recent_ohlcv(loader, trade.symbol, trade.entry_fill_date, today, offline)
    bro = settings.broker
    eff = trade.effective_stop if trade.effective_stop is not None else trade.stop_price
    age = _bar_age_busdays(df, today)

    # 1) exit decision against the latest bar — only if that bar is actually fresh.
    #    Acting on days-old prices is how a stale cache turns into a bad exit; the
    #    time-stop below stays active either way (it is price-insensitive).
    reason: str | None = None
    if age is not None and age <= 1:
        last = df.iloc[-1]
        low, high = float(last["low"]), float(last["high"])
        if eff is not None and low <= eff:
            reason = "stopped"
        elif trade.target_price is not None and high >= trade.target_price:
            reason = "target_hit"
    elif age is not None:
        log.warning(
            "%s: last bar is %d business days old — skipping price-based exits",
            trade.symbol, age,
        )
    if reason is None and _bars_held(trade.entry_fill_date, today) >= bro.max_hold_bars:
        reason = "time_exit"
    if reason is None and _earnings_exit_due(settings, earnings, trade.symbol, today):
        reason = "earnings_exit"
        log.info("%s: earnings %s within %dd — exiting before the print",
                 trade.symbol, (earnings or {}).get(trade.symbol),
                 settings.earnings.veto_days_before)

    if reason is not None:
        if not dry_run and _submit_exit_all(broker, trade, today, now, reason) == "closed":
            report.closed.append(trade.symbol)
        else:
            report.exits_submitted.append((trade.symbol, reason))
        return

    # 2) not exiting -> ratchet the chandelier for the NEXT session (only ever rises)
    chand = chandelier(df, settings.risk.chandelier_lookback, settings.risk.chandelier_multiple)
    if chand is not None:
        eff = max(eff, chand) if eff is not None else chand
    if eff is not None and not dry_run:
        trade.effective_stop = eff
        trade.chandelier_stop = chand if chand is not None else trade.chandelier_stop

    # 3) keep a standalone STOP-DAY protective order at the effective stop
    if bro.place_protective_stops and eff is not None and not dry_run:
        _refresh_protective_stop(broker, trade, pos, eff, today, now, report)


def _submit_exit_all(broker, trade, today, now, reason, *, suffix: str = "exit") -> str:
    """Cancel the resting stop, re-check what is actually held, market-sell all of it.

    Closes the cancel→sell race: if the protective stop filled in the window (or the
    position is otherwise gone), there is nothing to sell — submitting anyway would
    flip the position short. Returns "closed" (finalized from the stop's own fill)
    or "submitted" (market exit in flight).
    """
    po = _cancel_protective(broker, trade)
    live = broker.get_position(trade.symbol)
    qty = live.qty if live is not None else 0.0
    if qty <= 0:
        fill = po.filled_avg_price if (po is not None and po.filled_qty > 0) else None
        _finalize_closed(trade, fill, today, "stopped" if fill is not None else reason, now)
        return "closed"
    coid = f"swing-{today:%Y%m%d}-{trade.symbol}-{suffix}"
    o = broker.submit_sell(trade.symbol, qty=qty, order_type="market", client_order_id=coid)
    trade.exit_order_id = o.id
    trade.exit_reason = reason
    trade.status = "closing"
    trade.updated_at = now
    return "submitted"


def _manage_open_staged(
    broker, settings, trade, today, now, positions, loader, report, dry_run, offline,
    earnings: dict[str, date] | None = None,
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

    # Reconcile an in-flight partial sell with its REAL fill before deciding anything.
    _sync_partial(broker, trade, now, dry_run)

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
    age = _bar_age_busdays(df, today)
    fresh = age is not None and age <= 1

    entry = trade.actual_entry or 0.0
    rps = trade.risk_per_share or 0.0
    if rps <= 0 and entry and trade.stop_price is not None:
        rps = entry - trade.stop_price

    # Earnings exit pre-empts everything price-based: the gap risk exists whether or
    # not the latest bar is fresh, and a partial-scaled runner is still exposed.
    if _earnings_exit_due(settings, earnings, trade.symbol, today):
        log.info("%s: earnings %s within %dd — exiting before the print",
                 trade.symbol, (earnings or {}).get(trade.symbol),
                 settings.earnings.veto_days_before)
        if not dry_run and _submit_exit_all(
            broker, trade, today, now, "earnings_exit"
        ) == "closed":
            report.closed.append(trade.symbol)
        else:
            report.exits_submitted.append((trade.symbol, "earnings_exit"))
        return

    # Decide against the PRIOR effective stop (where the resting order actually was);
    # the chandelier is ratcheted after, for the next session — mirrors the backtest's
    # shift(1) trail. Stale data skips price-based exits but never the hard backstop.
    sold_this_cycle = 0.0
    actions: list[ExitAction] = []
    if fresh and eff is not None and entry > 0 and rps > 0:
        last = df.iloc[-1]
        actions = decide_exit(
            entry_fill=entry, risk_per_share=rps, effective_stop=eff,
            target_1=trade.target_price or (entry + 2.0 * rps),
            partial_done=partial_done, bars_held=_bars_held(trade.entry_fill_date, today),
            bar_open=float(last["open"]), bar_high=float(last["high"]),
            bar_low=float(last["low"]), bar_close=float(last["close"]), rules=rules,
        )
    else:
        if age is not None and not fresh:
            log.warning(
                "%s: last bar is %d business days old — skipping price-based exits",
                trade.symbol, age,
            )
        if _bars_held(trade.entry_fill_date, today) >= rules.hard_backstop_bars:
            actions = [ExitAction("EXIT_ALL", "time_stop")]

    for act in actions:
        if act.kind == "MOVE_STOP":
            if act.price is not None and (eff is None or act.price > eff):
                eff = act.price
                if not dry_run:
                    trade.effective_stop = eff
        elif act.kind == "SCALE_OUT":
            sell_qty = round((act.fraction or 0.0) * pos.qty, 6)
            if sell_qty > 0:
                if not dry_run:
                    po = _cancel_protective(broker, trade)  # re-placed on the remainder below
                    live = broker.get_position(trade.symbol)
                    live_qty = live.qty if live is not None else 0.0
                    if live_qty <= 0:  # the stop filled in the race window — nothing left
                        fill = (
                            po.filled_avg_price
                            if po is not None and po.filled_qty > 0
                            else None
                        )
                        _finalize_closed(
                            trade, fill, today, "stopped" if fill is not None else "external", now
                        )
                        report.closed.append(trade.symbol)
                        return
                    sell_qty = min(sell_qty, live_qty)
                    coid = f"swing-{today:%Y%m%d}-{trade.symbol}-partial"
                    o = broker.submit_sell(trade.symbol, qty=sell_qty, order_type="market",
                                           client_order_id=coid)
                    trade.partial_order_id = o.id  # reconciled to the real fill next run
                    trade.partial_done = True
                    trade.partial_qty = sell_qty
                    trade.partial_fill_price = act.price  # provisional until the fill syncs
                    trade.partial_fill_date = today
                    trade.updated_at = now
                sold_this_cycle = sell_qty
                report.exits_submitted.append((trade.symbol, "target_partial"))
        elif act.kind == "EXIT_ALL":
            if not dry_run and _submit_exit_all(broker, trade, today, now, act.reason) == "closed":
                report.closed.append(trade.symbol)
            else:
                report.exits_submitted.append((trade.symbol, act.reason))
            return  # fully closing

    # Trail the chandelier ONLY after the partial (matches backtest/tracker), for the
    # NEXT session; the stop only ever rises.
    if partial_done or sold_this_cycle > 0:
        chand = chandelier(
            df, settings.risk.chandelier_lookback, settings.risk.chandelier_multiple
        )
        if chand is not None and (eff is None or chand > eff):
            eff = chand
            if not dry_run:
                trade.effective_stop = eff
                trade.chandelier_stop = chand

    # Not exiting -> keep a STOP-DAY protective order on the REMAINING shares.
    remaining = max(0.0, pos.qty - sold_this_cycle)
    if bro.place_protective_stops and eff is not None and remaining > 0 and not dry_run:
        _refresh_protective_stop(broker, trade, pos, eff, today, now, report, qty=remaining)


def _sync_partial(broker, trade, now, dry_run) -> None:
    """Reconcile an in-flight partial sell with what actually happened.

    Filled -> overwrite the provisional (theoretical-target) qty/price with the real
    fill. Died unfilled -> the scale-out never happened: roll ``partial_done`` back so
    ``decide_exit`` can re-trigger it (the breakeven stop ratchet is kept — the stop
    only ever rises). Still open -> try again next run.
    """
    if not trade.partial_order_id or dry_run:
        return
    po: BrokerOrder | None = broker.get_order_by_id(trade.partial_order_id)
    if po is None or po.is_open:
        return
    if po.filled_qty and po.filled_qty > 0:
        trade.partial_qty = po.filled_qty
        if po.filled_avg_price is not None:
            trade.partial_fill_price = po.filled_avg_price
    else:
        log.warning(
            "%s: partial scale-out order died unfilled — rolling back partial_done",
            trade.symbol,
        )
        trade.partial_done = False
        trade.partial_qty = None
        trade.partial_fill_price = None
        trade.partial_fill_date = None
    trade.partial_order_id = None
    trade.updated_at = now


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

    # Full fill, or a partial fill on an order that then died: both mean real shares
    # (bracket legs activate for the filled qty) — open on what we actually got.
    if order is not None and (order.is_filled or (order.is_dead and order.filled_qty > 0)):
        if not dry_run:
            _mark_open(trade, order, today, now)
            tp_id, sl_id = _bracket_leg_ids(order)
            trade.take_profit_order_id = tp_id or trade.take_profit_order_id
            trade.stop_loss_order_id = sl_id or trade.stop_loss_order_id
        if not order.is_filled:
            log.warning(
                "%s: bracket entry filled partially (%.4f of %.4f sh) before dying — "
                "adopting the partial", trade.symbol, order.filled_qty, trade.qty or 0.0,
            )
        report.filled_entries.append(trade.symbol)
        return

    # GTC bracket entry doesn't expire; age it by business days since submission.
    aged = _bars_held(trade.pending_since, today)
    if order is not None and order.is_open and aged < bro.max_pending_days:
        return  # still working

    if aged >= bro.max_pending_days:
        if order is not None and order.is_open and not dry_run:
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
        else:
            if not dry_run:
                trade.status = "canceled"
                trade.exit_reason = "unfilled"
                trade.updated_at = now
            report.canceled.append(trade.symbol)


def _manage_open_bracket(
    broker, settings, trade, today, now, positions, loader, report, dry_run, offline,
    earnings: dict[str, date] | None = None,
) -> None:
    """Open bracketed position: trail the stop leg; time/earnings-stop manually; reconcile OCO."""
    pos = positions.get(trade.symbol)
    if pos is None:  # a child leg (stop or target) filled — reconcile P&L
        _reconcile_bracket_exit(broker, trade, today, now, report, dry_run)
        return

    df = _recent_ohlcv(loader, trade.symbol, trade.entry_fill_date, today, offline)
    bro = settings.broker

    # 1) ratchet the chandelier and trail the server-side stop leg up to it
    eff = trade.effective_stop if trade.effective_stop is not None else trade.stop_price
    chand = chandelier(df, settings.risk.chandelier_lookback, settings.risk.chandelier_multiple)
    if chand is not None and (eff is None or chand > eff):
        eff = chand
        if not dry_run:
            trade.effective_stop = eff
            trade.chandelier_stop = chand
            if trade.stop_loss_order_id:
                broker.replace_stop(trade.stop_loss_order_id, stop_price=eff)  # non-fatal

    # 2) time-stop (brackets don't expire) or earnings exit: cancel the OCO legs,
    #    then market-sell what is still held.
    reason = None
    if _bars_held(trade.entry_fill_date, today) >= bro.max_hold_bars:
        reason = "time_exit"
    elif _earnings_exit_due(settings, earnings, trade.symbol, today):
        reason = "earnings_exit"
        log.info("%s: earnings %s within %dd — exiting before the print",
                 trade.symbol, (earnings or {}).get(trade.symbol),
                 settings.earnings.veto_days_before)
    if reason is not None:
        if not dry_run:
            for oid in (trade.take_profit_order_id, trade.stop_loss_order_id):
                if oid:
                    broker.cancel_order(oid)
            # A leg may have filled in the race window — sell only what is still held.
            live = broker.get_position(trade.symbol)
            if live is None or live.qty <= 0:
                _reconcile_bracket_exit(broker, trade, today, now, report, dry_run)
                return
            coid = f"swing-{today:%Y%m%d}-{trade.symbol}-exit"
            o = broker.submit_sell(
                trade.symbol, qty=live.qty, order_type="market", client_order_id=coid
            )
            trade.exit_order_id = o.id
            trade.exit_reason = reason
            trade.status = "closing"
            trade.updated_at = now
        report.exits_submitted.append((trade.symbol, reason))


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


def _cancel_protective(broker, trade) -> BrokerOrder | None:
    """Cancel the resting protective stop; return its final state (it may have filled).

    The caller needs that state: if the stop filled before the cancel landed, the
    position is already (partly) gone and a follow-up sell must be sized accordingly.
    """
    pid = trade.protective_order_id
    if not pid:
        return None
    broker.cancel_order(pid)
    trade.protective_order_id = None
    return broker.get_order_by_id(pid)


def _refresh_protective_stop(broker, trade, pos, eff, today, now, report, *, qty=None) -> None:
    """Re-place a STOP-DAY sell at the current effective stop (DAY orders expire).

    ``qty`` defaults to the whole position; the staged path passes the post-partial
    remainder so the resting stop never tries to sell more shares than are held.
    The coid carries a time suffix: a same-day re-placement (ratcheted level, resized
    after a partial) must not reuse the canceled order's coid — Alpaca rejects the
    duplicate, which would leave the position with no resting stop all session.
    """
    q = pos.qty if qty is None else qty
    level = round(float(eff), 2)  # Alpaca tick size; also how the resting order reads back
    pid = trade.protective_order_id
    existing = broker.get_order_by_id(pid) if pid else None
    if (existing is not None and existing.is_open
            and existing.stop_price == level and existing.qty == q):
        return  # already protected at this level + size today
    if existing is not None and existing.is_open:
        broker.cancel_order(existing.id)
    coid = f"swing-{today:%Y%m%d}-{trade.symbol}-stop-{now:%H%M%S%f}"
    try:
        o = broker.submit_sell(
            trade.symbol, qty=q, order_type="stop", stop_price=level, client_order_id=coid
        )
    except Exception as exc:  # noqa: BLE001 - the old stop is already canceled
        trade.protective_order_id = None  # don't point at the canceled order; retry next run
        trade.updated_at = now
        log.warning(
            "%s: protective stop re-placement failed (%s) — position unprotected until "
            "the next manage run", trade.symbol, exc,
        )
        return
    trade.protective_order_id = o.id
    trade.updated_at = now
    report.protective_placed.append(trade.symbol)
