# Architecture Document: Cloud-Hosted Hands-Off Swing-Trading Signal Generator

## 1. Overview

This document specifies a **signal-only, cloud-hosted, hands-off swing-trading signal generator** for US individual stocks, to be built in Python by Claude Code. The system pulls daily market data, computes a battery of factor sub-scores (files 01–08), runs a scoring engine with regime/risk gates (file 10) against data sources (file 09) and config (file 11), and emits a daily ranked signal list — each with entry price, stop loss, and exit target — then alerts the user, who manually places orders in Robinhood. Nothing auto-executes.

**Design priorities, in order:** (1) runs unattended in the cloud even when the user's laptop is off; (2) modular factor architecture so individual factors drop in/out via a registry; (3) reliability (retries, caching, idempotent runs, failure alerts, dead-man's-switch monitoring); (4) low cost (free-tier-first, with a recommended paid data API in the $10–30/mo band); (5) build order optimized for an AI coding agent.

**Top-level recommendation stack:** Python 3.11+, data from **Tiingo** (paid Power tier) with **yfinance** as a free fallback, NYSE calendar via **pandas_market_calendars**, config via **YAML + Pydantic** validation, persistence in **SQLite** (committed/backed up) migratable to Postgres, alerts via **Telegram bot** (primary) + email (backup), scheduling on **GitHub Actions** for v1 then **Modal** or **Google Cloud Run Jobs + Cloud Scheduler** for production, monitored by **healthchecks.io**.

---

## 2. Architecture Diagram

```
                          ┌─────────────────────────────────────────┐
                          │   SCHEDULER (cloud, unattended)          │
                          │   GitHub Actions cron / Modal Cron /     │
                          │   Cloud Run Job + Cloud Scheduler        │
                          │   fires ~30-60 min after US close (ET)   │
                          └───────────────────┬─────────────────────┘
                                              │ triggers
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │                         APPLICATION (Python)                               │
   │                                                                            │
   │  ┌────────────┐   STEP 0: Calendar gate                                    │
   │  │ Calendar   │── is today an NYSE trading day? ── No ──▶ exit 0 (no-op)   │
   │  │ (pmcal)    │                                          ping healthcheck   │
   │  └────────────┘                                                            │
   │        │ Yes                                                               │
   │        ▼                                                                   │
   │  ┌────────────────┐     ┌──────────────────────────────────────────────┐ │
   │  │ DATA LAYER     │────▶│ Cache (Parquet/SQLite)  retries+backoff        │ │
   │  │ (file 09)      │     │ adjusted OHLCV, fundamentals, breadth/SPY      │ │
   │  │ Tiingo/yfin    │     └──────────────────────────────────────────────┘ │
   │  └───────┬────────┘                                                        │
   │          │ clean DataFrames (one per symbol + market context)             │
   │          ▼                                                                 │
   │  ┌──────────────────────────────────────────────────────────────────┐    │
   │  │ FACTOR REGISTRY  (plugin pattern, files 01-08)                     │    │
   │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ...        │    │
   │  │  │ F01  │ │ F02  │ │ F03  │ │ F04  │ │ F05  │ │ F06  │            │    │
   │  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘            │    │
   │  │  each: compute(symbol_data, ctx) -> sub_score in [0,1]            │    │
   │  └───────┬──────────────────────────────────────────────────────────┘    │
   │          │ per-symbol sub-score vector                                    │
   │          ▼                                                                 │
   │  ┌──────────────────────────────────────────────────────────────────┐    │
   │  │ SCORING ENGINE (file 10) + REGIME/RISK GATES (file 11 config)      │    │
   │  │  weighted composite → regime filter (SPY>200dma, VIX) →            │    │
   │  │  risk gate (liquidity, price, ATR) → rank → select top N          │    │
   │  └───────┬──────────────────────────────────────────────────────────┘    │
   │          │ ranked signals                                                  │
   │          ▼                                                                 │
   │  ┌──────────────────────────────────────────────────────────────────┐    │
   │  │ SIGNAL BUILDER: entry = close (or limit %), stop = entry-X%,       │    │
   │  │  exit = entry+Y% (or ATR multiple); compute R-multiple target     │    │
   │  └───────┬───────────────────────────────────────────┬──────────────┘    │
   │          ▼                                            ▼                    │
   │  ┌────────────────┐                          ┌─────────────────────┐      │
   │  │ PERSISTENCE    │                          │ ALERT/OUTPUT LAYER  │      │
   │  │ signals table  │                          │ Telegram (primary)  │      │
   │  │ outcomes table │                          │ + Email backup      │      │
   │  │ runs table     │                          │ + Streamlit dash    │      │
   │  │ SQLite/Postgres│                          └─────────────────────┘      │
   │  └────────────────┘                                                        │
   └────────────────────────────┬───────────────────────────────────────────┘
                                 │ on success AND on failure
                                 ▼
                      ┌─────────────────────────┐
                      │ healthchecks.io ping     │  (dead-man's switch:
                      │ + failure alert to user  │   alerts if job never runs)
                      └─────────────────────────┘
```

