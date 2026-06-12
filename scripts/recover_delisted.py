"""Recover delisted union members from Tiingo into the cache (2026-06-11).

The 2026-06 refill left 84 point-in-time S&P members unfetchable on
alpaca/yfinance — the survivorship residual that makes every backtest
optimistic. Tiingo's free tier covers many delisted tickers (YHOO verified:
625 bars through its 2017 delisting). This pulls each missing name's full
needed span straight from Tiingo into the union-merge cache; the staleness
guard then ends each name at its delist date in backtests, exactly like a
live death.

    python scripts/recover_delisted.py

Resumable and quota-frugal (lessons from the 2026-06-12 stall): names Tiingo
confirmed absent are recorded in a state file and never re-probed, and each
fetch runs under a wall-clock guard so one drip-feeding socket cannot freeze
the run (requests' read-timeout only bounds gaps BETWEEN bytes). Stops
cleanly on persistent 429s — re-run to resume.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.cache import OHLCVCache
from swing_signals.data.retry import PermanentDataError, TransientDataError
from swing_signals.data.tiingo_provider import TiingoProvider
from swing_signals.universe.membership import members_union

STATE_PATH = Path(".cache/tiingo_recovery_state.json")
FETCH_WALL_CLOCK_S = 90.0  # hard cap per symbol, retries included

WINDOWS = [
    (date(2015, 1, 1), date(2016, 12, 31)),
    (date(2017, 1, 1), date(2019, 12, 31)),
    (date(2020, 1, 1), date(2021, 12, 31)),
    (date(2022, 1, 1), date(2024, 12, 31)),
    (date(2025, 1, 1), date(2026, 6, 9)),
]


def main() -> int:
    settings, secrets = load_settings(), load_secrets()
    if secrets.tiingo_api_key is None:
        print("no SWING_TIINGO_API_KEY — nothing to do", file=sys.stderr)
        return 1
    tp = TiingoProvider(api_key=secrets.tiingo_api_key.get_secret_value())
    cache = OHLCVCache(settings.data.cache_dir)

    # Union members across all windows whose cache file is absent = the residual.
    span: dict[str, list[date]] = {}
    for start, end in WINDOWS:
        union = members_union(start, end)
        assert union is not None
        fs = start - timedelta(days=600)
        for sym in union:
            if sym in span:
                span[sym][0] = min(span[sym][0], fs)
                span[sym][1] = max(span[sym][1], end)
            else:
                span[sym] = [fs, end]
    state: dict[str, str] = (
        json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    )
    missing = sorted(
        s for s in span
        if cache.get(s) is None and state.get(s) != "dead"
    )
    n_dead_known = sum(1 for v in state.values() if v == "dead")
    print(f"{len(missing)} names to try ({n_dead_known} known-dead skipped)", flush=True)

    def _save_state() -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=0, sort_keys=True))

    ok, dead, hung = [], [], []
    with ThreadPoolExecutor(max_workers=1) as pool:
        for i, sym in enumerate(missing, 1):
            fs, fe = span[sym]
            fut = pool.submit(tp.get_ohlcv, sym, fs.isoformat(), fe.isoformat())
            try:
                df = fut.result(timeout=FETCH_WALL_CLOCK_S)
                cache.put(sym, df)
                ok.append(sym)
                state[sym] = "ok"
                print(f"  [{i}/{len(missing)}] {sym}: {len(df)} bars "
                      f"{df.index[0].date()}..{df.index[-1].date()}", flush=True)
            except FutureTimeout:
                # A drip-feeding socket outlives requests' read-timeout; abandon the
                # thread (daemon, dies with the process) and move on. Retryable later.
                hung.append(sym)
                print(f"  [{i}/{len(missing)}] {sym}: HUNG >{FETCH_WALL_CLOCK_S:.0f}s — "
                      f"skipped, will retry next run", flush=True)
                break  # the worker is wedged; a fresh run gets a fresh connection
            except PermanentDataError:
                dead.append(sym)
                state[sym] = "dead"
                print(f"  [{i}/{len(missing)}] {sym}: not on tiingo either", flush=True)
            except TransientDataError as exc:
                print(f"stopping on rate limit ({exc}) — re-run to resume", flush=True)
                break
            _save_state()
            time.sleep(2.5)
    _save_state()

    print(f"\nRECOVERED {len(ok)}/{len(missing)}: {','.join(ok) or '-'}", flush=True)
    print(f"confirmed dead {len(dead)}: {','.join(dead) or '-'}", flush=True)
    if hung:
        print(f"hung (retry next run): {','.join(hung)}", flush=True)
    remaining = len(missing) - len(ok) - len(dead)
    if remaining:
        print(f"{remaining} names remain for a future run", flush=True)
    return 0  # best-effort by design: downstream steps run with whatever was recovered


if __name__ == "__main__":
    raise SystemExit(main())
