"""Alembic environment configuration for embedded migrations."""

import os
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

from pointlessql.models import Base

target_metadata = Base.metadata

# Let operators run ``alembic`` from the shell against whatever
# backend ``POINTLESSQL_DB_URL`` points at, the same way the runtime
# ``init_db()`` overrides ``sqlalchemy.url`` programmatically.  Without
# this, ``alembic upgrade head`` always hits the SQLite path baked
# into ``alembic.ini``, which makes CI Postgres lanes and ad-hoc PG
# migrations needlessly painful.
_url_override = os.environ.get("POINTLESSQL_DB_URL")
if _url_override:
    context.config.set_main_option("sqlalchemy.url", _url_override)

# SQLite cannot reflect ``CREATE INDEX … (col DESC)`` from PRAGMA, so
# autogenerate sees the index without DESC on the DB side and with
# DESC on the model side, then proposes a drop+recreate every check.
# These two indexes carry DESC ordering by design (see
# :class:`pointlessql.models.scheduler.JobRun` and
# :class:`pointlessql.models.catalog.SyncRun` docstrings); skip them in
# diff comparison so ``alembic check`` stays green on SQLite.
# Postgres reflects expression-based indexes correctly and will still
# notice real drift.
_SQLITE_EXPRESSION_INDEX_ALLOWLIST = frozenset(
    {
        "ix_job_runs_job_started",
        "ix_sync_run_catalog_started",
    }
)

# Both FTS surfaces are created via raw SQL in their migrations
# rather than as ORM-defined tables, because the SQLite FTS5 vtable
# spawns shadow tables (``audit_search_data``, ``audit_search_idx``,
# ``audit_search_content``, ``audit_search_docsize``,
# ``audit_search_config``) that SQLAlchemy can't model, and the
# Postgres ``audit_search_index`` carries a generated tsvector column
# whose dialect-specific expression alembic autogenerate would
# re-render as drift.  Filtering the family out by name prefix keeps
# ``alembic check`` green on both backends.
_FTS_TABLE_PREFIXES: tuple[str, ...] = ("audit_search",)

# Phase 76.5 + 76.5.1 + 77.0.B — columns whose FK is added via raw
# ``ALTER TABLE ADD COLUMN ... REFERENCES`` because batch_alter_table
# fails on these tables (unnamed legacy CHECKs).  The ORM models
# declare the FK for relationship loading, but the constraint is
# only physically enforced on Postgres.  Without this filter
# ``alembic check`` keeps proposing to re-add the FK on every run.
# See ``u2w4y6a8c0e3_endorse_review_agent_author.py`` +
# ``w4z6b8d0f2h4_phase77b_social_target_id_columns.py``.
_AGENT_AUTHOR_FK_COLUMNS: frozenset[str] = frozenset(
    {
        "author_agent_id",
        "applied_by_agent_id",
        "social_target_id",
    },
)


def _include_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Filter out SQLite expression-index false positives in autogenerate.

    Args:
        obj: The schema object alembic is considering.
        name: The object's name (``None`` for some unnamed constraints).
        type_: ``"table"`` / ``"column"`` / ``"index"`` / etc.
        reflected: ``True`` if the object came from DB reflection.
        compare_to: The opposite-side counterpart, or ``None``.

    Returns:
        ``False`` to exclude the object from diff; ``True`` otherwise.
    """
    if type_ == "index" and name in _SQLITE_EXPRESSION_INDEX_ALLOWLIST:
        return False
    if (
        type_ == "table"
        and name is not None
        and any(name.startswith(prefix) for prefix in _FTS_TABLE_PREFIXES)
    ):
        return False
    if type_ == "foreign_key_constraint":
        cols = list(getattr(obj, "columns", []) or [])
        if cols and cols[0].name in _AGENT_AUTHOR_FK_COLUMNS:
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
