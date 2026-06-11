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


def _now_eastern():
    """Current US/Eastern time — separate so tests can monkeypatch the clock."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/New_York"))


def session_still_open(today: date) -> bool:
    """True when a run targets TODAY while the NYSE session is still trading.

    Today's bar is then partial — indicators, ATR levels, and the regime gate
    would all be computed on an incomplete candle (audit P1 #2: the 21:30 UTC
    schedule is safe by accident only; a manual midday run is not). A past
    ``today`` is always final; early-close days close at 13:00 ET.
    """
    now_et = _now_eastern()
    if now_et.date() != today or not is_trading_day(today):
        return False
    close_hour = 13 if is_early_close(today) else 16
    return now_et.hour < close_hour


def _persist(settings: Settings, today: date, result, secrets: Secrets | None = None) -> None:
    """Best-effort write of the run + its signals/rejections to the DB (never fails the run)."""
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
        n = persist_daily_run(
            settings, today, result.actionable, secrets=secrets, no_trades=result.no_trades
        )
        log.info("persisted %d signal(s) to %s", n, resolve_db_url(settings, secrets))
    except Exception as exc:  # noqa: BLE001 - a DB error must not fail the signal run
        log.warning("persistence failed (continuing): %s", exc)


def _build_budget_state(settings: Settings, secrets: Secrets, today: date):
    """Budget state from the DB, degrading loudly: a DB/dependency failure can lose the
    cross-day count (today still can't exceed the cap), never the whole ceiling."""
    if not settings.budget.enabled:
        return None
    from .scoring.budget import BudgetState  # dependency-free dataclass

    fallback = BudgetState(
        enabled=True, max_entries_per_month=settings.budget.max_entries_per_month
    )
    try:
        from .config_loader import resolve_db_url
        from .persistence.db import make_engine, session_scope
        from .scoring.budget import build_budget_state
    except ImportError:
        log.warning(
            "budget enabled but SQLAlchemy not installed — month-to-date entries unknown; "
            "today is still capped at %d", fallback.max_entries_per_month,
        )
        return fallback
    try:
        with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
            return build_budget_state(settings, session, today)
    except Exception as exc:  # noqa: BLE001 - budget query failure must not kill the run
        log.warning(
            "budget state query failed (%s) — month-to-date entries unknown; "
            "today is still capped at %d", exc, fallback.max_entries_per_month,
        )
        return fallback


def _attach_earnings(settings: Settings, secrets: Secrets, data, today: date,
                     *, offline: bool) -> None:
    """Populate ``SymbolData.next_earnings`` from the calendar (loud when unscreened)."""
    if not settings.earnings.enabled:
        return
    from datetime import timedelta

    from .data.earnings import EarningsCalendar

    cal = EarningsCalendar(
        secrets.finnhub_api_key.get_secret_value() if secrets.finnhub_api_key else None
    )
    if not cal.available:
        log.warning("earnings veto enabled but no Finnhub key — entries not earnings-screened")
        return
    if offline:
        log.warning("offline run — entries not earnings-screened")
        return
    window_end = today + timedelta(days=settings.earnings.veto_days_before + 4)
    edates = cal.upcoming(today, window_end)
    if edates is None:
        log.warning("earnings calendar unavailable — entries not earnings-screened today")
        return
    hits = 0
    for sym, sd in data.items():
        sd.next_earnings = edates.get(sym)
        hits += 1 if sd.next_earnings is not None else 0
    log.info("earnings calendar: %d upcoming print(s) within %s", hits, window_end)


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
    allow_partial_bar: bool = False,
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

    # Step 0b — bar-finality guard: a mid-session run computes signals on a PARTIAL
    # bar (wrong ATR, wrong close, wrong regime). Refuse unless explicitly overridden.
    if session_still_open(today):
        if not allow_partial_bar:
            log.error(
                "NYSE session is still open — today's bar is incomplete and signals "
                "computed on it are unreliable. Re-run after the 16:00 ET close, or "
                "pass --allow-partial-bar to override."
            )
            return 2
        log.warning("running on a PARTIAL intraday bar (--allow-partial-bar) — "
                    "levels and scores use an incomplete candle")

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

    # Universe: static list, or the dynamic screen (S&P 500 + themes + news movers).
    from .universe.screen import resolve_universe
    from .universe.thematic import sector_map

    symbols = resolve_universe(settings, secrets, loader, today, offline=offline)
    log.info("universe: %d symbol(s) (source=%s)", len(symbols), settings.watchlist.source)
    data = loader.load_watchlist(symbols, today, offline=offline)
    smap = sector_map()
    for sym, sd in data.items():
        sd.sector = smap.get(sym)  # feeds the correlation cap
    _attach_earnings(settings, secrets, data, today, offline=offline)  # feeds EARNINGS_SOON
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

    budget_state = _build_budget_state(settings, secrets, today)
    result = generate_signals(
        data, ctx, regime, macro_multiplier=macro.multiplier, budget=budget_state
    )
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
    universe: str = "watchlist",
    include_themes: bool = False,
    dump_trades: str | None = None,
) -> int:
    """Run the Stage-5 backtest harness. Returns process exit code."""
    from datetime import date as _date
    from datetime import timedelta as _timedelta

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
        "backtest | %s → %s | cost %.1f bps/side | max_hold %d bars | universe=%s | offline=%s",
        start, end, bt_cfg.cost_bps, bt_cfg.max_hold_bars, universe, offline,
    )

    loader = DataLoader(settings, secrets)
    index_syms = list(settings.data.index_symbols)

    # Resolve the symbol set + the per-bar membership filter.
    universe_asof = None
    sector_of: dict[str, str] | None = None
    if universe == "sp500":
        from .universe.membership import members_asof, members_union
        from .universe.thematic import sector_map, thematic_symbols

        union = members_union(start, end)
        if union is None:
            log.error(
                "--universe sp500 needs config/sp500_changes.csv — run "
                "`swing-signals refresh-sp500` once (and commit the CSVs)."
            )
            return 1
        themes: frozenset[str] = thematic_symbols() if include_themes else frozenset()
        all_symbols = sorted(union | themes)
        sector_of = sector_map()
        if include_themes:
            log.warning(
                "⚠  --include-themes adds TODAY'S curated theme list to history — that is "
                "selection bias by construction; use for live-parity exploration only."
            )

        def universe_asof(asof: _date, _themes=themes):  # noqa: ANN202
            m = members_asof(asof)
            return (m | _themes) if m is not None else None

        # Deep history for 500+ names is heavy; fetch only what the warmup needs
        # (~260 trading bars for momentum + slack) instead of 20+ years.
        fetch_start = (start - _timedelta(days=600)).isoformat()
    else:
        all_symbols = settings.watchlist.symbols
        # Static 10-name list: cheap to fetch deep history; the runner slices.
        fetch_start = "2000-01-01"

    log.info("loading OHLCV for %d symbols + %d indices ...", len(all_symbols), len(index_syms))
    # In offline mode, the cache returns whatever was stored by earlier runs.
    ohlcv_all: dict = {}
    missing: list[str] = []

    def _fetch(sym: str):
        try:
            return sym, loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=offline)
        except Exception as exc:  # noqa: BLE001 - one symbol must not kill the load
            log.debug("fetch failed for %s: %s", sym, exc)
            return sym, None

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=settings.data.max_workers) as pool:
        for sym, df in pool.map(_fetch, all_symbols):
            if df is not None and len(df) > 0:
                ohlcv_all[sym] = df
            else:
                missing.append(sym)
    if missing:
        log.warning(
            "no OHLCV for %d/%d symbols (delisted/renamed/offline-miss) — the backtest "
            "can select but not trade them; this is the residual survivorship gap%s",
            len(missing), len(all_symbols),
            f": {', '.join(sorted(missing)[:15])}{' …' if len(missing) > 15 else ''}",
        )

    index_ohlcv: dict = {}
    for sym in index_syms:
        df = loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=offline)
        if df is not None and len(df) > 0:
            index_ohlcv[sym] = df

    if not ohlcv_all:
        log.error(
            "No data loaded for any universe symbol. "
            "Run without --offline first to populate the cache with historical data, "
            "or check that the backtest date range (%s → %s) overlaps with cached bars.",
            start, end,
        )
        return 1

    # Historical VIX/VIX3M for the regime gate (sliced per bar by the runner). With
    # no FRED key the runner falls back to the SPY-ATR% proxy, exactly like live.
    vix_series = vix3m_series = None
    if not offline:
        from .data.fred_provider import FredProvider

        fred = FredProvider(
            secrets.fred_api_key.get_secret_value() if secrets.fred_api_key else None
        )
        if fred.available:
            try:
                vix_series = fred.get_series(settings.data.fred_series.get("vix", "VIXCLS"))
                vix3m_series = fred.get_series(settings.data.fred_series.get("vix3m", "VXVCLS"))
                log.info("historical VIX/VIX3M loaded from FRED for the regime gate")
            except Exception as exc:  # noqa: BLE001 - degrade to the ATR proxy
                log.warning("FRED VIX history unavailable (%s) — using the SPY-ATR%% proxy", exc)
        else:
            log.info("no FRED key — backtest regime uses the SPY-ATR%% proxy (same as live)")

    runner = BacktestRunner(
        settings=settings, bt_cfg=bt_cfg,
        ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv, secrets=secrets,
        universe_asof=universe_asof, sector_of=sector_of,
        vix_series=vix_series, vix3m_series=vix3m_series,
    )

    folds = None
    if walk_forward_folds > 1:
        log.info("running %d-fold walk-forward ...", walk_forward_folds)
        folds = walk_forward(runner, start, end, n_folds=walk_forward_folds)

    log.info("running full-range backtest %s → %s ...", start, end)
    result = runner.run(start, end)

    report = format_backtest_report(result, folds=folds)
    print(report)
    if dump_trades:
        import csv as _csv
        from dataclasses import asdict as _asdict
        from dataclasses import fields as _fields

        from .backtest.metrics import Trade as _Trade

        with open(dump_trades, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=[f.name for f in _fields(_Trade)])
            w.writeheader()
            for t in result.trades:
                w.writerow(_asdict(t))
        log.info("trade ledger written to %s (%d trades)", dump_trades, len(result.trades))
    log.info(
        "backtest complete: %d trades | expectancy %.3f R | max DD %.1f%%",
        result.metrics["n_trades"],
        result.metrics["expectancy"],
        result.metrics["max_drawdown"] * 100,
    )
    return 0
