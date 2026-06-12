"""BacktestRunner — the slice-and-replay engine (file 11 §3).

Design guarantee: the engine only ever sees data up to bar ``t`` (the signal bar).
The fill happens at bar ``t+1`` open — a bar that was NOT in the slice. This is
the canonical "signal on close, execute next open" convention that prevents
lookahead bias.

The runner calls the live ``generate_signals()`` function unchanged. Backtest
logic = slicing + execution + position tracking; signal logic = unchanged code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..config_loader import Secrets, Settings
from ..context import MarketContext, RunContext, SymbolData
from ..exits import build_rules, decide_exit
from ..factors import indicators as ind
from ..factors import register_builtins
from ..factors.f01_technical import build_panel
from ..market.f04_macro import MacroModule
from ..market.f07_regime import RegimeModule
from ..scoring.budget import BudgetState
from ..scoring.engine import generate_signals
from .config import BacktestCfg
from .costs import CostModel
from .metrics import Trade, compute_metrics

log = logging.getLogger("swing_signals.backtest")

_SURVIVORSHIP_WARNING = (
    "⚠  SURVIVORSHIP BIAS: yfinance excludes delisted names. "
    "This backtest only covers currently-listed stocks and will overstate returns. "
    "Use EODHD/Norgate/CRSP for a bias-free broad-universe backtest."
)


@dataclass
class _OpenPosition:
    """A position that has been filled and is currently held."""

    ticker: str
    signal_date: date
    entry_date: date
    entry_fill: float
    stop: float
    target: float
    risk_per_share: float
    shares: float
    risk_frac: float = 0.0        # fraction of equity at risk (portfolio heat bookkeeping)
    bars_open: int = 0
    effective_stop: float = 0.0   # trailed stop (staged); starts at the initial stop
    partial_done: bool = False    # scaled a partial out at the first target?
    partial_frac: float = 0.0     # fraction sold in the scale-out
    partial_fill: float = 0.0     # cost-adjusted fill price of the scale-out


@dataclass
class _PendingEntry:
    """A submitted-but-unfilled entry order (mirrors the live limit-in-zone flow).

    Live entries rest as a DAY limit at the signal day's close (entry_zone_high),
    are re-placed for up to ``max_pending_days`` sessions, then fall back to a
    market order. Modeling that here, rather than filling every signal market-at-
    next-open, keeps the backtest honest about the one-sided selection it creates:
    runners that gap away never touch the limit and fill late (or not at all),
    while names that sag below it always fill.
    """

    ticker: str
    signal_date: date
    limit: float
    stop: float
    target: float
    shares: float
    risk_frac: float
    is_market: bool = False   # market order: fills at the next processed bar's open
    bars_pending: int = 0


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[float]   # one value per trading day (after warmup)
    trading_days: list[date]    # dates corresponding to equity_curve
    metrics: dict
    bt_cfg: BacktestCfg
    n_signals_generated: int = 0
    n_no_trades: int = 0
    n_unfilled: int = 0         # signals whose entry never filled (limit aged out)
    n_capped: int = 0           # signals skipped by max-positions / heat / cash caps
    n_budget_deferred: int = 0  # signals deferred by the monthly entry budget
    n_halted_days: int = 0      # days the replayed loss-halt gates blocked new entries
    n_halt_blocked: int = 0     # actionable signals those halts refused
    # Costless side-portfolio of budget/cap-rejected signals (same entry/exit
    # mechanics, zero interaction with the real book). Settles whether the
    # ≤7/month mandate truncates the right tail or skims low-marginal-R trades —
    # without burning a selection trial. Fills assume liquidity the real book
    # might have competed for; read the expectancy, not the dollar P&L.
    rejected_shadow_trades: list[Trade] | None = None


class BacktestRunner:
    """Replay the live signal engine over historical data.

    Parameters
    ----------
    settings : Settings
        Live configuration (watchlist, factor weights, risk, universe filters).
    bt_cfg : BacktestCfg
        Backtest-specific config (date range, cost_bps, max_hold_bars).
    ohlcv_all : dict[str, pd.DataFrame]
        Full OHLCV history for every watchlist symbol, keyed by ticker.
        Must cover at least warmup_bars before ``start`` + the full [start, end] window.
    index_ohlcv : dict[str, pd.DataFrame]
        Full OHLCV for index symbols (SPY, QQQ, IWM) over the same span.
    secrets : Secrets
    """

    def __init__(
        self,
        settings: Settings,
        bt_cfg: BacktestCfg,
        ohlcv_all: dict[str, pd.DataFrame],
        index_ohlcv: dict[str, pd.DataFrame],
        secrets: Secrets,
        *,
        universe_asof: Callable[[date], frozenset[str] | None] | None = None,
        sector_of: dict[str, str] | None = None,
        vix_series: pd.Series | None = None,
        vix3m_series: pd.Series | None = None,
        earnings_history=None,
        rf_series: pd.Series | None = None,
    ) -> None:
        self.settings = settings
        self.bt_cfg = bt_cfg
        self.ohlcv_all = ohlcv_all
        self.index_ohlcv = index_ohlcv
        self.secrets = secrets
        self.costs = CostModel(
            per_side_bps=bt_cfg.cost_bps,
            stop_exit_mult=getattr(bt_cfg, "stop_exit_cost_mult", 1.0),
            market_entry_mult=getattr(bt_cfg, "market_entry_cost_mult", 1.0),
        )
        # Annualized risk-free yield in percent (e.g. FRED DGS3MO). Drives the
        # opt-in idle-cash credit (bt_cfg.rf_credit) and, whenever present, the
        # 'alpha over cash' metric — without touching the equity curve.
        self._rf = _clean_series(rf_series)
        self._panels: dict[str, pd.DataFrame] = {}  # per-symbol precomputed indicator panel
        # Point-in-time universe filter (None = every loaded symbol, the old behavior)
        # + the symbol->sector map that arms the live correlation cap in the engine.
        self.universe_asof = universe_asof
        self.sector_of = sector_of or {}
        # Historical VIX/VIX3M (FRED), sliced per bar so the regime gate sees the real
        # vol level (vix_max veto, backwardation) instead of only the SPY-ATR% proxy.
        self._vix = _clean_series(vix_series)
        self._vix3m = _clean_series(vix3m_series)
        # Historical earnings report dates (data/earnings_dates.csv via the AV
        # backfill). When present, _build_symbol_data sets next_earnings so the
        # engine's EARNINGS_SOON veto replays in backtests (it was inert before).
        self._earnings = earnings_history
        # Exit rules (legacy/staged) + a per-symbol chandelier trail series. Staged
        # trails after the partial; exits.trail_legacy_stop trails the legacy stop
        # from day one (the live owner-variant of 2026-06-12) so that variant is
        # replayable here with identical semantics.
        self.rules = build_rules(settings, bt_cfg.max_hold_bars)
        exits_cfg = getattr(settings, "exits", None)
        self._staged = getattr(exits_cfg, "mode", "legacy") == "staged"
        self._trail_legacy = (
            not self._staged and getattr(exits_cfg, "trail_legacy_stop", False)
        )
        self._chand: dict[str, pd.Series] = {}
        register_builtins()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, start: date, end: date) -> BacktestResult:
        """Run the backtest from ``start`` to ``end`` (inclusive).

        Portfolio realism mirrors the live gates: max_positions and the portfolio
        heat cap bind across days (pending entries count, as live ``active_trades``
        do), every fill is debited from CASH (no implicit leverage), and entries
        follow the live limit-in-zone → age → market-fallback mechanics.
        """
        log.warning(_SURVIVORSHIP_WARNING)

        equity_start = (
            self.bt_cfg.equity_start
            if self.bt_cfg.equity_start > 0
            else self.settings.account.equity
        )
        cash = equity_start
        equity = equity_start  # cash + open position value, updated each bar close

        # Build a master sorted list of all trading days in ANY symbol's index.
        all_bars = self._all_trading_bars(start, end)
        if len(all_bars) < 2:
            log.warning("backtest: fewer than 2 trading bars in [%s, %s]", start, end)
            return BacktestResult(
                [], [], [], compute_metrics([], [equity_start], equity_start, 0), self.bt_cfg
            )
        if (all_bars[0] - start).days > 45:
            log.warning(
                "⚠  backtest data begins %s but the configured period starts %s — the "
                "report covers a much shorter window than requested (stale/thin cache? "
                "run online or re-fetch deeper history)", all_bars[0], start,
            )

        positions: dict[str, _OpenPosition] = {}   # ticker -> open position
        pending: dict[str, _PendingEntry] = {}     # ticker -> resting entry order
        trades: list[Trade] = []
        equity_curve: list[float] = []
        trading_days: list[date] = []
        n_signals = 0
        n_no_trades = 0
        n_unfilled = 0
        n_capped = 0
        n_budget_deferred = 0
        n_halted_days = 0
        n_halt_blocked = 0
        # Exposure/utilization instrumentation (observational — never feeds back
        # into any decision): how much of the capital actually works.
        n_open_series: list[int] = []
        gross_exposure_series: list[float] = []
        cash_frac_series: list[float] = []
        n_at_cap_days = 0
        fill_counter = {"limit": 0, "market": 0}
        # Costless shadow book replaying budget/cap-rejected signals (see
        # BacktestResult.rejected_shadow_trades). Same mechanics, no cash clamp,
        # no caps, no budget charge — and zero writes back to the real book.
        shadow_positions: dict[str, _OpenPosition] = {}
        shadow_pending: dict[str, _PendingEntry] = {}
        shadow_trades: list[Trade] = []
        risk_cfg = self.settings.risk
        entry_type, max_pending, mkt_fallback = self._entry_model()
        # Budget mirror (mandate §4): the same monthly ceiling + cooldown the live
        # engine enforces, fed from simulated state — so the reported cadence is an
        # honest preview of live behavior, not an unconstrained upper bound. A charge
        # is one ENTRY SUBMISSION (mirrors live trades rows); held re-prints are free.
        budget_cfg = self.settings.budget
        charged_by_month: dict[str, int] = {}       # "YYYY-MM" -> entry submissions
        last_stop: dict[str, date] = {}             # ticker -> last stop-out date

        for signal_bar in all_bars[:-1]:  # the last bar only serves earlier fills
            trading_days.append(signal_bar)

            # 1. Exits on all open positions using TODAY's (signal_bar) OHLCV.
            closed, proceeds = self._check_exits(positions, signal_bar)
            cash += proceeds
            for trade in closed:
                trades.append(trade)
                del positions[trade.ticker]
                if trade.exit_reason in ("stop", "gap_stop"):
                    last_stop[trade.ticker] = signal_bar  # feeds the cooldown

            # 2. Work resting entry orders against TODAY's bar (they were created on
            #    an earlier signal bar — live submits post-close, works next session).
            fills, expired, spent = self._work_pending(
                pending, positions, signal_bar, cash,
                max_pending=max_pending, market_fallback=mkt_fallback,
                fill_counter=fill_counter,
            )
            cash -= spent
            n_unfilled += expired

            # 2b. Shadow book: same exit/fill mechanics on the rejected-signal side
            #     portfolio, with effectively unbounded cash (it is costless paper).
            shadow_closed, _ = self._check_exits(shadow_positions, signal_bar)
            for trade in shadow_closed:
                shadow_trades.append(trade)
                del shadow_positions[trade.ticker]
            self._work_pending(
                shadow_pending, shadow_positions, signal_bar, 1e15,
                max_pending=max_pending, market_fallback=mkt_fallback,
            )

            # 3. Build sliced data + market context, then run the LIVE signal engine.
            symbol_data = self._build_symbol_data(signal_bar)
            market_ctx = self._build_market_context(signal_bar)
            bt_settings = _clone_settings_with_equity(self.settings, equity)
            ctx = RunContext(
                settings=bt_settings, secrets=self.secrets,
                trading_day=signal_bar, equity=equity, market=market_ctx,
            )
            regime = RegimeModule().compute(ctx)
            macro = MacroModule().compute(ctx)
            mkey = f"{signal_bar:%Y-%m}"
            budget_state = None
            if budget_cfg.enabled:
                blocked = frozenset(
                    sym for sym, d in last_stop.items()
                    if (signal_bar - d).days <= budget_cfg.cooldown_days
                ) if budget_cfg.cooldown_days > 0 else frozenset()
                budget_state = BudgetState(
                    enabled=True,
                    max_entries_per_month=budget_cfg.max_entries_per_month,
                    charges_used=charged_by_month.get(mkey, 0),
                    held_symbols=frozenset(positions) | frozenset(pending),
                    cooldown_blocked=blocked,
                )
            result = generate_signals(
                symbol_data, ctx, regime, macro_multiplier=macro.multiplier,
                budget=budget_state,
            )
            n_signals += len(result.actionable)
            n_no_trades += len(result.no_trades)
            n_budget_deferred += sum(
                1 for s in result.no_trades if "BUDGET_EXHAUSTED" in s.flags
            )

            def _shadow_submit(sig, _bar=signal_bar):
                """Queue a budget/cap-rejected signal into the costless shadow book."""
                if sig.ticker in shadow_positions or sig.ticker in shadow_pending:
                    return
                limit = self._limit_price(sig)
                shares = sig.suggested_shares or 0.0
                if limit is None or limit <= 0 or shares <= 0:
                    return
                shadow_pending[sig.ticker] = _PendingEntry(
                    ticker=sig.ticker, signal_date=_bar, limit=limit,
                    stop=sig.stop_price or 0.0, target=sig.target_price or 0.0,
                    shares=shares, risk_frac=0.0,
                    is_market=(entry_type == "market"),
                )

            for sig in result.no_trades:
                if "BUDGET_EXHAUSTED" in sig.flags:
                    _shadow_submit(sig)

            # 4. Submit new entries under the LIVE portfolio constraints. Pending
            #    orders count toward the caps exactly as live active_trades do; the
            #    live loss-halt/drawdown gates are replayed first (audit P1 #4) —
            #    a halted live account would refuse these same entries.
            halt_new, risk_mult = False, 1.0
            if self.bt_cfg.replay_loss_halts:
                halt_new, risk_mult, halt_why = halt_state(
                    risk_cfg, equity_start, equity_curve, trading_days[:-1], signal_bar
                )
                if halt_new and result.actionable:
                    n_halt_blocked += len(result.actionable)
                if halt_new:
                    n_halted_days += 1
                    log.debug("%s: new entries halted (%s)", signal_bar, halt_why)
            for sig in result.actionable:
                if halt_new:
                    continue
                if sig.ticker in positions or sig.ticker in pending:
                    continue
                if len(positions) + len(pending) >= risk_cfg.max_positions:
                    n_capped += 1
                    _shadow_submit(sig)
                    continue
                open_heat = (
                    sum(p.risk_frac for p in positions.values())
                    + sum(p.risk_frac for p in pending.values())
                )
                risk_frac = (sig.suggested_risk_pct or 0.0) * risk_mult
                if open_heat + risk_frac > risk_cfg.portfolio_heat_cap + 1e-9:
                    n_capped += 1
                    _shadow_submit(sig)
                    continue
                limit = self._limit_price(sig)
                shares = (sig.suggested_shares or 0.0) * risk_mult
                if limit is None or limit <= 0 or shares <= 0:
                    continue
                pending[sig.ticker] = _PendingEntry(
                    ticker=sig.ticker, signal_date=signal_bar, limit=limit,
                    stop=sig.stop_price or 0.0, target=sig.target_price or 0.0,
                    shares=shares, risk_frac=risk_frac,
                    is_market=(entry_type == "market"),
                )
                # One submission = one budget charge (mirrors a live `trades` row).
                charged_by_month[mkey] = charged_by_month.get(mkey, 0) + 1

            # 4b. Opt-in risk-free credit on idle cash (default OFF — flipping it
            #     changes the equity curve, so every comparison must say so).
            if self.bt_cfg.rf_credit and self._rf is not None and cash > 0:
                rate = _series_asof(self._rf, signal_bar)
                if rate is not None:
                    cash *= (1.0 + rate / 100.0) ** (1.0 / 252.0)

            # 5. Equity = cash + value of what is actually held at this close.
            open_value = self._open_value(positions, signal_bar)
            equity = cash + open_value
            equity_curve.append(equity)
            n_open_series.append(len(positions))
            gross_exposure_series.append(open_value / equity if equity > 0 else 0.0)
            cash_frac_series.append(cash / equity if equity > 0 else 0.0)
            if len(positions) + len(pending) >= risk_cfg.max_positions:
                n_at_cap_days += 1

            # Increment bars held (skip positions that fill on a later bar — none
            # under the limit model, but keeps the invariant explicit).
            for pos in positions.values():
                if pos.entry_date <= signal_bar:
                    pos.bars_open += 1

        # Force-close any remaining open positions at the last processed close.
        if trading_days:
            last_bar = trading_days[-1]
            for ticker, pos in list(positions.items()):
                last_ohlcv = self.ohlcv_all.get(ticker)
                if last_ohlcv is not None:
                    row = _bar_at(last_ohlcv, last_bar)
                    if row is not None:
                        exit_price = self.costs.fill_exit(float(row["close"]))
                        trade = _make_trade(pos, last_bar, exit_price, "end_of_range")
                        trades.append(trade)
                        cash += pos.shares * (1.0 - pos.partial_frac) * exit_price
                        del positions[ticker]
            n_unfilled += len(pending)
            # Shadow book closes on the same convention so its R stats are complete.
            for ticker, pos in list(shadow_positions.items()):
                last_ohlcv = self.ohlcv_all.get(ticker)
                row = _bar_at(last_ohlcv, last_bar) if last_ohlcv is not None else None
                if row is not None:
                    exit_price = self.costs.fill_exit(float(row["close"]))
                    shadow_trades.append(_make_trade(pos, last_bar, exit_price, "end_of_range"))
                del shadow_positions[ticker]
            # The last equity point now reflects liquidation (with exit costs), not
            # a costless mark — keeps metrics['equity_end'] equal to realized cash.
            if equity_curve:
                equity_curve[-1] = cash + self._open_value(positions, last_bar)

        n_days = len(trading_days)
        metrics = compute_metrics(
            trades, equity_curve or [equity_start], equity_start, n_days,
            entries_by_month=charged_by_month,
            budget_cap=budget_cfg.max_entries_per_month if budget_cfg.enabled else None,
            exposure={
                "avg_open_positions": _mean_or_zero(n_open_series),
                "max_open_positions": max(n_open_series) if n_open_series else 0,
                "avg_gross_exposure": _mean_or_zero(gross_exposure_series),
                "max_gross_exposure": (max(gross_exposure_series)
                                       if gross_exposure_series else 0.0),
                "avg_cash_fraction": _mean_or_zero(cash_frac_series),
                "pct_days_at_position_cap": (
                    round(n_at_cap_days / n_days, 4) if n_days > 0 else 0.0
                ),
            },
            fills=dict(
                fill_counter,
                unfilled=n_unfilled,
                limit_fill_rate=(
                    round(fill_counter["limit"]
                          / (fill_counter["limit"] + fill_counter["market"] + n_unfilled), 4)
                    if (fill_counter["limit"] + fill_counter["market"] + n_unfilled) > 0
                    else None
                ),
            ),
            rejected_shadow=_shadow_summary(shadow_trades, n_budget_deferred, n_capped),
        )
        if self._rf is not None and n_days > 0:
            rf_growth = 1.0
            for d in trading_days:
                rate = _series_asof(self._rf, d)
                if rate is not None:
                    rf_growth *= (1.0 + rate / 100.0) ** (1.0 / 252.0)
            rf_cagr = rf_growth ** (252.0 / n_days) - 1.0
            metrics["rf_cagr"] = round(rf_cagr, 4)
            metrics["alpha_over_cash_cagr"] = round(metrics["cagr"] - rf_cagr, 4)
        result = BacktestResult(
            trades=trades,
            equity_curve=equity_curve or [equity],
            trading_days=trading_days,
            metrics=metrics,
            bt_cfg=self.bt_cfg,
            n_signals_generated=n_signals,
            n_no_trades=n_no_trades,
            n_unfilled=n_unfilled,
            n_capped=n_capped,
            n_budget_deferred=n_budget_deferred,
            n_halted_days=n_halted_days,
            n_halt_blocked=n_halt_blocked,
            rejected_shadow_trades=shadow_trades,
        )
        _audit_run(self.settings, start, end, result)
        return result

    def _entry_model(self) -> tuple[str, int, bool]:
        """(entry_order_type, max_pending_days, market_fallback) — the live execution model.

        Read from ``settings.broker`` when present so the backtest always exercises
        the SAME entry mechanics production runs; signal-only configs get the
        documented defaults (limit at the zone top, 3 sessions, market fallback).
        """
        bro = getattr(self.settings, "broker", None)
        if bro is not None:
            return bro.entry_order_type, bro.max_pending_days, bro.market_fallback
        return "limit", 3, True

    def _limit_price(self, sig) -> float | None:
        bro = getattr(self.settings, "broker", None)
        ref = bro.entry_price_ref if bro is not None else "zone_high"
        if ref == "zone_low":
            return sig.entry_zone_low
        if ref == "reference":
            return sig.reference_price
        return sig.entry_zone_high

    def _work_pending(
        self,
        pending: dict[str, _PendingEntry],
        positions: dict[str, _OpenPosition],
        bar: date,
        cash: float,
        *,
        max_pending: int,
        market_fallback: bool,
        fill_counter: dict[str, int] | None = None,
    ) -> tuple[int, int, float]:
        """Fill / age / expire resting entries against ``bar`` -> (fills, expired, spent).

        A limit fills when the bar trades through it (low <= limit), at
        min(open, limit) — an open below the limit fills at the open, better.
        After ``max_pending`` sessions the order becomes a market order filling at
        the next processed bar's open (or expires when fallback is off). Fills are
        clamped to available cash (live clamps to buying power at submit).
        ``fill_counter`` (when given) tallies 'limit' vs 'market' fills.
        """
        fills = 0
        expired = 0
        spent = 0.0
        for ticker, po in list(pending.items()):
            ohlcv = self.ohlcv_all.get(ticker)
            row = _bar_at(ohlcv, bar) if ohlcv is not None else None
            if row is None:
                po.bars_pending += 1
                if po.bars_pending > max_pending:  # no data and aged out -> drop
                    del pending[ticker]
                    expired += 1
                continue

            raw_px: float | None = None
            if po.is_market:
                raw_px = float(row["open"])
            elif float(row["low"]) <= po.limit:
                raw_px = min(float(row["open"]), po.limit)

            if raw_px is None:
                po.bars_pending += 1
                if po.bars_pending >= max_pending:
                    if market_fallback:
                        po.is_market = True  # fills at the next processed bar's open
                    else:
                        del pending[ticker]
                        expired += 1
                continue

            entry_fill = self.costs.fill_long_entry(raw_px, market=po.is_market)
            stop, target = po.stop, po.target
            # Live re-anchors stop/target to the actual fill at the same dollar
            # distances when it deviates >0.1% from the plan (market fallbacks).
            if po.limit > 0 and abs(entry_fill - po.limit) / po.limit > 0.001:
                dist = po.limit - stop
                if dist > 0:
                    stop = entry_fill - dist
                    if target > po.limit:
                        target = entry_fill + (target - po.limit)
            rps = entry_fill - stop
            if rps <= 0:
                del pending[ticker]
                expired += 1
                continue
            shares = po.shares
            available = max(0.0, cash - spent)
            if shares * entry_fill > available:  # no leverage: clamp to cash
                shares = available / entry_fill if entry_fill > 0 else 0.0
            if shares * entry_fill < 1.0:  # below any sensible minimum -> never filled
                del pending[ticker]
                expired += 1
                continue
            positions[ticker] = _OpenPosition(
                ticker=ticker,
                signal_date=po.signal_date,
                entry_date=bar,
                entry_fill=entry_fill,
                stop=stop,
                target=target,
                risk_per_share=rps,
                shares=shares,
                risk_frac=po.risk_frac,
                effective_stop=stop,
            )
            spent += shares * entry_fill
            fills += 1
            if fill_counter is not None:
                fill_counter["market" if po.is_market else "limit"] += 1
            del pending[ticker]
        return fills, expired, spent

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _all_trading_bars(self, start: date, end: date) -> list[date]:
        """Sorted list of trading bars across all symbols that fall in [start, end]."""
        bar_set: set[date] = set()
        all_dfs = list(self.ohlcv_all.values()) + list(self.index_ohlcv.values())
        for df in all_dfs:
            if df is None or len(df) == 0:
                continue
            for ts in df.index:
                d = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
                if start <= d <= end:
                    bar_set.add(d)
        return sorted(bar_set)

    def _build_symbol_data(self, asof: date) -> dict[str, SymbolData]:
        """Return SymbolData sliced to bars <= asof (no lookahead).

        With a point-in-time universe, only symbols that were ACTUALLY members on
        ``asof`` are scored — the broad backtest must not hand the engine names the
        live screen could not have seen that day. For symbols with enough history,
        attach the precomputed indicator row at ``asof`` (built once per symbol) so
        the technical factor reads O(1) scalars rather than recomputing every
        indicator over the slice on each bar.
        """
        ts = pd.Timestamp(asof)
        allowed = self.universe_asof(asof) if self.universe_asof is not None else None
        result: dict[str, SymbolData] = {}
        for ticker, df in self.ohlcv_all.items():
            if allowed is not None and ticker not in allowed:
                continue
            if df is None or len(df) == 0:
                sd = SymbolData(symbol=ticker)
                sd.issues.append(f"{ticker}: no OHLCV in backtest cache")
                result[ticker] = sd
                continue
            sliced = _slice_to(df, asof)
            sd = SymbolData(
                symbol=ticker,
                ohlcv=sliced if len(sliced) > 0 else None,
                sector=self.sector_of.get(ticker),
            )
            if sd.ohlcv is None or len(sd.ohlcv) < self.bt_cfg.warmup_bars:
                sd.issues.append(f"{ticker}: insufficient bars at {asof}")
            elif self._stale_at(sd.ohlcv, asof):
                # Mirror the LIVE staleness gate (data.max_staleness_days): a symbol
                # whose bars stop (delisting, cache hole) must be skipped, exactly as
                # the live loader skips it. Without this, a frame frozen at a
                # momentum high keeps re-signaling forever — zombie signals burned
                # 5 months of 2020 budget before this guard existed.
                last = sd.ohlcv.index[-1].date()
                sd.issues.append(f"{ticker}: stale at {asof} (last bar {last})")
            else:
                panel = self._panel_for(ticker, df).loc[:ts]
                if len(panel) > 0:
                    sd.indicators = panel.iloc[-1].to_dict()
                if self._earnings is not None:
                    sd.next_earnings = self._earnings.next_after(ticker, asof)
            result[ticker] = sd
        return result

    def _stale_at(self, sliced: pd.DataFrame, asof: date) -> bool:
        """True when the last bar is older than the live staleness tolerance."""
        import numpy as np

        last = sliced.index[-1]
        last_date = last.date() if hasattr(last, "date") else date.fromisoformat(str(last)[:10])
        return int(np.busday_count(last_date, asof)) > self.settings.data.max_staleness_days

    def _panel_for(self, ticker: str, df: pd.DataFrame) -> pd.DataFrame:
        """Indicator panel over a symbol's full history, computed once and cached."""
        panel = self._panels.get(ticker)
        if panel is None:
            panel = build_panel(df)
            self._panels[ticker] = panel
        return panel

    def _build_market_context(self, asof: date) -> MarketContext:
        """Return MarketContext with index data sliced to <= asof.

        VIX/VIX3M come from the real FRED history when the runner was given it —
        the last published value on/before ``asof`` (day-``asof`` close counts: the
        signal is computed on that close, same convention as the SPY bar) — so the
        regime's vix_max veto and backwardation penalty replay history. Without
        the series, both stay ``None`` and the regime module runs its SPY-ATR%
        proxy, the identical code path live uses when no FRED key is present.
        """
        def _s(sym: str) -> pd.DataFrame | None:
            df = self.index_ohlcv.get(sym)
            if df is None:
                return None
            sl = _slice_to(df, asof)
            return sl if len(sl) >= self.bt_cfg.warmup_bars else None

        return MarketContext(
            spy=_s("SPY"), qqq=_s("QQQ"), iwm=_s("IWM"),
            vix=_series_asof(self._vix, asof),
            vix3m=_series_asof(self._vix3m, asof),
        )

    def _check_exits(
        self, positions: dict[str, _OpenPosition], bar: date
    ) -> tuple[list[Trade], float]:
        """Trail, scale, and exit every open position via the shared exit machine.

        Returns (closed trades, cash proceeds) — sale proceeds (partials included)
        flow back to cash so the runner's accounting stays leverage-free.
        """
        closed: list[Trade] = []
        proceeds = 0.0
        for ticker, pos in list(positions.items()):
            ohlcv = self.ohlcv_all.get(ticker)
            if ohlcv is None:
                continue
            row = _bar_at(ohlcv, bar)
            if row is None:
                continue

            # Trail the chandelier only AFTER the partial is taken (staged). Before
            # that the fixed initial stop stands, so a trade can reach its +2R target
            # instead of being clipped near breakeven by an early trail. The stop
            # only ever rises. trail_legacy_stop trails from day one instead — the
            # live owner-variant, mirrored here so it is testable.
            if (self._staged and pos.partial_done) or self._trail_legacy:
                chand = self._chandelier_at(ticker, bar)
                if chand is not None and chand > pos.effective_stop:
                    pos.effective_stop = chand

            actions = decide_exit(
                entry_fill=pos.entry_fill, risk_per_share=pos.risk_per_share,
                effective_stop=pos.effective_stop, target_1=pos.target,
                partial_done=pos.partial_done, bars_held=pos.bars_open,
                bar_open=float(row["open"]), bar_high=float(row["high"]),
                bar_low=float(row["low"]), bar_close=float(row["close"]),
                rules=self.rules,
            )
            for act in actions:
                if act.kind == "MOVE_STOP":
                    if act.price is not None and act.price > pos.effective_stop:
                        pos.effective_stop = act.price
                elif act.kind == "SCALE_OUT":
                    px = act.price if act.price is not None else pos.target
                    pos.partial_done = True
                    pos.partial_frac = act.fraction or 0.0
                    pos.partial_fill = self.costs.fill_exit(px)
                    proceeds += pos.shares * pos.partial_frac * pos.partial_fill
                elif act.kind == "EXIT_ALL":
                    px = act.price if act.price is not None else float(row["close"])
                    exit_fill = self.costs.fill_exit(px, reason=act.reason)
                    closed.append(_make_trade(pos, bar, exit_fill, act.reason))
                    proceeds += pos.shares * (1.0 - pos.partial_frac) * exit_fill
                    break  # fully closed — stop processing this position

        return closed, proceeds

    def _chandelier_at(self, ticker: str, bar: date) -> float | None:
        """Chandelier trail value at ``bar`` from a per-symbol cached causal series."""
        series = self._chand.get(ticker)
        if series is None:
            df = self.ohlcv_all.get(ticker)
            if df is None:
                return None
            lb = self.settings.risk.chandelier_lookback
            mult = self.settings.risk.chandelier_multiple
            # .shift(1): the stop in force during bar t is the chandelier computed
            # through bar t-1. Without the shift we'd raise the stop using bar t's
            # OWN high and then check bar t's low against it — a same-bar lookahead
            # that stops trades out the instant they trail (a classic backtest bug).
            raw = df["high"].rolling(lb).max() - mult * ind.atr(
                df["high"], df["low"], df["close"], lb
            )
            series = raw.shift(1)
            self._chand[ticker] = series
        try:
            v = series.loc[pd.Timestamp(bar)]
        except KeyError:
            return None
        if isinstance(v, pd.Series):
            v = v.iloc[-1]
        return None if pd.isna(v) else float(v)

    def _open_value(self, positions: dict[str, _OpenPosition], bar: date) -> float:
        """Market value of the still-held shares at ``bar`` close.

        Positions only exist once filled (entry_date <= bar, intraday under the
        limit model), so there is no future-fill mark; the scaled-out piece is
        already realised into cash and never re-marked. A symbol with no bar today
        (halt/gap in data) is marked at its last fill price — conservative and rare.
        """
        total = 0.0
        for ticker, pos in positions.items():
            if pos.entry_date > bar:
                continue  # defensive: not yet filled
            open_shares = pos.shares * (1.0 - pos.partial_frac)
            ohlcv = self.ohlcv_all.get(ticker)
            row = _bar_at(ohlcv, bar) if ohlcv is not None else None
            px = float(row["close"]) if row is not None else pos.entry_fill
            total += open_shares * px
        return total


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _mean_or_zero(values: list) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _shadow_summary(shadow_trades: list[Trade], n_budget: int, n_capped: int) -> dict:
    """R-stats of the rejected-signal shadow book (the budget-mandate evidence)."""
    rs = [t.realized_r for t in shadow_trades]
    winners = [r for r in rs if r > 0]
    losers = [r for r in rs if r <= 0]
    return {
        "n": len(rs),
        "n_budget_rejected": n_budget,
        "n_cap_rejected": n_capped,
        "expectancy": round(sum(rs) / len(rs), 4) if rs else None,
        "win_rate": round(len(winners) / len(rs), 4) if rs else None,
        "profit_factor": (
            round(sum(winners) / abs(sum(losers)), 4)
            if losers and sum(losers) != 0
            else None
        ),
    }


