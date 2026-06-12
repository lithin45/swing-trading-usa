"""MassiveProvider (ex-Polygon): bar mapping, plan-window 403, rate-limit taxonomy."""

from __future__ import annotations

import pandas as pd
import pytest

from swing_signals.data.massive_provider import MassiveProvider
from swing_signals.data.retry import PermanentDataError, TransientDataError


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload)
        self.headers = {}

    def json(self):
        return self._payload


def _patched(monkeypatch, resp):
    import swing_signals.data.massive_provider as mod

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resp)
    return MassiveProvider(api_key="k")


def test_maps_aggregate_bars(monkeypatch):
    payload = {"status": "OK", "resultsCount": 2, "results": [
        {"t": 1717977600000, "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0,
         "v": 1_000_000, "vw": 100.5, "n": 9999},
        {"t": 1718064000000, "o": 101.0, "h": 103.0, "l": 100.5, "c": 102.5,
         "v": 1_200_000, "vw": 102.0, "n": 8888},
    ]}
    mp = _patched(monkeypatch, _Resp(payload=payload))
    df = mp.get_ohlcv("AAPL", "2024-06-09", "2024-06-11")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].tolist() == [101.0, 102.5]
    assert df.index[0] == pd.Timestamp("2024-06-10")  # ms epoch -> normalized date


def test_plan_window_403_is_permanent(monkeypatch):
    mp = _patched(monkeypatch, _Resp(status_code=403, payload={"status": "NOT_AUTHORIZED"}))
    with pytest.raises(PermanentDataError, match="plan does not cover"):
        mp.get_ohlcv("AAPL", "2013-01-01", "2014-12-31")


def test_rate_limit_is_transient(monkeypatch):
    mp = _patched(monkeypatch, _Resp(status_code=429))
    with pytest.raises(TransientDataError, match="rate limited"):
        mp.get_ohlcv.__wrapped__(mp, "AAPL", "2024-06-01", "2024-06-11")  # skip retry sleeps


def test_empty_results_is_permanent(monkeypatch):
    mp = _patched(monkeypatch, _Resp(payload={"status": "OK", "results": []}))
    with pytest.raises(PermanentDataError, match="no data"):
        mp.get_ohlcv("ZZZZ", "2024-06-01", "2024-06-11")


def test_unavailable_without_key():
    mp = MassiveProvider(api_key=None)
    assert not mp.available
    with pytest.raises(PermanentDataError, match="no API key"):
        mp.get_ohlcv("AAPL", "2024-06-01", "2024-06-11")
