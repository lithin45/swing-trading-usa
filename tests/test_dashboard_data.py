"""Dashboard data layer: plain query helpers + performance stats (no Streamlit runtime)."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

import _data  # noqa: E402

from swing_signals.persistence.db import make_engine, session_scope  # noqa: E402
from swing_signals.persistence.repository import (  # noqa: E402
    add_account_snapshot,
    upsert_brief,
    upsert_trade,
)

DAY = date(2024, 1, 8)
TS = datetime(2024, 1, 8, 17, 0, 0)


def _engine(tmp_path):
    return make_engine(f"sqlite:///{tmp_path}/dash.db")


def test_query_trades_and_stats(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        upsert_trade(s, signal_date=DAY, symbol="AAPL", now=TS, status="closed",
                     realized_r=2.0, pnl=18.0)
        upsert_trade(s, signal_date=DAY, symbol="MSFT", now=TS, status="closed",
                     realized_r=-1.0, pnl=-6.0)
        upsert_trade(s, signal_date=DAY, symbol="NVDA", now=TS, status="open")

    df = _data.query_trades(eng)
    assert len(df) == 3

    stats = _data.trade_stats(df)
    assert stats["n"] == 2          # only closed count
    assert stats["win_rate"] == 0.5
    assert stats["expectancy"] == 0.5    # (2 + -1) / 2
    assert stats["profit_factor"] == 3.0  # 18 / 6
    assert stats["total_pnl"] == 12.0


def test_query_snapshots_and_brief(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        add_account_snapshot(s, ts=TS, equity=500.0)
        add_account_snapshot(s, ts=datetime(2024, 1, 9, 17), equity=512.0)
        upsert_brief(s, trading_day=DAY, text="constructive", created_at=TS)

    snaps = _data.query_snapshots(eng)
    assert list(snaps["equity"]) == [500.0, 512.0]
    assert _data.query_brief(eng, DAY) == "constructive"
    assert _data.query_brief(eng, date(2030, 1, 1)) is None


def test_stats_empty():
    import pandas as pd

    assert _data.trade_stats(pd.DataFrame())["n"] == 0
