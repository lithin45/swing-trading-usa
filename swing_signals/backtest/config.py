"""BacktestCfg — backtest-specific configuration.

Separate from the live ``Settings`` so live and backtest params never clash.
Added as an optional field on ``Settings`` (default values mean old configs still
load without a ``backtest:`` section).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BacktestCfg(BaseModel):
    """Backtest parameters (all have safe defaults)."""

    model_config = ConfigDict(extra="forbid")

    start: str = "2022-01-01"   # ISO date string; inclusive
    end: str = "2024-12-31"     # ISO date string; inclusive (or "today")
    cost_bps: float = Field(default=10.0, ge=0)  # per-side spread+slippage in bps
    max_hold_bars: int = Field(default=20, gt=0)  # time-stop after N trading days
    warmup_bars: int = Field(default=210, gt=0)   # bars before first signal allowed
    equity_start: float = Field(default=0.0, ge=0)
    # 0 means "use settings.account.equity"
    # Replay the live account-level loss halts (risk.daily/weekly/monthly_loss_halt,
    # drawdown derisk/hard-halt) in the simulation. Default ON: without it the
    # backtest takes entries the live gates would refuse, overstating returns and
    # cadence (audit P1 #4). Turn off only to reproduce pre-2026-06 numbers.
    replay_loss_halts: bool = True
    # Cost-model stress multipliers (see backtest/costs.py). 1.0 = the historical
    # flat per-side model, bit-identical to every validated number.
    stop_exit_cost_mult: float = Field(default=1.0, ge=0)
    market_entry_cost_mult: float = Field(default=1.0, ge=0)
    # Credit a risk-free rate on idle cash (needs an rf series passed to the
    # runner). Default OFF so the equity curve stays comparable to every prior
    # number; 'alpha over cash' is reported either way when the series is present.
    rf_credit: bool = False
