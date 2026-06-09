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


class RiskCfg(StrictModel):
    atr_period: int = Field(gt=0)
    atr_stop_multiple: float = Field(gt=0)
    chandelier_lookback: int = Field(gt=0)
    chandelier_multiple: float = Field(gt=0)
    rr_target: float = Field(gt=0)
    max_positions: int = Field(ge=1, le=50)
    portfolio_heat_cap: float = Field(gt=0, le=1)
    sector_heat_cap: float = Field(gt=0, le=1)
    max_per_sector: int = Field(ge=1)
    daily_loss_halt: float = Field(gt=0, le=1)
    weekly_loss_halt: float = Field(gt=0, le=1)
    monthly_loss_halt: float = Field(gt=0, le=1)
    drawdown_derisk: float = Field(gt=0, le=1)
    drawdown_hard_halt: float = Field(gt=0, le=1)


class UniverseCfg(StrictModel):
    min_price: float = Field(ge=0)
    min_dollar_volume: float = Field(ge=0)


class DataCfg(StrictModel):
    provider_order: list[str] = Field(min_length=1)
    cache_dir: str = ".cache"
    lookback_days: int = Field(gt=0)
    max_staleness_days: int = Field(ge=0)
    index_symbols: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "IWM"])
    fred_series: dict[str, str] = Field(default_factory=dict)


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
