"""Claude AI layer: news scoring + brief — memoization, degradation (mocked SDK)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from swing_signals.ai import brief as brief_mod
from swing_signals.ai import news_scoring
from swing_signals.ai.prompts import NewsScoreOut
from swing_signals.config_loader import Secrets, load_settings
from swing_signals.context import RunContext
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Brief, NewsItem, NewsScore

DAY = date(2024, 1, 8)
ITEMS = [
    {"symbol": "AAPL", "url": "http://x/1", "headline": "Apple beats", "source": "Reuters"},
    {"symbol": "AAPL", "url": "http://x/2", "headline": "Apple guides up"},
]


class FakeScoringClient:
    instances = 0
    calls = 0

    def __init__(self, api_key):
        FakeScoringClient.instances += 1

    def score_headlines(self, symbol, items):
        FakeScoringClient.calls += 1
        return NewsScoreOut(score=72, catalyst="earnings_beat", rationale="strong print")


class FailingClient:
    def __init__(self, api_key):
        pass

    def score_headlines(self, symbol, items):
        return None


def _ctx(tmp_path, monkeypatch, *, key="ak"):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    s = load_settings()
    s.run.db_url = f"sqlite:///{tmp_path}/ai.db"
    secrets = Secrets(_env_file=None, anthropic_api_key=key)
    return RunContext(settings=s, secrets=secrets, trading_day=DAY)


def _rows(db_url, model):
    with session_scope(make_engine(db_url)) as s:
        return list(s.scalars(select(model)))


# --- news scoring -------------------------------------------------------------

def test_no_key_returns_none(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, key=None)
    assert news_scoring.score_news("AAPL", ITEMS, ctx) is None


def test_empty_items_returns_none(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    assert news_scoring.score_news("AAPL", [], ctx) is None


def test_scores_persists_and_memoizes(tmp_path, monkeypatch):
    FakeScoringClient.instances = FakeScoringClient.calls = 0
    monkeypatch.setattr(news_scoring, "AnthropicClient", FakeScoringClient)
    ctx = _ctx(tmp_path, monkeypatch)

    first = news_scoring.score_news("AAPL", ITEMS, ctx)
    assert first.value == 72.0
    assert first.catalyst == "earnings_beat"
    assert first.cached is False
    assert FakeScoringClient.calls == 1
    assert len(_rows(ctx.settings.run.db_url, NewsScore)) == 1
    assert len(_rows(ctx.settings.run.db_url, NewsItem)) == 2  # raw items cached for dashboard

    second = news_scoring.score_news("AAPL", ITEMS, ctx)  # same headline set
    assert second.cached is True
    assert second.value == 72.0
    assert FakeScoringClient.calls == 1  # no second API call


def test_client_failure_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(news_scoring, "AnthropicClient", FailingClient)
    ctx = _ctx(tmp_path, monkeypatch)
    assert news_scoring.score_news("AAPL", ITEMS, ctx) is None
    assert _rows(ctx.settings.run.db_url, NewsScore) == []  # nothing persisted on failure


# --- daily brief --------------------------------------------------------------

class FakeBriefClient:
    calls = 0

    def __init__(self, api_key):
        pass

    def write_brief(self, context_text):
        FakeBriefClient.calls += 1
        return "Market is constructive; one signal fired in AAPL."


def test_brief_no_key_returns_none(tmp_path, monkeypatch):
    s = _ctx(tmp_path, monkeypatch, key=None)
    assert brief_mod.generate_brief(s.settings, s.secrets, today=DAY) is None


def test_brief_generates_and_memoizes(tmp_path, monkeypatch):
    FakeBriefClient.calls = 0
    monkeypatch.setattr(brief_mod, "AnthropicClient", FakeBriefClient)
    ctx = _ctx(tmp_path, monkeypatch)

    text = brief_mod.generate_brief(ctx.settings, ctx.secrets, today=DAY)
    assert "AAPL" in text
    assert FakeBriefClient.calls == 1
    assert len(_rows(ctx.settings.run.db_url, Brief)) == 1

    again = brief_mod.generate_brief(ctx.settings, ctx.secrets, today=DAY)
    assert again == text
    assert FakeBriefClient.calls == 1  # served from DB, no second call
