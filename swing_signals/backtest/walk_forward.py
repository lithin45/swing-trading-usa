"""Rolling walk-forward analysis (file 11 §7).

Splits the date range into ``n_folds`` equal windows. Each fold gets:
  - In-sample (IS): the first 70% of the fold window (training).
  - Out-of-sample (OOS): the remaining 30% (test).

The IS period warms up the engine; the OOS result is the key validation metric.
Rolling (not anchored) windows are conservative and expose regime-change risk.
All OOS windows are concatenated into the final OOS equity curve.

File-11 threshold: if OOS performance is dramatically worse than IS across all
folds, the strategy is overfit — simplify rather than re-optimise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from .runner import BacktestResult, BacktestRunner

log = logging.getLogger("swing_signals.backtest")


@dataclass
class FoldResult:
    fold: int
    is_start: date
    is_end: date
    oos_start: date
    oos_end: date
    is_metrics: dict
    oos_metrics: dict
    oos_result: BacktestResult


def walk_forward(
    runner: BacktestRunner,
    start: date,
    end: date,
    n_folds: int = 3,
    oos_fraction: float = 0.30,
) -> list[FoldResult]:
    """Run n_folds rolling IS/OOS windows and return per-fold results."""
    total_days = (end - start).days
    if total_days < 60 or n_folds < 1:
        log.warning("walk_forward: date range too short or n_folds < 1, skipping")
        return []

    fold_days = total_days // n_folds
    results: list[FoldResult] = []

    for i in range(n_folds):
        fold_start = start + timedelta(days=i * fold_days)
        fold_end = (
            start + timedelta(days=(i + 1) * fold_days - 1)
            if i < n_folds - 1
            else end
        )
        oos_split_days = int((fold_end - fold_start).days * (1.0 - oos_fraction))
        is_end = fold_start + timedelta(days=oos_split_days)
        oos_start = is_end + timedelta(days=1)

        log.info(
            "Walk-forward fold %d/%d: IS %s–%s | OOS %s–%s",
            i + 1, n_folds, fold_start, is_end, oos_start, fold_end,
        )

        is_result = runner.run(fold_start, is_end)
        oos_result = runner.run(oos_start, fold_end)

        results.append(FoldResult(
            fold=i + 1,
            is_start=fold_start, is_end=is_end,
            oos_start=oos_start, oos_end=fold_end,
            is_metrics=is_result.metrics,
            oos_metrics=oos_result.metrics,
            oos_result=oos_result,
        ))

    return results
