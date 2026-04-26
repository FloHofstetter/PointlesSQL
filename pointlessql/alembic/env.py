"""Alembic environment configuration for embedded migrations."""

from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

from pointlessql.models import Base

target_metadata = Base.metadata

# SQLite cannot reflect ``CREATE INDEX … (col DESC)`` from PRAGMA, so
# autogenerate sees the index without DESC on the DB side and with
# DESC on the model side, then proposes a drop+recreate every check.
# These two indexes carry DESC ordering by design (see
# :class:`pointlessql.models.scheduler.JobRun` and
# :class:`pointlessql.models.sync.SyncRun` docstrings); skip them in
# diff comparison so ``alembic check`` stays green on SQLite.
# Postgres reflects expression-based indexes correctly and will still
# notice real drift.
_SQLITE_EXPRESSION_INDEX_ALLOWLIST = frozenset(
    {
        "ix_job_runs_job_started",
        "ix_sync_run_catalog_started",
    }
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
