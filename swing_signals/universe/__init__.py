"""Dynamic universe construction: S&P 500 + curated themes + news-discovered movers.

A two-stage funnel keeps cost bounded: a cheap technical+momentum scan over the
whole universe (no LLM) narrows to a small candidate set, and only those candidates
reach the costly Claude news factor. See :mod:`swing_signals.universe.screen`.
"""
