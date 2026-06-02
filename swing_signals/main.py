"""Daily orchestrator.

Stage 1: a no-op that validates config, runs the calendar gate, and logs the
planned pipeline so the skeleton can be exercised end to end. Each later stage
fills in a step. The system only ever *produces signals*; it never places orders.
"""

from __future__ import annotations

import logging
from datetime import date

from .calendar_gate import is_holiday_aware, is_trading_day
from .config_loader import Secrets, Settings, load_secrets, load_settings
from .factors.registry import all_factors
from .output.base import ConsoleAlerter

log = logging.getLogger("swing_signals")

# The pipeline the orchestrator will run once each stage lands. Logged in the
# scaffold so the wiring is visible before any factor logic exists.
PIPELINE_PLAN = [
    "Step 0  calendar gate — is today an NYSE trading day?",
    "Stage 2 data layer — adjusted OHLCV + market context (cache, retries, staleness checks)",
    "Stage 3 per-stock factors 01/02/03/05/06 -> 0-100 sub-scores (+ reasons)",
    "Stage 3 market modules — 04 macro (size multiplier), 07 regime (hard gate)",
    "Stage 4 scoring engine — weighted composite + agreement check + ATR entry/stop/target",
    "Stage 4 gates — 07 regime veto, 04 macro multiplier, 08 risk sizing/heat/halts",
    "Stage 4 rank -> select top N -> build signals (entry zone / stop / target / R)",
    "Stage 6 persist signals + alert (Telegram primary, email backup)",
    "Step N  healthcheck ping (on success AND failure)",
]


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run(
    *,
    settings: Settings | None = None,
    secrets: Secrets | None = None,
    dry_run: bool = False,
    today: date | None = None,
) -> int:
    """Execute one daily run. Returns a process exit code (0 = success/no-op)."""
    settings = settings if settings is not None else load_settings()
    secrets = secrets if secrets is not None else load_secrets()
    configure_logging(settings.run.log_level)
    today = today or date.today()

    log.info(
        "swing-signals scaffold run | dry_run=%s | equity=$%.2f | risk=%.2f%%",
        dry_run,
        settings.account.equity,
        settings.account.risk_pct * 100,
    )

    # Step 0 — calendar gate (decouples correctness from scheduler timing).
    if not is_trading_day(today):
        log.info("%s is not a trading day (weekday gate) -> no-op exit", today)
        return 0
    if not is_holiday_aware():
        log.warning(
            "calendar gate is a weekday-only PLACEHOLDER (not holiday-aware); "
            "Stage 2 adds the real NYSE calendar"
        )

    active = settings.active_factor_weights()
    log.info(
        "watchlist: %d symbols | active factors: %s",
        len(settings.watchlist.symbols),
        active or "(none)",
    )
    registered = sorted(all_factors())
    log.info("registered factor plugins: %s", registered or "(none yet — added in Stage 3)")

    log.info("planned pipeline (scaffold wires no factor logic yet):")
    for step in PIPELINE_PLAN:
        log.info("  [plan] %s", step)

    if dry_run:
        ConsoleAlerter().send(
            subject=f"swing-signals scaffold {today}",
            body=(
                "Scaffold dry-run OK — config validated and pipeline skeleton exercised. "
                "No signals produced (expected until Stage 2+ lands the data layer and factors)."
            ),
        )

    log.info("scaffold run complete — no signals produced (expected at this stage)")
    return 0
