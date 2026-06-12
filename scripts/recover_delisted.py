"""Recover delisted union members from Tiingo into the cache (2026-06-11).

The 2026-06 refill left 84 point-in-time S&P members unfetchable on
alpaca/yfinance — the survivorship residual that makes every backtest
optimistic. Tiingo's free tier covers many delisted tickers (YHOO verified:
625 bars through its 2017 delisting). This one-shot pulls each missing name's
full needed span straight from Tiingo into the union-merge cache; the
staleness guard then ends each name at its delist date in backtests, exactly
like a live death.

    python scripts/recover_delisted.py

Gentle throttle; stops cleanly on persistent 429s — re-run to resume (cache
hits make completed names free).
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.cache import OHLCVCache
from swing_signals.data.retry import PermanentDataError, TransientDataError
from swing_signals.data.tiingo_provider import TiingoProvider
from swing_signals.universe.membership import members_union

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
    missing = sorted(s for s in span if cache.get(s) is None)
    print(f"{len(missing)} union members have no cached data; trying Tiingo", flush=True)

    ok, dead = [], []
    for i, sym in enumerate(missing, 1):
        fs, fe = span[sym]
        try:
            df = tp.get_ohlcv(sym, fs.isoformat(), fe.isoformat())
            cache.put(sym, df)
            ok.append(sym)
            print(f"  [{i}/{len(missing)}] {sym}: {len(df)} bars "
                  f"{df.index[0].date()}..{df.index[-1].date()}", flush=True)
        except PermanentDataError:
            dead.append(sym)
            print(f"  [{i}/{len(missing)}] {sym}: not on tiingo either", flush=True)
        except TransientDataError as exc:
            print(f"stopping on rate limit ({exc}) — re-run to resume", flush=True)
            break
        time.sleep(2.5)

    print(f"\nRECOVERED {len(ok)}/{len(missing)}: {','.join(ok)}", flush=True)
    print(f"still missing {len(dead)}: {','.join(dead)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
