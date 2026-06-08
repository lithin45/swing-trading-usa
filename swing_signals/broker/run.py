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
    try:
        report = submit_entries(settings, secrets, today=today, dry_run=dry_run)
        log.info("trade%s: %s", " [dry-run]" if dry_run else "", report.summary())
    except Exception as exc:  # noqa: BLE001 - surface + non-zero, never raise past the CLI
        log.error("trade run failed: %s", exc)
        return 1
    return 0
