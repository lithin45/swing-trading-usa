"""Cost model (file 11 §5): bid-ask spread + slippage.

Commission is $0 for US equities (PFOF). The dominant cost is the bid-ask spread,
modelled as a fixed per-side bps applied to every fill. Default 10 bps per side
(≈ 20 bps round-trip) is a conservative but realistic estimate for liquid large-cap
swing trades (file 11: "Ernie Chan applied ~5 bps per side" for S&P 500; 10 bps
adds a slippage cushion).

The cost is deducted from every fill so the backtest equity curve is always
net-of-costs — costs are never optional or forgotten.

The stress multipliers (default 1.0 = the historical flat model, bit-identical)
exist because the flat calibration is large-cap while the universe floor is only
$10M ADV: stop-market fills in a breaking-down momentum name and market-fallback
entries are where real fills slip most. Sensitivity re-runs (15/20/30 bps, 2x
stop slippage) are a config change, not a code edit.
"""

from __future__ import annotations

from dataclasses import dataclass

# Exit reasons that fill as stop-markets (pay the stressed spread when configured).
_STOP_REASONS = frozenset({"stop", "gap_stop"})


@dataclass(frozen=True)
class CostModel:
    """Per-side spread+slippage model, in basis points."""

    per_side_bps: float = 10.0   # e.g. 10 bps = 0.10% per side
    stop_exit_mult: float = 1.0    # bps multiplier for stop/gap_stop exit fills
    market_entry_mult: float = 1.0  # bps multiplier for market-order entry fills

    @property
    def per_side_frac(self) -> float:
        return self.per_side_bps / 10_000.0

    def fill_long_entry(self, open_price: float, *, market: bool = False) -> float:
        """Simulated fill for a long buy: pay slightly above the open."""
        mult = self.market_entry_mult if market else 1.0
        return open_price * (1.0 + self.per_side_frac * mult)

    def fill_exit(self, price: float, *, reason: str | None = None) -> float:
        """Simulated fill for any exit: receive slightly below the reference price."""
        mult = self.stop_exit_mult if reason in _STOP_REASONS else 1.0
        return price * (1.0 - self.per_side_frac * mult)

    def round_trip_bps(self) -> float:
        """Total round-trip cost in bps (entry + exit, unstressed)."""
        return 2.0 * self.per_side_bps
