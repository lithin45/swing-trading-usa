"""Test isolation: never let a developer's real .env / DB env leak into tests.

Once a real ``.env`` (with ``SWING_DATABASE_URL``) exists locally, ``load_secrets()``
would carry that URL into ``resolve_db_url`` and tests that set a temp SQLite path
would silently hit the live Postgres instead. This autouse fixture neutralizes the
``.env`` file for every test and clears the DB env vars, keeping the suite hermetic
locally and in CI (CI has no ``.env``, so it's a no-op there).
"""

from __future__ import annotations

import pytest

from swing_signals.config_loader import Secrets


@pytest.fixture(autouse=True)
def _hermetic_secrets(monkeypatch):
    monkeypatch.setitem(Secrets.model_config, "env_file", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    # Test backtests are not real runs — keep them out of the runs audit file.
    monkeypatch.setenv("SWING_RUNS_AUDIT", "off")
    yield
