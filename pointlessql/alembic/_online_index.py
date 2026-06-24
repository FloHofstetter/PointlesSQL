"""Non-blocking (online) index build/drop helpers for migrations.

On Postgres a plain ``CREATE INDEX`` takes an ``ACCESS EXCLUSIVE`` lock and
blocks every write to the table until the build finishes — fatal on a
large, append-only, write-hot table (``audit_log`` sits on the request hot
path, ``query_history`` / ``lineage_*`` / ``*_snapshots`` grow unbounded).
``CREATE INDEX CONCURRENTLY`` builds without that lock, but it cannot run
inside a transaction, so it must execute in an ``autocommit_block``.

SQLite has no concurrent build and no write-blocking concern at our scale,
so both helpers fall back to the plain ``op.create_index`` /
``op.drop_index`` there, keeping migrations dialect-portable and
``alembic check`` green on the SQLite lane.

Prefer these over the bare ``op.*`` calls for any index on a large,
write-hot table.
"""

from __future__ import annotations

from typing import Any

from alembic import op


def create_index_online(
    index_name: str,
    table_name: str,
    columns: list[Any],
    *,
    unique: bool = False,
    **kw: Any,
) -> None:
    """Create an index without blocking writes on Postgres.

    On Postgres the index is built ``CONCURRENTLY`` (and ``IF NOT EXISTS``,
    so a retried migration after a failed concurrent build is idempotent)
    inside an ``autocommit_block`` — required, because a concurrent build
    cannot run in a transaction. On every other dialect a plain
    ``op.create_index`` is issued.

    Args:
        index_name: Name of the index to create.
        table_name: Table to index.
        columns: Column names / SQL expressions (e.g.
            ``sa.text("captured_at DESC")``).
        unique: Whether the index is unique.
        **kw: Extra keyword arguments forwarded to ``op.create_index``.
    """
    if op.get_context().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                index_name,
                table_name,
                columns,
                unique=unique,
                postgresql_concurrently=True,
                if_not_exists=True,
                **kw,
            )
    else:
        op.create_index(index_name, table_name, columns, unique=unique, **kw)


def drop_index_online(index_name: str, table_name: str, **kw: Any) -> None:
    """Drop an index without blocking writes on Postgres.

    Mirrors :func:`create_index_online` for the downgrade path: Postgres
    issues ``DROP INDEX CONCURRENTLY`` (and ``IF EXISTS``) in an
    ``autocommit_block``; other dialects use a plain ``op.drop_index``.

    Args:
        index_name: Name of the index to drop.
        table_name: Table the index belongs to.
        **kw: Extra keyword arguments forwarded to ``op.drop_index``.
    """
    if op.get_context().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                index_name,
                table_name=table_name,
                postgresql_concurrently=True,
                if_exists=True,
                **kw,
            )
    else:
        op.drop_index(index_name, table_name=table_name, **kw)
