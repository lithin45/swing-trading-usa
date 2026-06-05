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

from sqlalchemy import ForeignKey, UniqueConstraint
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
