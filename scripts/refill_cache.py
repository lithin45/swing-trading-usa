"""One-shot cache refill after the truncated-provider fix (2026-06-10).

For every symbol in any backtest window's point-in-time union, fetch its FULL
needed span in a single online call. With the loader's new start-truncation
guard the deep ranges come from yfinance (Alpaca IEX caps at ~6y), and the one
full-span call keeps each symbol's adjusted series internally consistent
(union-merge would otherwise splice differently-adjusted fragments).

    python scripts/refill_cache.py
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
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
    loader = DataLoader(settings, secrets)

    span: dict[str, list[date]] = {}  # symbol -> [min_fetch_start, max_end]
    for start, end in WINDOWS:
        union = members_union(start, end)
        assert union is not None, "run `swing-signals refresh-sp500` first"
        fs = start - timedelta(days=600)
        for sym in union:
            if sym in span:
                span[sym][0] = min(span[sym][0], fs)
                span[sym][1] = max(span[sym][1], end)
            else:
                span[sym] = [fs, end]
    for idx_sym in settings.data.index_symbols:
        span[idx_sym] = [WINDOWS[0][0] - timedelta(days=600), WINDOWS[-1][1]]

    print(f"refetching {len(span)} symbols (full spans, one call each)", flush=True)

    def _fetch(item):
        sym, (fs, fe) = item
        try:
            df = loader.get_ohlcv(sym, fs.isoformat(), fe.isoformat(), offline=False)
            return sym, (df is not None and len(df) > 0)
        except Exception:  # noqa: BLE001
            return sym, False

    ok = bad = 0
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (sym, success) in enumerate(pool.map(_fetch, sorted(span.items())), 1):
            ok += success
            if not success:
                bad += 1
                failed.append(sym)
            if i % 100 == 0:
                print(f"{i}/{len(span)} ({ok} ok, {bad} failed)", flush=True)
    print(f"DONE: {ok} ok, {bad} failed", flush=True)
    if failed:
        print("failed:", ",".join(sorted(failed)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
