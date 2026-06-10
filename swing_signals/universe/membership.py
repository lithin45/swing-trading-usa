"""S&P 500 membership from a versioned in-repo CSV (``config/sp500.csv``).

A committed CSV, deliberately NOT a runtime scrape: it's reproducible, diffable in
review, and can't silently mutate the universe in an unattended job. Refresh it by
hand (or via a separate, monitored job that opens a PR). Each symbol maps to its
GICS sector, which feeds the correlation cap.

Survivorship note: a single current-membership file is point-in-time-as-of-today, so
a backtest over it is survivorship-biased (today's index winners). For a less biased
backtest, keep dated snapshots (``config/sp500_YYYY.csv``) and select the one <= the
bar date; live trading correctly uses the latest membership.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config"
_SP500_CSV = _CONFIG / "sp500.csv"


@lru_cache(maxsize=1)
def sp500() -> dict[str, str]:
    """``symbol -> GICS sector`` for the current S&P 500 (empty if the CSV is absent)."""
    out: dict[str, str] = {}
    if not _SP500_CSV.exists():
        return out
    with _SP500_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                out[sym] = (row.get("sector") or "").strip()
    return out
