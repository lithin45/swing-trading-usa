"""Trial ledger — the honest count of every configuration ever evaluated.

Deflated Sharpe needs to know HOW MANY configurations were tried before the
deployed one was chosen; without a ledger that number lives in commit messages
and session notes and is silently understated. Every backtest evaluation that a
human looks at gets one JSONL row in ``docs/validation/trials.jsonl``:

- ``purpose="selection"``  — the result influenced which config was chosen
  (these are what DSR's N counts);
- ``purpose="validation"`` — out-of-sample confirmation of an already-chosen
  config (holdouts, second windows);
- ``purpose="robustness"`` — sensitivity sweeps around a fixed config (looked
  at, logged, but not used to re-tune — the report shows DSR under
  N_selection and N_all so the distinction stays visible).

Append-only; duplicate ids are rejected so re-runs don't inflate N.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = _ROOT / "docs" / "validation" / "trials.jsonl"

PURPOSES = ("selection", "validation", "robustness")


@dataclass(frozen=True)
class Trial:
    id: str                 # unique, e.g. "2026-06-10-r1-wide_stop-2022-24"
    date: str               # when evaluated (YYYY-MM-DD)
    window: str             # e.g. "2022-01-01..2024-12-31"
    universe: str           # e.g. "sp500-pit" | "watchlist-10"
    config: str             # human description of the variant
    purpose: str            # selection | validation | robustness
    source: str             # commit sha / script / session note
    n_trades: int | None = None
    expectancy_r: float | None = None
    profit_factor: float | None = None
    win_rate: float | None = None
    sharpe_daily: float | None = None   # PER-PERIOD (daily) Sharpe when curves exist
    max_drawdown: float | None = None
    cagr: float | None = None
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise ValueError(f"purpose must be one of {PURPOSES}, got {self.purpose!r}")


def load_trials(path: str | Path = DEFAULT_LEDGER) -> list[Trial]:
    p = Path(path)
    if not p.exists():
        return []
    trials: list[Trial] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        trials.append(Trial(**json.loads(line)))
    return trials


def append_trial(trial: Trial, path: str | Path = DEFAULT_LEDGER) -> None:
    """Append one trial; raises on a duplicate id (re-runs must not inflate N)."""
    p = Path(path)
    if any(t.id == trial.id for t in load_trials(p)):
        raise ValueError(f"trial id already in ledger: {trial.id}")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(trial), separators=(",", ":")) + "\n")


def ledger_counts(trials: list[Trial]) -> dict[str, int]:
    out = {p: 0 for p in PURPOSES}
    for t in trials:
        out[t.purpose] += 1
    out["all"] = len(trials)
    return out


def recorded_sharpes(trials: list[Trial]) -> list[float]:
    return [t.sharpe_daily for t in trials if t.sharpe_daily is not None]
