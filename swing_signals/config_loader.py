"""Configuration loading + validation (fail-fast).

Tunable params come from ``config/settings.yaml`` and are validated by the Pydantic
models below — a malformed weight, out-of-range stop, or typo'd key raises a clear
error on startup rather than producing garbage signals. Secrets come from the
environment / ``.env`` (never the YAML) via :class:`Secrets`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = _ROOT / "config" / "settings.yaml"
DEFAULT_ENV_PATH = _ROOT / ".env"

# Factor names the engine knows about (research files 01, 02, 03, 05, 06).
# Macro (04) and regime (07) are gates/modifiers, not weighted factors, so they
# are configured in their own sections rather than under `factors`.
ALLOWED_FACTORS = {
    "technical",
    "news_sentiment",
    "events",
    "themes_cycles",
    "smart_money",
    "momentum",  # f08 — momentum / relative strength (the core edge; research-backed)
    "setup",     # f09 — breakout/pullback pattern confirmation (low weight)
}


class StrictModel(BaseModel):
    """Base model that rejects unknown keys, so config typos fail fast."""

    model_config = ConfigDict(extra="forbid")


class AccountCfg(StrictModel):
    equity: float = Field(gt=0)
    risk_pct: float = Field(gt=0, le=0.5)
    risk_pct_ceiling: float = Field(gt=0, le=0.5)
    fractional_shares: bool = True
    broker_min_order_usd: float = Field(default=1.0, ge=0)

    @model_validator(mode="after")
    def _ceiling_ge_risk(self) -> AccountCfg:
        if self.risk_pct_ceiling < self.risk_pct:
            raise ValueError("account.risk_pct_ceiling must be >= account.risk_pct")
        return self


class WatchlistCfg(StrictModel):
    source: Literal["static", "universe_screen"] = "static"
    symbols: list[str] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return [s.strip().upper() for s in v if s and s.strip()]


class FactorCfg(StrictModel):
    enabled: bool = True
    weight: float = Field(ge=0, le=1)


class ScoringCfg(StrictModel):
    composite_min: float = Field(ge=0, le=100)
    agreement_min: float = Field(ge=0, le=1)
    tier_high: float = Field(ge=0, le=100)
    tier_medium: float = Field(ge=0, le=100)
    tier_low: float = Field(ge=0, le=100)
    # Don't-chase gate: veto entries more than this many ATRs above the 20-EMA
    # (0 = disabled). Momentum ranking favors the most extended names; this bounds
    # buying blow-off tops that mean-revert before reaching the 2R target.
    max_extension_atr: float = Field(default=0.0, ge=0)
    # Conviction-tier SIZE multipliers (2026-06-11, configurable). The historical
    # 1.0/0.66/0.33 stack double-charged conviction: the composite threshold +
    # budget ranking already select for it, then the size multiplier shrank the
    # fill again — one leg of the ~0.3% effective risk vs 1% nominal finding.
    # Defaults preserve the original behavior.
    tier_mult_high: float = Field(default=1.0, gt=0, le=1)
    tier_mult_medium: float = Field(default=0.66, gt=0, le=1)
    tier_mult_low: float = Field(default=0.33, gt=0, le=1)

    @model_validator(mode="after")
    def _tiers_ordered(self) -> ScoringCfg:
        if not (self.tier_high >= self.tier_medium >= self.tier_low):
            raise ValueError("scoring tiers must satisfy tier_high >= tier_medium >= tier_low")
        return self


class MacroCfg(StrictModel):
    enabled: bool = True
    risk_on_threshold: float = Field(ge=0, le=100)
    risk_off_threshold: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> MacroCfg:
        if self.risk_off_threshold > self.risk_on_threshold:
            raise ValueError("macro.risk_off_threshold must be <= macro.risk_on_threshold")
        return self


class RegimeCfg(StrictModel):
    enabled: bool = True
    spy_ma_days: int = Field(gt=0)
    require_spy_above_ma: bool = True
    vix_max: float = Field(gt=0)
    vix_backwardation_veto: bool = True
    green_only_entries: bool = False  # if True, open new longs ONLY in a GREEN regime (selectivity)


class RiskCfg(StrictModel):
    atr_period: int = Field(gt=0)
    atr_stop_multiple: float = Field(gt=0)
    chandelier_lookback: int = Field(gt=0)
    chandelier_multiple: float = Field(gt=0)
    rr_target: float = Field(gt=0)
    max_positions: int = Field(ge=1, le=50)
    portfolio_heat_cap: float = Field(gt=0, le=1)
    max_per_sector: int = Field(ge=1)
    daily_loss_halt: float = Field(gt=0, le=1)
    weekly_loss_halt: float = Field(gt=0, le=1)
    monthly_loss_halt: float = Field(gt=0, le=1)
    drawdown_derisk: float = Field(gt=0, le=1)
    drawdown_hard_halt: float = Field(gt=0, le=1)
    # Drawdown-brake recovery (2026-06-11). The original hard halt was an ABSORBING
    # state: once dd >= hard_halt, no new entries are allowed, so equity can never
    # climb back — 2017-19 replay spent 306/752 days dead and missed all of 2019.
    # peak_lookback bounds the high-water mark to a trailing window (0 = all-time,
    # the absorbing original); halt_resume_days re-opens entries at
    # halt_resume_risk_mult size after that many bars of continuous halt (0 = never
    # resume). Defaults preserve the original behavior for existing configs.
    drawdown_peak_lookback: int = Field(default=0, ge=0)        # trading bars; 0 = all-time
    halt_resume_days: int = Field(default=0, ge=0)              # 0 = absorbing halt
    halt_resume_risk_mult: float = Field(default=0.25, gt=0, le=1)
    # Concentration caps. Risk-at-stop sizing alone gives the LARGEST dollar exposure
    # to the LOWEST-volatility names (notional/equity = risk% / stop%), so a calm
    # mega-cap could absorb half the account; the real tail risk there is a gap
    # THROUGH the stop, which only a notional bound contains. Defaults keep old
    # configs loading (and the gross cap at 1.0 = never lever the account).
    max_position_notional_pct: float = Field(default=0.20, gt=0, le=1)
    max_gross_exposure: float = Field(default=1.0, gt=0, le=2)


class UniverseCfg(StrictModel):
    min_price: float = Field(ge=0)
    min_dollar_volume: float = Field(ge=0)
    top_n_scan: int = Field(default=30, ge=1)          # cheap-scan survivors handed to scoring
    max_llm_candidates: int = Field(default=30, ge=1)  # cap on names reaching the Claude factor
    # Live tradable universe = point-in-time S&P 500 only — the universe every
    # validated holdout traded. False re-admits thematic + news-discovered names,
    # which are unvalidated and consume the scarce monthly budget slots; flip it
    # only for explicitly-bucketed exploration, never for the evidence account.
    sp500_only: bool = True


class DataCfg(StrictModel):
    provider_order: list[str] = Field(min_length=1)
    cache_dir: str = ".cache"
    lookback_days: int = Field(gt=0)
    max_staleness_days: int = Field(ge=0)
    index_symbols: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "IWM"])
    fred_series: dict[str, str] = Field(default_factory=dict)
    max_workers: int = Field(default=8, ge=1)  # parallel symbol fetches (broad-universe scaling)


class AlertsCfg(StrictModel):
    channels: list[str] = Field(default_factory=list)
    dry_run_default: bool = False


class RunCfg(StrictModel):
    output_dir: str = "output"
    log_level: str = "INFO"
    db_url: str = "sqlite:///signals.db"
    persist: bool = True


class BrokerCfg(StrictModel):
    """Automated paper-trading execution (opt-in; default off keeps the signal-only behavior).

    Sized at ~$500 equity with mega-caps means positions are *fractional*, and Alpaca forbids
    bracket/OCO on fractional orders (TIF must be DAY). So exits are managed by the ``manage``
    job rather than server-side brackets; ``place_protective_stops`` adds a standalone STOP-DAY
    order per session as an intraday safety net.
    """

    enabled: bool = False
    provider: Literal["alpaca"] = "alpaca"
    paper: bool = True  # paper trading only — the bot never touches a live brokerage account
    # auto = native bracket (server-side stop+target OCO) when the position is whole-share,
    # else a simple limit + self-managed exits (the only option for fractional positions).
    entry_class: Literal["auto", "bracket", "simple"] = "auto"
    size_from_live_equity: bool = True  # size off the broker's live equity, not just config
    entry_order_type: Literal["limit", "market"] = "limit"
    entry_price_ref: Literal["zone_high", "zone_low", "reference"] = "zone_high"
    tif: Literal["day"] = "day"  # fractional orders require DAY time-in-force
    max_pending_days: int = Field(default=3, ge=1, le=30)
    market_fallback: bool = True  # market order if the limit never fills within max_pending_days
    entry_reprice_each_day: bool = True  # re-place the DAY limit each session until filled/aged
    place_protective_stops: bool = True  # standalone STOP-DAY per session (emulated OCO)
    max_hold_bars: int = Field(default=20, ge=1)  # time-stop (defaults align with backtest)
    whole_share_only: bool = False  # honor account.fractional_shares by default
    min_order_usd: float = Field(default=1.0, ge=1.0)  # Alpaca fractional minimum


class ExitsCfg(StrictModel):
    """Exit state machine (research file 11 + the momentum exit research).

    ``mode: legacy`` (default) reproduces the original full-exit-at-target + hard
    time-stop behaviour, so the system is unchanged until ``staged`` is validated.
    ``staged`` scales a partial out at the first target, ratchets to breakeven,
    rides a chandelier trail with no hard time cap, and time-cuts only stagnant
    (not-yet-working) trades — with a loose backstop so nothing is held forever.
    """

    mode: Literal["legacy", "staged"] = "legacy"
    partial_take_frac: float = Field(default=0.5, ge=0, le=1)  # sold at the first target
    move_stop_to: Literal["breakeven", "none"] = "breakeven"
    stagnation_bars: int = Field(default=15, ge=1)            # cut a non-working trade after N bars
    stagnation_min_r: float = Field(default=1.0)              # "working" threshold (R)
    hard_backstop_bars: int = Field(default=60, ge=1)         # absolute max hold


class SizingCfg(StrictModel):
    """Volatility-scaled position sizing (Daniel-Moskowitz; Barroso-Santa-Clara).

    Scales size DOWN for more volatile names (high ATR%) and in more volatile
    markets. It only ever *reduces* size (caps at 1.0), so it is risk-reducing by
    construction — the one robustly evidenced risk technique for momentum.
    """

    vol_scaling_enabled: bool = True
    vol_target_atr_pct: float = Field(default=2.5, gt=0)   # daily ATR% that earns full size
    vol_scalar_min: float = Field(default=0.4, gt=0, le=1)  # floor (never below 40% size)
    vol_scalar_max: float = Field(default=1.0, gt=0, le=1)  # ceiling (never upsize)


class BudgetCfg(StrictModel):
    """The prime directive (mandate §4): a hard ceiling on NEW entries per calendar month.

    The ceiling counts EMITTED BUY signals (what the alert tells you to do and what the
    paper broker acts on) — conservative: an emitted-but-unfilled entry still consumes
    budget. The cooldown bars a name from re-signaling right after it stopped out, the
    classic way one hot name burns the month's budget on noise.
    """

    enabled: bool = True
    max_entries_per_month: int = Field(default=7, ge=1, le=100)
    cooldown_days: int = Field(default=10, ge=0, le=90)  # calendar days after a stop-out


class EarningsCfg(StrictModel):
    """Earnings-date handling for a multi-day holder (strategy review 2026-06-10 §5 T1).

    A 3-ATR stop cannot contain an overnight earnings gap (a −15% print is a −3R to −5R
    realized loss), so the system must not OPEN within ``veto_days_before`` calendar days
    of a confirmed print, and ``manage`` exits open positions before one. Calendar data is
    key-gated (Finnhub); when unavailable the run proceeds unscreened but warns loudly.
    """

    enabled: bool = True
    veto_days_before: int = Field(default=3, ge=0, le=30)   # no new entries within N days
    exit_before_earnings: bool = True                       # manage: close before the print


class Settings(StrictModel):
    """Top-level validated configuration."""

    account: AccountCfg
    watchlist: WatchlistCfg
    factors: dict[str, FactorCfg]
    scoring: ScoringCfg
    macro: MacroCfg
    regime: RegimeCfg
    risk: RiskCfg
    universe: UniverseCfg
    data: DataCfg
    alerts: AlertsCfg
    run: RunCfg
    # Exit machine — defaulted (legacy) so configs without an `exits:` block are unchanged.
    exits: ExitsCfg = Field(default_factory=ExitsCfg)
    # Volatility-scaled sizing — defaulted so configs without a `sizing:` block still load.
    sizing: SizingCfg = Field(default_factory=SizingCfg)
    # Monthly entry budget + cooldown — defaulted ON (the mandate's ceiling must not
    # depend on a config block existing). Enforcement still requires the caller to
    # build budget state (live: from the DB; backtest: from sim state).
    budget: BudgetCfg = Field(default_factory=BudgetCfg)
    # Earnings-date veto/exit — defaulted ON; inert without a Finnhub key (warns loudly).
    earnings: EarningsCfg = Field(default_factory=EarningsCfg)
    # Broker config is optional — old configs without a `broker:` section still load, and
    # `broker is None or not broker.enabled` means signal-only (the current behavior).
    broker: BrokerCfg | None = None
    # Backtest config is optional — old configs without a `backtest:` section still load.
    # Stored as a raw dict and parsed by run_backtest() to avoid a circular import.
    backtest: dict[str, Any] | None = None

    @field_validator("factors")
    @classmethod
    def _known_factor_names(cls, v: dict[str, FactorCfg]) -> dict[str, FactorCfg]:
        unknown = set(v) - ALLOWED_FACTORS
        if unknown:
            raise ValueError(
                f"unknown factor(s) in config: {sorted(unknown)}; "
                f"allowed: {sorted(ALLOWED_FACTORS)}"
            )
        return v

    @model_validator(mode="after")
    def _at_least_one_active_factor(self) -> Settings:
        if not self.active_factor_weights():
            raise ValueError("at least one factor must be enabled with weight > 0")
        return self

    def active_factor_weights(self) -> dict[str, float]:
        """Names → weights for factors that are enabled with a positive weight."""
        return {
            name: cfg.weight
            for name, cfg in self.factors.items()
            if cfg.enabled and cfg.weight > 0
        }


class Secrets(BaseSettings):
    """Secrets read from environment / .env with the SWING_ prefix.

    All optional so the scaffold loads with no .env present; each stage checks for
    the specific secret it needs and fails loudly if missing.
    """

    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_PATH),
        env_prefix="SWING_",
        extra="ignore",
        case_sensitive=False,
    )

    fred_api_key: SecretStr | None = None
    finnhub_api_key: SecretStr | None = None
    stooq_api_key: SecretStr | None = None
    tiingo_api_key: SecretStr | None = None
    massive_api_key: SecretStr | None = None
    sec_edgar_user_agent: str | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None
    healthcheck_url: str | None = None
    # Optional per-step dead-man's switches. With one shared check, a later step's
    # success ping flips the monitor back up minutes after an earlier step failed —
    # and a step that silently stops running looks like a normal inter-step gap.
    # Each falls back to the shared URL when unset, so nothing breaks before the
    # per-step checks exist on healthchecks.io.
    healthcheck_trade_url: str | None = None
    healthcheck_manage_url: str | None = None
    healthcheck_track_url: str | None = None
    # --- Stage 8+ : automated paper trading + AI + cloud persistence (all optional) ---
    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    alphavantage_api_key: SecretStr | None = None
    # Neon/hosted Postgres for the dashboard + cross-run history. Read with the SWING_ prefix
    # from .env; CI/Streamlit conventionally inject a *bare* DATABASE_URL — resolve_db_url()
    # checks both. Plain str (it's a connection URL, not a single secret token).
    database_url: str | None = None
    dashboard_password: SecretStr | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _empty_str_is_unset(cls, v, info):
        """Treat an empty env var (GitHub sets undefined secrets to "") as unset.

        Without this, ``SWING_SMTP_PORT=""`` from a workflow fails int validation and aborts the
        whole run; other empty secrets would become ``SecretStr("")`` (truthy) and look 'present'.
        """
        if isinstance(v, str) and v == "":
            return 587 if info.field_name == "smtp_port" else None
        return v


def load_settings(path: str | Path | None = None) -> Settings:
    """Load and validate ``settings.yaml``. Raises on missing file or invalid config."""
    p = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not p.exists():
        raise FileNotFoundError(f"settings file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"settings file {p} did not parse to a mapping")
    return Settings(**raw)


def load_secrets() -> Secrets:
    """Load secrets from environment / .env (never from the YAML)."""
    return Secrets()


def _normalize_db_url(url: str) -> str:
    """Make a connection URL SQLAlchemy-ready.

    Hosted Postgres providers (Neon, Supabase) hand out ``postgres://`` / ``postgresql://``
    URLs; SQLAlchemy 2.x needs an explicit driver, so we pin psycopg 3 and require TLS (Neon
    rejects non-TLS). SQLite and already-driver-qualified URLs pass through untouched.
    """
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+psycopg://") and "sslmode=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
    return url


def resolve_db_url(settings: Settings, secrets: Secrets | None = None) -> str:
    """Resolve the effective DB URL with env > secrets(.env) > yaml precedence.

    Order: a *bare* ``DATABASE_URL`` env var (CI / Streamlit Cloud), then ``SWING_DATABASE_URL``
    env, then ``secrets.database_url`` (local ``.env``, only when ``secrets`` is passed), finally
    ``settings.run.db_url`` (yaml; SQLite by default). ``secrets`` is opt-in so test calls that
    pass only ``settings`` stay hermetic on their own SQLite file regardless of the dev's ``.env``.
    """
    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SWING_DATABASE_URL")
        or (secrets.database_url if secrets is not None else None)
        or settings.run.db_url
    )
    return _normalize_db_url(url)


def redact_db_url(url: str) -> str:
    """Loggable form of a DB URL: scheme + host + db name, never credentials.

    The normalized URL differs from the raw ``DATABASE_URL`` secret (driver pinned,
    sslmode appended), so GitHub Actions' exact-value masking does NOT cover it —
    in a public repo the full URL in a log line is a public credential. Anything
    that logs a resolved URL must go through here. Dependency-free on purpose: a
    redaction helper that can itself fail open is worse than none.
    """
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        if "@" in parts.netloc:
            host = parts.netloc.rsplit("@", 1)[1]
            return f"{parts.scheme}://***@{host}{parts.path}"
        if "@" in url:
            # '@' outside the netloc means urlsplit did not isolate the credentials
            # (e.g. a scheme-less 'user:pass@host/db' from a typo'd env var) — don't
            # risk echoing them.
            return "<unparseable db url - redacted>"
        return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else url
    except Exception:  # noqa: BLE001 - never raise, never echo the input back
        return "<unparseable db url - redacted>"
