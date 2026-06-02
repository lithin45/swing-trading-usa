"""Pure technical indicators (pandas/numpy).

Computed locally rather than via pandas-ta/TA-Lib (file 09 endorses this) — it
avoids extra deps and the pandas-ta/NumPy-2 breakage, and keeps every indicator
transparent and unit-testable. Wilder-smoothed series (RSI/ATR/ADX) use the
standard ``ewm(alpha=1/n, adjust=False)`` approximation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder(gain, n)
    avg_loss = _wilder(loss, n)
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)  # avg_loss==0 -> rs=inf -> 100
    out = out.mask((avg_gain == 0) & (avg_loss == 0), 50.0)  # flat -> neutral
    return out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return _wilder(true_range(high, low, close), n)


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (ADX, +DI, -DI), all 14-period Wilder by default."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    atr_n = _wilder(true_range(high, low, close), n)
    plus_di = 100.0 * _wilder(plus_dm, n) / atr_n
    minus_di = 100.0 * _wilder(minus_dm, n) / atr_n
    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    return _wilder(dx, n), plus_di, minus_di


def donchian_high(high: pd.Series, n: int) -> pd.Series:
    """Highest high of the PRIOR n bars (excludes the current bar)."""
    return high.shift(1).rolling(n).max()


def donchian_low(low: pd.Series, n: int) -> pd.Series:
    """Lowest low of the PRIOR n bars (excludes the current bar)."""
    return low.shift(1).rolling(n).min()


def bollinger(
    close: pd.Series, n: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return (mid, upper, lower, bandwidth, percent_b)."""
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    upper = mid + k * sd
    lower = mid - k * sd
    bandwidth = (upper - lower) / mid
    width = (upper - lower).replace(0.0, np.nan)
    percent_b = (close - lower) / width
    return mid, upper, lower, bandwidth, percent_b


def rvol(volume: pd.Series, n: int = 20) -> pd.Series:
    return volume / volume.rolling(n).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()
