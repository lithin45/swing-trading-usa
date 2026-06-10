"""The tiny additive migration: ADD COLUMN for partial-exit fields on an old table."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from swing_signals.persistence.db import _ensure_columns, make_engine

_PARTIAL_COLS = {"partial_done", "partial_qty", "partial_fill_price", "partial_fill_date"}


def test_ensure_columns_adds_missing_on_old_table(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    eng = create_engine(url)
    # Simulate a pre-migration `trades` table missing the partial columns.
    with eng.begin() as c:
        c.execute(text("CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT)"))

    _ensure_columns(eng)
    cols = {col["name"] for col in inspect(eng).get_columns("trades")}
    assert _PARTIAL_COLS <= cols

    # Idempotent: a second pass adds nothing and does not raise.
    _ensure_columns(eng)


def test_make_engine_fresh_db_has_partial_columns(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/fresh.db")
    cols = {col["name"] for col in inspect(eng).get_columns("trades")}
    assert _PARTIAL_COLS <= cols
