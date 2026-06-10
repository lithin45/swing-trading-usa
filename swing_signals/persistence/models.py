"""SQLAlchemy ORM models (research file 12): runs, signals, outcomes.

One row per scheduled run (health/audit), one per generated signal (with full
factor attribution + the git SHA and config hash that produced it), and one per
signal outcome as the trade resolves. Storage-agnostic — the same models run on
SQLite now and Postgres later by changing the connection string. The
``UNIQUE(signal_date, symbol)`` guard makes a re-run idempotent: it can never
duplicate a day's signal for a symbol.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Run(Base):
    """One scheduled execution (health/audit row)."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_ts: Mapped[datetime]
    trading_day: Mapped[date | None] = mapped_column(default=None)
    status: Mapped[str]  # success | no_trading_day | failed
    n_signals: Mapped[int] = mapped_column(default=0)
    data_provider: Mapped[str | None] = mapped_column(default=None)
    git_sha: Mapped[str | None] = mapped_column(default=None)
    config_hash: Mapped[str | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)

    signals: Mapped[list[Signal]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Signal(Base):
    """One generated (actionable) signal, with full attribution for reproducibility."""

    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("signal_date", "symbol", name="uq_signal_day_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    signal_date: Mapped[date]
    symbol: Mapped[str]
    direction: Mapped[str] = mapped_column(default="long")
    composite_score: Mapped[float]
    conviction_tier: Mapped[str | None] = mapped_column(default=None)
    rank: Mapped[int | None] = mapped_column(default=None)
    reference_price: Mapped[float | None] = mapped_column(default=None)
    entry_zone_low: Mapped[float | None] = mapped_column(default=None)
    entry_zone_high: Mapped[float | None] = mapped_column(default=None)
    stop_price: Mapped[float | None] = mapped_column(default=None)
    target_price: Mapped[float | None] = mapped_column(default=None)
    reward_risk: Mapped[float | None] = mapped_column(default=None)
    atr: Mapped[float | None] = mapped_column(default=None)
    risk_per_share: Mapped[float | None] = mapped_column(default=None)  # entry - stop = 1R
    suggested_shares: Mapped[float | None] = mapped_column(default=None)
    suggested_risk_pct: Mapped[float | None] = mapped_column(default=None)
    chandelier_stop: Mapped[float | None] = mapped_column(default=None)
    agreement_score: Mapped[float | None] = mapped_column(default=None)
    regime_state: Mapped[str | None] = mapped_column(default=None)
    factor_scores: Mapped[str | None] = mapped_column(default=None)  # JSON: per-factor attribution
    flags: Mapped[str | None] = mapped_column(default=None)          # JSON: list of flags
    created_at: Mapped[datetime]

    run: Mapped[Run] = relationship(back_populates="signals")
    outcome: Mapped[Outcome | None] = relationship(
        back_populates="signal", cascade="all, delete-orphan", uselist=False
    )


class Outcome(Base):
    """One signal's realized outcome, updated as the trade resolves (file 12 §6)."""

    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), unique=True)
    status: Mapped[str] = mapped_column(default="open")  # open|target_hit|stopped|time_exit
    actual_entry: Mapped[float | None] = mapped_column(default=None)  # user fill (for slippage)
    exit_price: Mapped[float | None] = mapped_column(default=None)
    exit_date: Mapped[date | None] = mapped_column(default=None)
    bars_held: Mapped[int | None] = mapped_column(default=None)
    realized_r: Mapped[float | None] = mapped_column(default=None)
    pct_return: Mapped[float | None] = mapped_column(default=None)
    slippage: Mapped[float | None] = mapped_column(default=None)
    mae: Mapped[float | None] = mapped_column(default=None)  # max adverse excursion (R)
    mfe: Mapped[float | None] = mapped_column(default=None)  # max favorable excursion (R)
    updated_at: Mapped[datetime]

    signal: Mapped[Signal] = relationship(back_populates="outcome")


# ---------------------------------------------------------------------------
# Stage 8 — automated paper trading + AI news (added off the same Base so
# make_engine's create_all auto-provisions them; no migration tooling needed).
# ---------------------------------------------------------------------------


