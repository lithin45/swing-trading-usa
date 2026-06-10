"""Pre-registered broad-universe strategy experiments.

MOTIVATION: the honest backtest (point-in-time S&P 500 membership, real
costs/caps/limit-fills, historical VIX) shows the production config losing on
the broad universe (2022-24: -0.134 R/trade, PF 0.77), while the legacy 10-name
backtest (+0.239 R) was flattered by its survivorship-curated list.

DISCIPLINE: these variants were registered BEFORE any was run; each changes ONE
thing vs baseline; no parameter sweeps. Winners must then be confirmed on a
HOLDOUT window (2025-01-01 -> 2026-06-09) that played no part in selection:

    python scripts/experiment_broad_universe.py                       # 2022-24 matrix
    python scripts/experiment_broad_universe.py --start 2025-01-01 \
        --end 2026-06-09 --variants base,<winners>                    # holdout

Variants (one mutation each):
  base       production config as-is
  pullback   entry limit at entry_zone_LOW (buy the dip edge of the zone, not the close)
  no_chase   scoring.max_extension_atr = 3.0 (veto entries >3 ATR above the 20-EMA)
  diversify  max_positions 16 @ risk_pct 0.5% (same 10% heat budget, 2x breadth)
  rank121    momentum blend 12-1-dominant (W_NH 0.15 / W_121 0.55); eligibility unchanged
  legacy_x   exits.mode = legacy (full exit at 2R + 20-bar time stop)
"""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, fields
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.metrics import Trade
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
from swing_signals.factors import f08_momentum as f08
from swing_signals.universe.membership import members_asof, members_union


def _mut_base(s):
    return s


def _mut_pullback(s):
    s.broker.entry_price_ref = "zone_low"
    return s


def _mut_no_chase(s):
    s.scoring.max_extension_atr = 3.0
    return s


def _mut_diversify(s):
    s.risk.max_positions = 16
    s.account.risk_pct = 0.005
    return s


def _mut_legacy_x(s):
    s.exits.mode = "legacy"
    return s


@contextmanager
def _rank121_weights():
    old = (f08.W_NH, f08.W_121, f08.W_TREND, f08.W_ROC)
    f08.W_NH, f08.W_121, f08.W_TREND, f08.W_ROC = 0.15, 0.55, 0.20, 0.10
    try:
        yield
    finally:
        f08.W_NH, f08.W_121, f08.W_TREND, f08.W_ROC = old


