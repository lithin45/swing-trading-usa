"""Smoke tests: package imports, scaffold run, CLI parser."""

from __future__ import annotations

from datetime import date

from swing_signals import __version__
from swing_signals.cli import build_parser
from swing_signals.main import run


def test_version_present():
    assert __version__


def test_dry_run_on_weekday_returns_zero():
    # 2024-01-08 is a Monday. offline=True => cache-only, no network in CI.
    assert run(dry_run=True, offline=True, today=date(2024, 1, 8)) == 0


def test_no_op_on_weekend_returns_zero():
    # 2024-01-06 is a Saturday — exits at the calendar gate before any data.
    assert run(dry_run=True, today=date(2024, 1, 6)) == 0


def test_cli_parser_dry_run_flag():
    args = build_parser().parse_args(["--dry-run"])
    assert args.dry_run is True
    assert args.config is None
