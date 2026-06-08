"""Outcome tracker (files 11/12 §6): resolve open signals against fresh prices.

A second daily job. For every signal still open in the DB it walks the bars from
the day after the signal forward and decides whether the trade hit its stop,
target, or time-stop — using the *same* exit conventions as the backtest (enter at
the next bar's open; gap-through stop fills at the open; stop checked before target
intraday; time-stop at the close) so live results are comparable to the backtest
on the same accounting. It records realized R, %-return, bars held, and MAE/MFE.

``resolve_outcome`` is a pure function (no DB / network) so the exit logic is unit
tested directly; ``run_tracker`` wires it to the DB and the data layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd

from ..backtest.costs import CostModel

if TYPE_CHECKING:
    from ..config_loader import Secrets, Settings
    from ..data.loader import DataLoader

log = logging.getLogger("swing_signals.tracking")


@dataclass(frozen=True)
class ResolvedOutcome:
    status: str                 # open | target_hit | stopped | time_exit
    entry_date: date
    entry_fill: float
    exit_date: date | None
    exit_price: float | None
    bars_held: int
    realized_r: float | None    # (exit - entry) / (entry - stop)
    pct_return: float | None
    mae: float                  # max adverse excursion in R (<= 0)
    mfe: float                  # max favorable excursion in R (>= 0)


def resolve_outcome(
    *,
    signal_date: date,
    stop: float,
    target: float,
    ohlcv: pd.DataFrame,
    cost_bps: float = 10.0,
    max_hold_bars: int = 20,
) -> ResolvedOutcome | None:
    """Resolve one long signal against forward OHLCV. None if not yet entered.

    The entry bar is the first bar strictly after ``signal_date`` (signal on close,
    execute next open). Returns ``status='open'`` while the trade is still running.
    """
    costs = CostModel(per_side_bps=cost_bps)
    future = ohlcv[ohlcv.index > pd.Timestamp(signal_date)]
    if len(future) == 0:
        return None  # no bar after the signal yet — can't even enter

    entry_fill = costs.fill_long_entry(float(future.iloc[0]["open"]))
    entry_date = future.index[0].date()
    rps = entry_fill - stop
    if rps <= 0:
        return None  # not a viable long (entry <= stop)

    mae_price = entry_fill
    mfe_price = entry_fill
    status = "open"
    exit_price: float | None = None
    exit_date: date | None = None
    bars_held = 0

    for i in range(len(future)):
        row = future.iloc[i]
        bars_held = i + 1
        o, h = float(row["open"]), float(row["high"])
        low, c = float(row["low"]), float(row["close"])
        # Track intrabar extremes over the holding period (incl. the exit bar).
        mae_price = min(mae_price, low)
        mfe_price = max(mfe_price, h)

        if o < stop:                          # gap-through the stop -> fill at the open
            exit_price, status = costs.fill_exit(o), "stopped"
        elif low <= stop:                     # stop hit intraday
            exit_price, status = costs.fill_exit(stop), "stopped"
        elif h >= target:                     # target hit
            exit_price, status = costs.fill_exit(target), "target_hit"
        elif bars_held >= max_hold_bars:      # time-stop
            exit_price, status = costs.fill_exit(c), "time_exit"

        if status != "open":
            exit_date = future.index[i].date()
            break

    realized_r = pct_return = None
    if exit_price is not None:
        realized_r = (exit_price - entry_fill) / rps
        pct_return = exit_price / entry_fill - 1.0

    return ResolvedOutcome(
        status=status,
        entry_date=entry_date,
        entry_fill=round(entry_fill, 4),
        exit_date=exit_date,
        exit_price=round(exit_price, 4) if exit_price is not None else None,
        bars_held=bars_held,
        realized_r=round(realized_r, 4) if realized_r is not None else None,
        pct_return=round(pct_return, 4) if pct_return is not None else None,
        mae=round((mae_price - entry_fill) / rps, 4),
        mfe=round((mfe_price - entry_fill) / rps, 4),
    )


def run_tracker(
    settings: Settings,
    secrets: Secrets,
    *,
    today: date | None = None,
    offline: bool = False,
    loader: DataLoader | None = None,
) -> int:
    """Resolve every open signal in the DB against fresh prices. Returns exit code."""
    from ..config_loader import resolve_db_url
    from ..data.loader import DataLoader
    from ..persistence.db import make_engine, session_scope
    from ..persistence.repository import open_signals, upsert_outcome

    today = today or date.today()
    bt = settings.backtest or {}
    cost_bps = float(bt.get("cost_bps", 10.0))
    max_hold = int(bt.get("max_hold_bars", 20))
    loader = loader if loader is not None else DataLoader(settings, secrets)

    resolved = closed = still_open = 0
    ohlcv_cache: dict[str, pd.DataFrame | None] = {}

    with session_scope(make_engine(resolve_db_url(settings, secrets))) as session:
        opens = open_signals(session)
        log.info("tracker: %d open signal(s) to resolve", len(opens))
        for sig in opens:
            if sig.stop_price is None or sig.target_price is None:
                continue
            if sig.symbol not in ohlcv_cache:
                start = (sig.signal_date - timedelta(days=5)).isoformat()
                end = (today + timedelta(days=1)).isoformat()
                try:
                    ohlcv_cache[sig.symbol] = loader.get_ohlcv(
                        sig.symbol, start, end, offline=offline
                    )
                except Exception as exc:  # noqa: BLE001 - a missing symbol must not stop the job
                    log.warning("tracker: no OHLCV for %s (%s)", sig.symbol, exc)
                    ohlcv_cache[sig.symbol] = None
            df = ohlcv_cache[sig.symbol]
            if df is None or len(df) == 0:
                continue

            res = resolve_outcome(
                signal_date=sig.signal_date, stop=sig.stop_price, target=sig.target_price,
                ohlcv=df, cost_bps=cost_bps, max_hold_bars=max_hold,
            )
            if res is None:
                continue
            upsert_outcome(
                session, sig.id, status=res.status, updated_at=datetime.now(),
                exit_price=res.exit_price, exit_date=res.exit_date, bars_held=res.bars_held,
                realized_r=res.realized_r, pct_return=res.pct_return, mae=res.mae, mfe=res.mfe,
            )
            resolved += 1
            if res.status == "open":
                still_open += 1
            else:
                closed += 1

    log.info("tracker: updated %d (%d closed, %d still open)", resolved, closed, still_open)
    return 0