VARIANTS = {
    "base": _mut_base,
    "pullback": _mut_pullback,
    "no_chase": _mut_no_chase,
    "diversify": _mut_diversify,
    "rank121": _mut_base,  # weights applied via the context manager below
    "legacy_x": _mut_legacy_x,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--dump-dir", default="/tmp/bt_experiments")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    names = [v.strip() for v in args.variants.split(",") if v.strip()]
    dump_dir = Path(args.dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)

    settings, secrets = load_settings(), load_secrets()
    union = members_union(start, end)
    assert union is not None, "run `swing-signals refresh-sp500` first"
    symbols = sorted(union)
    sector_of: dict[str, str] = {}
    from swing_signals.universe.thematic import sector_map

    sector_of = sector_map()

    loader = DataLoader(settings, secrets)
    fetch_start = (start - timedelta(days=600)).isoformat()

    def _fetch(sym):
        try:
            return sym, loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=args.offline)
        except Exception:  # noqa: BLE001
            return sym, None

    print(f"loading {len(symbols)} symbols ...", flush=True)
    ohlcv_all: dict = {}
    with ThreadPoolExecutor(max_workers=settings.data.max_workers) as pool:
        for sym, df in pool.map(_fetch, symbols):
            if df is not None and len(df) > 0:
                ohlcv_all[sym] = df
    index_ohlcv = {
        s: loader.get_ohlcv(s, fetch_start, end.isoformat(), offline=args.offline)
        for s in settings.data.index_symbols
    }
    print(f"loaded {len(ohlcv_all)}/{len(symbols)} symbols", flush=True)

    vix = vix3m = None
    if not args.offline:
        from swing_signals.data.fred_provider import FredProvider

        fred = FredProvider(
            secrets.fred_api_key.get_secret_value() if secrets.fred_api_key else None
        )
        if fred.available:
            vix = fred.get_series(settings.data.fred_series.get("vix", "VIXCLS"))
            vix3m = fred.get_series(settings.data.fred_series.get("vix3m", "VXVCLS"))

    # SPY buy-and-hold benchmark over the same window.
    spy = index_ohlcv.get("SPY")
    if spy is not None and len(spy) > 0:
        w = spy[(spy.index >= str(start)) & (spy.index <= str(end))]["close"]
        if len(w) > 1:
            print(f"SPY buy-and-hold {start}..{end}: {w.iloc[-1] / w.iloc[0] - 1.0:+.1%}\n")

    shared_panels: dict = {}
    rows = []
    for name in names:
        s = load_settings()
        VARIANTS[name](s)
        bt_cfg = BacktestCfg(
            start=str(start), end=str(end), cost_bps=10.0,
            max_hold_bars=s.broker.max_hold_bars if s.broker else 20,
            warmup_bars=210, equity_start=100_000.0,
        )
        runner = BacktestRunner(
            settings=s, bt_cfg=bt_cfg, ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv,
            secrets=secrets, universe_asof=members_asof, sector_of=sector_of,
            vix_series=vix, vix3m_series=vix3m,
        )
        runner._panels = shared_panels  # noqa: SLF001 - identical across variants
        if name == "rank121":
            with _rank121_weights():
                res = runner.run(start, end)
        else:
            res = runner.run(start, end)
        m = res.metrics
        rows.append((name, m["n_trades"], m["win_rate"], m["expectancy"],
                     m["profit_factor"], m["cagr"], m["max_drawdown"], m["sharpe"],
                     res.n_unfilled, res.n_capped))
        with (dump_dir / f"trades_{name}_{start}_{end}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=[f.name for f in fields(Trade)])
            w.writeheader()
            for t in res.trades:
                w.writerow(asdict(t))
        print(f"{name:10s} n={m['n_trades']:4d} win={m['win_rate']:6.1%} "
              f"exp={m['expectancy']:+.3f}R PF={m['profit_factor']:5.2f} "
              f"CAGR={m['cagr']:+6.1%} maxDD={m['max_drawdown']:6.1%} "
              f"sharpe={m['sharpe']:+5.2f} unfilled={res.n_unfilled} capped={res.n_capped}",
              flush=True)

    print("\nvariant     n     win    exp(R)   PF    CAGR    maxDD  sharpe")
    for r in rows:
        print(f"{r[0]:10s} {r[1]:4d} {r[2]:6.1%} {r[3]:+.3f}  {r[4]:5.2f} "
              f"{r[5]:+6.1%} {r[6]:6.1%} {r[7]:+5.2f}")
    return 0




# --- Round 2 (2026-06-10, EXPLORATORY): motivated by the round-1 ledger autopsy —
# 48% of trades stopped out within 10 bars at ~-0.9R (2-ATR stops sit inside the
# daily noise of freshly-ranked momentum names), while 10+ bar survivors are
# solidly positive. Round-2 cells below are combinations/one-step changes that
# target that finding. Because this is a SECOND round of selection on the same
# window, any winner's 2022-24 number is in-sample; only the untouched
# 2025->2026-06 holdout counts as evidence.


def _mut_wide_stop(s):
    s.risk.atr_stop_multiple = 3.0  # same $ risk per trade (size shrinks to match)
    return s


def _mut_combo_lnc(s):
    _mut_legacy_x(s)
    _mut_no_chase(s)
    return s


def _mut_combo_lncw(s):
    _mut_legacy_x(s)
    _mut_no_chase(s)
    _mut_wide_stop(s)
    return s


VARIANTS["wide_stop"] = _mut_wide_stop
VARIANTS["combo_lnc"] = _mut_combo_lnc
VARIANTS["combo_lncw"] = _mut_combo_lncw


if __name__ == "__main__":
    raise SystemExit(main())
