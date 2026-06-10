"""Every dashboard page executes without raising (Streamlit's headless AppTest)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1] / "dashboard"
sys.path.insert(0, str(DASH))

from streamlit.testing.v1 import AppTest  # noqa: E402

PAGES = [
    "app.py",
    "pages/1_Positions.py",
    "pages/2_Signals_and_Outcomes.py",
    "pages/3_Charts.py",
    "pages/4_News.py",
]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    import streamlit as st

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/dash.db")
    # Auth is fail-closed without a password; tests opt into the explicit open mode
    # so every page body actually executes.
    monkeypatch.setenv("SWING_DASHBOARD_ALLOW_OPEN", "1")
    for k in ("SWING_ALPACA_API_KEY", "SWING_ALPACA_SECRET_KEY", "SWING_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    st.cache_resource.clear()
    st.cache_data.clear()
    yield


def test_auth_fails_closed_without_password(monkeypatch):
    """No dashboard_password and no explicit open flag -> the page must NOT render."""
    monkeypatch.delenv("SWING_DASHBOARD_ALLOW_OPEN", raising=False)
    at = AppTest.from_file(str(DASH / "app.py"), default_timeout=30)
    at.secrets["dashboard_password"] = ""  # blank == unset (and masks any local secrets.toml)
    at.run()
    assert not at.exception
    assert at.error, "expected a refusing-to-serve error banner"
    assert not at.metric, "page content rendered despite missing password"


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(page):
    at = AppTest.from_file(str(DASH / page), default_timeout=30)
    at.run()
    assert not at.exception, f"{page} raised: {at.exception}"
