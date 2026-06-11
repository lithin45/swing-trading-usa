"""±10% parameter-sensitivity sweep + DSR/PBO — the overfitting controls run.

PURPOSE (research file 11 §7; audit P1 #3): confirm the deployed combo sits on a
performance PLATEAU, not a spike — a config whose edge vanishes when any one
threshold moves 10% was curve-fit, not discovered. This is a robustness CHECK:
results are logged to the trial ledger as ``purpose="robustness"`` and MUST NOT
be used to re-tune (acting on a sweep turns it into another selection round).

One parameter moves ±10% per variant, everything else stays deployed:

    composite_min 70 -> 63 / 77      agreement_min 0.70 -> 0.63 / 0.77
    max_extension_atr 3.0 -> 2.7/3.3 atr_stop_multiple 3.0 -> 2.7 / 3.3
    vol_target_atr_pct 2.5 -> 2.25 / 2.75

Outputs:
  - docs/validation/sweep-<start>-<end>.md  (table + DSR + PBO + verdicts)
  - trial-ledger rows (one per run, sharpe_daily recorded — closing the gap that
    historical trials lack curves)

Run (cache currently holds 2015–2019 daily bars):
    python scripts/sweep_sensitivity.py --offline
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.overfitting import cscv_pbo, deflated_sharpe, sharpe_per_period
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.backtest.trials import (
    DEFAULT_LEDGER,
    Trial,
    append_trial,
    ledger_counts,
    load_trials,
)
from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
from swing_signals.universe.membership import members_asof, members_union

# (name, mutate(settings)) — exactly one threshold moved per variant.
SWEEP = [
    ("base", lambda s: None),
    ("composite_min-10", lambda s: setattr(s.scoring, "composite_min", 63.0)),
    ("composite_min+10", lambda s: setattr(s.scoring, "composite_min", 77.0)),
    ("agreement_min-10", lambda s: setattr(s.scoring, "agreement_min", 0.63)),
    ("agreement_min+10", lambda s: setattr(s.scoring, "agreement_min", 0.77)),
    ("extension-10", lambda s: setattr(s.scoring, "max_extension_atr", 2.7)),
    ("extension+10", lambda s: setattr(s.scoring, "max_extension_atr", 3.3)),
    ("stop_mult-10", lambda s: setattr(s.risk, "atr_stop_multiple", 2.7)),
    ("stop_mult+10", lambda s: setattr(s.risk, "atr_stop_multiple", 3.3)),
    ("vol_target-10", lambda s: setattr(s.sizing, "vol_target_atr_pct", 2.25)),
    ("vol_target+10", lambda s: setattr(s.sizing, "vol_target_atr_pct", 2.75)),
]


def daily_returns(equity_curve: list[float], equity_start: float) -> list[float]:
    eq = [equity_start, *equity_curve]
    return [eq[i] / eq[i - 1] - 1.0 if eq[i - 1] > 0 else 0.0 for i in range(1, len(eq))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--end", default="2019-12-31")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-ledger", action="store_true",
                    help="skip appending runs to the trial ledger (debug only)")
    # Parallel mode: N workers each run a --variants slice dumping curves to
    # --curves-dir; one --aggregate pass then builds the report/ledger. An 11-run
    # sequential sweep is ~1h of wall clock; 6 workers cut it to ~15 min.
    ap.add_argument("--variants", default=None,
                    help="comma-separated subset to run (worker mode, with --curves-dir)")
    ap.add_argument("--curves-dir", default=None,
                    help="dump/read per-variant curves here (workers + --aggregate)")
    ap.add_argument("--aggregate", action="store_true",
                    help="combine curves from --curves-dir into the report (no runs)")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    curves_dir = Path(args.curves_dir) if args.curves_dir else None

    if args.aggregate:
        assert curves_dir is not None, "--aggregate needs --curves-dir"
        rows, returns_by_variant = [], []
        for name, _ in SWEEP:
            payload = json.loads((curves_dir / f"{name}.json").read_text(encoding="utf-8"))
            rows.append(payload["row"])
            returns_by_variant.append(payload["returns"])
        return _finalize(rows, returns_by_variant, start, end, no_ledger=args.no_ledger)

    settings, secrets = load_settings(), load_secrets()
    union = members_union(start, end)
    assert union is not None, "run `swing-signals refresh-sp500` first"
    symbols = sorted(union)
    from swing_signals.universe.thematic import sector_map

    sector_of = sector_map()
    loader = DataLoader(settings, secrets)
    fetch_start = (start - timedelta(days=600)).isoformat()

    def _fetch(sym):
        try:
            return sym, loader.get_ohlcv(sym, fetch_start, end.isoformat(), offline=args.offline)
        except Exception:  # noqa: BLE001 - one symbol must not kill the sweep
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

    shared_panels: dict = {}
    rows: list[dict] = []
    returns_by_variant: list[list[float]] = []
    selected = ([v.strip() for v in args.variants.split(",") if v.strip()]
                if args.variants else [n for n, _ in SWEEP])
    for name, mutate in SWEEP:
        if name not in selected:
            continue
        s = load_settings()
        mutate(s)
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
        res = runner.run(start, end)
        m = res.metrics
        rets = daily_returns(res.equity_curve, 100_000.0)
        returns_by_variant.append(rets)
        sr = sharpe_per_period(rets)
        rows.append({
            "name": name, "n": m["n_trades"], "win": m["win_rate"],
            "exp": m["expectancy"], "pf": m["profit_factor"], "cagr": m["cagr"],
            "maxdd": m["max_drawdown"], "sr_daily": sr,
            "halted_days": res.n_halted_days,
            "cad_max": m["cadence"]["entries_per_month_max"],
        })
        print(f"{name:18s} n={m['n_trades']:4d} win={m['win_rate']:6.1%} "
              f"exp={m['expectancy']:+.3f}R PF={m['profit_factor']!s:>5} "
              f"CAGR={m['cagr']:+6.1%} maxDD={m['max_drawdown']:6.1%} "
              f"SRd={sr:+.4f} halted={res.n_halted_days}d "
              f"cad_max={m['cadence']['entries_per_month_max']}", flush=True)
        if curves_dir is not None:
            curves_dir.mkdir(parents=True, exist_ok=True)
            (curves_dir / f"{name}.json").write_text(
                json.dumps({"row": rows[-1], "returns": rets}), encoding="utf-8"
            )

    if curves_dir is not None and len(selected) < len(SWEEP):
        return 0  # worker slice done; the --aggregate pass builds the report

    return _finalize(rows, returns_by_variant, start, end, no_ledger=args.no_ledger)


def _finalize(
    rows: list[dict], returns_by_variant: list[list[float]],
    start: date, end: date, *, no_ledger: bool,
) -> int:
    # --- overfitting numbers ---------------------------------------------------
    matrix = [list(col) for col in zip(*returns_by_variant, strict=True)]  # T x N
    pbo = cscv_pbo(matrix, n_blocks=8)
    sweep_srs = [r["sr_daily"] for r in rows]
    var_sr = statistics.pvariance(sweep_srs)
    ledger = load_trials()
    counts = ledger_counts(ledger)
    n_sel, n_all = counts["selection"], counts["all"]
    base_rets = returns_by_variant[0]
    ds_sel = deflated_sharpe(base_rets, n_trials=n_sel, var_sr_trials=var_sr)
    ds_all = deflated_sharpe(base_rets, n_trials=n_all + len(SWEEP), var_sr_trials=var_sr)
    ds_stress = deflated_sharpe(base_rets, n_trials=n_all + len(SWEEP),
                                var_sr_trials=2.0 * var_sr)

    # --- report -----------------------------------------------------------------
    out = Path(DEFAULT_LEDGER).parent / f"sweep-{start}-{end}.md"
    base_row = rows[0]
    lines = [
        f"# Sensitivity sweep ±10% — {start} → {end} (point-in-time S&P 500, offline cache)",
        "",
        "Deployed combo as base; one threshold moved per variant; loss-halt replay ON; "
        "monthly budget ON (cadence max shown). Generated by `scripts/sweep_sensitivity.py`.",
        "",
        "**This is a robustness check, not a tuning round.** Acting on any cell below to",
        "change config would be a new selection trial and must be logged as such.",
        "",
        "| variant | n | win | exp (R) | PF | CAGR | maxDD | SR(daily) | halted d | cad max |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['n']} | {r['win']:.1%} | {r['exp']:+.3f} | {r['pf']} "
            f"| {r['cagr']:+.1%} | {r['maxdd']:.1%} | {r['sr_daily']:+.4f} "
            f"| {r['halted_days']} | {r['cad_max']} |"
        )
    spread = max(r["exp"] for r in rows) - min(r["exp"] for r in rows)
    worst = min(rows, key=lambda r: r["exp"])
    lines += [
        "",
        "## Plateau verdict",
        "",
        f"- Base expectancy {base_row['exp']:+.3f}R; sweep spread {spread:.3f}R "
        f"(worst: {worst['name']} at {worst['exp']:+.3f}R).",
        "- Every variant must stay in the base's neighborhood for a plateau verdict; a "
        "single collapsing cell flags that threshold as load-bearing/fragile.",
        "",
        "## Overfitting controls",
        "",
        f"- Trial ledger: {n_sel} selection trials, {n_all} total before this sweep "
        f"(+{len(SWEEP)} robustness runs added by it).",
        f"- Daily Sharpe of base on this window: {ds_sel.sr_hat:+.4f} "
        f"({ds_sel.sr_hat * (252 ** 0.5):+.2f} annualized), T={ds_sel.n_obs}.",
        f"- var(SR) across the {len(SWEEP)} sweep runs: {var_sr:.2e} — used as the "
        f"trial-dispersion proxy. CAVEAT: sweep variants are highly correlated, so this "
        f"UNDERSTATES true selection dispersion; the stress row doubles it.",
        f"- PSR vs 0: **{ds_sel.psr_vs_zero:.1%}**",
        f"- DSR (N={n_sel} selection trials): **{ds_sel.dsr:.1%}** "
        f"(benchmark E[max SR] = {ds_sel.sr_benchmark:+.4f})",
        f"- DSR (N={n_all + len(SWEEP)} all looks): **{ds_all.dsr:.1%}**",
        f"- DSR (stress: N={n_all + len(SWEEP)}, 2×var): **{ds_stress.dsr:.1%}**",
        f"- CSCV PBO over the {pbo.n_trials} sweep variants, {pbo.n_splits} splits: "
        f"**{pbo.pbo:.1%}** (probability the IS winner ranks below OOS median; "
        f"<50% is the bare minimum, near 0% is what genuine plateaus produce. "
        f"Computed over near-identical variants it mostly measures noise-ranking — "
        f"interpret jointly with the table, not alone).",
        "",
        "## Honest limitations",
        "",
        "- Window is 2017–2019 only (the offline cache's coverage); the hostile 2022–24 "
        "window and the 2025–26 holdout are not re-swept here. Re-run online for those.",
        "- skew/kurt of daily strategy returns are estimated from the same window "
        f"(skew {ds_sel.skew:+.2f}, kurt {ds_sel.kurt:.1f}).",
        "- Historical ledger rows lack daily Sharpes, so trial dispersion comes from this "
        "sweep (see caveat above). Future runs record sharpe_daily and will replace it.",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {out}")
    print(f"PSR {ds_sel.psr_vs_zero:.1%} | DSR(N_sel={n_sel}) {ds_sel.dsr:.1%} | "
          f"DSR(N_all) {ds_all.dsr:.1%} | DSR(stress) {ds_stress.dsr:.1%} | "
          f"PBO {pbo.pbo:.1%}")

    if not no_ledger:
        added = 0
        for r in rows:
            trial = Trial(
                id=f"2026-06-10-sweep-{r['name']}-{start}-{end}",
                date=str(date.today()), window=f"{start}..{end}",
                universe="sp500-pit-union", config=f"combo ±10% sweep: {r['name']}",
                purpose="robustness", source="scripts/sweep_sensitivity.py",
                n_trades=r["n"], expectancy_r=round(r["exp"], 4),
                profit_factor=(r["pf"] if isinstance(r["pf"], (int, float)) else None),
                win_rate=round(r["win"], 4), sharpe_daily=round(r["sr_daily"], 6),
                max_drawdown=round(r["maxdd"], 4), cagr=round(r["cagr"], 4),
                notes="loss-halt replay ON; budget ON",
            )
            try:
                append_trial(trial)
                added += 1
            except ValueError:
                pass  # idempotent re-run
        print(f"ledger: {added} trial(s) appended to {DEFAULT_LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
