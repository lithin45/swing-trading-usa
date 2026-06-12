"""Run the DEPLOYED config over one window and persist the result as a validation trial.

The repeatable form of "backtest it on window X and write it down": offline cache
for OHLCV (prefetch first), real FRED VIX/VIX3M when a key is present (the regime
gate replays history instead of the ATR proxy), loss-halt replay + monthly budget
ON, one ledger row (purpose=validation), one markdown report in docs/validation/.

    python scripts/run_validation_window.py --start 2015-01-01 --end 2016-12-31
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_common import (
    CURVES_DIR,
    build_runner,
    cagr_of_returns,
    format_null_benchmarks,
    load_earnings_history,
    load_fred_vix,
    load_tbill_daily,
    window_returns,
    write_curve_csv,
)

from swing_signals.backtest.overfitting import sharpe_per_period
from swing_signals.backtest.report import format_backtest_report
from swing_signals.backtest.trials import DEFAULT_LEDGER, Trial, append_trial
from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
from swing_signals.universe.membership import members_union


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", default=None, help="ledger id suffix (default: window)")
    ap.add_argument("--config-note", default="combo_lncw (deployed)",
                    help="config description recorded in the ledger row")
    ap.add_argument("--no-ledger", action="store_true")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    settings, secrets = load_settings(), load_secrets()
    union = members_union(start, end)
    assert union is not None, "run `swing-signals refresh-sp500` first"
    symbols = sorted(union)
    from swing_signals.universe.thematic import sector_map

    loader = DataLoader(settings, secrets)
    fetch_start = (start - timedelta(days=600)).isoformat()

    def _fetch(sym):
        try:
            return sym, loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=True)
        except Exception:  # noqa: BLE001 - one symbol must not kill the run
            return sym, None

    print(f"loading {len(symbols)} symbols from cache ...", flush=True)
    ohlcv_all: dict = {}
    with ThreadPoolExecutor(max_workers=settings.data.max_workers) as pool:
        for sym, df in pool.map(_fetch, symbols):
            if df is not None and len(df) > 0:
                ohlcv_all[sym] = df
    index_ohlcv = {
        s: loader.get_ohlcv(s, fetch_start, end.isoformat(), offline=True)
        for s in settings.data.index_symbols
    }
    n_missing = len(symbols) - len(ohlcv_all)
    print(f"loaded {len(ohlcv_all)}/{len(symbols)} symbols "
          f"({n_missing} unfetchable = survivorship residual)", flush=True)

    # Real vol history for the regime gate — one cheap HTTP call, key-gated.
    vix, vix3m = load_fred_vix(settings, secrets)
    earnings_hist = load_earnings_history(ohlcv_all)

    runner = build_runner(
        settings, secrets, start=start, end=end, ohlcv_all=ohlcv_all,
        index_ohlcv=index_ohlcv, vix=vix, vix3m=vix3m,
        earnings_history=earnings_hist, sector_of=sector_map(),
    )
    res = runner.run(start, end)
    report = format_backtest_report(res)
    print(report)

    m = res.metrics
    rets_eq = [100_000.0, *res.equity_curve]
    rets = [rets_eq[i] / rets_eq[i - 1] - 1.0 for i in range(1, len(rets_eq))]
    sr = sharpe_per_period(rets)

    label = args.label or f"{start}-{end}"
    curve_path = write_curve_csv(CURVES_DIR / f"{start}-{end}", f"window-{label}",
                                 res.trading_days, rets)
    print(f"return curve persisted to {curve_path} (CSCV PBO input)")

    # Null benchmarks: what equal drawdown pain in SPY/T-bills (or plain MTUM)
    # would have paid over the same window — the bar the strategy must clear.
    spy_df = index_ohlcv.get("SPY")
    spy_rets = window_returns(spy_df, start, end) if spy_df is not None else []
    mtum_df = None
    try:
        mtum_df = loader.get_ohlcv("MTUM", fetch_start, end.isoformat(), offline=True)
    except Exception:  # noqa: BLE001 - benchmark data is best-effort
        pass
    mtum_rets = window_returns(mtum_df, start, end) if mtum_df is not None else None
    tbill_daily, tbill_note = load_tbill_daily(settings, secrets, start, end)
    null_section = format_null_benchmarks(
        strategy_cagr=(m["cagr"] if isinstance(m["cagr"], (int, float))
                       else cagr_of_returns(rets)),
        strategy_maxdd=m["max_drawdown"],
        spy_returns=spy_rets, mtum_returns=mtum_rets,
        tbill_daily=tbill_daily, tbill_note=tbill_note,
    )

    out = Path(DEFAULT_LEDGER).parent / f"window-{label}.md"
    out.write_text(
        f"# Validation window {start} → {end} (deployed combo, point-in-time S&P 500)\n\n"
        f"Generated by `scripts/run_validation_window.py`. Loss-halt replay ON, monthly\n"
        f"budget ON, offline cache ({len(ohlcv_all)}/{len(symbols)} members loaded; the\n"
        f"{n_missing} unfetchable names are the survivorship residual — results are\n"
        f"OPTIMISTIC by roughly that coverage gap), "
        f"{'real FRED VIX' if vix is not None else 'SPY-ATR% vol proxy'}.\n\n"
        f"```\n{report}\n```\n\n"
        f"{null_section}\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")

    if not args.no_ledger:
        try:
            append_trial(Trial(
                id=f"{date.today()}-window-{label}",
                date=str(date.today()), window=f"{start}..{end}",
                universe="sp500-pit-union", config=args.config_note,
                purpose="validation", source="scripts/run_validation_window.py",
                n_trades=m["n_trades"], expectancy_r=m["expectancy"],
                profit_factor=(m["profit_factor"]
                               if isinstance(m["profit_factor"], (int, float)) else None),
                win_rate=m["win_rate"], sharpe_daily=round(sr, 6),
                max_drawdown=m["max_drawdown"], cagr=m["cagr"],
                notes=f"halt replay ON; budget ON; {n_missing} members unfetchable",
            ))
            print("ledger row appended")
        except ValueError:
            print("ledger row already present (idempotent re-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