A **second scheduled job** (the "outcome tracker") runs daily to update open positions' realized outcomes against live prices, and a periodic job compares live performance to backtest expectations.

---

## 3. Module Breakdown

The system is layered so each layer talks to the next only through a narrow, typed interface. This separation of concerns (data ingestion → computation → scoring → output) is the standard pattern for quant/factor systems and keeps factors hot-swappable.

### Code-structure tree

```
swing_signals/
├── pyproject.toml              # deps + entry-point plugin registration
├── config/
│   ├── settings.yaml           # watchlist, weights, risk params, regime gates
│   ├── settings.schema.py      # Pydantic models that validate settings.yaml
│   └── .env                    # SECRETS ONLY (gitignored): API keys, bot token
├── swing_signals/
│   ├── __init__.py
│   ├── main.py                 # orchestrator / entrypoint (the daily run)
│   ├── calendar_gate.py        # NYSE trading-day + half-day awareness
│   ├── config_loader.py        # load+validate YAML, merge env secrets
│   ├── data/
│   │   ├── base.py             # DataProvider Protocol (interface)
│   │   ├── tiingo_provider.py  # primary provider
│   │   ├── yfinance_provider.py# fallback provider
│   │   ├── cache.py            # parquet/sqlite cache, TTL, idempotency
│   │   └── retry.py            # tenacity-based retry/backoff wrapper
│   ├── factors/
│   │   ├── base.py             # Factor ABC/Protocol + FactorResult
│   │   ├── registry.py         # the plugin registry
│   │   ├── f01_momentum.py     # one file per factor (files 01-08)
│   │   ├── f02_trend.py
│   │   ├── ...                 # f03..f08
│   ├── scoring/
│   │   ├── engine.py           # weighted composite (file 10)
│   │   ├── regime.py           # market regime gate
│   │   └── risk.py             # per-symbol risk gate + entry/stop/exit
│   ├── output/
│   │   ├── base.py             # Alerter Protocol
│   │   ├── telegram.py
│   │   ├── email_smtp.py
│   │   ├── discord.py
│   │   └── formatters.py       # tables/markdown for messages
│   ├── persistence/
│   │   ├── db.py               # engine/session (SQLAlchemy)
│   │   ├── models.py           # ORM: Signal, Outcome, Run
│   │   └── repository.py       # save_signals(), update_outcomes()
│   └── tracking/
│       ├── outcomes.py         # realized R, hit-rate, slippage
│       └── backtest_compare.py # live-vs-backtest attribution
└── tests/
    ├── fixtures/               # deterministic OHLCV snapshots
    ├── test_factors/           # golden/snapshot tests per factor
    ├── test_scoring.py
    └── test_integration.py
```

### 3.1 Data layer (file 09)

A `DataProvider` Protocol defines the contract every source must satisfy:

```python
from typing import Protocol
import pandas as pd

class DataProvider(Protocol):
    def get_ohlcv(self, symbol: str, start: str, end: str) -> pd.DataFrame: ...
    def get_fundamentals(self, symbol: str) -> dict: ...
    def get_market_context(self) -> pd.DataFrame: ...   # SPY, VIX, breadth
```

Concrete providers (`TiingoProvider`, `YfinanceProvider`) implement it. The orchestrator depends only on the Protocol (dependency inversion), so swapping providers is a one-line config change. Every network call goes through a `tenacity`-based retry wrapper and a cache layer that stores adjusted OHLCV as Parquet keyed by `(symbol, date)`, making the daily run **idempotent** — re-running the same day reads cache, never double-pulls.

### 3.2 Factor modules (files 01–08) — plugin/registry pattern

