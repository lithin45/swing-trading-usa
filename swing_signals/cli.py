"""Command-line entrypoint: ``swing-signals`` (see [project.scripts])."""

from __future__ import annotations

import argparse
import sys

from .config_loader import load_secrets, load_settings
from .main import run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="swing-signals",
        description=(
            "Signal-only swing-trading signal generator for US stocks. "
            "Decision support — never places orders."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline without sending alerts; print them to the console instead.",
    )
    p.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to settings.yaml (default: config/settings.yaml).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        secrets = load_secrets()
    except Exception as exc:  # noqa: BLE001 - fail fast with a clear message
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    dry_run = args.dry_run or settings.alerts.dry_run_default
    return run(settings=settings, secrets=secrets, dry_run=dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
