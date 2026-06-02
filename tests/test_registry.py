"""Factor plugin registry: register, look up, reject duplicates/nameless."""

from __future__ import annotations

import pytest

from swing_signals.factors import registry
from swing_signals.factors.base import Factor, SubScore


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear_registry()
    yield
    registry.clear_registry()


def test_register_and_lookup():
    @registry.register
    class Dummy(Factor):
        name = "dummy"
        requires = ("ohlcv",)

        def compute(self, data, ctx) -> SubScore:
            return SubScore(name=self.name, value=60.0, reasons=["test"])

    assert "dummy" in registry.all_factors()
    assert registry.get_factor("dummy") is Dummy


def test_duplicate_name_raises():
    @registry.register
    class A(Factor):
        name = "dup"

        def compute(self, data, ctx) -> SubScore:
            return SubScore(self.name)

    with pytest.raises(ValueError):

        @registry.register
        class B(Factor):
            name = "dup"

            def compute(self, data, ctx) -> SubScore:
                return SubScore(self.name)


def test_missing_name_raises():
    with pytest.raises(ValueError):

        @registry.register
        class C(Factor):
            def compute(self, data, ctx) -> SubScore:
                return SubScore("nameless")
