"""Engine + session helpers. SQLite today, Postgres-ready via the connection URL."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from .models import Base

log = logging.getLogger("swing_signals.persistence")

# Columns added to `trades` after the table first shipped. create_all() makes a fresh
# table with every column but does NOT alter an existing one, so for a DB created before
# these existed we ADD COLUMN the missing ones (idempotent, additive + nullable — safe on
# the live Postgres and on SQLite). Types are spelled in dialect-portable SQL.
_TRADE_ADDED_COLUMNS = {
    "partial_done": "BOOLEAN",
    "partial_qty": "FLOAT",
    "partial_fill_price": "FLOAT",
    "partial_fill_date": "DATE",
    "partial_order_id": "VARCHAR(64)",
}


def _ensure_columns(engine: Engine) -> None:
    """Add any post-hoc `trades` columns missing from an existing table (a tiny migration)."""
    insp = inspect(engine)
    if "trades" not in insp.get_table_names():
        return  # create_all already made it fresh with every column
    existing = {c["name"] for c in insp.get_columns("trades")}
    missing = {c: t for c, t in _TRADE_ADDED_COLUMNS.items() if c not in existing}
    # Each ADD in its own transaction + swallow errors, so a concurrent add (the bot
    # and the dashboard can both run this against the same DB) can't fail the caller.
    for col, sql_type in missing.items():
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col} {sql_type}"))
        except Exception:  # noqa: BLE001 - already added concurrently / by the other process
            pass
    if missing:
        # The swallow above is for the benign concurrent-add race; verify nothing REAL
        # (permissions, dropped connection) was silenced, else queries fail far from here.
        still_missing = missing.keys() - {c["name"] for c in inspect(engine).get_columns("trades")}
        if still_missing:
            log.error(
                "trades migration could not add columns %s — staged-exit queries will fail; "
                "check DB permissions/connectivity", sorted(still_missing),
            )


def make_engine(url: str = "sqlite:///signals.db", *, echo: bool = False) -> Engine:
    """Create the engine and ensure the schema exists (``create_all`` is idempotent)."""
    engine = create_engine(url, echo=echo)
    Base.metadata.create_all(engine)
    _ensure_columns(engine)
    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional session: commit on success, roll back on error, always close."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
