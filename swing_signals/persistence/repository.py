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

from .models import Outcome, Run, Signal

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
) -> int:
    """Open the configured DB, write a run row + its signals, return signals inserted.

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
