"""Shared plumbing for the validation scripts — one construction path, not two.

``run_validation_window.py`` and ``sweep_sensitivity.py`` must evaluate the SAME
machine: the sweep used to skip ``earnings_history`` (veto replay silently OFF)
and ``--offline`` used to skip FRED VIX (regime gate silently on the SPY-ATR%
proxy), so sweep cells were not comparable to the validated windows. Runner
construction, VIX loading, and earnings-history loading live here once.

Also home to:

- ledger helpers: run-date-stamped sweep trial ids + a LOUD duplicate guard
  (a hardcoded id date once made a clean re-run collide with contaminated rows
  and the silent ``except ValueError: pass`` ate the new looks);
- per-period return-curve persistence (``docs/validation/curves/<window>/
  <variant>.csv``) so CSCV PBO is recomputable without re-running backtests;
- the null-benchmark math (buy-and-hold + drawdown-matched SPY/T-bill blend)
  the window reports compare the strategy against.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.backtest.trials import DEFAULT_LEDGER, Trial, append_trial
from swing_signals.universe.membership import members_asof

CURVES_DIR = Path(DEFAULT_LEDGER).parent / "curves"


# ---------------------------------------------------------------------------
# Runner construction — the one place both scripts build the backtest from
# ---------------------------------------------------------------------------

def load_fred_vix(settings, secrets) -> tuple[pd.Series | None, pd.Series | None]:
    """Historical VIX/VIX3M from FRED (key-gated, one cheap HTTP call).

    Returns ``(None, None)`` when no key is present or the fetch fails — callers
    decide whether the SPY-ATR% proxy fallback is acceptable for their run.
    """
    from swing_signals.data.fred_provider import FredProvider

    fred = FredProvider(
        secrets.fred_api_key.get_secret_value() if secrets.fred_api_key else None
    )
    if not fred.available:
        return None, None
    try:
        vix = fred.get_series(settings.data.fred_series.get("vix", "VIXCLS"))
        vix3m = fred.get_series(settings.data.fred_series.get("vix3m", "VXVCLS"))
        print("historical VIX/VIX3M loaded from FRED", flush=True)
        return vix, vix3m
    except Exception as exc:  # noqa: BLE001 - degrade to the ATR proxy, loudly
        print(f"FRED unavailable ({exc}) — regime uses the SPY-ATR% proxy", flush=True)
        return None, None


def load_earnings_history(ohlcv_all: dict):
    """The committed earnings-dates table (veto replay), with coverage printed."""
    from swing_signals.data.earnings_history import EarningsHistory

    earnings_hist = EarningsHistory.load()
    if earnings_hist is not None:
        covered = sum(1 for s in ohlcv_all if s in earnings_hist)
        print(f"earnings history: {covered}/{len(ohlcv_all)} symbols covered "
              f"(veto replay {'ON' if covered else 'OFF'})", flush=True)
    return earnings_hist


def build_runner(
    settings, secrets, *, start: date, end: date,
    ohlcv_all: dict, index_ohlcv: dict,
    vix=None, vix3m=None, earnings_history=None, sector_of=None,
) -> BacktestRunner:
    """Construct the runner exactly as the validated windows do."""
    if sector_of is None:
        from swing_signals.universe.thematic import sector_map

        sector_of = sector_map()
    bt_cfg = BacktestCfg(
        start=str(start), end=str(end), cost_bps=10.0,
        max_hold_bars=settings.broker.max_hold_bars if settings.broker else 20,
        warmup_bars=210, equity_start=100_000.0,
    )
    return BacktestRunner(
        settings=settings, bt_cfg=bt_cfg, ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv,
        secrets=secrets, universe_asof=members_asof, sector_of=sector_of,
        vix_series=vix, vix3m_series=vix3m, earnings_history=earnings_history,
    )


# ---------------------------------------------------------------------------
# Trial-ledger helpers
# ---------------------------------------------------------------------------

def sweep_trial_id(run_date: date, variant: str, start: date, end: date) -> str:
    """Ledger id for one sweep cell, stamped with the ACTUAL run date.

    Same date stamp as the ``run_validation_window.py`` ids, so a clean re-run
    on a later day gets fresh ids instead of colliding with historical rows.
    """
    return f"{run_date}-sweep-{variant}-{start}-{end}"


def append_trial_loud(trial: Trial, path: str | Path = DEFAULT_LEDGER) -> bool:
    """Append one ledger row; a duplicate id is an ERROR, not a silent skip.

    Returns True when appended. On collision the ledger is left without the new
    look — that loss must be visible, so the colliding id is named on stderr.
    """
    try:
        append_trial(trial, path)
        return True
    except ValueError:
        print(f"ERROR: trial id already in ledger, row NOT appended: {trial.id!r} "
              f"— this run's result is missing from {path}; use a fresh run date "
              f"or a distinct label", file=sys.stderr, flush=True)
        return False


# ---------------------------------------------------------------------------
# Return-curve persistence
# ---------------------------------------------------------------------------

def write_curve_csv(out_dir: str | Path, name: str, dates, returns) -> Path:
    """Persist one per-period return curve as ``<out_dir>/<name>.csv``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.csv"
    lines = ["date,return"]
    lines += [f"{d},{r:.10f}" for d, r in zip(dates, returns, strict=True)]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Null benchmarks — what doing nothing clever would have earned
# ---------------------------------------------------------------------------

def window_returns(df: pd.DataFrame, start: date, end: date) -> list[float]:
    """Close-to-close daily returns of one symbol inside [start, end]."""
    closes = df["close"]
    closes = closes[(closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))]
    vals = [float(v) for v in closes.tolist()]
    if len(vals) < 2:
        return []
    return [vals[i] / vals[i - 1] - 1.0 for i in range(1, len(vals))]


