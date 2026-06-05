"""Engine + session helpers. SQLite today, Postgres-ready via the connection URL."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from .models import Base


def make_engine(url: str = "sqlite:///signals.db", *, echo: bool = False) -> Engine:
    """Create the engine and ensure the schema exists (``create_all`` is idempotent)."""
    engine = create_engine(url, echo=echo)
    Base.metadata.create_all(engine)
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