def _audit_run(settings, start: date, end: date, result: BacktestResult) -> None:
    """Append one line per BacktestRunner.run() to a runs audit file (best-effort).

    The trial ledger counts what a human LOOKED at; this counts what actually RAN,
    so an unledgered look (ad-hoc script, --no-ledger flag) is reconstructable
    instead of invisible — under-counting N is the failure mode DSR polices.
    Opt-out with SWING_RUNS_AUDIT=off (tests do); never breaks a run.
    """
    import hashlib
    import json
    import os

    target = os.environ.get("SWING_RUNS_AUDIT", "")
    if target.lower() in ("off", "0", "disabled"):
        return
    try:
        from pathlib import Path

        from .trials import DEFAULT_LEDGER

        path = Path(target) if target else Path(DEFAULT_LEDGER).parent / "runs.jsonl"
        cfg_md5 = hashlib.md5(
            settings.model_dump_json().encode("utf-8")
        ).hexdigest()[:12]
        line = json.dumps({
            "date": str(date.today()),
            "window": f"{start}..{end}",
            "config_md5": cfg_md5,
            "n_trades": result.metrics.get("n_trades"),
            "expectancy_r": result.metrics.get("expectancy"),
            "equity_end": result.metrics.get("equity_end"),
        })
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001, S110 - the audit must never break a run
        pass


