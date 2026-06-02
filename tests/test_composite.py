"""Composite scoring (file 10): weighted average, attribution, excludes bad data."""

from __future__ import annotations

from swing_signals.factors.base import SubScore
from swing_signals.scoring.engine import composite_score


def test_weighted_average_and_attribution():
    subs = [SubScore("a", 80.0), SubScore("b", 40.0)]
    score, attr = composite_score(subs, {"a": 0.5, "b": 0.5})
    assert abs(score - 60.0) < 1e-9
    assert set(attr) == {"a", "b"}
    assert abs(attr["a"]["contribution"] - 40.0) < 1e-9


def test_unavailable_subscore_excluded_and_renormalized():
    subs = [SubScore("a", 80.0), SubScore.unavailable("b", "no data")]
    score, attr = composite_score(subs, {"a": 0.5, "b": 0.5})
    assert abs(score - 80.0) < 1e-9  # weight renormalized onto 'a' alone
    assert "b" not in attr


def test_empty_returns_neutral():
    score, attr = composite_score([], {})
    assert score == 50.0
    assert attr == {}
