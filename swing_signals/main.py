"""Daily orchestrator + backtest entry point.

The system only ever *produces signals*; it never places orders.
"""

from __future__ import annotations

import logging
from datetime import date

from .calendar_gate import is_early_close, is_trading_day
from .config_loader import Secrets, Settings, load_secrets, load_settings
from .context import RunContext
from .data.loader import DataLoader
from .factors import register_builtins
from .market.f04_macro import MacroModule
from .market.f07_regime import RegimeModule
from .output.base import ConsoleAlerter
from .output.report import format_report
from .scoring.engine import generate_signals

log = logging.getLogger("swing_signals")

NEXT_STAGES = [
    "Stage 3 add factors 02 news / 03 events / 05 themes / 06 smart-money (need API keys)",
    "Stage 6 alerting: Telegram primary + email backup + failure alerts",
    "Stage 7 cloud scheduling (unattended) + healthcheck dead-man's switch",
]


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _persist(settings: Settings, today: date, result, secrets: Secrets | None = None) -> None:
    """Best-effort write of the run + its signals to the DB (never fails the run)."""
    try:
        from .config_loader import resolve_db_url
        from .persistence.repository import persist_daily_run
    except ImportError:
        log.warning(
            "persistence enabled but SQLAlchemy not installed "
            "(pip install -e '.[db]'); skipping DB write"
        )
        return
    try:
        n = persist_daily_run(settings, today, result.actionable, secrets=secrets)
        log.info("persisted %d signal(s) to %s", n, resolve_db_url(settings, secrets))
    except Exception as exc:  # noqa: BLE001 - a DB error must not fail the signal run
        log.warning("persistence failed (continuing): %s", exc)


def _maybe_brief(settings: Settings, secrets: Secrets, today: date, regime, macro, result) -> None:
    """Best-effort daily AI brief (key-gated, never fails the run; no-op without a key)."""
    if not secrets.anthropic_api_key:
        return
    try:
        from .ai.brief import generate_brief

        text = generate_brief(
            settings, secrets, today=today, regime=regime, macro=macro, result=result
        )
        if text:
            log.info("AI brief generated (%d chars)", len(text))
    except Exception as exc:  # noqa: BLE001 - the brief must never fail the signal run
        log.warning("AI brief failed (continuing): %s", exc)


def _dispatch_report(settings: Settings, secrets: Secrets, *, subject: str, body: str) -> None:
    """Send the daily report to all configured channels; console fallback if none/all fail."""
    from .output.dispatch import build_alerters, dispatch

    alerters = build_alerters(settings, secrets)
    if not alerters:
        ConsoleAlerter().send(subject=subject, body=body)
        return
    sent = dispatch(alerters, subject, body)
    if sent == 0:
        log.warning("all alert channels failed — printing report to console instead")
        ConsoleAlerter().send(subject=subject, body=body)
    else:
        log.info("report delivered to %d channel(s): %s",
                 sent, ", ".join(a.name for a in alerters))


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
    macro = MacroModule().compute(ctx)
    log.info("macro modifier: %s (score %s, size x%s)",
             macro.state, macro.score, macro.multiplier)

    active = settings.active_factor_weights()
    registered = sorted(register_builtins())
    log.info("active factors (config): %s", active or "(none)")
    log.info("registered factor plugins: %s", registered or "(none)")
    missing = [f for f in active if f not in registered]
    if missing:
        log.info("factors awaiting later stages/keys (excluded from composite): %s", missing)

    result = generate_signals(data, ctx, regime, macro_multiplier=macro.multiplier)
    log.info("signals: %d actionable LONG, %d no-trade",
             len(result.actionable), len(result.no_trades))

    report = format_report(result, settings=settings, today=today, regime=regime, macro=macro)
    if dry_run:
        ConsoleAlerter().send(subject=f"swing-signals {today}", body=report)
    else:
        _dispatch_report(settings, secrets, subject=f"swing-signals {today}", body=report)
        if settings.run.persist:
            _persist(settings, today, result, secrets=secrets)
        _maybe_brief(settings, secrets, today, regime, macro, result)

    log.info("next stages:")
    for stage in NEXT_STAGES:
        log.info("  [todo] %s", stage)
    log.info("run complete — %d actionable signal(s) (decision support; no orders placed)",
             len(result.actionable))
    return 0


