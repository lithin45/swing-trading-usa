"""Config validation: the real settings.yaml loads, and bad config fails fast."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from swing_signals.config_loader import (
    DEFAULT_SETTINGS_PATH,
    Settings,
    load_secrets,
    load_settings,
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
