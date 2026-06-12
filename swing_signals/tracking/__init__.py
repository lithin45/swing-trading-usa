"""Live-performance tracking (files 11/12).

``outcomes`` grades every persisted signal on a market-at-next-open reference
model (same exit machine as the backtest), records realized R, %-return, bars
held and MAE/MFE, and — where the Alpaca paper broker actually filled the
signal — copies the real fill onto the outcome row with its slippage vs the
reference entry. ``reconcile`` then joins closed paper trades to those
theoretical outcomes: entry/exit slippage, live-minus-shadow R, limit fill
rate, and monthly entry cadence — the authoritative live-vs-model comparison.
"""