Each factor is a self-contained module implementing a common interface and **self-registering** into a registry. This is the canonical Python plugin approach: an abstract base class (or `Protocol`) defines the contract; a decorator adds each concrete factor to a central dict; the engine iterates the registry. Adding a new factor = drop a new file + decorate; **no edits to the engine or `main.py`** (Open/Closed principle).

```python
# factors/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd

@dataclass
class FactorResult:
    name: str
    score: float          # normalized to [0, 1]
    raw: dict             # diagnostics for logging/attribution

class Factor(ABC):
    name: str
    requires: list[str]   # e.g. ["ohlcv", "fundamentals"]
    @abstractmethod
    def compute(self, data: pd.DataFrame, ctx: dict) -> FactorResult: ...

# factors/registry.py
_REGISTRY: dict[str, type[Factor]] = {}
def register(cls: type[Factor]) -> type[Factor]:
    _REGISTRY[cls.name] = cls
    return cls
def all_factors() -> dict[str, type[Factor]]:
    return dict(_REGISTRY)

# factors/f01_momentum.py
from .base import Factor, FactorResult
from .registry import register

@register
class MomentumFactor(Factor):
    name = "momentum"
    requires = ["ohlcv"]
    def compute(self, data, ctx) -> FactorResult:
        ret = data["adjClose"].pct_change(63).iloc[-1]   # ~3-month
        score = ctx["normalize"](ret)
        return FactorResult(self.name, score, {"ret_63d": ret})
```

**Two registration strategies, recommended progression:**
- **v1 (in-repo factors):** decorator registry + an `import factors.*` sweep at startup. Simplest, fully under your control.
- **v2 (distributable factors):** Python **entry points** (`[project.entry-points."swing.factors"]` in `pyproject.toml`, discovered via `importlib.metadata.entry_points(group="swing.factors")`). Use this only if factors become separate installable packages.

The registry only instantiates factors whose `name` appears in the config's active-factor list with weight > 0, so disabling a factor is a config edit. **Isolate factor failures**: the engine wraps each `compute()` in try/except so one broken factor degrades gracefully (logged + excluded) rather than killing the run.

### 3.3 Scoring engine (file 10) + regime/risk gates

```python
# scoring/engine.py
def composite_score(results: list[FactorResult], weights: dict[str, float]) -> float:
    active = [(r, weights[r.name]) for r in results if weights.get(r.name, 0) > 0]
    wsum = sum(w for _, w in active)
    return sum(r.score * w for r, w in active) / wsum if wsum else 0.0
```

Pipeline: composite score → **regime gate** (e.g., only go long when SPY > its 200-day MA and VIX below threshold; otherwise emit no/fewer signals) → **risk gate** (minimum dollar-volume liquidity, minimum price, maximum ATR%) → rank → select top N. All thresholds live in config.

### 3.4 Alert/output layer

An `Alerter` Protocol (`send(signals: list[Signal], run_meta: dict)`) with interchangeable backends (Telegram, email, Discord, Streamlit). The orchestrator can fan out to several. A separate `send_failure_alert()` path fires on exceptions so the user is told when the job **fails**, not only when it produces signals.

---

## 4. Scheduling Options

The job must fire unattended after the US market close (16:00 ET) — typically 30–60 minutes later (~16:30–17:00 ET) so end-of-day adjusted data has settled. All schedulers below run in **UTC unless otherwise noted**; 16:30 ET = 20:30 or 21:30 UTC depending on daylight saving, so prefer schedulers with native timezone support, or schedule in UTC and let the in-app **calendar gate** decide whether to actually run.

**Critical pattern regardless of scheduler:** schedule the cron generously (e.g., run every weekday) and make the *application* decide via `pandas_market_calendars` whether today is a real NYSE trading day (and handle early-close half-days). This decouples correctness from the scheduler's timing precision.

