"""The Factor interface and its output type.

Every per-stock factor (files 01, 02, 03, 05, 06) implements this one contract:
``compute(data, ctx) -> SubScore`` where the score is on a 0–100 scale with
50 = neutral, matching the research files. The factor also returns the
human-readable *reasons* it fired (transparency requirement) and a ``raw`` dict
of diagnostics for logging/attribution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..context import RunContext, SymbolData

#: Neutral sub-score: contributes nothing directional to the composite.
NEUTRAL = 50.0


@dataclass(frozen=True)
class SubScore:
    """The output of a factor for one symbol.

    Attributes:
        name: factor name (matches the registry key and config key).
        value: 0–100; 50 = neutral, >50 bullish, <50 bearish.
        reasons: human-readable bullet points explaining why it fired.
        raw: diagnostics (intermediate values) for logging and attribution.
        ok: False if the factor could not compute (e.g. missing data); such a
            sub-score is excluded from the composite rather than treated as neutral.
    """

    name: str
    value: float = NEUTRAL
    reasons: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    ok: bool = True

    @classmethod
    def neutral(cls, name: str, reason: str = "no signal") -> SubScore:
        return cls(name=name, value=NEUTRAL, reasons=[reason])

    @classmethod
    def unavailable(cls, name: str, reason: str) -> SubScore:
        """A sub-score the engine should exclude (data missing/insufficient)."""
        return cls(name=name, value=NEUTRAL, reasons=[reason], ok=False)


class Factor(ABC):
    """Base class for a per-stock factor.

    Subclasses set ``name`` and ``requires`` and implement ``compute``. ``requires``
    lists the data keys the factor needs (e.g. ``("ohlcv",)``) so the data layer
    knows what to fetch and the engine can skip a factor whose data is missing.
    """

    name: ClassVar[str]
    requires: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def compute(self, data: SymbolData, ctx: RunContext) -> SubScore:
        """Return a 0–100 SubScore for ``data.symbol`` given the run context."""
        raise NotImplementedError
