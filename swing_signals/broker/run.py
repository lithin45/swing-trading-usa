"""CLI orchestrators for the broker jobs.

Mirror ``tracking.outcomes.run_tracker``: build dependencies, call the pure-ish
entry/manage functions, log a one-line summary, and return a process exit code
without ever raising past the CLI (so the dead-man's-switch ping still fires).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from ..calendar_gate import is_trading_day

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings

log = logging.getLogger("swing_signals.broker")


def _broker_enabled(settings: Settings) -> bool:
    return settings.broker is not None and settings.broker.enabled


def _db_preflight(settings: Settings, secrets: Secrets) -> bool:
    """Fail loudly BEFORE touching the broker if the system-of-record is unreachable.

    Neon is the single source of open-trade truth (audit P1 #9): submitting or
    managing orders against an unreachable store risks duplicate/blind actions.
    """
    try:
        from sqlalchemy import text

        from ..config_loader import resolve_db_url
        from ..persistence.db import make_engine

        with make_engine(resolve_db_url(settings, secrets)).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - any failure here means do not trade
        log.error("DB preflight failed — refusing to touch the broker without the "
                  "system of record: %s", exc)
        return False


def run_trade(
    settings: Settings,
    secrets: Secrets,
    *,
    today: date | None = None,
    dry_run: bool = False,
    offline: bool = False,
) -> int:
    """Submit entries for today's persisted signals (paper)."""
    from ..main import configure_logging
    from .entries import submit_entries

    configure_logging(settings.run.log_level)
    today = today or date.today()
    if not _broker_enabled(settings):
        log.info("broker disabled (settings.broker.enabled=false); skipping trade")
        return 0
    if not is_trading_day(today):
        log.info("%s is not an NYSE trading day; skipping trade", today)
        return 0
    if not _db_preflight(settings, secrets):
        return 1
    try:
        report = submit_entries(settings, secrets, today=today, dry_run=dry_run)
        log.info("trade%s: %s", " [dry-run]" if dry_run else "", report.summary())
    except Exception as exc:  # noqa: BLE001 - surface + non-zero, never raise past the CLI
        log.error("trade run failed: %s", exc)
        return 1
    return 0


def run_manage(
    settings: Settings,
    secrets: Secrets,
    *,
    today: date | None = None,
    dry_run: bool = False,
    offline: bool = False,
) -> int:
    """Reconcile fills + manage exits for open paper trades (paper)."""
    from ..main import configure_logging
    from .manage import reconcile_and_manage

    configure_logging(settings.run.log_level)
    today = today or date.today()
    if not _broker_enabled(settings):
        log.info("broker disabled (settings.broker.enabled=false); skipping manage")
        return 0
    if not is_trading_day(today):
        log.info("%s is not an NYSE trading day; skipping manage", today)
        return 0
    if not _db_preflight(settings, secrets):
        return 1
    try:
        report = reconcile_and_manage(
            settings, secrets, today=today, dry_run=dry_run, offline=offline
        )
        log.info("manage%s: %s", " [dry-run]" if dry_run else "", report.summary())
    except Exception as exc:  # noqa: BLE001 - surface + non-zero, never raise past the CLI
        log.error("manage run failed: %s", exc)
        return 1
    return 0
