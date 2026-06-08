"""News providers + aggregation: parsing, dedupe, ordering, key gating (no network)."""

from __future__ import annotations

from datetime import date, datetime

from swing_signals.news import aggregate
from swing_signals.news.aggregate import fetch_news
from swing_signals.news.base import NewsItem
from swing_signals.news.finnhub_news import FinnhubNews

ASOF = date(2024, 1, 31)


class _Prov:
    def __init__(self, name, items, *, boom=False):
        self.name = name
        self.available = True
        self._items = items
        self._boom = boom

    def get_news(self, symbol, start, end):
        if self._boom:
            raise RuntimeError("provider down")
        return self._items


def _item(headline, url, when):
    return NewsItem(symbol="AAPL", headline=headline, url=url, source="x", published_at=when)


def test_dedupe_by_url_and_sort_recent_first():
    p1 = _Prov("a", [
        _item("Apple beats", "http://x/1", datetime(2024, 1, 10)),
        _item("Apple guides up", "http://x/2", datetime(2024, 1, 20)),
    ])
    p2 = _Prov("b", [
        _item("Apple beats (dup url)", "http://x/1", datetime(2024, 1, 10)),  # dup -> dropped
        _item("Apple new product", "http://x/3", datetime(2024, 1, 25)),
    ])
    out = fetch_news("AAPL", ASOF, providers=[p1, p2])
    assert [i.url for i in out] == ["http://x/3", "http://x/2", "http://x/1"]  # newest first


def test_failed_provider_does_not_sink_others():
    good = _Prov("good", [_item("h", "http://x/9", datetime(2024, 1, 9))])
    out = fetch_news("AAPL", ASOF, providers=[_Prov("bad", [], boom=True), good])
    assert [i.url for i in out] == ["http://x/9"]


def test_truncates_to_max_items():
    items = [_item(f"h{i}", f"http://x/{i}", datetime(2024, 1, 1)) for i in range(50)]
    out = fetch_news("AAPL", ASOF, providers=[_Prov("a", items)], max_items=5)
    assert len(out) == 5


def test_build_providers_skips_missing_keys():
    from swing_signals.config_loader import Secrets

    secrets = Secrets(_env_file=None, finnhub_api_key="fk")  # only finnhub set
    provs = aggregate.build_providers(secrets)
    assert [p.name for p in provs] == ["finnhub"]


def test_finnhub_parses_payload(monkeypatch):
    payload = [
        {"datetime": 1704880800, "headline": "Beat", "url": "http://f/1",
         "source": "Reuters", "summary": "s"},
        {"datetime": 1704880800, "headline": "", "url": "http://f/2"},  # no headline -> dropped
    ]
    monkeypatch.setattr("swing_signals.news.finnhub_news.http_json", lambda *a, **k: payload)
    items = FinnhubNews("key").get_news("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert len(items) == 1
    assert items[0].headline == "Beat"
    assert items[0].source == "Reuters"


def test_provider_without_key_returns_empty():
    assert FinnhubNews(None).get_news("AAPL", date(2024, 1, 1), date(2024, 1, 31)) == []
