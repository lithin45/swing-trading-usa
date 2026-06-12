"""Quota-aware earnings-date backfill (Alpha Vantage free tier, ~25 req/day).

Fetches each backtest-universe symbol's full history of earnings REPORT dates
into the committed table (data/earnings_dates.csv + state CSV), a few symbols
per day. Resumable and crash-safe: state is rewritten after every symbol, and
symbols already fetched (including confirmed-empty dead tickers) are never
re-requested. Run daily until coverage is complete:

    python scripts/backfill_earnings.py            # default budget 15 requests
    python scripts/backfill_earnings.py --budget 5 # gentler probe

Priority: symbols of the most recent backtest windows first, so the windows
that matter most become replayable soonest. The shared AV key also serves the
live news factor — the default budget leaves headroom for it.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.config_loader import load_secrets
from swing_signals.data.earnings_history import load_state, fetch_av_earnings, save_symbol
from swing_signals.data.retry import TransientDataError
from swing_signals.universe.membership import members_union

# Most-recent window first: their replayability matters most.
WINDOWS = [
    (date(2025, 1, 1), date(2026, 6, 9)),
    (date(2022, 1, 1), date(2024, 12, 31)),
    (date(2020, 1, 1), date(2021, 12, 31)),
    (date(2017, 1, 1), date(2019, 12, 31)),
    (date(2015, 1, 1), date(2016, 12, 31)),
]
THROTTLE_S = 13.0  # free tier also caps ~5 req/min


def universe_in_priority_order() -> list[str]:
    seen: list[str] = []
    for start, end in WINDOWS:
        union = members_union(start, end)
        assert union is not None, "run `swing-signals refresh-sp500` first"
        for sym in sorted(union):
            if sym not in seen:
                seen.append(sym)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=15,
                    help="max AV requests this run (free tier ~25/day, shared with news)")
    args = ap.parse_args()

    secrets = load_secrets()
    if secrets.alphavantage_api_key is None:
        print("no SWING_ALPHAVANTAGE_API_KEY in .env — nothing to do", file=sys.stderr)
        return 1
    key = secrets.alphavantage_api_key.get_secret_value()

    state = load_state()
    universe = universe_in_priority_order()
    fresh = [s for s in universe if s not in state]
    retries = [s for s in universe if state.get(s, {}).get("status") == "retry"]
    todo = fresh + retries  # never-tried first, then AV-flaked symbols
    print(f"{len(state)} symbols recorded ({len(retries)} awaiting retry), "
          f"{len(fresh)} never tried, budget {args.budget}")

    fetched = 0
    for sym in todo:
        if fetched >= args.budget:
            break
        try:
            dates = fetch_av_earnings(sym, key)
        except TransientDataError as exc:
            print(f"stopping: {exc}")
            break
        save_symbol(sym, dates)
        fetched += 1
        label = (f"{len(dates)} report dates" if dates is not None and dates
                 else "shaped-empty (terminal)" if dates is not None
                 else "shapeless response (will retry)")
        print(f"  {sym}: {label}", flush=True)
        time.sleep(THROTTLE_S)

    remaining = len(todo) - fetched
    print(f"done: {fetched} fetched this run, {remaining} remaining "
          f"(~{(remaining + 14) // 15} more daily runs at budget 15)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