def halt_state(
    risk_cfg,
    equity_start: float,
    equity_curve: list[float],
    curve_days: list[date],
    today: date,
) -> tuple[bool, float, str]:
    """Replay the live loss-halt/drawdown gates from the simulated equity curve.

    Mirrors ``broker/gates.py``: losses are measured from the last equity value
    BEFORE each period started (yesterday / ISO-week start / month start), and
    drawdown from the running peak — all using yesterday's close (the live gate
    runs pre-trade off the latest snapshot, never today's unknown close).

    Returns ``(halt_new_entries, risk_multiplier, reason)``.
    """
    if not equity_curve:
        return False, 1.0, ""
    cur = equity_curve[-1]

    def _loss_vs(baseline: float) -> float:
        return (cur - baseline) / baseline if baseline > 0 else 0.0

    # Daily: vs the close before yesterday's session.
    daily_base = equity_curve[-2] if len(equity_curve) >= 2 else equity_start
    if _loss_vs(daily_base) <= -risk_cfg.daily_loss_halt:
        return True, 0.0, "daily_loss_halt"

    # Weekly / monthly: vs the last close before the current period began.
    week_key = today.isocalendar()[:2]
    month_key = (today.year, today.month)
    week_base: float | None = None
    month_base: float | None = None
    for i in range(len(curve_days) - 1, -1, -1):
        d = curve_days[i]
        if week_base is None and d.isocalendar()[:2] != week_key:
            week_base = equity_curve[i]
        if month_base is None and (d.year, d.month) != month_key:
            month_base = equity_curve[i]
        if week_base is not None and month_base is not None:
            break
    if _loss_vs(week_base if week_base is not None else equity_start) <= -risk_cfg.weekly_loss_halt:
        return True, 0.0, "weekly_loss_halt"
    if (
        _loss_vs(month_base if month_base is not None else equity_start)
        <= -risk_cfg.monthly_loss_halt
    ):
        return True, 0.0, "monthly_loss_halt"

    dd = _trailing_dd(equity_curve, equity_start, len(equity_curve) - 1, risk_cfg)
    if dd <= -risk_cfg.drawdown_hard_halt:
        # Resume ramp (non-absorbing brake): after `halt_resume_days` consecutive
        # bars at/under the hard-halt line, re-open entries at a reduced size
        # instead of staying dead forever. resume_days == 0 keeps the original
        # absorbing behavior. We only need "has the breach persisted >= resume
        # days", so the walk-back is bounded by resume_days.
        resume = getattr(risk_cfg, "halt_resume_days", 0)
        if resume > 0:
            i, run_len = len(equity_curve) - 1, 0
            hard_halt = -risk_cfg.drawdown_hard_halt
            while i >= 0 and run_len < resume:
                if _trailing_dd(equity_curve, equity_start, i, risk_cfg) > hard_halt:
                    break
                run_len += 1
                i -= 1
            if run_len >= resume:
                return False, risk_cfg.halt_resume_risk_mult, "drawdown_halt_resumed"
        return True, 0.0, "drawdown_hard_halt"
    if dd <= -risk_cfg.drawdown_derisk:
        return False, 0.5, "drawdown_derisk"
    return False, 1.0, ""


