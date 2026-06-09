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
    for k in ("SWING_ALPACA_API_KEY", "SWING_ALPACA_SECRET_KEY", "SWING_DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    st.cache_resource.clear()
    st.cache_data.clear()
    yield


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(page):
    at = AppTest.from_file(str(DASH / page), default_timeout=30)
    at.run()
    assert not at.exception, f"{page} raised: {at.exception}"
