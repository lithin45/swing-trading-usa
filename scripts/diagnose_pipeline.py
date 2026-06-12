"""Pipeline diagnostics (2026-06-10 overnight): WHERE does the edge die?

Three instruments, all offline-cache, all ledgered:

  trace      base config + a per-bar log of every pending entry order's life
             (created / waiting / converted-to-market / filled / expired-why) —
             chasing the five 2020 months with 7 submissions and ZERO fills.
  no_budget  budget.enabled=false — the strategy's raw capacity.
  market     broker.entry_order_type='market' — kill the limit dance entirely.

    python scripts/diagnose_pipeline.py --variant trace --start 2020-01-01 --end 2021-12-31
"""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.report import format_backtest_report
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.backtest.trials import Trial, append_trial
from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
from swing_signals.universe.membership import members_asof, members_union
from swing_signals.universe.thematic import sector_map

EVENTS: list[dict] = []  # trace variant: pending-order lifecycle events


class TracingRunner(BacktestRunner):
    """BacktestRunner with a pending-order event log (diagnosis only).

    _work_pending is copied from the parent with EVENTS.append lines added at
    every decision point — throwaway instrumentation, not production code.
    """

    def _work_pending(self, pending, positions, bar, cash, *, max_pending, market_fallback):
        from swing_signals.backtest.runner import _bar_at

        fills = 0
        expired = 0
        spent = 0.0
        for ticker, po in list(pending.items()):
            ohlcv = self.ohlcv_all.get(ticker)
            row = _bar_at(ohlcv, bar) if ohlcv is not None else None
            if row is None:
                po.bars_pending += 1
                if po.bars_pending > max_pending:
                    del pending[ticker]
                    expired += 1
                    EVENTS.append(dict(bar=bar, ticker=ticker, event="EXPIRE_NO_DATA",
                                       bars_pending=po.bars_pending, detail=""))
                else:
                    EVENTS.append(dict(bar=bar, ticker=ticker, event="WAIT_NO_DATA",
                                       bars_pending=po.bars_pending, detail=""))
                continue

            raw_px = None
            if po.is_market:
                raw_px = float(row["open"])
            elif float(row["low"]) <= po.limit:
                raw_px = min(float(row["open"]), po.limit)

            if raw_px is None:
                po.bars_pending += 1
                if po.bars_pending >= max_pending:
                    if market_fallback:
                        if not po.is_market:
                            EVENTS.append(dict(bar=bar, ticker=ticker, event="CONVERT_MARKET",
                                               bars_pending=po.bars_pending,
                                               detail=f"limit={po.limit:.2f} low={float(row['low']):.2f}"))
                        po.is_market = True
                    else:
                        del pending[ticker]
                        expired += 1
                        EVENTS.append(dict(bar=bar, ticker=ticker, event="EXPIRE_AGED",
                                           bars_pending=po.bars_pending, detail=""))
                else:
                    EVENTS.append(dict(bar=bar, ticker=ticker, event="WAIT_ABOVE_LIMIT",
                                       bars_pending=po.bars_pending,
                                       detail=f"limit={po.limit:.2f} low={float(row['low']):.2f}"))
                continue

            entry_fill = self.costs.fill_long_entry(raw_px)
            stop, target = po.stop, po.target
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
                EVENTS.append(dict(bar=bar, ticker=ticker, event="EXPIRE_BAD_RPS",
                                   bars_pending=po.bars_pending,
                                   detail=f"fill={entry_fill:.2f} stop={stop:.2f}"))
                continue
            shares = po.shares
            available = max(0.0, cash - spent)
            clamped = False
            if shares * entry_fill > available:
                shares = available / entry_fill if entry_fill > 0 else 0.0
                clamped = True
            if shares * entry_fill < 1.0:
                del pending[ticker]
                expired += 1
                EVENTS.append(dict(bar=bar, ticker=ticker, event="EXPIRE_NO_CASH",
                                   bars_pending=po.bars_pending,
                                   detail=f"avail=${available:.0f} want=${po.shares * entry_fill:.0f}"))
                continue

            from swing_signals.backtest.runner import _OpenPosition
            positions[ticker] = _OpenPosition(
                ticker=ticker, signal_date=po.signal_date, entry_date=bar,
                entry_fill=entry_fill, stop=stop, target=target,
                risk_per_share=rps, shares=shares, risk_frac=po.risk_frac,
                effective_stop=stop,
            )
            spent += shares * entry_fill
            fills += 1
            del pending[ticker]
            EVENTS.append(dict(bar=bar, ticker=ticker,
                               event="FILL_MARKET" if po.is_market else "FILL_LIMIT",
                               bars_pending=po.bars_pending,
                               detail=f"px={entry_fill:.2f}" + (" CASH_CLAMPED" if clamped else "")))
        return fills, expired, spent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=["trace", "no_budget", "market"])
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2021-12-31")
    ap.add_argument("--no-ledger", action="store_true")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    settings, secrets = load_settings(), load_secrets()
    if args.variant == "no_budget":
        settings.budget.enabled = False
    elif args.variant == "market":
        settings.broker.entry_order_type = "market"

    union = members_union(start, end)
    assert union is not None
    symbols = sorted(union)
    loader = DataLoader(settings, secrets)
    fetch_start = (start - timedelta(days=600)).isoformat()

    def _fetch(sym):
        try:
            return sym, loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=True)
        except Exception:  # noqa: BLE001
            return sym, None

    ohlcv_all: dict = {}
    with ThreadPoolExecutor(max_workers=settings.data.max_workers) as pool:
        for sym, df in pool.map(_fetch, symbols):
            if df is not None and len(df) > 0:
                ohlcv_all[sym] = df
    index_ohlcv = {
        s: loader.get_ohlcv(s, fetch_start, end.isoformat(), offline=True)
        for s in settings.data.index_symbols
    }
    print(f"loaded {len(ohlcv_all)}/{len(symbols)}", flush=True)

    vix = vix3m = None
    from swing_signals.data.fred_provider import FredProvider
    fred = FredProvider(secrets.fred_api_key.get_secret_value() if secrets.fred_api_key else None)
    if fred.available:
        try:
            vix = fred.get_series("VIXCLS")
            vix3m = fred.get_series("VXVCLS")
        except Exception as exc:  # noqa: BLE001
            print(f"FRED unavailable ({exc})", flush=True)

    bt_cfg = BacktestCfg(
        start=str(start), end=str(end), cost_bps=10.0,
        max_hold_bars=settings.broker.max_hold_bars if settings.broker else 20,
        warmup_bars=210, equity_start=100_000.0,
    )
    cls = TracingRunner if args.variant == "trace" else BacktestRunner
    runner = cls(
        settings=settings, bt_cfg=bt_cfg, ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv,
        secrets=secrets, universe_asof=members_asof, sector_of=sector_map(),
        vix_series=vix, vix3m_series=vix3m,
    )
    res = runner.run(start, end)
    print(format_backtest_report(res))

    out_dir = Path("/tmp/bt_diag")
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{args.variant}_{start}_{end}"

    # Trades dump (all variants) for exit-anatomy analysis.
    from dataclasses import asdict, fields
    from swing_signals.backtest.metrics import Trade
    with (out_dir / f"trades_{tag}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[f.name for f in fields(Trade)])
        w.writeheader()
        for t in res.trades:
            w.writerow(asdict(t))

    if args.variant == "trace" and EVENTS:
        with (out_dir / f"events_{tag}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["bar", "ticker", "event", "bars_pending", "detail"])
            w.writeheader()
            for e in EVENTS:
                w.writerow(e)
        from collections import Counter
        print("\nPENDING-ORDER EVENT SUMMARY")
        for ev, n in Counter(e["event"] for e in EVENTS).most_common():
            print(f"  {ev:18s} {n}")

    m = res.metrics
    print(f"\nsummary: n={m['n_trades']} exp={m['expectancy']:+.3f}R PF={m['profit_factor']} "
          f"win={m['win_rate']:.1%} CAGR={m['cagr']:+.2%} maxDD={m['max_drawdown']:.1%} "
          f"unfilled={res.n_unfilled} capped={res.n_capped} deferred={res.n_budget_deferred} "
          f"halted_days={res.n_halted_days}")

    if not args.no_ledger:
        try:
            append_trial(Trial(
                id=f"2026-06-10-diag-{tag}",
                date=str(date.today()), window=f"{start}..{end}",
                universe="sp500-pit-union",
                config=f"diagnostic: {args.variant} (base combo otherwise)",
                purpose="selection", source="scripts/diagnose_pipeline.py",
                n_trades=m["n_trades"], expectancy_r=m["expectancy"],
                profit_factor=(m["profit_factor"]
                               if isinstance(m["profit_factor"], (int, float)) else None),
                win_rate=m["win_rate"],
                max_drawdown=m["max_drawdown"], cagr=m["cagr"],
                notes=f"halt replay ON; unfilled={res.n_unfilled} "
                      f"deferred={res.n_budget_deferred} halted_d={res.n_halted_days}",
            ))
        except ValueError:
            print("ledger row already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