def cagr_of_returns(returns: list[float], periods_per_year: float = 252.0) -> float:
    if not returns:
        return 0.0
    growth = 1.0
    for r in returns:
        growth *= 1.0 + r
    if growth <= 0:
        return -1.0
    return growth ** (periods_per_year / len(returns)) - 1.0


def max_drawdown_of_returns(returns: list[float]) -> float:
    """Peak-to-trough decline of the compounded curve (negative fraction)."""
    value = peak = 1.0
    max_dd = 0.0
    for r in returns:
        value *= 1.0 + r
        if value > peak:
            peak = value
        dd = (value - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def blend_returns(
    asset_returns: list[float], weight: float, cash_daily: float = 0.0
) -> list[float]:
    """Daily-rebalanced ``weight``×asset + (1−weight)×cash."""
    return [weight * r + (1.0 - weight) * cash_daily for r in asset_returns]


def dd_matched_weight(
    asset_returns: list[float], target_maxdd: float, cash_daily: float = 0.0
) -> float:
    """Asset weight whose blend maxDD ≈ ``target_maxdd`` (a negative fraction).

    Bisection — blend drawdown deepens monotonically with weight when the cash
    leg is non-negative. Returns 1.0 when even 100% asset stays shallower than
    the target (callers should note the cap) and 0.0 for a non-negative target.
    """
    if target_maxdd >= 0:
        return 0.0
    if max_drawdown_of_returns(asset_returns) >= target_maxdd:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if max_drawdown_of_returns(blend_returns(asset_returns, mid, cash_daily)) > target_maxdd:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def format_null_benchmarks(
    *, strategy_cagr: float, strategy_maxdd: float,
    spy_returns: list[float], mtum_returns: list[float] | None,
    tbill_daily: float | None, tbill_note: str,
) -> str:
    """Markdown null-benchmark section for one window report.

    ``mtum_returns`` may be None (no data) or partial (history starts inside the
    window) — both degrade to a note instead of a misleading number. The blend's
    cash leg earns ``tbill_daily`` (0% when no rate series was loadable).
    """
    lines = [
        "## Null benchmarks (same window)",
        "",
        "| series | CAGR | maxDD |",
        "|---|---|---|",
        f"| strategy (deployed combo) | {strategy_cagr:+.1%} | {strategy_maxdd:.1%} |",
    ]
    if not spy_returns:
        lines += [
            "",
            "- SPY data unavailable for this window — null benchmarks not computed.",
        ]
        return "\n".join(lines)

    lines.append(
        f"| buy-and-hold SPY | {cagr_of_returns(spy_returns):+.1%} "
        f"| {max_drawdown_of_returns(spy_returns):.1%} |"
    )
    mtum_note = None
    if mtum_returns and len(mtum_returns) >= 0.9 * len(spy_returns):
        lines.append(
            f"| buy-and-hold MTUM | {cagr_of_returns(mtum_returns):+.1%} "
            f"| {max_drawdown_of_returns(mtum_returns):.1%} |"
        )
    else:
        lines.append("| buy-and-hold MTUM | n/a | n/a |")
        mtum_note = ("- MTUM history unavailable or incomplete for this window — "
                     "buy-and-hold MTUM not computed.")

    cash_daily = tbill_daily if tbill_daily is not None else 0.0
    w = dd_matched_weight(spy_returns, strategy_maxdd, cash_daily)
    blend = blend_returns(spy_returns, w, cash_daily)
    blend_cagr = cagr_of_returns(blend)
    blend_dd = max_drawdown_of_returns(blend)
    lines.append(
        f"| DD-matched blend ({w:.0%} SPY / {1 - w:.0%} T-bill) "
        f"| {blend_cagr:+.1%} | {blend_dd:.1%} |"
    )
    lines += [
        "",
        f"- T-bill leg: {tbill_note}",
        f"- DD matching: SPY weight scaled so blend maxDD ≈ strategy maxDD "
        f"({strategy_maxdd:.1%})."
        + (" SPY's own maxDD is already shallower than the strategy's, so the "
           "blend caps at 100% SPY." if w >= 1.0 else ""),
        f"- **Alpha over DD-matched null: {strategy_cagr - blend_cagr:+.1%}** "
        f"(strategy CAGR − blend CAGR). The strategy must beat this null — equal "
        f"drawdown pain for index returns — or it adds complexity without pay.",
    ]
    if mtum_note:
        lines.append(mtum_note)
    return "\n".join(lines)


def load_tbill_daily(settings, secrets, start: date, end: date) -> tuple[float | None, str]:
    """(daily T-bill rate, source note) for the window — (None, note) when unloadable.

    Mean 3-month constant-maturity yield (FRED DGS3MO) over the window, converted
    to a daily compounding rate. No new plumbing: same FredProvider the regime
    gate uses, just a different series id.
    """
    from swing_signals.data.fred_provider import FredProvider

    fred = FredProvider(
        secrets.fred_api_key.get_secret_value() if secrets.fred_api_key else None
    )
    if not fred.available:
        return None, "no FRED key — cash leg earns 0%"
    series_id = settings.data.fred_series.get("tbill3m", "DGS3MO")
    try:
        series = fred.get_series(series_id).dropna()
    except Exception as exc:  # noqa: BLE001 - benchmark must not kill the run
        return None, f"FRED {series_id} unavailable ({exc}) — cash leg earns 0%"
    series = series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
    if len(series) == 0:
        return None, f"FRED {series_id} has no data in this window — cash leg earns 0%"
    annual = float(series.mean()) / 100.0
    daily = (1.0 + annual) ** (1.0 / 252.0) - 1.0
    return daily, f"mean FRED {series_id} over the window = {annual:.2%} annualized"
