"""Entry submission: today's persisted signals -> Alpaca limit-in-zone orders.

Reads the signals the daily run already persisted/alerted (so the bot trades
exactly what was reported), applies the live risk gates, and submits a DAY limit
at the top of the pullback zone. Idempotent two ways: a ``Trade`` row unique on
``(signal_date, symbol)`` and a deterministic ``client_order_id`` Alpaca won't
duplicate. Fills, exits, and the market fallback for unfilled limits are the
``manage`` job's responsibility — entries only opens positions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ..config_loader import resolve_db_url
from .alpaca_client import AlpacaBroker
from .gates import can_open, evaluate_gates
from .sizing import to_alpaca_order_qty

if TYPE_CHECKING:
    from datetime import date

    from ..config_loader import Secrets, Settings
    from .base import BrokerClient

log = logging.getLogger("swing_signals.broker")


@dataclass
class EntryReport:
    submitted: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    skipped_position: list[str] = field(default_factory=list)
    skipped_gated: list[tuple[str, str]] = field(default_factory=list)
    skipped_size: list[tuple[str, str]] = field(default_factory=list)
    halted: bool = False
    halt_reason: str | None = None

    def summary(self) -> str:
        if self.halted:
            return f"halted ({self.halt_reason})"
        return (
            f"{len(self.submitted)} submitted, {len(self.skipped_existing)} existing, "
            f"{len(self.skipped_position)} held, {len(self.skipped_gated)} gated, "
            f"{len(self.skipped_size)} size-skip"
        )


def _reveal(secret):
    return secret.get_secret_value() if secret is not None else None


def _entry_price(signal, ref: str) -> float | None:
    if ref == "zone_low":
        return signal.entry_zone_low
    if ref == "reference":
        return signal.reference_price
    return signal.entry_zone_high  # zone_high (default): top of the pullback band


def _leg_ids(order) -> tuple[str | None, str | None]:
    """Pull (take_profit_id, stop_loss_id) from a bracket order's child legs (if activated)."""
    tp = sl = None
    for leg in getattr(order, "legs", ()) or ():
        if leg.stop_price is not None:
            sl = leg.id
        elif leg.limit_price is not None:
            tp = leg.id
    return tp, sl


