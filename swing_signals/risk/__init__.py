"""Risk & sizing (research file 08) — HARD constraints.

Position size is derived from risk, never a fixed share/dollar count:
``shares = (equity * risk_pct) / (entry - stop)``, rounded down. Portfolio heat
caps, correlation/sector limits, and drawdown halts (which can veto or shrink any
trade) are implemented in Stage 4. This stage provides the core sizing seam.
"""
