"""Point-in-time S&P 500 membership reconstruction from the changes log."""

from __future__ import annotations

from datetime import date

import pytest

from swing_signals.universe import membership as mod


@pytest.fixture
def fake_membership(tmp_path, monkeypatch):
    """Tiny synthetic current-members + changes CSVs; caches cleared around the test."""
    cur = tmp_path / "sp500.csv"
    cur.write_text("symbol,sector\nA,Tech\nB,Energy\nC,Tech\n", encoding="utf-8")
    chg = tmp_path / "sp500_changes.csv"
    chg.write_text(
        "date,added,removed\n2023-01-15,B,Y\n2024-06-01,C,X\n", encoding="utf-8"
    )
    monkeypatch.setattr(mod, "_SP500_CSV", cur)
    monkeypatch.setattr(mod, "_SP500_CHANGES_CSV", chg)
    mod.sp500.cache_clear()
    mod.sp500_changes.cache_clear()
    mod.members_asof.cache_clear()
    yield
    mod.sp500.cache_clear()
    mod.sp500_changes.cache_clear()
    mod.members_asof.cache_clear()


def test_members_asof_rolls_changes_back(fake_membership):
    assert mod.members_asof(date(2024, 12, 31)) == {"A", "B", "C"}
    # before the 2024 change: C (added) undone, X (removed) restored
    assert mod.members_asof(date(2024, 5, 31)) == {"A", "B", "X"}
    # before the 2023 change as well: B undone, Y restored
    assert mod.members_asof(date(2023, 1, 14)) == {"A", "Y", "X"}
    # the event day itself is effective (change visible by that close)
    assert mod.members_asof(date(2023, 1, 15)) == {"A", "B", "X"}


def test_members_union_covers_everyone_ever_in_window(fake_membership):
    assert mod.members_union(date(2023, 1, 1), date(2024, 12, 31)) == {
        "A", "B", "C", "X", "Y",
    }


def test_members_asof_none_without_changes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_SP500_CHANGES_CSV", tmp_path / "absent.csv")
    mod.sp500_changes.cache_clear()
    mod.members_asof.cache_clear()
    try:
        assert mod.members_asof(date(2024, 1, 1)) is None
    finally:
        mod.sp500_changes.cache_clear()
        mod.members_asof.cache_clear()


def test_real_committed_changes_log_parses():
    """The committed CSV loads, is chronological, and reconstructs a plausible index."""
    events = mod.sp500_changes()
    assert len(events) > 100
    assert all(a.day <= b.day for a, b in zip(events, events[1:], strict=False))
    m = mod.members_asof(date(2024, 12, 31))
    assert m is not None and 480 <= len(m) <= 520
