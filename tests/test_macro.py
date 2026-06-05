"""Macro modifier (file 04): risk-on/off sizing, stress overlay, graceful degrade."""

from __future__ import annotations

from datetime import date

import pytest

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.context import MarketContext, RunContext
from swing_signals.market.f04_macro import MacroModule


def _ctx(*, vix=None, vix3m=None, macro_series=None) -> RunContext:
    s = load_settings()
    mc = MarketContext(vix=vix, vix3m=vix3m, macro_series=macro_series)
    return RunContext(
        settings=s, secrets=load_secrets(), trading_day=date(2024, 1, 8),
        market=mc, equity=s.account.equity,
    )


def test_risk_on_full_size():
    ms = MacroModule().compute(
        _ctx(vix=13.0, vix3m=15.0, macro_series={"hy_oas": 290.0, "t10y2y": 0.8})
    )
    assert ms.state == "RISK_ON"
    assert ms.multiplier == 1.0
    assert ms.veto is False


def test_risk_off_cuts_size():
    ms = MacroModule().compute(
        _ctx(vix=33.0, vix3m=28.0, macro_series={"hy_oas": 650.0, "t10y2y": -0.6})
    )
    assert ms.state == "RISK_OFF"
    assert ms.multiplier < 0.7
    assert ms.veto is False


def test_degraded_is_neutral_full_size():
    ms = MacroModule().compute(_ctx())  # no FRED data at all
    assert ms.state == "NEUTRAL"
    assert ms.multiplier == 1.0
    assert ms.raw.get("degraded") is True


def test_credit_stress_overlay_lowers_score():
    """HY OAS crossing 500 bps forces the score one band lower (file 04 §168/§217)."""
    calm = MacroModule().compute(_ctx(vix=18.0, macro_series={"hy_oas": 480.0, "t10y2y": 0.3}))
    stress = MacroModule().compute(_ctx(vix=18.0, macro_series={"hy_oas": 520.0, "t10y2y": 0.3}))
    assert stress.score == pytest.approx(calm.score - 20.0)
    assert any("overlay" in r for r in stress.reasons)


def test_macro_never_vetoes():
    ms = MacroModule().compute(
        _ctx(vix=80.0, vix3m=40.0, macro_series={"hy_oas": 2000.0, "t10y2y": -2.0})
    )
    assert ms.veto is False  # macro scales size; it never blocks (that's the regime gate)
    assert 0.0 < ms.multiplier <= 1.0


def test_partial_inputs_still_score():
    """With only VIX available (no FRED macro series), it still produces a score."""
    ms = MacroModule().compute(_ctx(vix=16.0))
    assert ms.state in {"RISK_ON", "NEUTRAL", "RISK_OFF"}
    assert ms.raw.get("degraded") is None
    assert 0.0 < ms.multiplier <= 1.0
