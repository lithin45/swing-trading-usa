# swing-signals

A **signal-only** swing-trading signal generator for US individual stocks (holding horizon: a
few days to ~1 month). Each trading day it pulls end-of-day data, scores each watchlist stock on
a set of factor modules, combines them into one conviction score, applies market-regime and risk
gates as hard overrides, and emits a ranked list of recommendations — each with an entry zone,
**ATR-based** stop, and target — then alerts you. **You place every order manually in Robinhood.**

> ⚠️ **This system is decision support, not financial advice, and never executes anything.**
> It does not connect to a broker, does not touch your account, and has no auto-execution path —
> by design. Every output is a suggestion for you to review and act on (or ignore) manually.

## How the pieces fit (research files 01–12 → modules)

| Research file | Role | Module |
|---|---|---|
| 01 technical | Per-stock factor + **source of truth for ATR stops/targets** | `factors/f01_technical.py` |
| 02 news/sentiment | Per-stock factor | `factors/f02_news_sentiment.py` |
| 03 events | Per-stock factor | `factors/f03_events.py` |
| 04 macro/geopolitical | Market-level **size modifier** (risk-on/off) | `market/f04_macro.py` |
| 05 themes/cycles | Per-stock factor (with froth penalty) | `factors/f05_themes_cycles.py` |
| 06 smart money | Per-stock factor | `factors/f06_smart_money.py` |
| 07 regime/breadth | Market-level **hard gate** (GREEN/YELLOW/RED) | `market/f07_regime.py` |
| 08 risk/sizing | **Hard constraints** — sizing, heat, halts | `risk/` |
| 09 data sources | Free-first data layer | `data/` |
| 10 scoring engine | Weighted composite + gates + attribution | `scoring/` |
| 11 backtesting | Validation harness | `backtest/` |
| 12 architecture | App shape, scheduling, alerting, logging | (whole tree) |

**Engine topology (composite + gates):** factors 01/02/03/05/06 are weighted into a per-stock
conviction score; **04 macro** scales position size; **07 regime** can hard-veto all new longs;
**08 risk** sizes every trade and can veto or shrink it. A high score can never buy its way past a
risk-off market or a blown risk limit.

**Principles:** modular and config-driven (add/remove a factor or change a weight in
`config/settings.yaml`, never in code); transparent (every signal records which factors fired and
why); fail safe and loud (missing/stale data → skip the stock and say so, never emit a confident
signal from bad data).

## Build stages

Built incrementally; each stage is confirmed before the next.

1. **Scaffold** — package layout, config + validation, interface stubs, tests *(this stage)*
2. Data layer (free-first: yfinance/Stooq, FRED, Finnhub, SEC EDGAR, FINRA) with cache + retries
3. Factor modules one at a time (01 → 02 → 03 → 05 → 06), each testable in isolation
4. Scoring engine + regime/risk gates + ATR entry/stop/target
5. Backtest harness (realistic costs, no lookahead/survivorship bias)
6. Alert/output layer (daily report + Telegram/email) + signal logging
7. Scheduling (cloud, unattended)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # scaffold deps only; add extras per stage, e.g. -e ".[dev,data]"
pytest                          # should pass
```

## Run (scaffold)

```bash
swing-signals --dry-run         # loads + validates config, prints the planned pipeline (no-op)
# or: python -m swing_signals.cli --dry-run
```

The scaffold wires no factor logic yet — `--dry-run` validates config and prints each pipeline
stage as a no-op so you can confirm the skeleton end to end.

## Configuration

- **Tunable params** → `config/settings.yaml` (watchlist, factor weights, risk %, account equity,
  regime/macro thresholds). Version-controlled and validated by Pydantic on startup (fail-fast).
- **Secrets** (API keys, bot tokens) → environment variables / `.env` (gitignored). Copy
  `.env.example` to `.env`. Nothing is hardcoded; account equity is read from config at runtime,
  so the same percentage rules run at $500 and at $500,000.
