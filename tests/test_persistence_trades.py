"""Stage 8 persistence: trades, snapshots, news items/scores, briefs."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Trade
from swing_signals.persistence.repository import (
    active_trades,
    add_account_snapshot,
    closed_trades,
    get_brief,
    get_cached_news,
    get_news_score,
    get_trade,
    list_snapshots,
    open_trades,
    pending_entry_trades,
    save_news_score,
    upsert_brief,
    upsert_news_items,
    upsert_trade,
)

DAY = date(2024, 1, 8)
TS = datetime(2024, 1, 8, 17, 0, 0)


def _engine(tmp_path):
    return make_engine(f"sqlite:///{tmp_path}/trades.db")


def test_trade_upsert_is_idempotent_on_day_symbol(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        t = upsert_trade(
            s, signal_date=DAY, symbol="AAPL", now=TS, status="pending_entry",
            limit_price=100.0, qty=1.5, stop_price=94.0, target_price=112.0,
        )
        assert t.id is not None
    # second upsert for the same (day, symbol) updates the same row, not a new one
    with session_scope(eng) as s:
        upsert_trade(s, signal_date=DAY, symbol="AAPL", now=TS, status="open", actual_entry=99.5)
    with session_scope(eng) as s:
        rows = list(s.scalars(select(Trade)))
        assert len(rows) == 1
        assert rows[0].status == "open"
        assert rows[0].actual_entry == 99.5
        assert rows[0].limit_price == 100.0  # preserved across the update


def test_trade_status_filters(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        upsert_trade(s, signal_date=DAY, symbol="AAPL", now=TS, status="pending_entry")
        upsert_trade(s, signal_date=DAY, symbol="MSFT", now=TS, status="open")
        upsert_trade(s, signal_date=DAY, symbol="NVDA", now=TS, status="closed")
    with session_scope(eng) as s:
        assert {t.symbol for t in pending_entry_trades(s)} == {"AAPL"}
        assert {t.symbol for t in open_trades(s)} == {"MSFT"}
        assert {t.symbol for t in active_trades(s)} == {"AAPL", "MSFT"}  # excludes closed
        assert {t.symbol for t in closed_trades(s)} == {"NVDA"}


def test_get_trade_missing(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        assert get_trade(s, DAY, "TSLA") is None


def test_account_snapshots(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        add_account_snapshot(s, ts=TS, equity=500.0, cash=480.0, open_positions=1)
        add_account_snapshot(
            s, ts=datetime(2024, 1, 9, 17), equity=505.0, cash=470.0, open_positions=2
        )
    with session_scope(eng) as s:
        snaps = list_snapshots(s)
        assert [round(x.equity, 1) for x in snaps] == [500.0, 505.0]  # ordered by ts


def test_news_items_dedupe_and_query(tmp_path):
    eng = _engine(tmp_path)
    items = [
        {"symbol": "AAPL", "headline": "Apple beats", "url": "http://x/1",
         "published_at": datetime(2024, 1, 7, 9), "source": "finnhub"},
        {"symbol": "AAPL", "headline": "Apple beats (dup)", "url": "http://x/1",
         "published_at": datetime(2024, 1, 7, 9)},  # same (symbol,url) -> skipped
        {"symbol": "AAPL", "headline": "Apple guidance", "url": "http://x/2",
         "published_at": datetime(2024, 1, 8, 9)},
    ]
    with session_scope(eng) as s:
        assert upsert_news_items(s, items, fetched_at=TS) == 2
    with session_scope(eng) as s:
        assert upsert_news_items(s, items, fetched_at=TS) == 0  # all cached now
        rows = get_cached_news(s, "AAPL")
        assert len(rows) == 2
        assert rows[0].url == "http://x/2"  # most recent first


def test_news_score_memoization(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        save_news_score(
            s, score_key="k1", symbol="AAPL", value=72.0, created_at=TS,
            catalyst="earnings_beat", rationale="strong print", items_considered=3,
        )
    with session_scope(eng) as s:
        # second save with the same key returns the existing row, does not overwrite value
        row = save_news_score(s, score_key="k1", symbol="AAPL", value=10.0, created_at=TS)
        assert row.value == 72.0
        assert get_news_score(s, "k1").catalyst == "earnings_beat"
        assert get_news_score(s, "missing") is None


def test_brief_upsert(tmp_path):
    eng = _engine(tmp_path)
    with session_scope(eng) as s:
        upsert_brief(s, trading_day=DAY, text="first", created_at=TS, model="m")
    with session_scope(eng) as s:
        upsert_brief(s, trading_day=DAY, text="updated", created_at=TS, model="m2")
    with session_scope(eng) as s:
        b = get_brief(s, DAY)
        assert b.text == "updated"  # one row per day, overwritten
        assert b.model == "m2"
