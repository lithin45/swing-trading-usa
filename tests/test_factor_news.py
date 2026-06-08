"""f02 news factor: degrades to ok=False without key/news; composite stays technical-only."""

from __future__ import annotations

from swing_signals.ai.news_scoring import NewsScore
from swing_signals.config_loader import Secrets, load_settings
from swing_signals.context import RunContext, SymbolData
from swing_signals.factors import f02_news_sentiment, register_builtins
from swing_signals.factors.f02_news_sentiment import NewsSentimentFactor
from swing_signals.scoring.engine import composite_score

ITEMS = [{"symbol": "AAPL", "headline": "Apple beats", "url": "http://x/1"}]


def _ctx(key=None):
    secrets = Secrets(_env_file=None, anthropic_api_key=key)
    return RunContext(settings=load_settings(), secrets=secrets)


def test_f02_is_registered():
    assert "news_sentiment" in register_builtins()


def test_no_key_is_unavailable():
    sub = NewsSentimentFactor().compute(SymbolData(symbol="AAPL", news=ITEMS), _ctx(key=None))
    assert not sub.ok


def test_no_news_is_unavailable():
    sub = NewsSentimentFactor().compute(SymbolData(symbol="AAPL", news=None), _ctx(key="ak"))
    assert not sub.ok


def test_scoring_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(f02_news_sentiment, "score_news", lambda *a, **k: None)
    sub = NewsSentimentFactor().compute(SymbolData(symbol="AAPL", news=ITEMS), _ctx(key="ak"))
    assert not sub.ok


def test_scores_when_key_and_news_present(monkeypatch):
    monkeypatch.setattr(
        f02_news_sentiment, "score_news",
        lambda *a, **k: NewsScore(72.0, "earnings_beat", "strong print", 1, "m", False),
    )
    sub = NewsSentimentFactor().compute(SymbolData(symbol="AAPL", news=ITEMS), _ctx(key="ak"))
    assert sub.ok
    assert sub.value == 72.0
    assert "earnings_beat" in sub.reasons[0]
    assert sub.raw["catalyst"] == "earnings_beat"


def test_composite_unchanged_when_news_unavailable():
    """The backward-compat lock: an excluded news factor leaves the composite technical-only."""
    from swing_signals.factors.base import SubScore

    tech = SubScore(name="technical", value=80.0)
    news = SubScore.unavailable("news_sentiment", "no key")
    weights = {"technical": 0.2, "news_sentiment": 0.2}
    with_news, _ = composite_score([tech, news], weights)
    tech_only, _ = composite_score([tech], {"technical": 0.2})
    assert with_news == tech_only == 80.0  # weight renormalized over the one usable factor
