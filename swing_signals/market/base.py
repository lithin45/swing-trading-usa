"""Interface for market-level modules (macro 04, regime 07).

These compute once per run from :class:`MarketContext` and return a
:class:`MarketState`: a 0–100 score, a discrete label, a position-size
``multiplier`` in [0, 1], and (for the regime gate) a hard ``veto`` flag.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..context import RunContext


@dataclass(frozen=True)
class MarketState:
    """Output of a market-level module.

    Attributes:
        name: module name ("macro" or "regime").
        score: 0–100 (higher = more risk-on / more favorable).
        state: discrete label, e.g. "GREEN"/"YELLOW"/"RED" (regime) or
            "RISK_ON"/"NEUTRAL"/"RISK_OFF" (macro).
        multiplier: position-size multiplier in [0, 1] applied to risk %.
        veto: if True, suppress all new long signals regardless of score
            (used by the regime gate's hard override; macro never vetoes).
        reasons: human-readable explanation.
        raw: diagnostics for logging.
    """

    name: str
    score: float
    state: str
    multiplier: float = 1.0
    veto: bool = False
    reasons: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class MarketModule(ABC):
    name: ClassVar[str]

    @abstractmethod
    def compute(self, ctx: RunContext) -> MarketState:
        """Return the market state from ``ctx.market``."""
        raise NotImplementedError
