"""News & Claude sentiment panel."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="News & Sentiment", page_icon="📰", layout="wide")

from _auth import require_auth  # noqa: E402
from _data import load_news, load_news_scores  # noqa: E402

require_auth()
st.title("📰 News & Sentiment")

scores = load_news_scores()
st.subheader("Claude sentiment scores")
if scores.empty:
    st.caption("No scored news yet (needs an Anthropic key + the news_sentiment factor active).")
else:
    cols = [c for c in [
        "trading_day", "symbol", "value", "catalyst", "rationale", "items_considered", "model",
    ] if c in scores.columns]
    st.dataframe(scores[cols], width="stretch", hide_index=True)

st.subheader("Recent headlines")
news = load_news()
if news.empty:
    st.caption("No cached headlines yet.")
else:
    syms = ["(all)"] + sorted(news["symbol"].unique())
    pick = st.selectbox("Filter by symbol", syms)
    view = news if pick == "(all)" else load_news(pick)
    cols = [c for c in ["published_at", "symbol", "source", "headline", "url"] if c in view.columns]
    st.dataframe(
        view[cols], width="stretch", hide_index=True,
        column_config={"url": st.column_config.LinkColumn("link")},
    )
