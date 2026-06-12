"""Config validation: the real settings.yaml loads, and bad config fails fast."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from swing_signals.config_loader import (
    DEFAULT_SETTINGS_PATH,
    Secrets,
    Settings,
    _normalize_db_url,
    load_secrets,
    load_settings,
    redact_db_url,
    resolve_db_url,
)


def _raw() -> dict:
    with DEFAULT_SETTINGS_PATH.open() as fh:
        return yaml.safe_load(fh)


def test_default_settings_valid():
    s = load_settings()
    assert s.account.equity > 0
    assert s.active_factor_weights()  # at least one active factor


def test_min_dollar_volume_parsed_as_number():
    # YAML 1.1 underscores: 10_000_000 must parse to an int, not a string.
    s = load_settings()
    assert s.universe.min_dollar_volume == 10_000_000


def test_secrets_load_without_env():
    sec = load_secrets()
    assert sec.smtp_port == 587  # default present; no .env required for scaffold


def test_risk_ceiling_below_risk_raises():
    raw = _raw()
    raw["account"]["risk_pct_ceiling"] = 0.005  # below risk_pct (0.01)
    with pytest.raises(ValidationError):
        Settings(**raw)


def test_unknown_factor_name_raises():
    raw = _raw()
    raw["factors"]["bogus_factor"] = {"enabled": True, "weight": 0.1}
    with pytest.raises(ValidationError):
        Settings(**raw)


def test_unknown_top_level_key_raises():
    raw = _raw()
    raw["bogus_section"] = 123
    with pytest.raises(ValidationError):
        Settings(**raw)


def test_typo_in_section_key_raises():
    raw = _raw()
    raw["risk"]["atr_stop_multiplee"] = 2.0  # typo'd key
    with pytest.raises(ValidationError):
        Settings(**raw)


def test_all_factors_disabled_raises():
    raw = _raw()
    for f in raw["factors"].values():
        f["enabled"] = False
    with pytest.raises(ValidationError):
        Settings(**raw)


def test_tier_order_validation():
    raw = _raw()
    raw["scoring"]["tier_high"] = 50.0
    raw["scoring"]["tier_medium"] = 70.0
    with pytest.raises(ValidationError):
        Settings(**raw)


# --- broker config (Stage 8) ---------------------------------------------------

def test_broker_config_loads_paper_only():
    s = load_settings()
    assert s.broker is not None
    assert s.broker.paper is True  # never a live brokerage account
    assert s.broker.entry_price_ref == "zone_high"
    assert s.broker.entry_class == "auto"


def test_broker_section_optional():
    raw = _raw()
    raw.pop("broker", None)  # old configs without a broker: block still load
    s = Settings(**raw)
    assert s.broker is None


def test_broker_bad_provider_raises():
    raw = _raw()
    raw["broker"]["provider"] = "robinhood"  # only alpaca supported
    with pytest.raises(ValidationError):
        Settings(**raw)


# --- DB URL resolution + normalization (Neon/Postgres) -------------------------

def test_resolve_db_url_defaults_to_yaml(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    s = load_settings()
    assert resolve_db_url(s) == s.run.db_url  # sqlite default, untouched


def test_resolve_db_url_bare_env_wins_and_normalizes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")
    s = load_settings()
    out = resolve_db_url(s)
    assert out == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_resolve_db_url_swing_env_fallback(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SWING_DATABASE_URL", "postgresql://u:p@host/db?sslmode=require")
    s = load_settings()
    # already psycopg-less postgresql:// -> driver added, existing sslmode preserved (not doubled)
    assert resolve_db_url(s) == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_resolve_db_url_secrets_only_when_passed(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    s = load_settings()
    sec = Secrets(database_url="postgres://x/y")
    assert resolve_db_url(s, sec).startswith("postgresql+psycopg://x/y")
    # without secrets, the same call stays on the yaml default (hermetic for tests)
    assert resolve_db_url(s) == s.run.db_url


def test_normalize_leaves_sqlite_untouched():
    assert _normalize_db_url("sqlite:///signals.db") == "sqlite:///signals.db"


def test_redact_db_url_strips_credentials():
    # the normalized form GitHub's exact-value secret masking does NOT cover
    out = redact_db_url("postgresql+psycopg://neondb_owner:S3cretPw@ep-x.neon.tech/sig?sslmode=require")
    assert out == "postgresql+psycopg://***@ep-x.neon.tech/sig"
    assert "S3cretPw" not in out
    assert "neondb_owner" not in out  # whole userinfo masked, not just the password


def test_redact_db_url_sqlite_passthrough():
    assert redact_db_url("sqlite:///signals.db") == "sqlite:///signals.db"


def test_redact_db_url_fails_closed_on_schemeless_credentials():
    # a typo'd env var can drop the scheme; urlsplit then leaves user:pass in the
    # path — the helper must redact wholesale rather than echo it back
    out = redact_db_url("neondb_owner:S3cretPw@ep-x.neon.tech/sig")
    assert "S3cretPw" not in out


def test_empty_env_secrets_treated_as_unset(monkeypatch):
    # GitHub Actions sets undefined secrets to "" — must not abort the run.
    monkeypatch.setenv("SWING_SMTP_PORT", "")
    monkeypatch.setenv("SWING_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("SWING_ALPACA_API_KEY", "")
    sec = Secrets(_env_file=None)
    assert sec.smtp_port == 587            # empty int env -> default, not a crash
    assert sec.telegram_bot_token is None  # empty secret -> unset, not SecretStr("")
    assert sec.alpaca_api_key is None