class Trade(Base):
    """One paper trade: a persisted signal the broker acted on, through its lifecycle.

    ``UNIQUE(signal_date, symbol)`` makes the entry submission idempotent the same way the
    ``signals`` table is — a re-run of the ``trade`` job can never open two positions for one
    day's signal. ``effective_stop`` is the chandelier-ratcheted stop (only ever rises).
    """

    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("signal_date", "symbol", name="uq_trade_day_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), default=None)
    signal_date: Mapped[date]
    symbol: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(default="pending_entry")
    # pending_entry | open | closing | closed | canceled
    order_class: Mapped[str] = mapped_column(String(12), default="simple")  # bracket | simple

    # --- entry ---
    entry_order_id: Mapped[str | None] = mapped_column(String(64), default=None)
    entry_client_order_id: Mapped[str | None] = mapped_column(String(80), default=None)
    entry_order_type: Mapped[str | None] = mapped_column(String(12), default=None)  # limit|market
    limit_price: Mapped[float | None] = mapped_column(default=None)
    qty: Mapped[float | None] = mapped_column(default=None)
    actual_entry: Mapped[float | None] = mapped_column(default=None)  # fill price
    entry_fill_date: Mapped[date | None] = mapped_column(default=None)
    filled_qty: Mapped[float | None] = mapped_column(default=None)

    # --- risk levels (absolute prices) ---
    stop_price: Mapped[float | None] = mapped_column(default=None)
    target_price: Mapped[float | None] = mapped_column(default=None)
    chandelier_stop: Mapped[float | None] = mapped_column(default=None)
    effective_stop: Mapped[float | None] = mapped_column(default=None)  # max(stop, chandelier)
    risk_per_share: Mapped[float | None] = mapped_column(default=None)  # actual_entry - stop = 1R
    suggested_risk_pct: Mapped[float | None] = mapped_column(default=None)  # live portfolio heat

    # --- staged-exit partial scale-out (exits.mode=staged; null on legacy trades) ---
    partial_done: Mapped[bool | None] = mapped_column(default=False)
    partial_qty: Mapped[float | None] = mapped_column(default=None)  # shares sold at the 1st target
    partial_fill_price: Mapped[float | None] = mapped_column(default=None)
    partial_fill_date: Mapped[date | None] = mapped_column(default=None)

    # --- bracket child legs (native OCO; server-side stop+target) ---
    take_profit_order_id: Mapped[str | None] = mapped_column(String(64), default=None)
    stop_loss_order_id: Mapped[str | None] = mapped_column(String(64), default=None)

    # --- exit ---
    exit_order_id: Mapped[str | None] = mapped_column(String(64), default=None)
    protective_order_id: Mapped[str | None] = mapped_column(String(64), default=None)  # STOP-DAY
    exit_price: Mapped[float | None] = mapped_column(default=None)
    exit_date: Mapped[date | None] = mapped_column(default=None)
    exit_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    # stopped | target_hit | time_exit | canceled
    realized_r: Mapped[float | None] = mapped_column(default=None)
    pct_return: Mapped[float | None] = mapped_column(default=None)
    pnl: Mapped[float | None] = mapped_column(default=None)
    bars_held: Mapped[int | None] = mapped_column(default=None)

    # --- pending lifecycle (DAY limits expire; we re-place until aged out) ---
    pending_since: Mapped[date | None] = mapped_column(default=None)
    pending_days: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class AccountSnapshot(Base):
    """A point-in-time broker account reading — the dashboard equity curve."""

    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime]
    trading_day: Mapped[date | None] = mapped_column(default=None)
    equity: Mapped[float]
    cash: Mapped[float | None] = mapped_column(default=None)
    buying_power: Mapped[float | None] = mapped_column(default=None)
    open_positions: Mapped[int] = mapped_column(default=0)
    open_risk_pct: Mapped[float | None] = mapped_column(default=None)


class NewsItem(Base):
    """A cached news headline tagged to a symbol — dashboard panel + Claude input cache."""

    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("symbol", "url", name="uq_news_symbol_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16))
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    url: Mapped[str] = mapped_column(String(512))
    source: Mapped[str | None] = mapped_column(String(64), default=None)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    sentiment_hint: Mapped[float | None] = mapped_column(default=None)  # provider's own score
    fetched_at: Mapped[datetime]


class NewsScore(Base):
    """A memoized Claude entity-level news score, keyed on a content hash.

    An idempotent re-run is free (no re-billing):
    ``score_key = hash(symbol + item ids + model + prompt_version)``.
    """

    __tablename__ = "news_scores"
    __table_args__ = (UniqueConstraint("score_key", name="uq_news_score_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16))
    trading_day: Mapped[date | None] = mapped_column(default=None)
    score_key: Mapped[str] = mapped_column(String(64))
    value: Mapped[float]  # 0-100, 50 = neutral (matches SubScore)
    catalyst: Mapped[str | None] = mapped_column(String(40), default=None)
    rationale: Mapped[str | None] = mapped_column(Text, default=None)
    model: Mapped[str | None] = mapped_column(String(64), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(16), default=None)
    items_considered: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime]


class Brief(Base):
    """The daily plain-English AI market/portfolio brief shown on the dashboard."""

    __tablename__ = "briefs"
    __table_args__ = (UniqueConstraint("trading_day", name="uq_brief_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trading_day: Mapped[date]
    text: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime]
