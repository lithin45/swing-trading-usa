"""Live-vs-backtest decision-parity replay — the 2026-06-12 parity-fix acceptance check.

The fix batch aligned the live paper account with the validated configuration on
three axes (exits trail, news-factor weight, tradable universe). This script is
the acceptance test: replay recent trading days through BOTH decision paths on
the SAME cached data and confirm zero decision flips.

* **Path A — validated/backtest semantics**: the universe is point-in-time S&P
  500 membership (``members_asof``), SymbolData is the runner's sliced view
  (``news=None``, precomputed indicator panel), exactly how every holdout
  number was produced.
* **Path B — the live pipeline as now configured**: the ``universe.screen``
  funnel (``sp500_only`` honored, cheap pre-score, ``top_n_scan`` cap) feeding
  ``DataLoader.load_watchlist`` frames, exactly how the daily job builds the
  engine's input.

Both paths call the one shared ``generate_signals`` with the same market
context, the same equity, and ``budget=None`` (budget/cooldown depend on
portfolio state, which is path-external and would conflate state drift with
config drift — the three fixed axes are all pre-budget). A "decision" is a
ticker emitted as an actionable LONG on a given day; a flip is a ticker
emitted by one path and not the other.

Known benign sources of divergence the report attributes explicitly:

* the live screen's ``top_n_scan`` cheap-scan cap (a name the backtest scores
  that never ranked top-N live) — reported as ``not in live candidates``;
* current-vs-point-in-time membership inside the replay window (an index
  change in the last ~2 weeks);
* sub-1e-6 indicator differences from EMA warmup over a 400-day window vs the
  full history (reported as score deltas on commonly-emitted names).

NOTE (owner decision 2026-06-12, after the fix batch): live deliberately
re-diverges on the news-factor weight (0.20, live-only) and the universe
(``sp500_only: false`` re-admits thematic/news-discovered names), and possibly
the legacy trail (``exits.trail_legacy_stop``, pending the r5 experiment) —
see docs/validation/README.md. Flips attributable to those knobs are now
EXPECTED; this script remains the acceptance check for the *mechanical* axes
(ranking key, tie-breaks, staleness, membership, indicator parity). To verify
those in isolation, run it with the knobs set to the validated values.

Offline by construction: only the parquet cache is read (no network, no DB
writes), and ``DataLoader.get_ohlcv(offline=True)`` trims every frame to
``<= asof`` so the replay is lookahead-safe.

Usage:
    .venv/bin/python scripts/verify_live_parity.py [--days 10] [--end YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from swing_signals.backtest.config import BacktestCfg
from swing_signals.backtest.runner import BacktestRunner
from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import RunContext
from swing_signals.data.loader import DataLoader
from swing_signals.market.f04_macro import MacroModule
from swing_signals.market.f07_regime import RegimeModule
from swing_signals.scoring.engine import generate_signals
from swing_signals.universe.membership import members_asof, members_union
from swing_signals.universe.screen import screen
from swing_signals.universe.thematic import sector_map


class AsofLoader(DataLoader):
    """Replay-safe loader: clamps every frame to bars <= the replay day.

    The live loader requests ``end = asof + 1 day`` (inclusive-range convention
    for the providers). Live that is harmless — the next bar does not exist yet —
    but replaying a PAST asof against a cache that already holds the next bar
    hands the live path one future bar the real run never saw. (First replay run
    showed exactly this: every Mon–Thu day was off by one bar, Fridays aligned.)
    """

    def __init__(self, settings, secrets) -> None:
        super().__init__(settings, secrets)
        self.asof_clamp: date | None = None

    def get_ohlcv(self, symbol, start, end, *, asof=None, offline=False):
        df = super().get_ohlcv(symbol, start, end, asof=asof, offline=offline)
        if self.asof_clamp is not None and df is not None and len(df) > 0:
            df = df[df.index <= pd.Timestamp(self.asof_clamp)]
        return df


def _precap_set(result) -> set[str]:
    """Tickers that PASSED every gate/threshold (before the portfolio-cap ranking).

    The max-positions/heat/sector caps amplify tiny ordering differences into many
    pairwise diffs; the pre-cap pass set is the cleaner per-symbol decision."""
    capped = {
        s.ticker for s in result.no_trades
        if any(f.startswith("CAPPED_") or f == "BUDGET_EXHAUSTED" for f in s.flags)
    }
    return {s.ticker for s in result.actionable} | capped


def _check_config(settings) -> list[str]:
    """The three parity axes must hold in the loaded config before replaying."""
    problems: list[str] = []
    if settings.exits.mode != "legacy":
        problems.append(f"exits.mode is {settings.exits.mode!r}, validated mode is 'legacy'")
    active = settings.active_factor_weights()
    if "news_sentiment" in active:
        problems.append(
            f"news_sentiment carries live composite weight {active['news_sentiment']} "
            "but is inert in every backtest"
        )
    news_cfg = settings.factors.get("news_sentiment")
    if news_cfg is None or not news_cfg.enabled:
        problems.append(
            "news_sentiment is disabled outright — the research pipeline "
            "(NewsScore persistence) should stay running at weight 0"
        )
    if not settings.universe.sp500_only:
        problems.append("universe.sp500_only is False — live universe ≠ validated universe")
    return problems


def _load_offline(loader: DataLoader, symbols: list[str], start: date, end: date) -> dict:
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = loader.get_ohlcv(sym, start.isoformat(), end.isoformat(), offline=True)
        except Exception:  # noqa: BLE001 - cache miss = symbol not replayable (reported)
            continue
        if df is not None and len(df) > 0:
            out[sym] = df
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=10, help="trading days to replay (default 10)")
    ap.add_argument("--end", default=None, help="last replay day (default: cache max bar)")
    args = ap.parse_args()

    settings, secrets = load_settings(), load_secrets()

    problems = _check_config(settings)
    print("== config parity axes ==")
    if problems:
        for p in problems:
            print(f"  FAIL {p}")
        return 2
    print("  ok  exits.mode=legacy (fixed stop + 2R target + time stop)")
    print("  ok  news_sentiment enabled at weight 0 (research-only)")
    print("  ok  universe.sp500_only=true (validated universe)")

    loader = AsofLoader(settings, secrets)

    # Anchor the window on the index cache (SPY defines the trading calendar here,
    # exactly as the runner's bar list would).
    spy = loader.get_ohlcv("SPY", "2024-01-01", date.today().isoformat(), offline=True)
    cache_max = spy.index.max().date()
    end = min(date.fromisoformat(args.end), cache_max) if args.end else cache_max
    bars = [ts.date() for ts in spy.index if ts.date() <= end]
    days = bars[-args.days:]
    start = days[0]
    print(f"\n== replaying {len(days)} trading days: {days[0]} → {days[-1]} "
          f"(cache through {cache_max}) ==")

    union = members_union(start, end)
    if union is None:
        print("ERROR: config/sp500_changes.csv missing — run `swing-signals refresh-sp500`")
        return 2
    fetch_start = start - timedelta(days=600)  # warmup for the runner's slices
    ohlcv_all = _load_offline(loader, sorted(union), fetch_start, end)
    index_ohlcv = _load_offline(loader, list(settings.data.index_symbols), fetch_start, end)
    missing = sorted(union - set(ohlcv_all))
    print(f"loaded {len(ohlcv_all)}/{len(union)} members from cache"
          + (f" (no cache: {', '.join(missing[:8])}{' …' if len(missing) > 8 else ''})"
             if missing else ""))

    smap = sector_map()
    bt_cfg = BacktestCfg(
        start=str(start), end=str(end), cost_bps=10.0,
        max_hold_bars=settings.broker.max_hold_bars if settings.broker else 20,
        warmup_bars=210, equity_start=settings.account.equity,
    )
    runner = BacktestRunner(
        settings=settings, bt_cfg=bt_cfg, ohlcv_all=ohlcv_all, index_ohlcv=index_ohlcv,
        secrets=secrets, universe_asof=members_asof, sector_of=smap,
    )

    total_flips = 0
    common_score_dmax = 0.0
    for d in days:
        # --- Path A: backtest semantics ---
        sd_a = runner._build_symbol_data(d)                    # noqa: SLF001
        mc = runner._build_market_context(d)                   # noqa: SLF001
        ctx = RunContext(settings=settings, secrets=secrets, trading_day=d,
                         equity=settings.account.equity, market=mc)
        regime = RegimeModule().compute(ctx)
        macro = MacroModule().compute(ctx)
        res_a = generate_signals(sd_a, ctx, regime, macro_multiplier=macro.multiplier)

        # --- Path B: the live pipeline as now configured ---
        loader.asof_clamp = d  # replay-only: live never has bars past "today"
        candidates = screen(settings, secrets, asof=d, loader=loader, offline=True)
        sd_b = loader.load_watchlist(candidates, d, offline=True, news=False)
        loader.asof_clamp = None
        for sym, sd in sd_b.items():
            sd.sector = smap.get(sym)
        res_b = generate_signals(sd_b, ctx, regime, macro_multiplier=macro.multiplier)

        set_a = {s.ticker for s in res_a.actionable}
        set_b = {s.ticker for s in res_b.actionable}
        flips = set_a ^ set_b
        total_flips += len(flips)
        # Pre-cap gate agreement is only comparable on names BOTH paths scored —
        # the backtest path scores every member while the live funnel scores the
        # top-N candidates, so an unrestricted symmetric difference just measures
        # the funnel's intentional truncation, not disagreement.
        covered = set(sd_b)
        precap_flips = (_precap_set(res_a) & covered) ^ (_precap_set(res_b) & covered)

        score_a = {s.ticker: s.conviction_score for s in res_a.actionable}
        score_b = {s.ticker: s.conviction_score for s in res_b.actionable}
        for t in set_a & set_b:
            common_score_dmax = max(common_score_dmax, abs(score_a[t] - score_b[t]))

        status = "OK " if not flips else "FLIP"
        print(f"{d}  regime={regime.state:<6} A={sorted(set_a) or '—'}  "
              f"B={sorted(set_b) or '—'}  [{status}] "
              f"(pre-cap gate disagreements on commonly-scored names: {len(precap_flips)})")
        for t in sorted(flips):
            if t in set_a:
                if t not in candidates:
                    why = "backtest-only: never reached live candidates (top_n_scan funnel)"
                else:
                    nt = next((s for s in res_b.no_trades if s.ticker == t), None)
                    why = (f"live no-trade: {','.join(nt.flags) or nt.explanation}"
                           if nt else "live: not scored")
                print(f"    ⚠ {t}: emitted by BACKTEST only — {why}")
            else:
                allowed = members_asof(d) or frozenset()
                if t not in allowed:
                    why = "not a point-in-time member (membership drift inside the window)"
                else:
                    nt = next((s for s in res_a.no_trades if s.ticker == t), None)
                    why = (f"backtest no-trade: {','.join(nt.flags) or nt.explanation}"
                           if nt else "backtest: not scored")
                print(f"    ⚠ {t}: emitted by LIVE only — {why}")

    print("\n== verdict ==")
    print(f"decision flips: {total_flips}")
    print(f"max conviction-score delta on commonly-emitted names: {common_score_dmax:.6f}")
    if total_flips == 0:
        print("PASS — the live configuration and the backtest engine make identical "
              "decisions on the replayed window.")
        return 0
    print("FAIL — decision flips found; live ≠ validated on the replayed window.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
