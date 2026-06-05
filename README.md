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

1. ✅ **Scaffold** — package layout, config + validation, interface stubs, tests
2. ✅ **Data layer** (free-first: yfinance/Stooq + FRED) with Parquet cache + retries
3. 🔶 **Factor modules** — 01 technical, 04 macro, 07 regime done; 02 news / 03 events / 05 themes / 06 smart-money still need API keys
4. ✅ **Scoring engine** + regime/macro/risk gates + ATR entry/stop/target
5. ✅ **Backtest harness** (realistic costs, signal-on-close → next-open, survivorship-warned)
6. ✅ **Output + logging** — ranked report, SQLite persistence (runs/signals/outcomes), Telegram + email + failure alerts
7. ✅ **Scheduling** — GitHub Actions daily cron + NYSE calendar gate + healthchecks.io dead-man's switch

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,data,db]"   # dev tooling + data layer + SQLite persistence
pytest                            # should pass
```

## Run

```bash
swing-signals --dry-run     # full pipeline; prints the ranked report, sends/persists nothing
swing-signals               # live run: pull EOD data, score, persist to SQLite, alert
swing-signals --offline     # cached data only (no network)
swing-signals backtest --from 2022-01-01 --to 2024-12-31   # backtest harness
```

`--dry-run` runs the real pipeline (data → factors → regime/macro gates → scoring → ATR levels
+ equity sizing) and prints a ranked report, but never writes the DB or sends alerts. A live run
persists each signal to SQLite and pushes the report to Telegram/email when configured (it falls
back to the console otherwise). FRED/Telegram/email stay dormant until the matching `SWING_*`
secrets are set — the run degrades loudly rather than failing. Unattended daily runs are wired in
`.github/workflows/daily.yml` (cron + NYSE calendar gate + healthchecks.io ping).

## Configuration

- **Tunable params** → `config/settings.yaml` (watchlist, factor weights, risk %, account equity,
  regime/macro thresholds). Version-controlled and validated by Pydantic on startup (fail-fast).
- **Secrets** (API keys, bot tokens) → environment variables / `.env` (gitignored). Copy
  `.env.example` to `.env`. Nothing is hardcoded; account equity is read from config at runtime,
  so the same percentage rules run at $500 and at $500,000.
