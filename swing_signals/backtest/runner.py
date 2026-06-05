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
from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..config_loader import Secrets, Settings
from ..context import MarketContext, RunContext, SymbolData
from ..factors import register_builtins
from ..factors.f01_technical import build_panel
from ..market.f07_regime import RegimeModule
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
    bars_open: int = 0


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[float]   # one value per trading day (after warmup)
    trading_days: list[date]    # dates corresponding to equity_curve
    metrics: dict
    bt_cfg: BacktestCfg
    n_signals_generated: int = 0
    n_no_trades: int = 0


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
    ) -> None:
        self.settings = settings
        self.bt_cfg = bt_cfg
        self.ohlcv_all = ohlcv_all
        self.index_ohlcv = index_ohlcv
        self.secrets = secrets
        self.costs = CostModel(per_side_bps=bt_cfg.cost_bps)
        self._panels: dict[str, pd.DataFrame] = {}  # per-symbol precomputed indicator panel
        register_builtins()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, start: date, end: date) -> BacktestResult:
        """Run the backtest from ``start`` to ``end`` (inclusive)."""
        log.warning(_SURVIVORSHIP_WARNING)

        equity = (
            self.bt_cfg.equity_start
            if self.bt_cfg.equity_start > 0
            else self.settings.account.equity
        )
        equity_start = equity   # preserve for metrics (equity is mutated during the run)

        # Build a master sorted list of all trading days in ANY symbol's index.
        all_bars = self._all_trading_bars(start, end)
        if len(all_bars) < 2:
            log.warning("backtest: fewer than 2 trading bars in [%s, %s]", start, end)
            return BacktestResult(
                [], [], [], compute_metrics([], [equity_start], equity_start, 0), self.bt_cfg
            )

        positions: dict[str, _OpenPosition] = {}  # ticker -> open position
        trades: list[Trade] = []
        equity_curve: list[float] = []
        trading_days: list[date] = []
        n_signals = 0
        n_no_trades = 0

        for bar_idx, signal_bar in enumerate(all_bars):
            # No bar_idx warmup guard: the full historical OHLCV slice always
            # gives the engine enough data for SMA-200 etc. Per-symbol checks in
            # _build_symbol_data handle any symbol-level insufficiency.
            # Need bar_idx+1 for next-open fill — skip the last bar.
            if bar_idx + 1 >= len(all_bars):
                break

            fill_bar = all_bars[bar_idx + 1]
            trading_days.append(signal_bar)

            # 1. Check exits on all open positions using TODAY's (signal_bar) OHLCV.
            closed = self._check_exits(positions, signal_bar)
            for trade in closed:
                trades.append(trade)
                equity += trade.pnl_dollars
                del positions[trade.ticker]

            # 2. Build sliced data for the signal bar.
            symbol_data = self._build_symbol_data(signal_bar)
            market_ctx = self._build_market_context(signal_bar)

            # Override equity in settings clone so sizing reflects current BT equity.
            bt_settings = _clone_settings_with_equity(self.settings, equity)
            ctx = RunContext(
                settings=bt_settings, secrets=self.secrets,
                trading_day=signal_bar, equity=equity, market=market_ctx,
            )

            # 3. Generate signals — the live function, no modifications.
            regime = RegimeModule().compute(ctx)
            result = generate_signals(symbol_data, ctx, regime)
            n_signals += len(result.actionable)
            n_no_trades += len(result.no_trades)

            # 4. Open new positions at the NEXT bar's open (fill_bar).
            for sig in result.actionable:
                if sig.ticker in positions:
                    continue  # already holding this ticker
                next_ohlcv = self.ohlcv_all.get(sig.ticker)
                if next_ohlcv is None:
                    continue
                next_row = _bar_at(next_ohlcv, fill_bar)
                if next_row is None:
                    continue
                # Lookahead guard: entry_fill is taken from fill_bar (NOT signal_bar).
                entry_fill = self.costs.fill_long_entry(float(next_row["open"]))
                rps = entry_fill - (sig.stop_price or 0.0)
                if rps <= 0:
                    continue
                shares = sig.suggested_shares or 0.0
                positions[sig.ticker] = _OpenPosition(
                    ticker=sig.ticker,
                    signal_date=signal_bar,
                    entry_date=fill_bar,
                    entry_fill=entry_fill,
                    stop=sig.stop_price or 0.0,
                    target=sig.target_price or 0.0,
                    risk_per_share=rps,
                    shares=shares,
                )

            # 5. Mark-to-market open positions and update equity.
            mtm_pnl = self._mtm(positions, signal_bar)
            equity_curve.append(equity + mtm_pnl)

            # Increment bars_open for time-stop tracking.
            for pos in positions.values():
                pos.bars_open += 1

        # Force-close any remaining open positions at last close.
        if all_bars and trading_days:
            last_bar = trading_days[-1]
            for ticker, pos in list(positions.items()):
                last_ohlcv = self.ohlcv_all.get(ticker)
                if last_ohlcv is not None:
                    row = _bar_at(last_ohlcv, last_bar)
                    if row is not None:
                        exit_price = self.costs.fill_exit(float(row["close"]))
                        trade = _make_trade(pos, last_bar, exit_price, "end_of_range")
                        trades.append(trade)
                        equity += trade.pnl_dollars

        n_days = len(trading_days)
        metrics = compute_metrics(trades, equity_curve or [equity_start], equity_start, n_days)
        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve or [equity],
            trading_days=trading_days,
            metrics=metrics,
            bt_cfg=self.bt_cfg,
            n_signals_generated=n_signals,
            n_no_trades=n_no_trades,
        )

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

        For symbols with enough history, attach the precomputed indicator row at
        ``asof`` (built once per symbol) so the technical factor reads O(1) scalars
        rather than recomputing every indicator over the slice on each bar.
        """
        ts = pd.Timestamp(asof)
        result: dict[str, SymbolData] = {}
        for ticker, df in self.ohlcv_all.items():
            if df is None or len(df) == 0:
                sd = SymbolData(symbol=ticker)
                sd.issues.append(f"{ticker}: no OHLCV in backtest cache")
                result[ticker] = sd
                continue
            sliced = _slice_to(df, asof)
            sd = SymbolData(symbol=ticker, ohlcv=sliced if len(sliced) > 0 else None)
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

        VIX/VIX3M are left as ``None`` so the regime module runs its own SPY-ATR%
        volatility proxy — the *identical* code path the live engine uses when no
        FRED key is present, so backtest regime calls match live regime calls.
        (Previously this synthesized a notional VIX from ATR% and fed it through
        the VIX-level bins, a different transfer function than live. For higher
        fidelity a future version can feed real historical VIX from FRED — VIXCLS
        has history back to 1990 — sliced per bar.)
        """
        def _s(sym: str) -> pd.DataFrame | None:
            df = self.index_ohlcv.get(sym)
            if df is None:
                return None
            sl = _slice_to(df, asof)
            return sl if len(sl) >= self.bt_cfg.warmup_bars else None

        return MarketContext(spy=_s("SPY"), qqq=_s("QQQ"), iwm=_s("IWM"))

    def _check_exits(
        self, positions: dict[str, _OpenPosition], bar: date
    ) -> list[Trade]:
        """Check stop, target, and time-stop for every open position."""
        closed: list[Trade] = []
        for ticker, pos in list(positions.items()):
            ohlcv = self.ohlcv_all.get(ticker)
            if ohlcv is None:
                continue
            row = _bar_at(ohlcv, bar)
            if row is None:
                continue

            open_ = float(row["open"])
            low = float(row["low"])
            high = float(row["high"])
            close = float(row["close"])

            exit_price: float | None = None
            reason = ""

            if open_ < pos.stop:          # gap-through stop
                exit_price = self.costs.fill_exit(open_)
                reason = "gap_stop"
            elif low <= pos.stop:          # stop hit intraday
                exit_price = self.costs.fill_exit(pos.stop)
                reason = "stop"
            elif high >= pos.target:       # target hit
                exit_price = self.costs.fill_exit(pos.target)
                reason = "target"
            elif pos.bars_open >= self.bt_cfg.max_hold_bars:  # time-stop
                exit_price = self.costs.fill_exit(close)
                reason = "time_stop"

            if exit_price is not None:
                closed.append(_make_trade(pos, bar, exit_price, reason))

        return closed

    def _mtm(self, positions: dict[str, _OpenPosition], bar: date) -> float:
        """Mark-to-market unrealised P&L of all open positions at bar close.

        A position opened on this bar fills at the NEXT bar's open, so it is not
        yet held at this close — skip it (``bars_open == 0``) so it is not marked
        against its future fill price. That was a 1-bar lookahead in the equity
        curve, distorting Sharpe/Sortino/drawdown (the R-based trade metrics were
        unaffected, since they use the real entry_fill).
        """
        total = 0.0
        for ticker, pos in positions.items():
            if pos.bars_open <= 0:
                continue
            ohlcv = self.ohlcv_all.get(ticker)
            if ohlcv is None:
                continue
            row = _bar_at(ohlcv, bar)
            if row is None:
                continue
            total += (float(row["close"]) - pos.entry_fill) * pos.shares
        return total


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

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
