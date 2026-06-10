"""S&P 500 membership — current (``config/sp500.csv``) and point-in-time.

Committed CSVs, deliberately NOT a runtime scrape: reproducible, diffable in
review, and can't silently mutate the universe in an unattended job. Refresh them
by hand with ``swing-signals refresh-sp500`` (or via a separate, monitored job
that opens a PR). Each current symbol maps to its GICS sector, which feeds the
correlation cap.

Point-in-time membership (``config/sp500_changes.csv``) is reconstructed by
rolling Wikipedia's index-change log BACKWARD from the current membership:
``members_asof(d)`` undoes every addition/removal dated after ``d``. That removes
the *selection* bias of backtesting today's winners list. The residual bias is
honest and disclosed: names that left the index by delisting (acquired/bankrupt)
usually have no free price history, so the backtest can select them but often
cannot trade them.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("swing_signals.universe")

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config"
_SP500_CSV = _CONFIG / "sp500.csv"
_SP500_CHANGES_CSV = _CONFIG / "sp500_changes.csv"

_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


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


@dataclass(frozen=True)
class MembershipChange:
    """One index change event: on ``day``, ``added`` joined and/or ``removed`` left."""

    day: date
    added: str | None
    removed: str | None


@lru_cache(maxsize=1)
def sp500_changes(path: Path | None = None) -> tuple[MembershipChange, ...]:
    """Chronological membership-change events from the committed changes CSV."""
    p = path or _SP500_CHANGES_CSV
    if not p.exists():
        return ()
    events: list[MembershipChange] = []
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                day = date.fromisoformat((row.get("date") or "").strip())
            except ValueError:
                continue
            added = (row.get("added") or "").strip().upper() or None
            removed = (row.get("removed") or "").strip().upper() or None
            if added or removed:
                events.append(MembershipChange(day, added, removed))
    events.sort(key=lambda e: e.day)
    return tuple(events)


@lru_cache(maxsize=4096)
def members_asof(asof: date) -> frozenset[str] | None:
    """Point-in-time S&P 500 membership on ``asof`` (None if no changes file).

    Starts from the CURRENT membership and undoes every change dated after
    ``asof``: the symbol that was added gets dropped, the one removed gets
    restored. Events on ``asof`` itself are considered effective (the change has
    happened by that day's close).
    """
    changes = sp500_changes()
    current = set(sp500())
    if not changes or not current:
        return None
    earliest = changes[0].day
    if asof < earliest:
        log.warning(
            "members_asof(%s) predates the changes log (starts %s) — returning the "
            "oldest reconstructable membership", asof, earliest,
        )
    members = current
    for ev in reversed(changes):
        if ev.day <= asof:
            break
        if ev.added:
            members.discard(ev.added)
        if ev.removed:
            members.add(ev.removed)
    return frozenset(members)


def members_union(start: date, end: date) -> frozenset[str] | None:
    """Every symbol that was a member at ANY point in [start, end].

    The backtest fetches data for this superset once; the per-bar point-in-time
    filter then decides which of them are tradable on each day.
    """
    base = members_asof(start)
    if base is None:
        return None
    syms = set(base)
    for ev in sp500_changes():
        if start <= ev.day <= end and ev.added:
            syms.add(ev.added)
    return frozenset(syms)


def refresh_from_wikipedia() -> tuple[int, int]:
    """Fetch Wikipedia's S&P 500 page and rewrite BOTH committed CSVs.

    Returns (n_members, n_change_events). Network + parse errors raise — this is
    an operator command (``swing-signals refresh-sp500``), never an unattended path.
    """
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(_WIKI_URL, timeout=30, headers={"User-Agent": "swing-signals/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # --- current constituents (table id="constituents": Symbol | Security | GICS Sector | ...)
    members: list[tuple[str, str]] = []
    table = soup.find("table", id="constituents")
    if table is None:
        raise ValueError("Wikipedia page: constituents table not found (layout changed?)")
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 3 and cells[0]:
            members.append((cells[0].upper(), cells[2]))
    if len(members) < 480:
        raise ValueError(f"Wikipedia page: only {len(members)} constituents parsed — refusing")

    # --- change log (table id="changes": Date | Added Ticker/Security | Removed ... | Reason)
    events: list[tuple[date, str, str]] = []
    table = soup.find("table", id="changes")
    if table is None:
        raise ValueError("Wikipedia page: changes table not found (layout changed?)")
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 5:
            continue  # header rows
        try:
            day = datetime.strptime(cells[0], "%B %d, %Y").date()
        except ValueError:
            continue
        added, removed = cells[1].upper(), cells[3].upper()
        if added or removed:
            events.append((day, added, removed))
    if len(events) < 100:
        raise ValueError(f"Wikipedia page: only {len(events)} change events parsed — refusing")

    members.sort()
    with _SP500_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "sector"])
        w.writerows(members)
    events.sort(key=lambda e: e[0])
    with _SP500_CHANGES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "added", "removed"])
        w.writerows([(d.isoformat(), a, r) for d, a, r in events])

    sp500.cache_clear()
    sp500_changes.cache_clear()
    members_asof.cache_clear()
    return len(members), len(events)
