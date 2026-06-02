"""Plugin registry for factors.

A factor self-registers by decorating its class with ``@register``. The engine
iterates the registry and instantiates only the factors named (with weight > 0)
in config — so adding a factor is "drop a file + decorate" with no engine edits
(Open/Closed principle), and disabling one is a config change.
"""

from __future__ import annotations

from .base import Factor

_REGISTRY: dict[str, type[Factor]] = {}


def register(cls: type[Factor]) -> type[Factor]:
    """Class decorator that adds a Factor subclass to the registry."""
    name = getattr(cls, "name", None)
    if not name:
        raise ValueError(f"{cls.__name__} must set a non-empty 'name' to be registered")
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ValueError(f"factor name already registered: {name!r}")
    _REGISTRY[name] = cls
    return cls


def all_factors() -> dict[str, type[Factor]]:
    """Return a copy of the registry (name → Factor class)."""
    return dict(_REGISTRY)


def get_factor(name: str) -> type[Factor]:
    return _REGISTRY[name]


def clear_registry() -> None:
    """Reset the registry — used by tests for isolation."""
    _REGISTRY.clear()