| Option | Cost | Reliability | Cold start | Native TZ | Secrets | Verdict |
|---|---|---|---|---|---|---|
| **Local cron** | Free | Poor — laptop must be on | n/a | OS-level | OS env/file | Fails the hands-off requirement. Dev only. |
| **GitHub Actions** | Free (public repo unlimited; private ~2,000 min/mo) | Good but per GitHub Docs the schedule event "can be delayed during periods of high loads... some queued jobs may be dropped"; in public repos "scheduled workflows are automatically disabled when no repository activity has occurred in 60 days" | Fresh runner each time (~seconds) | UTC by default; IANA timezone now supported via `timezone:` key | Encrypted **repo secrets** | **Recommended for v1.** Free, simple, git-native. |
| **Modal** | Free tier with monthly compute credit; pay-per-second after | Very good; purpose-built for scheduled Python | Sub-second to low-second | `modal.Cron("0 21 * * *", timezone="America/New_York")` | `modal.Secret` | **Recommended for production.** Pythonic cron, TZ-aware, generous free tier. |
| **Google Cloud Run Jobs + Cloud Scheduler** | Cloud Run jobs effectively $0 at this scale (free monthly vCPU/GiB-seconds); Cloud Scheduler: 3 free jobs/account/mo then $0.10/job/mo | Excellent; managed, retries | Container start (~seconds) | Cloud Scheduler supports TZ | Secret Manager / env | Strong production alternative; more setup than Modal. |
| **AWS Lambda + EventBridge Scheduler** | Lambda free tier (1M req + 400k GB-s/mo) covers it; EventBridge Scheduler 14M free invocations/mo | Excellent; managed, retries, DLQ | Container/zip cold start | EventBridge Scheduler supports TZ + DST | Secrets Manager / env | Strong, but packaging deps (pandas) into Lambda is fiddly. |
| **Railway** | Usage-based after free trial credits; native cron on paid plans | Good; some reported outages | Container | env vars | Built-in env vars | Fine if already using it. |
| **Render** | Cron jobs are a first-class service type; Hobby $0 + compute | Good, predictable | Container | env vars | Built-in env vars | Good, predictable pricing. |
| **PythonAnywhere** | Free tier scheduled tasks limited (free-account scheduling restricted for newer accounts); paid ~$5/mo | OK | n/a (always-on host) | Fixed UTC-ish | Web UI | Beginner-friendly but limited free scheduling. |
| **Vercel Cron** | Hobby cron limited to once/day, imprecise timing | OK | Serverless | UTC | env vars | Too limited for Python data jobs. |

**Recommendation:** Start on **GitHub Actions** (free, zero infra, secrets built in, the same repo Claude Code builds in). Cron `30 21 * * 1-5` (≈16:30 ET in winter) plus the in-app calendar gate; add `workflow_dispatch` for manual runs. Mitigate the 60-day auto-disable (which applies once 60 days pass with no repository activity) with any periodic commit or an external nudge. **Graduate to Modal** when you want tighter timing, native ET scheduling, and longer/heavier runs — its decorator-based `modal.Cron(..., timezone="America/New_York")` is the cleanest fit for a Python-only stack. Use **Cloud Run Jobs + Cloud Scheduler** if you prefer a major-cloud, container-based deployment.

Every option must ping **healthchecks.io** on completion so a missed run alerts you.

---

## 5. Alerting Options

| Channel | Setup ease | Reliability | Richness (tables/charts) | Cost | Mobile push |
|---|---|---|---|---|---|
| **Telegram bot** | Easy — `@BotFather` token, send via HTTPS `sendMessage`; no server/webhook needed for *outbound* | High | Markdown tables/code blocks; can send images/files. Per the official Telegram Bot API `sendMessage` docs, the text field is "1-4096 characters after entities parsing", and bots are rate-limited to ~30 messages/second — chunk long messages | Free | Yes (native push) |
| **Discord webhook** | Easiest — create channel webhook URL, POST JSON | High | Embeds, code blocks; 2,000-char limit; relies on WebSocket gateway for richer bots | Free | Yes (app) |
| **Email (SMTP / SendGrid / Amazon SES)** | Moderate — SMTP simplest; SendGrid/SES need account + verified sender | High (watch spam) | Full HTML tables/charts | Free–low (SES ~pennies; SendGrid/SES free tiers) | Via mail app |
| **Streamlit dashboard** | Moderate — separate web app | Depends on host | Best — interactive tables, charts, history | Free tier (Community Cloud) | Browser only, no push |

**Recommendation:** **Telegram bot as primary** push alert (one-token setup, native mobile push, rich-enough Markdown for a ranked signal table with entry/stop/exit), with **email (SMTP or Amazon SES) as a redundant backup** so a single channel failure never silences a signal. Send a compact ranked table to Telegram (symbol, score, entry, stop, exit, R) and attach/CSV the full detail. Add a **Streamlit dashboard** later for browsing signal history and the live-vs-backtest equity curve — it complements but doesn't replace push. Discord webhook is an equally valid primary if the user already lives in Discord.

