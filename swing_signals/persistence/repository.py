"""Repository: persist runs/signals idempotently; read/update outcomes.

``save_signals`` relies on the ``UNIQUE(signal_date, symbol)`` guard for
idempotency — re-running the same trading day inserts nothing new. Every run also
records the git SHA + config hash, so any stored signal is traceable to the exact
code and parameters that produced it (file 12 §7).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AccountSnapshot,
    Brief,
    NewsItem,
    NewsScore,
    Outcome,
    Rejection,
    Run,
    Signal,
    Trade,
)

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings
    from ..scoring.engine import Signal as EngineSignal


def create_run(
    session: Session,
    *,
    run_ts: datetime,
    trading_day: date | None,
    status: str,
    data_provider: str | None = None,
    git_sha: str | None = None,
    config_hash: str | None = None,
    error: str | None = None,
) -> Run:
    run = Run(
        run_ts=run_ts, trading_day=trading_day, status=status,
        data_provider=data_provider, git_sha=git_sha, config_hash=config_hash, error=error,
    )
    session.add(run)
    session.flush()  # assign run.id
    return run


def save_signals(
    session: Session, run: Run, signals: list[EngineSignal], *, created_at: datetime
) -> int:
    """Persist actionable signals; returns the count newly inserted.

    Existing ``(signal_date, symbol)`` rows are skipped, so a same-day re-run is a
    no-op rather than a duplicate.
    """
    inserted = 0
    for sig in signals:
        existing = session.scalar(
            select(Signal).where(
                Signal.signal_date == sig.signal_date, Signal.symbol == sig.ticker
            )
        )
        if existing is not None:
            continue
        rps = None
        if sig.entry_zone_high is not None and sig.stop_price is not None:
            rps = round(sig.entry_zone_high - sig.stop_price, 4)
        factor_json = json.dumps(sig.factor_contributions) if sig.factor_contributions else None
        flags_json = json.dumps(sig.flags) if sig.flags else None
        session.add(Signal(
            run_id=run.id,
            signal_date=sig.signal_date,
            symbol=sig.ticker,
            direction=(sig.direction or "long").lower(),
            composite_score=sig.conviction_score,
            conviction_tier=sig.conviction_tier,
            rank=sig.rank,
            reference_price=sig.reference_price,
            entry_zone_low=sig.entry_zone_low,
            entry_zone_high=sig.entry_zone_high,
            stop_price=sig.stop_price,
            target_price=sig.target_price,
            reward_risk=sig.reward_risk,
            atr=sig.atr,
            risk_per_share=rps,
            suggested_shares=sig.suggested_shares,
            suggested_risk_pct=sig.suggested_risk_pct,
            chandelier_stop=sig.chandelier_stop,
            agreement_score=sig.agreement_score,
            regime_state=sig.regime_state,
            factor_scores=factor_json,
            flags=flags_json,
            created_at=created_at,
        ))
        inserted += 1
    run.n_signals = (run.n_signals or 0) + inserted
    return inserted


def save_rejections(
    session: Session, run: Run | None, rejections: list[EngineSignal], *, created_at: datetime
) -> int:
    """Persist the day's rejected/deferred setups (idempotent on ``(signal_date, symbol)``).

    This is the budget/near-miss audit trail: without it, a 69.8-vs-70.0 near miss or
    a BUDGET_EXHAUSTED deferral exists only in the printed report and is gone by morning.
    """
    inserted = 0
    for sig in rejections:
        existing = session.scalar(
            select(Rejection).where(
                Rejection.signal_date == sig.signal_date, Rejection.symbol == sig.ticker
            )
        )
        if existing is not None:
            continue
        session.add(Rejection(
            run_id=run.id if run is not None else None,
            signal_date=sig.signal_date,
            symbol=sig.ticker,
            composite_score=sig.conviction_score,
            conviction_tier=sig.conviction_tier,
            agreement_score=sig.agreement_score,
            regime_state=sig.regime_state,
            flags=json.dumps(sig.flags) if sig.flags else None,
            reasons=json.dumps(sig.reasons) if sig.reasons else None,
            explanation=sig.explanation or None,
            created_at=created_at,
        ))
        inserted += 1
    return inserted


def month_entry_charges(session: Session, *, month_of: date) -> int:
    """Entry submissions this calendar month = ``trades`` rows with a signal_date in it.

    Each row is one real entry decision (unique per ``(signal_date, symbol)``; a
    re-entry of a closed name on a later day is a new row — a new charge; a held
    name's re-emission creates no row — no charge). Canceled rows still count:
    the slot was spent when the order was submitted.
    """
    from sqlalchemy import func

    start = month_of.replace(day=1)
    return int(session.scalar(
        select(func.count()).select_from(Trade).where(Trade.signal_date >= start)
    ) or 0)


def month_emitted_symbols(session: Session, *, month_of: date, before_day: date) -> set[str]:
    """Distinct symbols emitted as BUY signals in ``month_of``'s calendar month with
    signal_date < before_day — the signal-only fallback for budget charges.

    Distinct symbols, because the screen re-emits a still-strong name daily; in
    signal-only mode there are no trade rows to count exactly, so a same-month
    re-entry after a stop is undercounted (documented approximation). The strict
    ``< before_day`` keeps a same-day re-run idempotent: today's own
    (already-persisted) signals never shrink today's remaining budget.
    """
    start = month_of.replace(day=1)
    return set(session.scalars(
        select(Signal.symbol).distinct().where(
            Signal.signal_date >= start,
            Signal.signal_date < before_day,
            Signal.direction == "long",
        )
    ))


def recent_stop_symbols(session: Session, *, since: date) -> set[str]:
    """Symbols stopped out on/after ``since`` — the per-name cooldown set.

    Reads both worlds: real paper trades (``trades.exit_reason='stopped'``) and the
    signal tracker's theoretical outcomes (``outcomes.status='stopped'``), so the
    cooldown protects signal-only operation exactly like broker operation.
    """
    stopped: set[str] = set()
    for sym in session.scalars(
        select(Trade.symbol).where(
            Trade.status == "closed",
            Trade.exit_reason == "stopped",
            Trade.exit_date >= since,
        )
    ):
        stopped.add(sym)
    for sym in session.scalars(
        select(Signal.symbol).join(Outcome, Outcome.signal_id == Signal.id).where(
            Outcome.status == "stopped",
            Outcome.exit_date >= since,
        )
    ):
        stopped.add(sym)
    return stopped


def open_signals(session: Session) -> list[Signal]:
    """Signals with no outcome yet, or an outcome still 'open' — for the tracker job."""
    return list(session.scalars(
        select(Signal).outerjoin(Signal.outcome).where(
            (Outcome.id.is_(None)) | (Outcome.status == "open")
        )
    ))


def upsert_outcome(
    session: Session, signal_id: int, *, status: str, updated_at: datetime, **fields: Any
) -> Outcome:
    """Create or update the outcome row for a signal (used by the outcome tracker)."""
    outcome = session.scalar(select(Outcome).where(Outcome.signal_id == signal_id))
    if outcome is None:
        outcome = Outcome(signal_id=signal_id, status=status, updated_at=updated_at, **fields)
        session.add(outcome)
    else:
        outcome.status = status
        outcome.updated_at = updated_at
        for key, value in fields.items():
            setattr(outcome, key, value)
    return outcome


def persist_daily_run(
    settings: Settings,
    trading_day: date | None,
    actionable: list[EngineSignal],
    *,
    status: str = "success",
    error: str | None = None,
    secrets: Secrets | None = None,
    no_trades: list[EngineSignal] | None = None,
) -> int:
    """Open the configured DB, write a run row + its signals (and the day's rejections),
    return signals inserted.

    Passing ``secrets`` lets a local ``.env`` ``SWING_DATABASE_URL`` redirect to Postgres; tests
    that omit it stay on ``settings.run.db_url`` (their temp SQLite).
    """
    from ..config_loader import resolve_db_url
    from .db import make_engine, session_scope

    run_ts = datetime.now()
    provider = settings.data.provider_order[0] if settings.data.provider_order else None
    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        run = create_run(
            session, run_ts=run_ts, trading_day=trading_day, status=status,
            data_provider=provider, git_sha=_git_sha(), config_hash=_config_hash(settings),
            error=error,
        )
        if no_trades:
            save_rejections(session, run, no_trades, created_at=run_ts)
        return save_signals(session, run, actionable, created_at=run_ts)


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
    except Exception:  # noqa: BLE001 - git absence must not break a run
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def _config_hash(settings: Settings) -> str:
    return hashlib.sha256(settings.model_dump_json().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Stage 8 — trades / snapshots / news / briefs (broker + AI + dashboard).
# Same idempotent, session-scoped style as the signal/outcome helpers above.
# ---------------------------------------------------------------------------


def get_signals_for_day(
    session: Session, day: date, *, direction: str | None = "long"
) -> list[Signal]:
    """The persisted signals for one trading day (what the broker acts on)."""
    stmt = select(Signal).where(Signal.signal_date == day)
    if direction is not None:
        stmt = stmt.where(Signal.direction == direction)
    return list(session.scalars(stmt.order_by(Signal.rank)))


def get_trade(session: Session, signal_date: date, symbol: str) -> Trade | None:
    return session.scalar(
        select(Trade).where(Trade.signal_date == signal_date, Trade.symbol == symbol)
    )


def upsert_trade(
    session: Session, *, signal_date: date, symbol: str, now: datetime, **fields: Any
) -> Trade:
    """Create or update the trade for ``(signal_date, symbol)`` — idempotent on the unique key."""
    trade = get_trade(session, signal_date, symbol)
    if trade is None:
        trade = Trade(
            signal_date=signal_date, symbol=symbol, created_at=now, updated_at=now, **fields
        )
        session.add(trade)
    else:
        for key, value in fields.items():
            setattr(trade, key, value)
        trade.updated_at = now
    session.flush()
    return trade


def _trades_with_status(session: Session, statuses: list[str]) -> list[Trade]:
    return list(session.scalars(select(Trade).where(Trade.status.in_(statuses))))


def active_trades(session: Session) -> list[Trade]:
    """Every trade still in flight (anything not closed/canceled) — the manage loop's worklist."""
    return list(
        session.scalars(select(Trade).where(Trade.status.notin_(["closed", "canceled"])))
    )


def active_trade_symbols(session: Session) -> set[str]:
    """Symbols with an in-flight trade — re-emissions of these never charge the budget
    (a held name re-printing is not a NEW entry; the broker skips it as held anyway)."""
    return {t.symbol for t in active_trades(session)}


def open_trades(session: Session) -> list[Trade]:
    return _trades_with_status(session, ["open"])


def pending_entry_trades(session: Session) -> list[Trade]:
    return _trades_with_status(session, ["pending_entry"])


def closing_trades(session: Session) -> list[Trade]:
    return _trades_with_status(session, ["closing"])


def closed_trades(session: Session) -> list[Trade]:
    return list(
        session.scalars(select(Trade).where(Trade.status == "closed").order_by(Trade.exit_date))
    )


def add_account_snapshot(
    session: Session,
    *,
    ts: datetime,
    equity: float,
    trading_day: date | None = None,
    cash: float | None = None,
    buying_power: float | None = None,
    open_positions: int = 0,
    open_risk_pct: float | None = None,
) -> AccountSnapshot:
    snap = AccountSnapshot(
        ts=ts, trading_day=trading_day, equity=equity, cash=cash, buying_power=buying_power,
        open_positions=open_positions, open_risk_pct=open_risk_pct,
    )
    session.add(snap)
    return snap


def list_snapshots(session: Session) -> list[AccountSnapshot]:
    return list(session.scalars(select(AccountSnapshot).order_by(AccountSnapshot.ts)))


def upsert_news_items(
    session: Session, items: list[dict[str, Any]], *, fetched_at: datetime
) -> int:
    """Insert news rows not already cached on ``(symbol, url)``; return the inserted count."""
    inserted = 0
    for it in items:
        symbol = it.get("symbol")
        url = (it.get("url") or "")[:512]
        if not symbol or not url:
            continue
        existing = session.scalar(
            select(NewsItem).where(NewsItem.symbol == symbol, NewsItem.url == url)
        )
        if existing is not None:
            continue
        session.add(NewsItem(
            symbol=symbol, headline=(it.get("headline") or "")[:2000],
            summary=it.get("summary"), url=url, source=it.get("source"),
            published_at=it.get("published_at"), sentiment_hint=it.get("sentiment_hint"),
            fetched_at=fetched_at,
        ))
        inserted += 1
    return inserted


def get_cached_news(
    session: Session, symbol: str, *, since: datetime | None = None
) -> list[NewsItem]:
    stmt = select(NewsItem).where(NewsItem.symbol == symbol)
    if since is not None:
        stmt = stmt.where(NewsItem.published_at >= since)
    return list(session.scalars(stmt.order_by(NewsItem.published_at.desc())))


def get_news_score(session: Session, score_key: str) -> NewsScore | None:
    return session.scalar(select(NewsScore).where(NewsScore.score_key == score_key))


def save_news_score(
    session: Session, *, score_key: str, symbol: str, value: float, created_at: datetime,
    trading_day: date | None = None, catalyst: str | None = None, rationale: str | None = None,
    model: str | None = None, prompt_version: str | None = None, items_considered: int = 0,
) -> NewsScore:
    """Persist a Claude news score; a no-op returning the existing row if the key is present."""
    row = get_news_score(session, score_key)
    if row is not None:
        return row
    row = NewsScore(
        score_key=score_key, symbol=symbol, value=value, created_at=created_at,
        trading_day=trading_day, catalyst=catalyst, rationale=rationale, model=model,
        prompt_version=prompt_version, items_considered=items_considered,
    )
    session.add(row)
    return row


def get_brief(session: Session, trading_day: date) -> Brief | None:
    return session.scalar(select(Brief).where(Brief.trading_day == trading_day))


def upsert_brief(
    session: Session, *, trading_day: date, text: str, created_at: datetime,
    model: str | None = None,
) -> Brief:
    row = get_brief(session, trading_day)
    if row is None:
        row = Brief(trading_day=trading_day, text=text, model=model, created_at=created_at)
        session.add(row)
    else:
        row.text = text
        row.model = model
    return row
