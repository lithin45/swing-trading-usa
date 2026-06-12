"""A weight-0 enabled factor (e.g. news at 0.0 pending validation) computes for
research persistence but must never move the composite, the agreement gate, or
the signal's stated reasons — live parity with backtests where it is inert."""

from __future__ import annotations

from swing_signals.factors.base import SubScore
from swing_signals.scoring.engine import agreement_ratio, composite_score


def _subs():
    return [
        SubScore(name="momentum", value=80.0, reasons=["strong 12-1"]),
        SubScore(name="news_sentiment", value=5.0, reasons=["bearish headline"]),
    ]


def test_zero_weight_factor_excluded_from_composite():
    weights = {"momentum": 0.45, "news_sentiment": 0.0}
    score, attribution = composite_score(_subs(), weights)
    base_score, _ = composite_score([_subs()[0]], {"momentum": 0.45})
    assert score == base_score          # the bearish news score moved nothing
    assert "news_sentiment" not in attribution


def test_zero_weight_factor_excluded_from_agreement():
    weights = {"momentum": 0.45, "news_sentiment": 0.0}
    # news (5.0) disagrees with LONG; with weight 0 it may not dilute agreement.
    assert agreement_ratio(_subs(), weights, "LONG") == 1.0


def test_zero_weight_news_matches_backtest_inertness():
    # Backtest: news=None -> factor unavailable -> excluded. Live: weight 0.0 ->
    # excluded. Both paths must yield the identical composite.
    weights_live = {"momentum": 0.45, "technical": 0.25, "news_sentiment": 0.0}
    weights_bt = {"momentum": 0.45, "technical": 0.25, "news_sentiment": 0.2}
    subs_live = [
        SubScore(name="momentum", value=75.0),
        SubScore(name="technical", value=65.0),
        SubScore(name="news_sentiment", value=20.0),
    ]
    subs_bt = subs_live[:2] + [SubScore.unavailable("news_sentiment", "news=None")]
    live_score, _ = composite_score(subs_live, weights_live)
    bt_score, _ = composite_score(subs_bt, weights_bt)
    assert live_score == bt_score
