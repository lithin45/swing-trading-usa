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

def test_broker_config_loads_disabled_by_default():
    s = load_settings()
    assert s.broker is not None
    assert s.broker.enabled is False  # signal-only until explicitly enabled
    assert s.broker.paper is True
    assert s.broker.entry_price_ref == "zone_high"


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
