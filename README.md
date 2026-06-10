# swing-signals

A **signal-only** swing-trading signal generator for US individual stocks (holding horizon: a
few days to ~1 month). Each trading day it pulls end-of-day data, scores each watchlist stock on
a set of factor modules, combines them into one conviction score, applies market-regime and risk
gates as hard overrides, and emits a ranked list of recommendations — each with an entry zone,
**ATR-based** stop, and target — then alerts you.

By default it is **signal-only**: it places nothing and you act on the report manually. An
**optional, opt-in automation layer** (Stage 8) can additionally run a fully automated **Alpaca
paper-trading** account, score news with **Claude**, and serve an online **dashboard** — see
[Stage 8](#stage-8--automated-paper-trading--dashboard-optional).

> ⚠️ **Decision support, not financial advice.** With the broker disabled (the default) it never
> connects to any account. With the broker enabled it trades a **simulated Alpaca _paper_ account
> only** — never real money, never a live brokerage.

## How the pieces fit (research files 01–12 → modules)

| Research file | Role | Module |
|---|---|---|
| 01 technical | Per-stock factor + **source of truth for ATR stops/targets** | `factors/f01_technical.py` |
| 02 news/sentiment | Per-stock factor (**Claude**-scored, entity-level) | `factors/f02_news_sentiment.py` |
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

**Trade budget (prime directive):** a hard ceiling of `budget.max_entries_per_month` (default 7)
NEW entries per calendar month, enforced in the engine (so alerts, the paper broker, and the
backtest all respect it), with a per-name post-stop cooldown (`budget.cooldown_days`). Each new
position submission charges a slot; re-prints of a still-held name ride free; a re-entry after a
close charges again. Deferred setups are flagged `BUDGET_EXHAUSTED` and persisted to the
`rejections` table; the backtest report prints the per-month entry-cadence histogram so the
ceiling is *proven*, not assumed (2018 replay: max 7/month, 0 months over cap).

**Earnings guard:** with a Finnhub key, the engine vetoes new entries within
`earnings.veto_days_before` days of a confirmed print (`EARNINGS_SOON`), and `manage` exits open
positions before one (`earnings_exit`) — a 3-ATR stop cannot contain an earnings gap. Without a
key the run proceeds unscreened and warns loudly.

**Principles:** modular and config-driven (add/remove a factor or change a weight in
`config/settings.yaml`, never in code); transparent (every signal records which factors fired and
why); fail safe and loud (missing/stale data → skip the stock and say so, never emit a confident
signal from bad data).

## Build stages

Built incrementally; each stage is confirmed before the next.

1. ✅ **Scaffold** — package layout, config + validation, interface stubs, tests
2. ✅ **Data layer** (free-first: yfinance/Stooq + FRED) with Parquet cache + retries
3. 🔶 **Factor modules** — 01 technical, 02 news (Claude), 04 macro, 07 regime done; 03 events / 05 themes / 06 smart-money still need API keys
4. ✅ **Scoring engine** + regime/macro/risk gates + ATR entry/stop/target
5. ✅ **Backtest harness** (realistic costs, signal-on-close → next-open, survivorship-warned)
6. ✅ **Output + logging** — ranked report, SQLite persistence (runs/signals/outcomes), Telegram + email + failure alerts
7. ✅ **Scheduling** — GitHub Actions daily cron + NYSE calendar gate + healthchecks.io dead-man's switch
8. ✅ **Automated paper trading + dashboard (opt-in)** — Alpaca paper execution, Claude news factor + daily brief, Neon Postgres history, Streamlit dashboard

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
swing-signals track         # resolve open signals' outcomes (realized R, MAE/MFE) vs fresh prices
swing-signals backtest --from 2022-01-01 --to 2024-12-31   # backtest harness (static watchlist)
swing-signals backtest --universe sp500                    # point-in-time S&P 500 membership —
                                #   the broad universe live trades, with index changes replayed
                                #   historically (needs config/sp500_changes.csv; see below)
swing-signals refresh-sp500     # rewrite config/sp500.csv + sp500_changes.csv from Wikipedia
swing-signals trade --dry-run   # Stage 8: preview today's paper entries (submits nothing)
swing-signals trade             # submit Alpaca paper entries (needs broker.enabled + keys)
swing-signals manage            # reconcile fills, trail stops, exit, snapshot the account
```

The broad backtest (`--universe sp500`) reconstructs index membership per bar from the committed
change log, so it never hands the engine a name the live screen could not have seen that day; it
also feeds the regime gate **real historical VIX/VIX3M from FRED** (with the SPY-ATR% proxy as the
no-key fallback) and reports how many membership names had no fetchable price history (the honest
residual survivorship gap — fully delisted names usually lack free data). `--include-themes` adds
today's curated theme list for live-parity exploration (explicitly biased — not for validation).

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

## Stage 8 — automated paper trading + dashboard (optional)

Everything here is **opt-in and paper-only**. Left off, the system behaves exactly as the
signal-only tool above. Turn it on by adding keys and flipping `broker.enabled: true` in
`config/settings.yaml`.

**What it adds**
- **Automated Alpaca paper trading.** After signals are generated, `trade` sizes each position off
  your **live paper equity** (this account: ~$100k), capped by a per-position notional limit and a
  gross-exposure ceiling, and submits the entry; `manage` reconciles fills (including partials),
  trails the chandelier stop, applies the staged/time exits, adopts any orphaned positions under a
  synthesized stop, and falls back to a market order (re-anchoring stop/target off the actual fill)
  if an entry ages out. In `exits.mode: staged` (live) entries are simple orders with self-managed
  exits + a standalone STOP-DAY protective order; in legacy mode, whole-share positions use a native
  Alpaca bracket (server-side stop + target, OCO). Idempotent: it can never double-open a day's
  signal.
- **Claude news factor + daily brief.** The `news_sentiment` (f02) factor scores headlines
  (Finnhub / Alpha Vantage / SEC 8-Ks) at the entity level with Claude; a plain-English daily
  brief is written for the dashboard. Both DB-memoized — an idempotent re-run never re-bills.
- **Alpaca price data** ahead of yfinance (more reliable), key-gated; yfinance/Stooq stay fallbacks.
- **Neon Postgres** so history persists across ephemeral CI runs and feeds the dashboard.
- **Streamlit dashboard** (`dashboard/`): equity curve, positions, realized performance
  (win rate / expectancy / profit factor), per-symbol candlestick charts, and the news panel.

**Setup**
1. Create free accounts: **Alpaca** (Paper Trading keys), **Anthropic** (API key), **Neon**
   (Postgres — copy both the direct and the *pooled* connection URLs), optionally **Alpha Vantage**.
2. Fill the Stage-8 vars in `.env` (see `.env.example`), then:
   ```bash
   pip install -e ".[data,db,broker,ai,postgres]"
   ```
3. In `config/settings.yaml` set `broker.enabled: true` (keep `paper: true`). Sizing auto-tracks
   your live paper equity (`broker.size_from_live_equity`), so you don't need to hand-tune
   `account.equity`; brackets are used automatically for whole-share positions (`entry_class: auto`).
4. Dry-run first, then go live on paper:
   ```bash
   swing-signals && swing-signals trade --dry-run     # preview intended orders
   swing-signals trade && swing-signals manage        # submit + manage (paper)
   ```
5. **Automation:** add the same keys as GitHub Actions repo secrets (plus a bare `DATABASE_URL`).
   `.github/workflows/daily.yml` runs signals → trade → manage → track after the close;
   `.github/workflows/intraday.yml` re-runs `manage` through the day.
6. **Dashboard:** `streamlit run dashboard/app.py` locally, or deploy to **Streamlit Community
   Cloud** with entrypoint `dashboard/app.py` and secrets `DATABASE_URL` (Neon *pooled* URL),
   `dashboard_password`, and the Alpaca paper keys (see `dashboard/.streamlit/secrets.toml.example`).

> Cost is a few cents/day (Claude with caching + memoization); everything else is free-tier. To cut
> it further, set a cheaper model in `swing_signals/ai/prompts.py` (e.g. `claude-haiku-4-5`).
