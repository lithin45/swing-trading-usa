"""Cached data access for the dashboard — Postgres/SQLite history + live Alpaca.

Query logic lives in plain ``query_*`` functions that take an engine (so they're
unit-testable without a Streamlit runtime); the ``load_*`` wrappers add caching
and the shared engine. Reads the same DB the bot writes (Neon in the cloud), and
live account/positions straight from Alpaca via the bot's own broker wrapper.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

# Make `swing_signals` importable on Streamlit Cloud without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402

from swing_signals.config_loader import _normalize_db_url  # noqa: E402
from swing_signals.persistence.db import _ensure_columns  # noqa: E402
from swing_signals.persistence.models import (  # noqa: E402
    AccountSnapshot,
    Base,
    Brief,
    BrokerRejection,
    NewsItem,
    NewsScore,
    Outcome,
    Signal,
    Trade,
)


def _secret(name: str) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - secrets file may be absent locally
        pass
    return os.environ.get(name)


def db_url() -> str:
    url = (
        _secret("DATABASE_URL")
        or _secret("SWING_DATABASE_URL")
        or "sqlite:///signals.db"
    )
    return _normalize_db_url(url)


@st.cache_resource
def get_engine():
    url = db_url()
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql"):  # tiny pool for Neon's connection ceiling
        kwargs.update(pool_size=2, max_overflow=3)
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)  # idempotent; no-op once the bot has created the tables
    _ensure_columns(engine)  # add staged-exit columns if this DB predates them (race-safe)
    return engine


@st.cache_resource
def get_broker():
    from swing_signals.broker.alpaca_client import AlpacaBroker

    return AlpacaBroker(
        _secret("SWING_ALPACA_API_KEY"), _secret("SWING_ALPACA_SECRET_KEY"), paper=True
    )


# -- plain queries (engine in; DataFrame out) — unit-testable -------------------

def _df(engine, stmt) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def query_signals(engine, *, limit: int = 500) -> pd.DataFrame:
    return _df(engine, select(Signal).order_by(Signal.signal_date.desc(), Signal.rank).limit(limit))


def query_trades(engine) -> pd.DataFrame:
    return _df(engine, select(Trade).order_by(Trade.signal_date.desc()))


def query_outcomes(engine) -> pd.DataFrame:
    return _df(engine, select(Outcome))


def query_snapshots(engine) -> pd.DataFrame:
    return _df(engine, select(AccountSnapshot).order_by(AccountSnapshot.ts))


def query_news(engine, *, symbol: str | None = None, limit: int = 200) -> pd.DataFrame:
    stmt = select(NewsItem).order_by(NewsItem.published_at.desc()).limit(limit)
    if symbol:
        stmt = select(NewsItem).where(NewsItem.symbol == symbol).order_by(
            NewsItem.published_at.desc()
        ).limit(limit)
    return _df(engine, stmt)


def query_news_scores(engine) -> pd.DataFrame:
    return _df(engine, select(NewsScore).order_by(NewsScore.created_at.desc()))


def query_brief(engine, day: date) -> str | None:
    df = _df(engine, select(Brief).where(Brief.trading_day == day))
    return None if df.empty else str(df.iloc[0]["text"])


def query_broker_rejections(engine, limit: int = 500) -> pd.DataFrame:
    return _df(
        engine,
        select(BrokerRejection).order_by(BrokerRejection.signal_date.desc()).limit(limit),
    )


def reconciliation_report(engine) -> tuple[pd.DataFrame, dict]:
    """Per-trade live-vs-shadow reconciliation rows + aggregate summary.

    Delegates to ``swing_signals.tracking.reconcile`` so the dashboard shows the
    exact numbers the track job logs — one reconciliation, two surfaces.
    """
    from dataclasses import asdict

    from sqlalchemy.orm import Session

    from swing_signals.tracking.reconcile import reconcile

    with Session(engine) as session:
        report = reconcile(session)
    rows = pd.DataFrame([asdict(r) for r in report.rows])
    return rows, report.summary()


def trade_stats(trades: pd.DataFrame) -> dict:
    """Win rate / expectancy / profit factor from closed trades."""
    closed = trades[trades["status"] == "closed"] if "status" in trades else trades
    closed = closed.dropna(subset=["realized_r"]) if "realized_r" in closed else closed
    n = len(closed)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "total_pnl": 0.0}
    wins = closed[closed["realized_r"] > 0]
    losses = closed[closed["realized_r"] <= 0]
    gross_win = wins["pnl"].sum() if "pnl" in wins else 0.0
    gross_loss = abs(losses["pnl"].sum()) if "pnl" in losses else 0.0
    return {
        "n": n,
        "win_rate": len(wins) / n,
        "expectancy": float(closed["realized_r"].mean()),
        "profit_factor": float(gross_win / gross_loss) if gross_loss else float("inf"),
        "total_pnl": float(closed["pnl"].sum()) if "pnl" in closed else 0.0,
    }


# -- cached wrappers (used by the pages) ---------------------------------------

@st.cache_data(ttl=300)
def load_signals(limit: int = 500) -> pd.DataFrame:
    return query_signals(get_engine(), limit=limit)


@st.cache_data(ttl=300)
def load_trades() -> pd.DataFrame:
    return query_trades(get_engine())


@st.cache_data(ttl=300)
def load_outcomes() -> pd.DataFrame:
    return query_outcomes(get_engine())


@st.cache_data(ttl=300)
def load_snapshots() -> pd.DataFrame:
    return query_snapshots(get_engine())


@st.cache_data(ttl=300)
def load_news(symbol: str | None = None) -> pd.DataFrame:
    return query_news(get_engine(), symbol=symbol)


@st.cache_data(ttl=300)
def load_news_scores() -> pd.DataFrame:
    return query_news_scores(get_engine())


@st.cache_data(ttl=300)
def load_broker_rejections(limit: int = 500) -> pd.DataFrame:
    return query_broker_rejections(get_engine(), limit=limit)


@st.cache_data(ttl=300)
def load_reconciliation() -> tuple[pd.DataFrame, dict]:
    return reconciliation_report(get_engine())


@st.cache_data(ttl=600)
def load_brief(day: date) -> str | None:
    return query_brief(get_engine(), day)


@st.cache_data(ttl=60)
def load_account() -> dict | None:
    b = get_broker()
    if not b.enabled:
        return None
    a = b.get_account()
    return {
        "equity": a.equity, "cash": a.cash, "buying_power": a.buying_power,
        "daytrade_count": a.daytrade_count,
    }


@st.cache_data(ttl=60)
def load_positions() -> pd.DataFrame:
    b = get_broker()
    if not b.enabled:
        return pd.DataFrame()
    rows = [
        {
            "symbol": p.symbol, "qty": p.qty, "avg_entry": p.avg_entry_price,
            "current": p.current_price, "market_value": p.market_value,
            "unrealized_pl": p.unrealized_pl,
        }
        for p in b.list_positions()
    ]
    return pd.DataFrame(rows)


def fetch_ohlcv(symbol: str, *, days: int = 400) -> pd.DataFrame:
    """Daily bars for charts via Alpaca (keys from secrets). Empty if no keys/data."""
    from datetime import timedelta

    from swing_signals.data.alpaca_provider import AlpacaProvider

    prov = AlpacaProvider(_secret("SWING_ALPACA_API_KEY"), _secret("SWING_ALPACA_SECRET_KEY"))
    if not prov.available:
        return pd.DataFrame()
    end = date.today()
    start = end - timedelta(days=days)
    try:
        return prov.get_ohlcv(symbol, start.isoformat(), (end + timedelta(days=1)).isoformat())
    except Exception:  # noqa: BLE001 - chart data is best-effort
        return pd.DataFrame()