def _trailing_dd(
    equity_curve: list[float], equity_start: float, i: int, risk_cfg
) -> float:
    """Drawdown of ``equity_curve[i]`` vs its (possibly trailing) high-water mark.

    ``drawdown_peak_lookback`` bounds the peak to the last N bars ending at ``i``
    so an ancient high cannot anchor the halt forever; 0 = all-time peak (the
    original behavior). ``equity_start`` seeds the peak only while the window
    still reaches back to the start of the simulation.
    """
    lookback = getattr(risk_cfg, "drawdown_peak_lookback", 0)
    lo = 0 if lookback <= 0 else max(0, i + 1 - lookback)
    window_peak = max(equity_curve[lo:i + 1])
    if lo == 0:
        window_peak = max(equity_start, window_peak)
    cur = equity_curve[i]
    return (cur - window_peak) / window_peak if window_peak > 0 else 0.0


def _clean_series(s: pd.Series | None) -> pd.Series | None:
    """Drop NaNs and normalize the index to Timestamps, sorted ascending."""
    if s is None or len(s) == 0:
        return None
    s = s.dropna()
    if len(s) == 0:
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _series_asof(s: pd.Series | None, asof: date) -> float | None:
    """Last value of ``s`` on/before ``asof`` (None if absent or all-future)."""
    if s is None:
        return None
    sl = s.loc[: pd.Timestamp(asof)]
    return float(sl.iloc[-1]) if len(sl) else None


