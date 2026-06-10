"""Backtest report formatter (file 11 §6 + §8 validation checklist).

Produces a plaintext summary with:
- Date range, cost model, survivorship-bias caveat (always shown)
- Full metric suite with file-11 gate checks (✓/✗)
- Per-ticker breakdown
- Walk-forward IS vs OOS table (when folds provided)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import BacktestResult
    from .walk_forward import FoldResult

_SURVIVORSHIP = (
    "⚠  SURVIVORSHIP BIAS: yfinance excludes delisted stocks. "
    "Returns shown are optimistic. Use EODHD/Norgate for an unbiased broad universe."
)


def _gate(label: str, ok: bool) -> str:
    mark = "✓" if ok else "✗"
    return f"  {mark}  {label}"


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def format_backtest_report(
    result: BacktestResult,
    folds: list[FoldResult] | None = None,
) -> str:
    lines: list[str] = []
    cfg = result.bt_cfg
    m = result.metrics

    lines.append("=" * 72)
    lines.append("SWING SIGNALS — BACKTEST REPORT")
    lines.append("=" * 72)
    lines.append(_SURVIVORSHIP)
    lines.append("")
    lines.append(
        f"Period:      {cfg.start} → {cfg.end}"
        f"  ({len(result.trading_days)} trading days)"
    )
    lines.append(
        f"Cost model:  {cfg.cost_bps} bps/side = {cfg.cost_bps * 2:.0f} bps round-trip "
        f"(commission $0, spread+slippage only)"
    )
    lines.append(
        f"Hold limit:  {cfg.max_hold_bars} bars (time-stop), warmup {cfg.warmup_bars} bars"
    )
    lines.append(
        f"Equity:      ${m['equity_start']:,.2f} → ${m['equity_end']:,.2f}"
    )
    lines.append(
        f"Signals gen: {result.n_signals_generated} entries opened, "
        f"{result.n_no_trades} no-trades"
    )
    lines.append("")

    lines.append("METRICS")
    lines.append("-" * 40)
    lines.append(f"  Trades       {m['n_trades']}  ({m.get('trades_per_month', 0)}/month)")
    lines.append(f"  Win rate     {_pct(m['win_rate'])}")
    lines.append(f"  Expectancy   {m['expectancy']:+.3f} R/trade")
    lines.append(f"  Avg win      {m['avg_win_r']:+.3f} R   avg loss  {m['avg_loss_r']:+.3f} R")
    lines.append(f"  Profit factor {m['profit_factor']}")
    lines.append(f"  Max drawdown {_pct(m['max_drawdown'])}")
    lines.append(f"  CAGR         {_pct(m['cagr'])}")
    lines.append(f"  Sharpe       {m['sharpe']:.3f}")
    lines.append(f"  Sortino      {m['sortino']:.3f}")
    lines.append(f"  Calmar       {m['calmar']}")
    lines.append("")

    lines.append("FILE-11 GATE CHECKS (advance only if all pass)")
    lines.append("-" * 40)
    g = m["gates"]
    lines.append(_gate("Expectancy > 0 R/trade", g["expectancy_positive"]))
    lines.append(_gate("Profit factor ≥ 1.3", g["profit_factor_1_3"]))
    lines.append(_gate("Calmar ≥ 1", g["calmar_1"]))
    lines.append("")

    if m["ticker_breakdown"]:
        lines.append("PER-TICKER BREAKDOWN")
        lines.append("-" * 40)
        for sym, td in sorted(m["ticker_breakdown"].items()):
            lines.append(
                f"  {sym:<6}  n={td['n']:>3}  exp={td['expectancy']:+.3f} R"
                f"  win={_pct(td['win_rate'])}"
            )
        lines.append("")

    if folds:
        lines.append("WALK-FORWARD SUMMARY")
        lines.append("-" * 72)
        lines.append(
            f"{'Fold':>4} {'IS period':<22} {'IS exp':>8} {'IS PF':>7}"
            f"  {'OOS period':<22} {'OOS exp':>9} {'OOS PF':>8}"
        )
        lines.append("-" * 72)
        for f in folds:
            i, o = f.is_metrics, f.oos_metrics
            lines.append(
                f"{f.fold:>4} {str(f.is_start)+' '+str(f.is_end):<22}"
                f" {i['expectancy']:>+8.3f} {str(i['profit_factor']):>7}"
                f"  {str(f.oos_start)+' '+str(f.oos_end):<22}"
                f" {o['expectancy']:>+9.3f} {str(o['profit_factor']):>8}"
            )
        lines.append("")
        oos_all = [f.oos_metrics["expectancy"] for f in folds]
        oos_avg = sum(oos_all) / len(oos_all)
        lines.append(f"Average OOS expectancy: {oos_avg:+.3f} R")
        oos_gates_pass = all(f.oos_metrics["gates"]["expectancy_positive"] for f in folds)
        lines.append(
            _gate("All OOS folds expectancy > 0 (no overfit)", oos_gates_pass)
        )
        lines.append("")

    lines.append("Decision support only — review manually. Not financial advice.")
    lines.append("=" * 72)
    return "\n".join(lines)
