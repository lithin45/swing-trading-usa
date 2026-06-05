"""Cost model (file 11 §5): bid-ask spread + slippage.

Commission is $0 for US equities (PFOF). The dominant cost is the bid-ask spread,
modelled as a fixed per-side bps applied to every fill. Default 10 bps per side
(≈ 20 bps round-trip) is a conservative but realistic estimate for liquid large-cap
swing trades (file 11: "Ernie Chan applied ~5 bps per side" for S&P 500; 10 bps
adds a slippage cushion).

The cost is deducted from every fill so the backtest equity curve is always
net-of-costs — costs are never optional or forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """Per-side spread+slippage model, in basis points."""

    per_side_bps: float = 10.0  # e.g. 10 bps = 0.10% per side

    @property
    def per_side_frac(self) -> float:
        return self.per_side_bps / 10_000.0

    def fill_long_entry(self, open_price: float) -> float:
        """Simulated fill for a long buy: pay slightly above the open."""
        return open_price * (1.0 + self.per_side_frac)

    def fill_exit(self, price: float) -> float:
        """Simulated fill for any exit: receive slightly below the reference price."""
        return price * (1.0 - self.per_side_frac)

    def round_trip_bps(self) -> float:
        """Total round-trip cost in bps (entry + exit)."""
        return 2.0 * self.per_side_bps
