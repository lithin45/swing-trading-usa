"""SEC EDGAR 8-K provider (free, no key — just a descriptive User-Agent).

8-Ks are the highest-integrity catalyst feed (material events: earnings, M&A,
guidance, exec changes). We map ticker -> CIK once (cached), then read the
company's recent filings and keep 8-Ks in the window. Per research file 02 this
is the backbone hard-news corroborator for a small account.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from .base import NewsItem, http_json

log = logging.getLogger("swing_signals.news")

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

_cik_cache: dict[str, int] = {}  # process-lifetime ticker -> CIK cache


class SecEdgarNews:
    name = "sec_edgar"

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = user_agent

    @property
    def available(self) -> bool:
        return bool(self.user_agent)

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent or "", "Accept-Encoding": "gzip, deflate"}

    def _cik_for(self, symbol: str) -> int | None:
        if not _cik_cache:
            data = http_json(_TICKERS_URL, headers=self._headers())
            for row in (data or {}).values():
                tkr = (row.get("ticker") or "").upper()
                if tkr:
                    _cik_cache[tkr] = int(row["cik_str"])
        return _cik_cache.get(symbol.upper())

    def get_news(self, symbol: str, start: date, end: date) -> list[NewsItem]:
        if not self.user_agent:
            return []
        cik = self._cik_for(symbol)
        if cik is None:
            return []
        data = http_json(_SUBMISSIONS_URL.format(cik=cik), headers=self._headers())
        recent = (data or {}).get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary = recent.get("primaryDocument", [])
        items: list[NewsItem] = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            try:
                filed = datetime.strptime(dates[i], "%Y-%m-%d").date()
            except (ValueError, IndexError):
                continue
            if filed < start or filed > end:
                continue
            acc = accessions[i].replace("-", "") if i < len(accessions) else ""
            doc = primary[i] if i < len(primary) else ""
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
            items.append(NewsItem(
                symbol=symbol, headline=f"SEC 8-K filed {filed.isoformat()}", url=url,
                source="sec_edgar", published_at=datetime(filed.year, filed.month, filed.day),
                summary="Material-event 8-K filing.",
            ))
        return items
