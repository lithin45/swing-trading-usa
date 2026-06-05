"""Stage 5 backtest harness (research file 11).

A slice-and-replay engine that feeds historical data bar-by-bar to the exact same
``generate_signals()`` function used in live runs — so the backtest tests what the
live system would have done, not a separate approximation. No lookahead: the engine
only ever sees data up to bar ``t``; fills happen at bar ``t+1`` open.

Key modules:
- ``config``   — BacktestCfg (start/end/cost/hold parameters)
- ``costs``    — CostModel (spread + slippage, per-side bps)
- ``metrics``  — compute_metrics() → all file-11 statistics
- ``runner``   — BacktestRunner → BacktestResult
- ``walk_forward`` — rolling n-fold walk-forward split
- ``report``   — format_backtest_report() → human-readable output
"""
