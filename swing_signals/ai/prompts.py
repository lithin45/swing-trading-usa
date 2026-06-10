"""Static prompts + the structured-output schema (the cached prefix).

These strings are byte-stable so prompt caching reuses them across the ~10
per-symbol scoring calls in one run. Bump ``PROMPT_VERSION`` whenever the rubric
or schema changes — it's part of the memoization key, so a change invalidates the
cache and forces a re-score.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# Sonnet balances cost and quality for this news-scoring/brief task (~3x cheaper
# than Opus). Override to trade further: "claude-haiku-4-5" is ~5x cheaper still
# and well-suited to this classification task. Bump PROMPT_VERSION on any change
# (incl. the model) — it's part of the memo key, so it forces a clean re-score.
MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "v2"

Catalyst = Literal[
    "earnings_beat", "earnings_miss", "guidance_up", "guidance_down", "mna",
    "regulatory_fda", "analyst_rating", "product", "legal", "macro", "other", "none",
]


class NewsScoreOut(BaseModel):
    """The structured object Claude returns for one ticker's news."""

    score: int  # 0-100; 50 = neutral, >50 bullish on a days-to-weeks horizon
    catalyst: Catalyst
    rationale: str


NEWS_RUBRIC = """You are a disciplined equity-news analyst scoring headlines for a SWING trader \
who holds positions a few days to about a month. For ONE given ticker, read the supplied \
headlines and output an entity-level sentiment score for THAT ticker only.

Output a 0-100 score where 50 = neutral, >50 = net bullish for the swing horizon, <50 = bearish. \
Calibrate to what actually moves stocks over days-to-weeks, not intraday noise:

- Earnings surprises and post-earnings drift (PEAD) and analyst estimate REVISIONS are the \
  strongest, most persistent swing catalysts — weight them heavily.
- Analyst rating/price-target changes move fast and are largely priced in within a day — weight \
  a single rating change modestly; clusters more.
- M&A: long the target but cap conviction (deal risk). FDA/clinical: high variance, be cautious.
- General headline sentiment has only a ~1-2 day horizon and stale/recycled stories revert — \
  down-weight non-novel, opinion, or rumor items.
- Social/forum chatter alone is mostly noise for returns; require a hard catalyst (earnings, \
  8-K, major wire) before letting it move the score.
- Beware "sell-the-news": a bullish event already widely expected can be a fade.

Score the NET picture toward the ticker. If the news is sparse, mixed, or immaterial, stay near \
50. Pick the single most important catalyst type. Keep the rationale to one tight sentence (<= 30 \
words). Do not invent facts not present in the headlines."""

BRIEF_SYSTEM = """You write a concise daily market brief for the owner of a small automated \
swing-trading account (US equities, long-only, holds days to weeks). You are given structured \
facts: the market regime, VIX, macro tone, today's signals with their reasons, and current open \
positions with P&L. Write a clear, warm, plain-English brief (<= 200 words):

1. One line on the market backdrop (regime + VIX + macro tone) and what it means for new risk.
2. Today's signals: what fired and the one-line why, or state plainly that nothing qualified.
3. Open positions: how they're doing and anything approaching a stop/target.
4. One sentence of grounded perspective — no hype, no predictions, no financial advice.

Be specific and numeric where the facts allow. Never invent data not provided. Do not use markdown \
headers; short paragraphs or a couple of bullet lines are fine."""