Critically, route **failure alerts** through the same Telegram channel and through healthchecks.io's own notifications (it integrates email, Telegram, Discord, Slack, etc.), giving a dead-man's switch independent of your app.

---

## 6. Logging / Tracking

### Storage choice

| Store | Pros | Cons | Verdict |
|---|---|---|---|
| **CSV / Parquet** | Trivial, git-diffable (CSV) | No constraints, race-prone, weak querying | Use for the *data cache*, not signal records. |
| **SQLite** | Zero-config single file, ACID, full SQL, trivial to back up / commit / sync | Single-writer; not for high concurrency | **Recommended.** Perfect for one daily writer. |
| **Postgres (managed)** | Concurrency, durability, cloud-native | Costs money, more ops | Migrate here if multi-process/scale. |
| **Cloud DB (e.g., Cloud SQL, Supabase)** | Managed Postgres, accessible from any scheduler | Cost, setup | Good once on Cloud Run/Modal full-time. |

**Recommendation:** **SQLite via SQLAlchemy**, with the DB file persisted across runs (committed to a private repo on GitHub Actions, or on a Modal Volume / Cloud Run + Cloud SQL in production). Because SQLAlchemy ORM models are storage-agnostic, the **same code migrates to Postgres** by changing the connection string — design for SQLite now, Postgres-ready.

### Suggested schema

```sql
-- One row per generated signal
CREATE TABLE signals (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    signal_date     DATE    NOT NULL,        -- the trading day signal was produced
    symbol          TEXT    NOT NULL,
    direction       TEXT    NOT NULL DEFAULT 'long',
    composite_score REAL    NOT NULL,
    rank            INTEGER,
    entry_price     REAL    NOT NULL,        -- modeled entry (e.g., signal-day close)
    stop_price      REAL    NOT NULL,
    exit_target     REAL    NOT NULL,
    risk_per_share  REAL    NOT NULL,        -- entry - stop  (defines 1R)
    factor_scores   TEXT,                    -- JSON: per-factor sub-scores (attribution)
    regime_state    TEXT,                    -- e.g. "risk_on"/"risk_off"
    created_at      TIMESTAMP NOT NULL,
    UNIQUE(signal_date, symbol)              -- idempotency: re-run can't dupe
);

-- One row per signal outcome, updated as the trade resolves
CREATE TABLE outcomes (
    id              INTEGER PRIMARY KEY,
    signal_id       INTEGER NOT NULL REFERENCES signals(id),
    status          TEXT    NOT NULL,        -- open / target_hit / stopped / time_exit
    actual_entry    REAL,                    -- user-reported fill (for slippage)
    exit_price      REAL,
    exit_date       DATE,
    bars_held       INTEGER,
    realized_r      REAL,                    -- (exit-entry)/risk_per_share
    pct_return      REAL,
    slippage        REAL,                    -- actual_entry - modeled entry_price
    mae             REAL,                    -- max adverse excursion (R)
    mfe             REAL,                    -- max favorable excursion (R)
    updated_at      TIMESTAMP NOT NULL
);

-- One row per scheduled run (health/audit)
CREATE TABLE runs (
    id              INTEGER PRIMARY KEY,
    run_ts          TIMESTAMP NOT NULL,
    trading_day     DATE,
    status          TEXT NOT NULL,           -- success / no_trading_day / failed
    n_signals       INTEGER,
    data_provider   TEXT,
    git_sha         TEXT,                    -- which code version produced signals
    config_hash     TEXT,                    -- which config version was active
    error           TEXT
);
```

### Real vs backtest performance tracking

The **R-multiple** is the unit of account: 1R = `entry − stop` (risk per share); a trade exiting at +2R returned twice the risk, a stop-out is −1R. Track, on a rolling basis:

- **Hit rate** (% of closed trades with realized_r > 0)
- **Average R / expectancy** = `win% × avg_win_R − loss% × avg_loss_R` (the average R-multiple per trade — the mathematical edge)
- **R-multiple distribution** (positively skewed systems live on occasional large winners)
- **Equity curve** in R and in %, plus **max drawdown**
- **Slippage** = actual_entry − modeled entry (the gap between signal price and your real Robinhood fill — a swing strategy on daily bars should have modest, trackable slippage)
- **MAE/MFE** to see if stops/targets are well-placed

