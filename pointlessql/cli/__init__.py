"""Operational CLI helpers (Sprint 30+).

Currently houses :mod:`pointlessql.cli.migrate_to_postgres` — the
operator-facing one-shot tool for porting an existing SQLite
PointlesSQL deployment to Postgres.  Wired into the top-level
``pointlessql`` Typer app via :mod:`pointlessql.api.main` (the
existing console-scripts entry).
"""
