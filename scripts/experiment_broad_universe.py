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
from swing_signals.backtest.overfitting import sharpe_per_period
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.backtest.trials import Trial, append_trial
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
    ap.add_argument("--max-workers", type=int, default=None,
                    help="fetch parallelism (lower it for yfinance-heavy deep-past runs)")
    ap.add_argument("--ledger-round", default=None,
                    help="append every run to the trial ledger with this round tag (e.g. r3)")
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

    if args.max_workers:
        settings.data.max_workers = args.max_workers
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

    # Historical earnings dates (AV backfill): when the committed table exists,
    # the EARNINGS_SOON veto replays in these runs. Coverage is printed so a
    # partially-backfilled table is never mistaken for full screening.
    from swing_signals.data.earnings_history import EarningsHistory

    earnings_hist = EarningsHistory.load()
    if earnings_hist is not None:
        covered = sum(1 for s in ohlcv_all if s in earnings_hist)
        print(f"earnings history: {covered}/{len(ohlcv_all)} loaded symbols covered "
              f"(veto replay {'ON' if covered else 'OFF'})\n", flush=True)

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
            vix_series=vix, vix3m_series=vix3m, earnings_history=earnings_hist,
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
        if args.ledger_round:
            eq = [bt_cfg.equity_start, *res.equity_curve]
            rets = [eq[i] / eq[i - 1] - 1.0 for i in range(1, len(eq))]
            try:
                append_trial(Trial(
                    id=f"{date.today()}-{args.ledger_round}-{name}-{start}-{end}",
                    date=str(date.today()), window=f"{start}..{end}",
                    universe="sp500-pit-union", config=f"{args.ledger_round}: {name}",
                    purpose="selection", source="scripts/experiment_broad_universe.py",
                    n_trades=m["n_trades"], expectancy_r=m["expectancy"],
                    profit_factor=(m["profit_factor"]
                                   if isinstance(m["profit_factor"], (int, float)) else None),
                    win_rate=m["win_rate"], sharpe_daily=round(sharpe_per_period(rets), 6),
                    max_drawdown=m["max_drawdown"], cagr=m["cagr"],
                    notes=f"halt replay ON; unfilled={res.n_unfilled} capped={res.n_capped} "
                          f"halted_d={res.n_halted_days}",
                ))
            except ValueError:
                print(f"  (ledger row for {name} already present)", flush=True)
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


# --- 2026-06-10b: settings.yaml now SHIPS the validated combo (3-ATR stop +
# no-chase gate + legacy exits), so "base" == combo going forward. `old_base`
# reconstructs the pre-combo config for honest side-by-side runs on new windows.


def _mut_old_base(s):
    s.risk.atr_stop_multiple = 2.0
    s.scoring.max_extension_atr = 0.0
    s.exits.mode = "staged"
    return s


VARIANTS["old_base"] = _mut_old_base


# --- Round 3 (2026-06-10 overnight, pre-registered): deployment mechanics, not
# signal patterns. Diagnostics on 2020-21 (ledger ids 2026-06-10-diag-*) showed the
# per-trade edge survives every variant of the entry/budget question while CAGR
# moves 10-30x — the strategy's compounding dies in execution mechanics:
# zombie-free fills, absorbing halts, the 5-multiplier size shrink stack, and
# right-tail truncation at 20 bars / 2R. One mutation each; selection windows
# 2015-16 / 2020-21 / 2022-24; survivors combine; 2017-19 + 2025-26 stay untouched
# for validation.


def _mut_market(s):
    s.broker.entry_order_type = "market"  # signal close -> next-open market entry
    return s


def _mut_brake(s):
    # Non-absorbing drawdown brake: trailing 1y high-water mark; resume at 0.25x
    # after 10 halted bars (live gates.py + backtest halt_state share the logic).
    s.risk.drawdown_peak_lookback = 252
    s.risk.halt_resume_days = 10
    s.risk.halt_resume_risk_mult = 0.25
    return s


def _mut_tier_flat(s):
    # Stop double-charging conviction: threshold+ranking already select for it.
    # Only High/Medium ever trade (tier_low 60 < composite_min 70).
    s.scoring.tier_mult_medium = 1.0
    return s


def _mut_hold40(s):
    s.broker.max_hold_bars = 40  # bt_cfg reads broker.max_hold_bars
    return s


def _mut_staged_v2(s):
    s.exits.mode = "staged"  # partial @2R + breakeven + chandelier trail (3-ATR-stop era retest)
    return s


VARIANTS["market"] = _mut_market
VARIANTS["brake"] = _mut_brake
VARIANTS["tier_flat"] = _mut_tier_flat
VARIANTS["hold40"] = _mut_hold40
VARIANTS["staged_v2"] = _mut_staged_v2


# --- Round 4 (2026-06-11, pre-registered after r3 landed): r3 said the exit
# LEASH is the live axis — hold40 best-in-class on the 2020-21 trend (+0.168R,
# PF 1.35) and worst-in-class in 2015-16 chop (-0.228R). The asymmetric leash
# already exists in the exit machine as pure config: cut a trade that is not
# yet working at the stagnation gate, give working trades a longer backstop.
# Parameters are the SHIPPED staged-mode defaults (stagnation 15 bars / +1R,
# backstop 60->40), not swept values. brake rides along because the absorbing
# halt must die for live anyway; its cost shows only as deeper within-window
# DD on windows that previously froze.


def _mut_smart_hold(s):
    # Full exit at the 2R target (no partial), stagnation cut for non-workers,
    # 40-bar backstop for workers. partial_take_frac=1.0 => takes_partial=False
    # => first-target EXIT_ALL, exactly the legacy target behavior.
    s.exits.mode = "staged"
    s.exits.partial_take_frac = 1.0
    s.exits.move_stop_to = "none"
    s.exits.stagnation_bars = 15
    s.exits.stagnation_min_r = 1.0
    s.exits.hard_backstop_bars = 40
    return s


def _mut_smart_hold_brake(s):
    _mut_smart_hold(s)
    _mut_brake(s)
    return s


def _mut_hold40_brake(s):
    _mut_hold40(s)
    _mut_brake(s)
    return s


VARIANTS["smart_hold"] = _mut_smart_hold
VARIANTS["smart_hold_brake"] = _mut_smart_hold_brake
VARIANTS["hold40_brake"] = _mut_hold40_brake


# --- Round 5 (2026-06-12, owner-requested): chandelier-trail the LEGACY stop
# from day one — the exact exit policy the live account ran before the parity
# fix (broker/manage.py, now config: exits.trail_legacy_stop). Owner thesis:
# ratcheting the stop up locks in profit on pullbacks. Distinct from the r3/r4
# trail family (staged_v2 trailed after a partial; hold40/smart_hold changed the
# leash, not the stop): this cell isolates the day-one trail itself, with the 2R
# target and 20-bar time-stop unchanged. base re-runs alongside because the
# Tiingo enrichment changed the universe since the r3/r4 baselines.


def _mut_legacy_trail(s):
    s.exits.trail_legacy_stop = True
    return s


VARIANTS["legacy_trail"] = _mut_legacy_trail


if __name__ == "__main__":
    raise SystemExit(main())
