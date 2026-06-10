"""Plotly chart builders (candles, equity curve, R distribution) for the dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from swing_signals.factors import indicators as ind  # noqa: E402


def equity_curve(snaps: pd.DataFrame) -> go.Figure:
    """Equity line over its running peak, with the drawdown underwater below.

    A bare ``st.line_chart`` anchors y at 0, so a ±5% move on a $100k account
    renders as a flat line — exactly the thing the owner most needs to SEE.
    """
    eq = snaps.set_index("ts")["equity"].astype(float)
    peak = eq.cummax()
    dd = (eq / peak - 1.0) * 100.0
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.03
    )
    fig.add_trace(go.Scatter(x=peak.index, y=peak, name="peak",
                             line=dict(color="#9ca3af", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=eq.index, y=eq, name="equity",
                             line=dict(color="#3b82f6", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dd.index, y=dd, name="drawdown",
                             fill="tozeroy", line=dict(color="#dc2626", width=1)), row=2, col=1)
    fig.update_yaxes(tickformat="$,.0f", row=1, col=1)
    fig.update_yaxes(ticksuffix="%", row=2, col=1)
    fig.update_layout(height=380, showlegend=False, margin=dict(l=0, r=0, t=10, b=0),
                      hovermode="x unified")
    return fig


def r_histogram(closed: pd.DataFrame) -> go.Figure:
    """Distribution of realized R — the shape of the edge (asymmetry), not just the mean."""
    r = closed["realized_r"].dropna().astype(float)
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=r[r > 0], xbins=dict(size=0.5), name="wins",
                               marker_color="#16a34a", opacity=0.85))
    fig.add_trace(go.Histogram(x=r[r <= 0], xbins=dict(size=0.5), name="losses",
                               marker_color="#dc2626", opacity=0.85))
    fig.add_vline(x=0, line_color="#9ca3af", line_width=1)
    fig.update_layout(barmode="overlay", height=260, margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_title="realized R", yaxis_title="trades", showlegend=False)
    return fig


def cumulative_r(closed: pd.DataFrame) -> go.Figure:
    """Cumulative realized R by exit date — is the expectancy actually accruing?"""
    df = closed.dropna(subset=["realized_r", "exit_date"]).sort_values("exit_date")
    cum = df["realized_r"].astype(float).cumsum()
    fig = go.Figure(go.Scatter(x=df["exit_date"], y=cum, mode="lines+markers",
                               line=dict(color="#3b82f6", width=2)))
    fig.add_hline(y=0, line_color="#9ca3af", line_width=1)
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0),
                      yaxis_title="cumulative R")
    return fig


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