def run_backtest(
    *,
    settings: Settings | None = None,
    secrets: Secrets | None = None,
    bt_start: str | None = None,
    bt_end: str | None = None,
    cost_bps: float | None = None,
    walk_forward_folds: int = 0,
    offline: bool = False,
) -> int:
    """Run the Stage-5 backtest harness. Returns process exit code."""
    from datetime import date as _date

    from .backtest.config import BacktestCfg
    from .backtest.report import format_backtest_report
    from .backtest.runner import BacktestRunner
    from .backtest.walk_forward import walk_forward

    settings = settings if settings is not None else load_settings()
    secrets = secrets if secrets is not None else load_secrets()
    configure_logging(settings.run.log_level)

    # Merge CLI overrides with config defaults.
    raw_bt = dict(settings.backtest or {})
    if bt_start:
        raw_bt["start"] = bt_start
    if bt_end:
        raw_bt["end"] = bt_end
    if cost_bps is not None:
        raw_bt["cost_bps"] = cost_bps
    bt_cfg = BacktestCfg(**raw_bt)

    # Resolve date range.
    start = _date.fromisoformat(bt_cfg.start)
    end = _date.fromisoformat(bt_cfg.end) if bt_cfg.end != "today" else _date.today()

    log.info(
        "backtest | %s → %s | cost %.1f bps/side | max_hold %d bars | offline=%s",
        start, end, bt_cfg.cost_bps, bt_cfg.max_hold_bars, offline,
    )

    # Pull full history for watchlist + indices (cache-first if offline).
    loader = DataLoader(settings, secrets)
    all_symbols = settings.watchlist.symbols
    index_syms = list(settings.data.index_symbols)

    log.info("loading OHLCV for %d symbols + %d indices ...", len(all_symbols), len(index_syms))
    # Fetch from a far-back start so we capture enough warmup history before bt_start.
    # yfinance returns 20+ years; the runner filters to [start, end] itself.
    # In offline mode, the cache returns whatever was stored by the daily run.
    fetch_start = "2000-01-01"
    ohlcv_all: dict = {}
    for sym in all_symbols:
        df = loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=offline)
        if df is not None and len(df) > 0:
            ohlcv_all[sym] = df
        else:
            log.warning("no OHLCV for %s — skipping (no data or offline cache miss)", sym)

    index_ohlcv: dict = {}
    for sym in index_syms:
        df = loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=offline)
        if df is not None and len(df) > 0:
            index_ohlcv[sym] = df

    if not ohlcv_all:
        log.error(
            "No data loaded for any watchlist symbol. "
            "Run without --offline first to populate the cache with historical data, "
            "or check that the backtest date range (%s → %s) overlaps with cached bars.",
            start, end,
        )
        return 1

    runner = BacktestRunner(
        settings=settings, bt_cfg=bt_cfg,
        ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv, secrets=secrets,
    )

    folds = None
    if walk_forward_folds > 1:
        log.info("running %d-fold walk-forward ...", walk_forward_folds)
        folds = walk_forward(runner, start, end, n_folds=walk_forward_folds)

    log.info("running full-range backtest %s → %s ...", start, end)
    result = runner.run(start, end)

    report = format_backtest_report(result, folds=folds)
    print(report)
    log.info(
        "backtest complete: %d trades | expectancy %.3f R | max DD %.1f%%",
        result.metrics["n_trades"],
        result.metrics["expectancy"],
        result.metrics["max_drawdown"] * 100,
    )
    return 0