**Backtest-vs-live comparison:** store the backtest's expected hit rate, expectancy, and average R alongside live results and compute the deltas. **Detect strategy decay** by watching for sustained out-of-sample degradation — e.g., live expectancy persistently below the backtest's confidence band, rising slippage, or a drawdown exceeding the worst backtested drawdown. Segment attribution by factor (using the stored `factor_scores`) and by regime to see *which* part of the edge is decaying. A second daily scheduled job updates `outcomes` from fresh prices for open positions.

---

## 7. Config

Two strictly separated concerns:

1. **Tunable params** → `config/settings.yaml`, version-controlled, code-reviewed, diffable.
2. **Secrets** (API keys, bot token) → environment variables / `.env` (gitignored) / cloud secret store — **never** in the repo.

**Format recommendation: YAML** for the tunable config (comments + nesting beat JSON; more standard than TOML for nested ML/quant config), validated by **Pydantic** (`pydantic-settings`) which also reads secrets from env vars with type validation and `SecretStr` masking. This gives fail-fast validation: a malformed weight or out-of-range stop % raises a clear error on startup rather than producing garbage signals.

```yaml
# config/settings.yaml
watchlist:
  source: static            # static | universe_screen
  symbols: [AAPL, MSFT, NVDA, ...]

factors:                    # only listed factors with weight>0 run
  momentum:   {weight: 0.25}
  trend:      {weight: 0.20}
  value:      {weight: 0.15}
  quality:    {weight: 0.15}
  volatility: {weight: 0.10}
  volume:     {weight: 0.15}

risk:
  entry_mode: close          # close | limit_pct
  stop_pct:   0.07           # 7% below entry => defines 1R
  exit_pct:   0.15           # 15% target  (~2.1R)
  max_atr_pct: 0.06
  min_dollar_volume: 5_000_000
  min_price: 5.0
  max_positions: 8

regime:
  spy_ma_days: 200
  require_spy_above_ma: true
  vix_max: 28

run:
  lookback_days: 400
  data_provider: tiingo      # tiingo | yfinance
```

```python
# config/settings.schema.py
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class RiskCfg(BaseModel):
    stop_pct: float = Field(gt=0, lt=0.5)
    exit_pct: float = Field(gt=0, lt=2.0)
    max_positions: int = Field(ge=1, le=50)
    # ...

class Secrets(BaseSettings):                 # read from env / .env
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SWING_")
    tiingo_api_key: SecretStr
    telegram_bot_token: SecretStr
    telegram_chat_id: str
    healthcheck_url: str
```

**Versioning & validation:** the active config's hash is written to `runs.config_hash` and the git SHA to `runs.git_sha`, so every signal is traceable to the exact params and code that produced it. On GitHub Actions/Modal/Cloud, secrets live in the platform's encrypted secret store and are injected as env vars at runtime; the YAML stays in the repo.

---

## 8. Step-by-Step Build Order for Claude Code

Each milestone is independently testable and ends in a green test suite. Build a **dry-run/paper mode** flag (`--dry-run`) early: it runs the full pipeline but uses cached/fixture data and prints alerts instead of sending them.

**Milestone 0 — Scaffolding.** Create the package tree, `pyproject.toml` (deps: pandas, requests, tenacity, pydantic, pydantic-settings, sqlalchemy, pandas_market_calendars, pyyaml, python-telegram-bot, pytest), `.gitignore` (excludes `.env`, db, cache), README, and a no-op `main.py`. *Test:* `pytest` runs, package imports.

**Milestone 1 — Config + calendar gate.** Implement `config_loader.py` with Pydantic validation and `calendar_gate.py` using `pandas_market_calendars` (NYSE valid days + early-close detection, ET timezone). *Tests:* invalid config raises; known holidays (e.g., Christmas, July 4) correctly flagged as non-trading; a normal weekday flagged trading.

**Milestone 2 — Data layer with caching + retries.** Define `DataProvider` Protocol; implement `YfinanceProvider` first (free, no key) and `TiingoProvider`; add the tenacity retry wrapper and the Parquet/SQLite cache with idempotency. *Tests:* mock HTTP, assert retry on transient failure, assert cache hit avoids second call, assert adjusted-price column present. Include an **integration test** (network, marked `@pytest.mark.network`) that pulls one symbol.

**Milestone 3 — One factor as a template.** Implement `factors/base.py`, `registry.py`, and **one** factor (`f01_momentum.py`) end-to-end with the `@register` decorator. *Tests:* **golden/snapshot test** — feed a deterministic OHLCV fixture, assert the factor returns an exact, pinned score; assert registry contains the factor.

