"""Earnings-calendar provider (Finnhub) — feeds the EARNINGS_SOON veto + manage exits.

One bulk ``/calendar/earnings?from=&to=`` call returns every US print in the window,
so a daily run costs a single request regardless of universe size. Key-gated and
fail-loud: no key → ``available`` is False; an HTTP/parse failure → ``None`` (callers
warn that the run is unscreened) — never a silent empty dict that reads as
"no earnings anywhere".
"""

from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger("swing_signals.data")

_URL = "https://finnhub.io/api/v1/calendar/earnings"


class EarningsCalendar:
    name = "finnhub_earnings"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._cache: dict[tuple[date, date], dict[str, date]] = {}

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def upcoming(self, start: date, end: date) -> dict[str, date] | None:
        """``{symbol: next print date}`` within [start, end], or None on failure.

        A symbol with several prints in the window (shouldn't happen) keeps the
        earliest. Memoized per (start, end) so trade + manage in one process share
        one request.
        """
        if not self.api_key:
            return None
        key = (start, end)
        if key in self._cache:
            return self._cache[key]
        from ..news.base import http_json

        try:
            # Key in the header, never the URL: exception messages embed the URL and
            # get logged/retried — they must not carry a secret.
            payload = http_json(
                _URL,
                params={"from": start.isoformat(), "to": end.isoformat()},
                headers={"X-Finnhub-Token": self.api_key},
            )
        except Exception as exc:  # noqa: BLE001 - callers decide what unscreened means
            log.warning("earnings calendar fetch failed: %s", exc)
            return None
        rows = (payload or {}).get("earningsCalendar")
        if rows is None:
            log.warning("earnings calendar response missing 'earningsCalendar' key")
            return None
        out: dict[str, date] = {}
        for r in rows:
            sym = (r.get("symbol") or "").strip().upper()
            ds = r.get("date")
            if not sym or not ds:
                continue
            try:
                d = date.fromisoformat(str(ds)[:10])
            except ValueError:
                continue
            if start <= d <= end and (sym not in out or d < out[sym]):
                out[sym] = d
        self._cache[key] = out
        return out
