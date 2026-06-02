"""Persistence (research file 12): signals / outcomes / runs.

SQLAlchemy models over SQLite (Postgres-ready via connection string). Records
every signal with its factor attribution and the git SHA + config hash that
produced it, so any signal is reproducible. Implemented in Stage 6.
"""