**Milestone 4 — Remaining factors (02–08).** Implement each remaining factor as its own file following the template. *Tests:* one golden test per factor with a committed fixture; a registry test asserting all 8 register; a test that a broken factor is isolated (engine logs + skips).

**Milestone 5 — Scoring engine + regime/risk gates.** Implement weighted composite (file 10), regime gate, risk gate, ranking, top-N selection. *Tests:* composite math with known weights; regime gate suppresses signals when SPY<200dma / VIX high; risk gate filters illiquid/cheap names.

**Milestone 6 — Signal builder (entry/stop/exit).** Compute entry, stop, exit, and risk_per_share (1R) per config. *Tests:* with stop_pct=0.07, exit_pct=0.15, assert exact stop/exit/R values; assert R-multiple target math.

**Milestone 7 — Persistence.** SQLAlchemy models + repository; `save_signals()` with the `UNIQUE(signal_date, symbol)` idempotency guard; write a `runs` row each execution. *Tests:* save then re-run same day → no duplicates; schema round-trips.

**Milestone 8 — Alerting.** `Alerter` Protocol + Telegram backend + email backup + `send_failure_alert()`. *Tests:* formatter produces a correct table from sample signals; in `--dry-run`, alerts print not send; mock Telegram API asserts payload.

**Milestone 9 — Orchestration + scheduling/deployment.** Wire `main.py`: calendar gate → data → factors → scoring → signal builder → persist → alert → healthcheck ping (success *and* failure). Add the GitHub Actions workflow (`30 21 * * 1-5` + `workflow_dispatch`), repo secrets, and the healthchecks.io check. *Tests:* full pipeline integration test in dry-run on fixtures asserts end-to-end signal list; a "non-trading-day" run exits cleanly and pings health.

**Milestone 10 — Performance tracking + backtest comparison.** Implement the outcome-tracker job (`tracking/outcomes.py`: realized R, slippage, MAE/MFE, status transitions) and `backtest_compare.py` (live vs backtest expectancy/hit-rate/drawdown, decay detection). Add a Streamlit dashboard reading the DB. *Tests:* realized-R math on synthetic closed trades; expectancy/hit-rate aggregation; decay-flag fires when live expectancy drops below the backtest band.

**Testing strategy summary:** unit tests with **deterministic fixtures** and **golden/snapshot** assertions for every factor (the AI agent re-runs them after each change to catch regressions); **integration tests** (network-marked) for live data; a **dry-run/paper mode** for safe end-to-end validation without sending alerts or relying on live APIs; and CI (GitHub Actions) running the suite on every push so each milestone stays green.

---

## 9. Data Source Selection (supporting Section 3.1 / file 09)

| Provider | Free tier | Cheapest paid | Adjusted prices | Fundamentals | Best for hands-off daily pull? |
|---|---|---|---|---|---|
| **yfinance (Yahoo)** | Unofficial, no key, no hard limit | n/a | Yes | Limited/unofficial | OK as free fallback; unofficial, scrapes Yahoo, breaks periodically, ToS-grey |
| **Tiingo** | Per Tiingo's official pricing: "30+ years of historical data… up to 50 requests per hour and up to 1,000 requests per day, and can view up to 500 unique symbols per month" — EOD adjusted prices included; fundamentals/news excluded | "Power" ~ $10–30/mo (see caveat) | Yes (split+dividend adjusted) | Paid add-on | **Recommended.** Clean, reliable, cheap, daily-EOD focused |
| **Alpha Vantage** | 25 req/day, 5/min | $49.99/mo | Yes (adj + raw) | Yes | Free tier too tight; cheapest paid above budget |
| **Polygon.io (now "Massive")** | Stocks Basic: end-of-day data, 5 calls/min | $29/mo Stocks Starter: unlimited API calls, 5 years history, 15-min delayed data, technical indicators + corporate actions | Yes | Limited | Strong US data; fine within budget |
| **Alpaca Market Data** | Free IEX feed; SIP (full-market) paid | ~$49/mo (full SIP) | Yes | No | Good if also using Alpaca elsewhere; free feed is IEX-only |
| **Finnhub** | 60 req/min, real-time US quotes + basic fundamentals | $11.99–$99.99/mo | Yes | Basic free / detailed paid | Most generous free tier; good fundamentals |
| **Financial Modeling Prep (FMP)** | 250 req/day | Low-cost paid tiers | Yes | Strong | Good for fundamentals-heavy factors |
| **EODHD** | 20 req/day | EOD All-World $19.99/mo; All-in-One $99.99/mo | Yes (split+div adjusted) | $59.99/mo feed | Good all-in-one if you need global + fundamentals |
| **IEX Cloud** | — | — | — | — | **Discontinued** (retirement announced May 31, 2024; all IEX Cloud API products fully shut down August 31, 2024) — do not use |

