"""Data layer (research file 09): free-first, swappable sources.

The orchestrator depends only on the ``DataProvider`` interface, so providers
(yfinance, Stooq, FRED, Finnhub, EDGAR, FINRA) can be swapped or reordered from
config. Concrete providers, caching, and retries arrive in Stage 2.
"""
