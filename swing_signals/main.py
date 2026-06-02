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
from .context import RunContext
from .data.loader import DataLoader
from .factors import register_builtins
from .market.f07_regime import RegimeModule
from .output.base import ConsoleAlerter
from .output.report import format_report
from .scoring.engine import generate_signals

log = logging.getLogger("swing_signals")

# Stages still to come, logged so the wiring is visible.
NEXT_STAGES = [
    "Stage 3 add factors 02 news / 03 events / 04 macro / 05 themes / 06 smart-money (keys)",
    "Stage 5 backtest harness (realistic costs, no lookahead/survivorship)",
    "Stage 6 persist signals to SQLite + alert (Telegram primary, email backup)",
    "Stage 7 cloud scheduling (unattended)",
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

    # Build the shared run context, evaluate the regime gate, then score.
    ctx = RunContext(
        settings=settings, secrets=secrets, trading_day=today,
        equity=settings.account.equity, market=market, dry_run=dry_run,
    )
    regime = RegimeModule().compute(ctx)
    log.info("regime gate: %s (score %s, size x%s, veto=%s)",
             regime.state, regime.score, regime.multiplier, regime.veto)

    active = settings.active_factor_weights()
    registered = sorted(register_builtins())
    log.info("active factors (config): %s", active or "(none)")
    log.info("registered factor plugins: %s", registered or "(none)")
    missing = [f for f in active if f not in registered]
    if missing:
        log.info("factors awaiting later stages/keys (excluded from composite): %s", missing)

    result = generate_signals(data, ctx, regime)
    log.info("signals: %d actionable LONG, %d no-trade",
             len(result.actionable), len(result.no_trades))

    report = format_report(result, settings=settings, today=today, regime=regime)
    if dry_run:
        ConsoleAlerter().send(subject=f"swing-signals {today}", body=report)
    else:
        # Real alerting (Telegram/email) + persistence land in Stage 6.
        print(report)

    log.info("next stages:")
    for stage in NEXT_STAGES:
        log.info("  [todo] %s", stage)
    log.info("run complete — %d actionable signal(s) (decision support; no orders placed)",
             len(result.actionable))
    return 0
