"""Daily orchestrator.

Stage 2: runs the calendar gate, then the data layer — pulls market context and
the watchlist, applies the fail-loud quality gate, and reports which symbols
passed vs. were skipped (with reasons). Scoring/signals are wired in Stage 4.
The system only ever *produces signals*; it never places orders.
"""

from __future__ import annotations

import logging
from datetime import date

from .calendar_gate import is_early_close, is_holiday_aware, is_trading_day
from .config_loader import Secrets, Settings, load_secrets, load_settings
from .data.loader import DataLoader
from .factors.registry import all_factors
from .output.base import ConsoleAlerter

log = logging.getLogger("swing_signals")

# Stages still to come, logged so the wiring is visible.
NEXT_STAGES = [
    "Stage 3 per-stock factors 01/02/03/05/06 -> 0-100 sub-scores (+ reasons)",
    "Stage 3 market modules — 04 macro (size multiplier), 07 regime (hard gate)",
    "Stage 4 scoring engine — weighted composite + agreement + ATR entry/stop/target",
    "Stage 4 gates — 07 regime veto, 04 macro multiplier, 08 risk sizing/heat/halts",
    "Stage 6 persist signals + alert (Telegram primary, email backup)",
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
    offline: bool = False,
    today: date | None = None,
    loader: DataLoader | None = None,
) -> int:
    """Execute one daily run. Returns a process exit code (0 = success/no-op)."""
    settings = settings if settings is not None else load_settings()
    secrets = secrets if secrets is not None else load_secrets()
    configure_logging(settings.run.log_level)
    today = today or date.today()

    log.info(
        "swing-signals run | dry_run=%s offline=%s | equity=$%.2f risk=%.2f%%",
        dry_run, offline, settings.account.equity, settings.account.risk_pct * 100,
    )

    # Step 0 — calendar gate.
    if not is_trading_day(today):
        log.info("%s is not an NYSE trading day -> no-op exit", today)
        return 0
    if is_early_close(today):
        log.info("%s is an NYSE half-day (early close)", today)
    assert is_holiday_aware()

    # Stage 2 — data layer.
    loader = loader if loader is not None else DataLoader(settings, secrets)

    market = loader.load_market_context(today, offline=offline)
    indices_loaded = [n for n in ("spy", "qqq", "iwm") if getattr(market, n) is not None]
    log.info(
        "market context | indices=%s | VIX=%s VIX3M=%s | issues=%d",
        indices_loaded or "(none)",
        f"{market.vix:.2f}" if market.vix is not None else "NA",
        f"{market.vix3m:.2f}" if market.vix3m is not None else "NA",
        len(market.issues),
    )
    for issue in market.issues:
        log.warning("market data issue: %s", issue)

    symbols = settings.watchlist.symbols
    data = loader.load_watchlist(symbols, today, offline=offline)
    passed = [s for s, sd in data.items() if sd.ok]
    skipped = {s: sd.issues for s, sd in data.items() if not sd.ok}

    log.info("watchlist data: %d/%d symbols passed quality gate", len(passed), len(symbols))
    for sym, issues in skipped.items():
        log.warning("SKIP %s (fail-loud): %s", sym, "; ".join(issues))

    active = settings.active_factor_weights()
    registered = sorted(all_factors())
    log.info("active factors (config): %s", active or "(none)")
    log.info("registered factor plugins: %s", registered or "(none yet — added in Stage 3)")
    log.info("next stages not yet wired:")
    for stage in NEXT_STAGES:
        log.info("  [todo] %s", stage)

    if dry_run:
        body = (
            f"Stage 2 data layer OK for {today}.\n"
            f"Indices loaded: {indices_loaded or 'none'} | VIX: "
            f"{market.vix if market.vix is not None else 'NA'}\n"
            f"Watchlist: {len(passed)}/{len(symbols)} passed quality"
            + (f"; skipped {sorted(skipped)}" if skipped else "")
            + "\nNo signals yet (scoring lands in Stage 4)."
        )
        ConsoleAlerter().send(subject=f"swing-signals data check {today}", body=body)

    log.info("Stage 2 run complete — data assembled; no signals produced yet (expected)")
    return 0