**Recommendation given the $10–30/mo budget:** **Tiingo (paid Power tier)** as primary — its free tier already provides split- and dividend-adjusted EOD US equity prices (the core need for daily swing signals), it's clean and reliable, and the cheap Power upgrade lifts the 500-symbol/month and hourly limits at a price in/near budget. Keep **yfinance as a zero-cost fallback** behind the `DataProvider` Protocol so a Tiingo outage doesn't blank a day. If your factors lean heavily on **fundamentals**, **Finnhub** (generous free tier, $11.99 entry paid) or **FMP** are the better-value picks; if you want one provider for prices *and* deep fundamentals, **EODHD** at $19.99 (EOD) bundles well. **Polygon Starter ($29/mo)** is the pick if you want premium US-only price infrastructure within budget. All pricing/limits can change — verify on each provider's official pricing page before committing.

> **Pricing caveat (Tiingo Power tier):** Tiingo's live pricing/documentation pages are JavaScript-rendered and could not be machine-verified. Older sources cite the Power plan at ~$10/month; the most recent (April 2026) third-party source citing Tiingo's public pricing page lists Power/Individual at ~$30/month with ~10,000 req/hr and ~100,000 req/day, and a separate commercial/Business plan (~$50/month). Tiingo's official documentation confirms the license structure verbatim: "For Basic and Power accounts, data is for internal and personal use only. You may not redistribute the data in any form… For Commercial accounts, data is licensed for internal commercial usage." Load tiingo.com/pricing in a browser to confirm the current number before subscribing.

---

## 10. Reliability & Monitoring (cross-cutting)

- **Retries with backoff** on every external call (tenacity: exponential backoff, capped attempts).
- **Caching** of pulled data (Parquet) → idempotent re-runs, fewer API calls, resilience to partial outages.
- **Idempotent daily runs** enforced by `UNIQUE(signal_date, symbol)` and cache reads.
- **Failure alerting**: the user is notified when the job *fails* (exception path → Telegram + email), not just when signals fire.
- **Dead-man's-switch monitoring** via **healthchecks.io** (free Hobbyist plan monitors up to 20 jobs with up to 3 team members and 100 log entries per check; paid Business plan is $20/mo for 100 checks): the job pings on completion; if a scheduled run never happens (scheduler outage, repo auto-disable, crash before alert), healthchecks.io alerts you. Use the `/start` + success ping pattern to also catch hung runs.
- **Auditability**: every run records git SHA + config hash so any signal is reproducible.

This combination ensures that the single most dangerous failure mode for a hands-off system — *silent* non-execution — is always surfaced.

---

### Recommendations (staged) & decision thresholds

1. **Build v1 now:** GitHub Actions cron + in-app NYSE calendar gate → Tiingo (free tier first) with yfinance fallback → 8-factor registry → SQLite persistence → Telegram + email alerts → healthchecks.io. This is entirely free and satisfies the hands-off requirement.
2. **Upgrade to paid data when** you exceed Tiingo's free limits (50 req/hr, 1,000 req/day, 500 unique symbols/mo) — i.e., once your watchlist passes ~500 symbols/month or you add fundamentals-heavy factors. Subscribe to Tiingo Power (or switch to Finnhub/FMP/EODHD if fundamentals dominate).
3. **Migrate scheduling to Modal (or Cloud Run Jobs + Cloud Scheduler) when** GitHub Actions' delivery delays, 60-day auto-disable, or runtime limits become a problem, or when the run grows heavy. Modal gives native `America/New_York` cron and per-second billing within a free credit.
4. **Migrate persistence to Postgres when** you run more than one writer process or want a hosted DB accessible from any scheduler.
5. **Pause/retune the strategy when** live expectancy stays below the backtest's confidence band over a meaningful sample, drawdown exceeds the worst backtested drawdown, or slippage trends upward — these are your concrete strategy-decay triggers.

*All third-party pricing and free-tier limits cited can change; verify on each provider's official pricing page before committing spend.*