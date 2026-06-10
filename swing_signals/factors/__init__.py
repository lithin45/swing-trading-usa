"""Per-stock factor modules (research files 01, 02, 03, 05, 06).

Each factor self-registers via the ``@register`` decorator and implements the
same :class:`~swing_signals.factors.base.Factor` interface, so it is testable in
isolation and can be enabled/disabled or reweighted purely from config.
"""

from __future__ import annotations


def register_builtins() -> dict[str, type]:
    """Import the built-in factor modules so they self-register, and return the registry.

    Importing each ``f0x_*`` module triggers its ``@register`` decorator. Called by
    the orchestrator at startup; adding a new factor means adding one import here.
    """
    from . import (
        f01_technical,  # noqa: F401  (self-registers on import)
        f02_news_sentiment,  # noqa: F401  (self-disables without a key/news)
        f08_momentum,  # noqa: F401  (momentum / relative strength — the core edge)
        f09_setup,  # noqa: F401  (low-weight breakout/pullback entry confirmation)
    )
    from .registry import all_factors

    return all_factors()