def submit_entries(
    settings: Settings,
    secrets: Secrets,
    *,
    today: date,
    broker: BrokerClient | None = None,
    dry_run: bool = False,
) -> EntryReport:
    """Submit limit-in-zone entries for today's signals. Never raises on a single bad symbol."""
    report = EntryReport()
    bro = settings.broker
    if bro is None or not bro.enabled:
        log.info("broker disabled in config; no entries")
        return report
    if broker is None:
        broker = AlpacaBroker(
            _reveal(secrets.alpaca_api_key), _reveal(secrets.alpaca_secret_key), paper=bro.paper
        )
    if not broker.enabled:
        log.info("alpaca broker has no keys; no entries")
        return report

    from ..persistence import repository as repo
    from ..persistence.db import make_engine, session_scope
    from ..universe.thematic import sector_map

    account = broker.get_account()
    held = {p.symbol for p in broker.list_positions()}
    open_buys = {o.symbol for o in broker.list_open_orders() if o.side == "buy"}
    sector_of = sector_map()  # symbol -> sector/theme for the correlation cap
    now = datetime.now()

    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        signals = repo.get_signals_for_day(session, today)
        active = repo.active_trades(session)
        gate = evaluate_gates(
            settings, account=account, open_trades=active,
            snapshots=repo.list_snapshots(session), today=today, sector_of=sector_of,
        )
        if gate.halted:
            report.halted, report.halt_reason = True, gate.halt_reason
            log.warning("entry gate halted: %s", gate.halt_reason)
            return report

        existing = {t.symbol for t in active}
        for sig in signals:
            sym = sig.symbol
            if sym in existing:
                report.skipped_existing.append(sym)
                continue
            if sym in held or sym in open_buys:
                report.skipped_position.append(sym)
                continue

            risk_pct = (sig.suggested_risk_pct or 0.0) * gate.derisk_multiplier
            ok, why = can_open(gate, settings, risk_pct=risk_pct, sector=sector_of.get(sym))
            if not ok:
                report.skipped_gated.append((sym, why or "gated"))
                continue

            entry_px = _entry_price(sig, bro.entry_price_ref)
            if not entry_px or entry_px <= 0:
                report.skipped_size.append((sym, "no entry price"))
                continue
            rps = (entry_px - sig.stop_price) if sig.stop_price is not None else None
            if not rps or rps <= 0:
                report.skipped_size.append((sym, "missing/invalid stop"))
                continue

            # Size off LIVE equity (tracks the real paper account) or the engine's number.
            if bro.size_from_live_equity and account.equity > 0:
                desired = (account.equity * risk_pct) / rps
            else:
                desired = (sig.suggested_shares or 0.0) * gate.derisk_multiplier

            # Native bracket (server-side stop+target OCO) when the position is whole-share;
            # otherwise a simple limit + self-managed exits (the only path for fractional).
            # Staged exits scale a partial out, which Alpaca brackets can't do, so staged
            # mode always uses simple entries and lets `manage` own the exits.
            use_bracket = (
                settings.exits.mode != "staged"
                and bro.entry_class in ("auto", "bracket")
                and sig.target_price is not None
                and (bro.entry_class == "bracket" or desired >= 1.0)
            )
            if use_bracket:
                oq = to_alpaca_order_qty(
                    suggested_shares=desired, entry_price=entry_px,
                    buying_power=account.buying_power, min_order_usd=bro.min_order_usd,
                    whole_share_only=True,
                )
                if (not oq.ok or oq.qty is None) and bro.entry_class == "auto":
                    use_bracket = False  # not whole-share viable → fall back to fractional
            if not use_bracket:
                oq = to_alpaca_order_qty(
                    suggested_shares=desired, entry_price=entry_px,
                    buying_power=account.buying_power, min_order_usd=bro.min_order_usd,
                    whole_share_only=bro.whole_share_only,
                )
            if not oq.ok or oq.qty is None:
                report.skipped_size.append((sym, oq.skipped_reason or "size skip"))
                continue

            klass = "bracket" if use_bracket else "simple"
            coid = f"swing-{today:%Y%m%d}-{sym}-entry"
            is_market = bro.entry_order_type == "market"
            if dry_run:
                log.info(
                    "[dry-run] would %s %s %s %.4f sh @ %.2f (stop %.2f target %s)",
                    klass, bro.entry_order_type, sym, oq.qty, entry_px, sig.stop_price,
                    sig.target_price,
                )
            else:
                try:
                    if use_bracket:
                        assert sig.target_price is not None and sig.stop_price is not None
                        order = broker.submit_bracket_buy(
                            sym, qty=oq.qty, limit_price=(None if is_market else entry_px),
                            take_profit=sig.target_price, stop_loss=sig.stop_price,
                            client_order_id=coid, market=is_market,
                        )
                    elif is_market:
                        order = broker.submit_market_buy(sym, qty=oq.qty, client_order_id=coid)
                    else:
                        order = broker.submit_limit_buy(
                            sym, qty=oq.qty, limit_price=entry_px, client_order_id=coid
                        )
                except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the batch
                    log.warning("submit failed for %s: %s", sym, exc)
                    report.skipped_size.append((sym, f"submit failed: {exc}"))
                    continue
                tp_id, sl_id = _leg_ids(order)
                repo.upsert_trade(
                    session, signal_date=today, symbol=sym, now=now, signal_id=sig.id,
                    status="pending_entry", order_class=klass, entry_order_id=order.id,
                    entry_client_order_id=coid, entry_order_type=bro.entry_order_type,
                    limit_price=round(entry_px, 4), qty=oq.qty, stop_price=sig.stop_price,
                    target_price=sig.target_price, chandelier_stop=sig.chandelier_stop,
                    effective_stop=sig.stop_price, risk_per_share=round(rps, 4),
                    suggested_risk_pct=risk_pct, take_profit_order_id=tp_id,
                    stop_loss_order_id=sl_id, pending_since=today, pending_days=0,
                )

            report.submitted.append(sym)
            gate.open_positions += 1  # apply caps within this batch too
            gate.open_heat_pct += risk_pct
            sec = sector_of.get(sym)
            if sec:
                gate.sector_counts[sec] = gate.sector_counts.get(sec, 0) + 1

    return report
