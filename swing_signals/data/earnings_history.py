"""Historical earnings report dates — makes the EARNINGS_SOON veto replayable.

The live veto (engine + manage exits) reads ``SymbolData.next_earnings`` from
Finnhub's forward calendar; backtests had no point-in-time earnings history, so
the veto was inert in every backtest — never measured. Alpha Vantage's free
``EARNINGS`` endpoint returns each symbol's full history of *reported* dates;
``scripts/backfill_earnings.py`` chips away at the universe under the free
quota (~25 requests/day) and persists into two committed CSVs:

- ``data/earnings_dates.csv`` — symbol, report_date (the facts)
- ``data/earnings_backfill_state.csv`` — symbol, status, fetched_at, n_quarters
  (so empty results for dead/renamed tickers never burn quota twice)

Replay caveat, stated once and honestly: the backtest treats the ACTUAL report
date as known ``veto_days_before`` in advance. Real prints are scheduled weeks
ahead, so this is almost always true; surprise reschedules are a small error
source, and the unmodeled live behavior of exiting positions before a print
makes the backtest slightly PESSIMISTIC (simulated positions sit through gaps
the live system steps around).
"""

from __future__ import annotations

import csv
import logging
from bisect import bisect_left
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("swing_signals.data")

_ROOT = Path(__file__).resolve().parents[2]
DATES_CSV = _ROOT / "data" / "earnings_dates.csv"
STATE_CSV = _ROOT / "data" / "earnings_backfill_state.csv"

_AV_URL = "https://www.alphavantage.co/query"


def fetch_av_earnings(symbol: str, api_key: str) -> list[date] | None:
    """Historical reported dates for ``symbol`` from Alpha Vantage EARNINGS.

    Returns:
    - a list of dates when AV answered with the EARNINGS shape;
    - ``None`` when the response is shapeless (``{}``) — AV's flaky mode, seen
      returning ``{}`` for mega-caps like ACN that have 99 rows on the next try.
      Callers record a RETRY, never a terminal empty, off a single ``None``.
    Raises TransientDataError on the daily-quota notice so the run stops cleanly.
    """
    from ..news.base import http_json
    from .retry import TransientDataError

    try:
        payload = http_json(
            _AV_URL,
            params={"function": "EARNINGS", "symbol": symbol, "apikey": api_key},
        )
    except Exception as exc:  # noqa: BLE001 - sanitize: the URL embeds the key
        msg = str(exc).replace(api_key, "***")
        raise TransientDataError(f"alphavantage EARNINGS failed for {symbol}: {msg}") from None

    if not isinstance(payload, dict):
        return None
    # Free-tier quota notice arrives as a 200 with an Information/Note field.
    notice = payload.get("Information") or payload.get("Note")
    if notice:
        raise TransientDataError(f"alphavantage quota/notice: {str(notice)[:120]}")
    if "quarterlyEarnings" not in payload and "annualEarnings" not in payload:
        return None  # shapeless response — flake or unknown symbol; retry later

    out: list[date] = []
    for row in payload.get("quarterlyEarnings") or []:
        ds = (row.get("reportedDate") or "").strip()
        if not ds:
            continue
        try:
            out.append(date.fromisoformat(ds[:10]))
        except ValueError:
            continue
    return sorted(set(out))


class EarningsHistory:
    """Point-in-time lookup over the committed earnings-dates table."""

    def __init__(self, dates_by_symbol: dict[str, list[date]]) -> None:
        # Sorted-unique per symbol; bisect gives O(log n) next-print lookups.
        self._dates = {s: sorted(set(ds)) for s, ds in dates_by_symbol.items()}

    @classmethod
    def load(cls, path: str | Path = DATES_CSV) -> EarningsHistory | None:
        """Load the table, or None when the backfill hasn't produced one yet."""
        p = Path(path)
        if not p.exists():
            return None
        by_sym: dict[str, list[date]] = {}
        with p.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    by_sym.setdefault(row["symbol"], []).append(
                        date.fromisoformat(row["report_date"])
                    )
                except (KeyError, ValueError):
                    continue
        if not by_sym:
            return None
        return cls(by_sym)

    def __len__(self) -> int:
        return len(self._dates)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._dates

    def next_after(self, symbol: str, asof: date) -> date | None:
        """Earliest report date on/after ``asof`` (None if unknown symbol / no more)."""
        ds = self._dates.get(symbol)
        if not ds:
            return None
        i = bisect_left(ds, asof)
        return ds[i] if i < len(ds) else None


# ---------------------------------------------------------------------------
# Backfill persistence (both CSVs are committed; updates are crash-safe
# because the script rewrites them after every symbol)
# ---------------------------------------------------------------------------

def load_state(path: str | Path = STATE_CSV) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(newline="", encoding="utf-8") as fh:
        return {row["symbol"]: row for row in csv.DictReader(fh)}


MAX_RETRIES = 3  # shapeless responses before a symbol is declared terminally empty


def save_symbol(
    symbol: str,
    dates: list[date] | None,
    *,
    dates_path: str | Path = DATES_CSV,
    state_path: str | Path = STATE_CSV,
) -> None:
    """Record one fetch outcome.

    ``dates`` list -> facts appended, status ok (or empty for a shaped-but-
    dateless answer). ``None`` (shapeless response) -> status retry with an
    attempt counter; after MAX_RETRIES the symbol is declared terminally empty
    so dead tickers don't burn quota forever, while one AV flake never
    permanently hides a real symbol.
    """
    dp, sp = Path(dates_path), Path(state_path)
    dp.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(sp)

    if dates is not None:
        new_file = not dp.exists()
        with dp.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(["symbol", "report_date"])
            for d in sorted(set(dates)):
                w.writerow([symbol, d.isoformat()])
        status, attempts = ("ok" if dates else "empty"), 0
    else:
        attempts = int(state.get(symbol, {}).get("attempts") or 0) + 1
        status = "retry" if attempts < MAX_RETRIES else "empty"

    state[symbol] = {
        "symbol": symbol,
        "status": status,
        "fetched_at": datetime.now().date().isoformat(),
        "n_quarters": str(len(dates)) if dates is not None else "0",
        "attempts": str(attempts),
    }
    with sp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["symbol", "status", "fetched_at", "n_quarters", "attempts"]
        )
        w.writeheader()
        for sym in sorted(state):
            row = {"attempts": "0", **state[sym]}
            w.writerow(row)
