"""Per-stock factor modules (research files 01, 02, 03, 05, 06).

Each factor self-registers via the ``@register`` decorator and implements the
same :class:`~swing_signals.factors.base.Factor` interface, so it is testable in
isolation and can be enabled/disabled or reweighted purely from config.
"""