def _slice_to(df: pd.DataFrame, asof: date) -> pd.DataFrame:
    """Return rows whose DatetimeIndex date <= asof (no lookahead).

    Vectorized: the index is a normalized (midnight) DatetimeIndex, so a single
    boolean comparison against ``Timestamp(asof)`` keeps every bar on/through the
    as-of date and drops the future. (Previously a per-row Python ``.apply`` —
    O(bars) interpreted calls per symbol per day, which dominated backtest time.)
    """
    return df[df.index <= pd.Timestamp(asof)]


def _bar_at(df: pd.DataFrame, d: date) -> pd.Series | None:
    """Return the row for date ``d``, or None if not present.

    O(1) hashed index lookup (was a linear scan over the whole index).
    """
    ts = pd.Timestamp(d)
    try:
        row = df.loc[ts]
    except KeyError:
        return None
    # normalize_ohlcv de-dups the index, but stay defensive: a duplicate date
    # would yield a DataFrame here — take the last bar for that date.
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    return row


def _make_trade(pos: _OpenPosition, exit_date: date, exit_fill: float, reason: str) -> Trade:
    return Trade(
        ticker=pos.ticker,
        signal_date=pos.signal_date,
        entry_date=pos.entry_date,
        entry_fill=pos.entry_fill,
        exit_date=exit_date,
        exit_fill=exit_fill,
        exit_reason=reason,
        stop=pos.stop,
        target=pos.target,
        risk_per_share=pos.risk_per_share,
        shares=pos.shares,
        bars_held=pos.bars_open,
        partial_frac=pos.partial_frac,
        partial_fill=pos.partial_fill,
    )


def _clone_settings_with_equity(settings: Settings, equity: float) -> Settings:
    """Return a copy of settings with account.equity updated to the current BT equity.

    Uses ``model_copy`` (a plain deep copy, no validation) rather than
    ``model_dump()`` + ``Settings(**raw)``, which re-ran every Pydantic validator
    over the whole config tree once per trading day.
    """
    clone = settings.model_copy(deep=True)
    clone.account.equity = equity
    return clone
