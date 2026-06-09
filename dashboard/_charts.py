"""Plotly candlestick + indicator overlays, reusing the bot's own indicators."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from swing_signals.factors import indicators as ind  # noqa: E402


def candlestick(df: pd.DataFrame, *, symbol: str, levels: dict | None = None) -> go.Figure:
    """Candles + SMA200/50 + EMA20/50, with optional entry/stop/target lines."""
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=symbol,
    ))
    close = df["close"]
    for n, color in ((200, "#9ca3af"), (50, "#3b82f6")):
        if len(df) >= n:
            fig.add_trace(go.Scatter(
                x=df.index, y=ind.sma(close, n), name=f"SMA{n}", line=dict(width=1, color=color),
            ))
    for n, color in ((20, "#f59e0b"), (50, "#10b981")):
        if len(df) >= n:
            fig.add_trace(go.Scatter(
                x=df.index, y=ind.ema(close, n), name=f"EMA{n}",
                line=dict(width=1, dash="dot", color=color),
            ))
    for label, key, color in (
        ("entry", "entry_zone_high", "#2563eb"),
        ("stop", "stop_price", "#dc2626"),
        ("target", "target_price", "#16a34a"),
    ):
        price = (levels or {}).get(key)
        if price:
            fig.add_hline(y=float(price), line_dash="dash", line_color=color,
                          annotation_text=label, annotation_position="right")
    fig.update_layout(
        height=620, xaxis_rangeslider_visible=False, legend_orientation="h",
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig
