"""Per-symbol candlestick charts with indicators + the latest signal's levels."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Charts", page_icon="🕯️", layout="wide")

from _auth import require_auth  # noqa: E402
from _charts import candlestick  # noqa: E402
from _data import fetch_ohlcv, load_signals  # noqa: E402

require_auth()
st.title("🕯️ Charts")

sigs = load_signals(limit=500)
symbols = sorted(sigs["symbol"].unique()) if not sigs.empty else ["AAPL", "MSFT", "NVDA"]
symbol = st.selectbox("Symbol", symbols)

df = fetch_ohlcv(symbol)
if df.empty:
    st.warning(
        "No price data — set SWING_ALPACA_API_KEY/SECRET_KEY in Streamlit secrets for charts."
    )
else:
    levels = None
    if not sigs.empty:
        rows = sigs[sigs["symbol"] == symbol]
        if not rows.empty:
            r = rows.iloc[0]
            levels = {
                "entry_zone_high": r.get("entry_zone_high"),
                "stop_price": r.get("stop_price"),
                "target_price": r.get("target_price"),
            }
    st.plotly_chart(candlestick(df, symbol=symbol, levels=levels), width="stretch")
    if levels:
        st.caption(
            f"Latest signal levels — entry {levels['entry_zone_high']}, "
            f"stop {levels['stop_price']}, target {levels['target_price']}"
        )
