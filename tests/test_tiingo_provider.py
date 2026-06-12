"""TiingoProvider: adjusted-field mapping, error taxonomy, key gating."""

from __future__ import annotations

import pandas as pd
import pytest

from swing_signals.data.retry import PermanentDataError
from swing_signals.data.tiingo_provider import TiingoProvider


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = str(payload)
        self.headers = {}

    def json(self):
        return self._payload


def _rows():
    return [
        {"date": "2020-01-02T00:00:00.000Z", "open": 1, "high": 1, "low": 1, "close": 1,
         "volume": 1, "adjOpen": 100.0, "adjHigh": 102.0, "adjLow": 99.0,
         "adjClose": 101.0, "adjVolume": 1_000_000, "divCash": 0.0, "splitFactor": 1.0},
        {"date": "2020-01-03T00:00:00.000Z", "open": 1, "high": 1, "low": 1, "close": 1,
         "volume": 1, "adjOpen": 101.0, "adjHigh": 103.0, "adjLow": 100.0,
         "adjClose": 102.5, "adjVolume": 1_100_000, "divCash": 0.0, "splitFactor": 1.0},
    ]


def _patched(monkeypatch, resp):
    import swing_signals.data.tiingo_provider as mod

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resp)
    return TiingoProvider(api_key="k")


def test_uses_adjusted_fields(monkeypatch):
    tp = _patched(monkeypatch, _Resp(payload=_rows()))
    df = tp.get_ohlcv("TGT", "2020-01-01", "2020-01-31")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].tolist() == [101.0, 102.5]  # adjClose, not raw close
    assert df.index[0] == pd.Timestamp("2020-01-02")  # tz-stripped, normalized


def test_404_is_permanent_no_data(monkeypatch):
    tp = _patched(monkeypatch, _Resp(status_code=404))
    with pytest.raises(PermanentDataError, match="unknown ticker"):
        tp.get_ohlcv("NOPE", "2020-01-01", "2020-01-31")


def test_empty_list_is_permanent(monkeypatch):
    tp = _patched(monkeypatch, _Resp(payload=[]))
    with pytest.raises(PermanentDataError, match="no data"):
        tp.get_ohlcv("TGT", "2020-01-01", "2020-01-31")


def test_missing_adj_fields_rejected(monkeypatch):
    tp = _patched(monkeypatch, _Resp(payload=[{"date": "2020-01-02", "close": 1.0}]))
    with pytest.raises(PermanentDataError, match="unexpected response shape"):
        tp.get_ohlcv("TGT", "2020-01-01", "2020-01-31")


def test_unavailable_without_key():
    tp = TiingoProvider(api_key=None)
    assert not tp.available
    with pytest.raises(PermanentDataError, match="no API key"):
        tp.get_ohlcv("TGT", "2020-01-01", "2020-01-31")
