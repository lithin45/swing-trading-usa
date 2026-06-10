"""Command-line entrypoint: ``swing-signals`` (see [project.scripts])."""

from __future__ import annotations

import argparse
import sys

from .config_loader import load_secrets, load_settings
from .main import run, run_backtest
from .output.healthcheck import ping


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="swing-signals",
        description=(
            "Signal-only swing-trading signal generator for US stocks. "
            "Decision support — never places orders."
        ),
    )
    sub = p.add_subparsers(dest="command")

    # ---- default (daily run) ----
    run_p = sub.add_parser("run", help="Daily signal run (default when no subcommand given)")
    _add_run_flags(run_p)

    # ---- backtest ----
    bt_p = sub.add_parser("backtest", help="Run the Stage-5 backtest harness")
    bt_p.add_argument("--from", dest="bt_from", metavar="YYYY-MM-DD",
                      help="Backtest start date (overrides config)")
    bt_p.add_argument("--to", dest="bt_to", metavar="YYYY-MM-DD",
                      help="Backtest end date (overrides config)")
    bt_p.add_argument("--cost-bps", type=float, metavar="N",
                      help="Per-side cost in basis points (overrides config, default 10)")
    bt_p.add_argument("--walk-forward", type=int, default=0, metavar="N_FOLDS",
                      help="Number of rolling walk-forward folds (0 = disabled)")
    bt_p.add_argument("--offline", action="store_true",
                      help="Use cached data only; never hit the network.")
    bt_p.add_argument("--config", default=None, metavar="PATH")

    # ---- track (outcome tracker) ----
    tr_p = sub.add_parser("track", help="Resolve open signals' outcomes against fresh prices")
    tr_p.add_argument("--offline", action="store_true",
                      help="Use cached data only; never hit the network.")
    tr_p.add_argument("--config", default=None, metavar="PATH")

    # ---- trade (submit paper entries from today's signals) ----
    trade_p = sub.add_parser("trade", help="Submit Alpaca paper entries for today's signals")
    trade_p.add_argument("--dry-run", action="store_true",
                         help="Print intended orders; submit nothing, write nothing.")
    trade_p.add_argument("--offline", action="store_true",
                         help="Use cached data only; never hit the network.")
    trade_p.add_argument("--config", default=None, metavar="PATH")

    # ---- manage (reconcile fills + exits for open paper trades) ----
    mng_p = sub.add_parser("manage", help="Reconcile fills + manage exits for open paper trades")
    mng_p.add_argument("--dry-run", action="store_true",
                       help="Print intended actions; submit nothing, write nothing.")
    mng_p.add_argument("--offline", action="store_true",
                       help="Use cached data only; never hit the network.")
    mng_p.add_argument("--config", default=None, metavar="PATH")

    # Also attach run flags to top-level for backwards compat (no subcommand).
    _add_run_flags(p)

    return p


def _add_run_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true",
                   help="Print alerts instead of sending; no-op write.")
    p.add_argument("--offline", action="store_true",
                   help="Use cached data only; never hit the network.")
    p.add_argument("--config", default=None, metavar="PATH")


def _alert_failure(settings, secrets, error: str) -> None:
    """Best-effort failure alert (dead-man's switch); never masks the original error."""
    try:
        from .output.dispatch import build_alerters, dispatch_failure
        dispatch_failure(build_alerters(settings, secrets), error)
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        secrets = load_secrets()
    except Exception as exc:  # noqa: BLE001
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.command == "backtest":
        return run_backtest(
            settings=settings,
            secrets=secrets,
            bt_start=args.bt_from,
            bt_end=args.bt_to,
            cost_bps=args.cost_bps,
            walk_forward_folds=args.walk_forward,
            offline=args.offline,
        )

    # The dead-man's switch must cover EVERY scheduled command, not just the signal
    # run: a trade/manage/track job that crashes (or silently stops being scheduled)
    # is exactly the failure mode healthchecks.io exists to surface.
    if args.command == "track":
        from .tracking.outcomes import run_tracker
        rc = run_tracker(settings=settings, secrets=secrets, offline=args.offline)
        ping(secrets.healthcheck_url, fail=rc != 0)
        return rc

    if args.command == "trade":
        from .broker.run import run_trade
        rc = run_trade(
            settings=settings, secrets=secrets, dry_run=args.dry_run, offline=args.offline
        )
        ping(None if args.dry_run else secrets.healthcheck_url, fail=rc != 0)
        return rc

    if args.command == "manage":
        from .broker.run import run_manage
        rc = run_manage(
            settings=settings, secrets=secrets, dry_run=args.dry_run, offline=args.offline
        )
        ping(None if args.dry_run else secrets.healthcheck_url, fail=rc != 0)
        return rc

    # Default: daily run (``swing-signals`` or ``swing-signals run``).
    dry_run = args.dry_run or settings.alerts.dry_run_default
    healthcheck_url = None if dry_run else secrets.healthcheck_url
    try:
        rc = run(settings=settings, secrets=secrets, dry_run=dry_run, offline=args.offline)
    except Exception as exc:  # noqa: BLE001 - fail loud: surface + alert, never silent
        print(f"run failed: {exc}", file=sys.stderr)
        if not dry_run:
            _alert_failure(settings, secrets, str(exc))
        ping(healthcheck_url, fail=True)
        return 1
    ping(healthcheck_url, fail=rc != 0)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
