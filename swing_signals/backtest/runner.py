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
    ) -> None:
        self.settings = settings
        self.bt_cfg = bt_cfg
        self.ohlcv_all = ohlcv_all
        self.index_ohlcv = index_ohlcv
        self.secrets = secrets
        self.costs = CostModel(per_side_bps=bt_cfg.cost_bps)
        self._panels: dict[str, pd.DataFrame] = {}  # per-symbol precomputed indicator panel
        # Point-in-time universe filter (None = every loaded symbol, the old behavior)
        # + the symbol->sector map that arms the live correlation cap in the engine.
        self.universe_asof = universe_asof
        self.sector_of = sector_of or {}
        # Historical VIX/VIX3M (FRED), sliced per bar so the regime gate sees the real
        # vol level (vix_max veto, backwardation) instead of only the SPY-ATR% proxy.
        self._vix = _clean_series(vix_series)
        self._vix3m = _clean_series(vix3m_series)
        # Exit rules (legacy/staged) + a per-symbol chandelier trail series (staged only).
        self.rules = build_rules(settings, bt_cfg.max_hold_bars)
        self._staged = getattr(getattr(settings, "exits", None), "mode", "legacy") == "staged"
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
            )
            cash -= spent
            n_unfilled += expired

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
                    continue
                open_heat = (
                    sum(p.risk_frac for p in positions.values())
                    + sum(p.risk_frac for p in pending.values())
                )
                risk_frac = (sig.suggested_risk_pct or 0.0) * risk_mult
                if open_heat + risk_frac > risk_cfg.portfolio_heat_cap + 1e-9:
                    n_capped += 1
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

            # 5. Equity = cash + value of what is actually held at this close.
            equity = cash + self._open_value(positions, signal_bar)
            equity_curve.append(equity)

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
            # The last equity point now reflects liquidation (with exit costs), not
            # a costless mark — keeps metrics['equity_end'] equal to realized cash.
            if equity_curve:
                equity_curve[-1] = cash + self._open_value(positions, last_bar)

        n_days = len(trading_days)
        metrics = compute_metrics(
            trades, equity_curve or [equity_start], equity_start, n_days,
            entries_by_month=charged_by_month,
            budget_cap=budget_cfg.max_entries_per_month if budget_cfg.enabled else None,
        )
        return BacktestResult(
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
        )

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
    ) -> tuple[int, int, float]:
        """Fill / age / expire resting entries against ``bar`` -> (fills, expired, spent).

        A limit fills when the bar trades through it (low <= limit), at
        min(open, limit) — an open below the limit fills at the open, better.
        After ``max_pending`` sessions the order becomes a market order filling at
        the next processed bar's open (or expires when fallback is off). Fills are
        clamped to available cash (live clamps to buying power at submit).
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

            entry_fill = self.costs.fill_long_entry(raw_px)
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
            else:
                panel = self._panel_for(ticker, df).loc[:ts]
                if len(panel) > 0:
                    sd.indicators = panel.iloc[-1].to_dict()
            result[ticker] = sd
        return result

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
            # only ever rises.
            if self._staged and pos.partial_done:
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
                    exit_fill = self.costs.fill_exit(px)
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
    peak = max(equity_start, *equity_curve)

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

    dd = (cur - peak) / peak if peak > 0 else 0.0
    if dd <= -risk_cfg.drawdown_hard_halt:
        return True, 0.0, "drawdown_hard_halt"
    if dd <= -risk_cfg.drawdown_derisk:
        return False, 0.5, "drawdown_derisk"
    return False, 1.0, ""


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
