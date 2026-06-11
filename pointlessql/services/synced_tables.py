"""Synced-tables worker — reverse-ETL Delta tables into a SQL store.

Synced-table rows live in the metadata DB
(:class:`pointlessql.models.synced_tables.SyncedTable`); this module
owns their lifecycle: CRUD, the :func:`sync_once` copy worker that
moves a Delta table (full snapshot or Change-Data-Feed increment)
into a Postgres/SQLite target, and the :func:`lookup` primary-key
read path that backs the low-latency lookup API.

The target URL stored on the row may carry
``{{secrets/<scope>/<key>}}`` placeholders; the worker resolves them
just-in-time via
:func:`pointlessql.services.secret_scopes.resolve_secret_references`
so credentials never rest in the row.

:func:`sync_executor` adapts :func:`sync_once` to the scheduler's
``JobExecutor`` signature.  It is exported but **not registered**
anywhere — the integrating session adds it to
:func:`pointlessql.services.scheduler.registry.build_default_registry`
under a ``"synced_table_sync"`` kind.
"""

from __future__ import annotations

import asyncio
import datetime
import re
from typing import TYPE_CHECKING, Any, cast

import deltalake
import pandas as pd
import pyarrow as pa
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from pointlessql.exceptions import ValidationError
from pointlessql.models.synced_tables import (
    SYNCED_TABLE_MODES,
    SYNCED_TABLE_STATUSES,
    SyncedTable,
)
from pointlessql.services import secret_scopes as secret_scopes_service

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.services.unitycatalog import UnityCatalogClient
    from pointlessql.types import UserInfo

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CDF_META_COLUMNS: tuple[str, ...] = ("_change_type", "_commit_version", "_commit_timestamp")
"""Metadata columns ``load_cdf`` adds; never written to the target."""

_CHUNK_ROWS = 1000

_MAX_LOOKUP_ROWS = 100


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _validate_identifier(value: str, *, what: str) -> str:
    """Return *value* stripped, or raise when it is not a safe identifier.

    Identifiers end up double-quoted inside generated SQL, so the
    grammar is deliberately strict: leading letter/underscore, then
    letters/digits/underscores only.

    Args:
        value: Candidate table or column name.
        what: Noun used in the error message.

    Returns:
        The stripped identifier.

    Raises:
        ValueError: When the identifier does not match
            ``[A-Za-z_][A-Za-z0-9_]*``.
    """
    candidate = value.strip()
    if not _IDENTIFIER_RE.match(candidate):
        raise ValueError(f"{what} must match [A-Za-z_][A-Za-z0-9_]*, got {value!r}")
    return candidate


def parse_primary_keys(primary_keys: str | None) -> list[str]:
    """Split a comma-separated key list into validated column names.

    Each key is validated as a safe SQL identifier (the validator
    raises :class:`ValueError` on anything else).

    Args:
        primary_keys: Raw ``primary_keys`` column value (may be
            ``None`` or empty).

    Returns:
        The validated key columns, in declaration order.
    """
    if not primary_keys:
        return []
    return [
        _validate_identifier(part, what="primary key column")
        for part in primary_keys.split(",")
        if part.strip()
    ]


# ---------------------------------------------------------------------------
# DB CRUD
# ---------------------------------------------------------------------------


def create_synced_table(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: str,
    source_fqn: str,
    target_url: str,
    target_table: str,
    primary_keys: str | None,
    mode: str,
    principal: str | None,
) -> SyncedTable:
    """Create a synced-table row in ``idle`` state.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        name: Synced-table identifier (validated).
        source_fqn: Three-part UC name of the source Delta table.
        target_url: SQLAlchemy URL of the serving database; stored
            verbatim, including ``{{secrets/...}}`` placeholders.
        target_table: Table name written in the target database.
        primary_keys: Comma-separated key columns; required for
            ``cdf`` mode.
        mode: One of
            :data:`pointlessql.models.synced_tables.SYNCED_TABLE_MODES`.
        principal: Creator e-mail.

    Returns:
        The persisted row (detached).

    Raises:
        ValueError: On malformed input or a name already taken in
            the workspace.
    """
    candidate = name.strip()
    if not _NAME_RE.match(candidate):
        raise ValueError(f"synced-table name must be 1-128 chars from [A-Za-z0-9_-], got {name!r}")
    fqn = source_fqn.strip()
    parts = fqn.split(".")
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError(
            f"source_fqn must be three parts 'catalog.schema.table', got {source_fqn!r}"
        )
    if mode not in SYNCED_TABLE_MODES:
        raise ValueError(f"mode must be one of {', '.join(SYNCED_TABLE_MODES)}, got {mode!r}")
    if not target_url.strip():
        raise ValueError("target_url must be a non-empty SQLAlchemy URL")
    table_name = _validate_identifier(target_table, what="target_table")
    keys = parse_primary_keys(primary_keys)
    if mode == "cdf" and not keys:
        raise ValueError("cdf mode requires primary_keys (used to apply deletes and upserts)")
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(SyncedTable).where(
                SyncedTable.workspace_id == workspace_id,
                SyncedTable.name == candidate,
            )
        )
        if existing is not None:
            raise ValueError(f"synced table {candidate!r} already exists")
        row = SyncedTable(
            workspace_id=workspace_id,
            name=candidate,
            source_fqn=fqn,
            target_url=target_url.strip(),
            target_table=table_name,
            primary_keys=",".join(keys) if keys else None,
            mode=mode,
            created_by=principal,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def list_synced_tables(factory: sessionmaker[Session], *, workspace_id: int) -> list[SyncedTable]:
    """List the workspace's synced tables ordered by name.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Detached synced-table rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(SyncedTable)
                .where(SyncedTable.workspace_id == workspace_id)
                .order_by(SyncedTable.name)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_synced_table(
    factory: sessionmaker[Session], *, workspace_id: int, name: str
) -> SyncedTable | None:
    """Return the workspace's synced table by name, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        name: Synced-table identifier.

    Returns:
        The detached row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(SyncedTable).where(
                SyncedTable.workspace_id == workspace_id,
                SyncedTable.name == name,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def delete_synced_table(factory: sessionmaker[Session], *, synced_table_id: int) -> bool:
    """Delete a synced-table row (the target table is left in place).

    Args:
        factory: SQLAlchemy session factory.
        synced_table_id: Primary key.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(SyncedTable, synced_table_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


def set_status(
    factory: sessionmaker[Session],
    *,
    synced_table_id: int,
    status: str,
    error: str | None = None,
) -> None:
    """Persist a sync lifecycle transition.

    Args:
        factory: SQLAlchemy session factory.
        synced_table_id: Primary key.
        status: New status (caller passes a member of
            :data:`pointlessql.models.synced_tables.SYNCED_TABLE_STATUSES`).
        error: Failure detail recorded on ``failed`` transitions and
            cleared otherwise.

    Raises:
        ValueError: When *status* is not a known lifecycle state.
    """
    if status not in SYNCED_TABLE_STATUSES:
        raise ValueError(
            f"status must be one of {', '.join(SYNCED_TABLE_STATUSES)}, got {status!r}"
        )
    with factory() as session:
        row = session.get(SyncedTable, synced_table_id)
        if row is None:
            return
        row.status = status
        row.last_error = error
        row.updated_at = _utcnow()
        session.commit()


def _record_sync_success(
    factory: sessionmaker[Session],
    *,
    synced_table_id: int,
    rows_affected: int,
    version: int,
) -> None:
    """Persist a successful sync: cursor, counters, ``ok`` status."""
    now = _utcnow()
    with factory() as session:
        row = session.get(SyncedTable, synced_table_id)
        if row is None:
            return
        row.status = "ok"
        row.last_error = None
        row.last_synced_version = version
        row.rows_synced = int(row.rows_synced or 0) + rows_affected
        row.last_synced_at = now
        row.updated_at = now
        session.commit()


# ---------------------------------------------------------------------------
# Sync worker
# ---------------------------------------------------------------------------


def _full_load(engine: Engine, *, target_table: str, storage_location: str) -> tuple[int, int]:
    """Replace the target table with a full snapshot of the source.

    Args:
        engine: Target SQLAlchemy engine.
        target_table: Validated target table name.
        storage_location: Filesystem path or URI of the Delta table.

    Returns:
        ``(rows_written, source_version)``.
    """
    dt = deltalake.DeltaTable(storage_location)
    frame = cast(
        "pd.DataFrame",
        dt.to_pyarrow_table().to_pandas(),  # pyright: ignore[reportUnknownMemberType]
    )
    frame.to_sql(  # pyright: ignore[reportUnknownMemberType]
        target_table, engine, if_exists="replace", index=False, chunksize=_CHUNK_ROWS
    )
    return len(frame.index), int(dt.version())


def _delete_by_keys(
    conn: Connection,
    *,
    target_table: str,
    keys: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """Issue one executemany DELETE matching *rows* by primary key."""
    predicate = " AND ".join(f'"{key}" = :{key}' for key in keys)
    statement = sa.text(f'DELETE FROM "{target_table}" WHERE {predicate}')
    params = [{key: row.get(key) for key in keys} for row in rows]
    conn.execute(statement, params)


def _apply_changes(
    engine: Engine,
    *,
    target_table: str,
    keys: list[str],
    last_synced_version: int,
    storage_location: str,
) -> tuple[int, int]:
    """Apply Change-Data-Feed events since the cursor to the target.

    Events are replayed in commit order.  Deletes remove rows by
    primary key; inserts and update post-images are applied as
    delete-then-append upserts — portable across SQLite and Postgres
    without dialect-specific ``ON CONFLICT`` clauses.  Pre-image rows
    and the CDF metadata columns never reach the target.

    Args:
        engine: Target SQLAlchemy engine.
        target_table: Validated target table name.
        keys: Validated primary-key columns.
        last_synced_version: Delta version already applied.
        storage_location: Filesystem path or URI of the Delta table.

    Returns:
        ``(rows_affected, source_version)``.

    Raises:
        ValueError: When the change data feed cannot be read —
            typically because ``delta.enableChangeDataFeed`` is not
            set on the source table.
    """
    dt = deltalake.DeltaTable(storage_location)
    version = int(dt.version())
    try:
        reader = dt.load_cdf(starting_version=last_synced_version + 1, allow_out_of_range=True)
        raw_events = cast(
            "list[dict[str, Any]]",
            pa.table(reader.read_all()).to_pylist(),  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        )
    except Exception as exc:
        raise ValueError(
            f"could not read the change data feed of {storage_location!r}: {exc} — "
            "enable the delta.enableChangeDataFeed table property on the source "
            "or switch the synced table to 'full' mode"
        ) from exc
    events = [event for event in raw_events if event.get("_change_type") != "update_preimage"]
    if not events:
        return 0, version
    affected = 0
    with engine.begin() as conn:
        commit_versions = sorted({int(event["_commit_version"]) for event in events})
        for commit_version in commit_versions:
            batch = [event for event in events if int(event["_commit_version"]) == commit_version]
            deletes = [event for event in batch if event["_change_type"] == "delete"]
            if deletes:
                _delete_by_keys(conn, target_table=target_table, keys=keys, rows=deletes)
                affected += len(deletes)
            upserts = [
                event for event in batch if event["_change_type"] in ("insert", "update_postimage")
            ]
            if upserts:
                _delete_by_keys(conn, target_table=target_table, keys=keys, rows=upserts)
                payload = pd.DataFrame.from_records(  # pyright: ignore[reportUnknownMemberType]
                    [
                        {
                            column: value
                            for column, value in event.items()
                            if column not in _CDF_META_COLUMNS
                        }
                        for event in upserts
                    ]
                )
                payload.to_sql(  # pyright: ignore[reportUnknownMemberType]
                    target_table, conn, if_exists="append", index=False, chunksize=_CHUNK_ROWS
                )
                affected += len(upserts)
    return affected, version


def sync_once(
    factory: sessionmaker[Session],
    *,
    synced_table_id: int,
    storage_location: str,
) -> dict[str, Any]:
    """Run one sync of a Delta source into its SQL target.

    ``full`` mode replaces the target with a snapshot; ``cdf`` mode
    applies Change-Data-Feed events since the version cursor (the
    first ``cdf`` sync is a full load that seeds the cursor).  The
    target URL's secret placeholders are resolved just-in-time and
    the engine is disposed before returning, success or not.

    Args:
        factory: SQLAlchemy session factory.
        synced_table_id: Primary key of the synced-table row.
        storage_location: Resolved Delta storage URI / path for the
            source table.  The caller owns the UC lookup so this
            worker stays sync-safe.

    Returns:
        ``{"name", "mode", "rows_affected", "version"}`` —
        ``rows_affected`` counts rows written/deleted this run,
        ``version`` is the new Delta cursor.

    Raises:
        ValueError: When the row is missing, the change data feed is
            unavailable, or the secret references cannot resolve.
        Exception: Any engine/Delta failure propagates after the row
            is marked ``failed`` with the error message.
    """
    with factory() as session:
        row = session.get(SyncedTable, synced_table_id)
        if row is None:
            raise ValueError(f"synced table {synced_table_id} not found")
        session.expunge(row)
    set_status(factory, synced_table_id=row.id, status="syncing")
    try:
        resolved_url = secret_scopes_service.resolve_secret_references(
            factory, workspace_id=row.workspace_id, text=row.target_url
        )
        engine = sa.create_engine(resolved_url)
        try:
            if row.mode == "cdf" and row.last_synced_version is not None:
                affected, version = _apply_changes(
                    engine,
                    target_table=row.target_table,
                    keys=parse_primary_keys(row.primary_keys),
                    last_synced_version=row.last_synced_version,
                    storage_location=storage_location,
                )
            else:
                affected, version = _full_load(
                    engine, target_table=row.target_table, storage_location=storage_location
                )
        finally:
            engine.dispose()
    except Exception as exc:
        set_status(factory, synced_table_id=row.id, status="failed", error=str(exc))
        raise
    _record_sync_success(factory, synced_table_id=row.id, rows_affected=affected, version=version)
    return {
        "name": row.name,
        "mode": row.mode,
        "rows_affected": affected,
        "version": version,
    }


# ---------------------------------------------------------------------------
# Lookup API
# ---------------------------------------------------------------------------


def _json_safe(value: object) -> object:
    """Project a DB cell to a JSON-serializable value (str() fallback)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _coerce_key_value(
    engine: Engine, *, target_table: str, key_column: str, key_value: str
) -> object:
    """Coerce the lookup value to the target column's Python type.

    SQLite's column affinity forgives a string bound against an
    integer column, but Postgres does not — reflect the column once
    and coerce so a numeric key works on both dialects.  Falls back
    to the raw string when reflection or conversion fails.

    Args:
        engine: Target SQLAlchemy engine.
        target_table: Validated target table name.
        key_column: Validated key column name.
        key_value: Raw query-string value.

    Returns:
        The value to bind.
    """
    try:
        columns = sa.inspect(engine).get_columns(target_table)
    except SQLAlchemyError:
        return key_value
    for column in columns:
        if column["name"] != key_column:
            continue
        try:
            python_type = column["type"].python_type
        except NotImplementedError:
            return key_value
        if python_type in (int, float):
            try:
                return python_type(key_value)
            except ValueError:
                return key_value
        return key_value
    return key_value


def lookup(
    factory: sessionmaker[Session],
    *,
    synced_table_id: int,
    key_column: str,
    key_value: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Point-read rows from the synced target by primary key.

    Only the row's configured primary-key columns are queryable —
    that keeps index usage predictable and matches what the sync
    worker guarantees about the target.  The value is always bound
    as a parameter (never interpolated) and the identifiers are
    validated before quoting, so injection-shaped inputs degrade to
    an empty result.

    Args:
        factory: SQLAlchemy session factory.
        synced_table_id: Primary key of the synced-table row.
        key_column: Column to filter on; must be one of the row's
            ``primary_keys``.
        key_value: Value to match (coerced to the column type).
        limit: Maximum rows returned (clamped to 1–100).

    Returns:
        JSON-safe row dicts.

    Raises:
        ValueError: When the row is missing, no primary keys are
            configured, or *key_column* is not a primary-key column.
    """
    with factory() as session:
        row = session.get(SyncedTable, synced_table_id)
        if row is None:
            raise ValueError(f"synced table {synced_table_id} not found")
        session.expunge(row)
    keys = parse_primary_keys(row.primary_keys)
    if not keys:
        raise ValueError(f"synced table {row.name!r} has no primary_keys configured for lookup")
    candidate = _validate_identifier(key_column, what="key_column")
    if candidate not in keys:
        raise ValueError(
            f"key_column must be one of the primary keys ({', '.join(keys)}), got {key_column!r}"
        )
    bounded = max(1, min(int(limit), _MAX_LOOKUP_ROWS))
    resolved_url = secret_scopes_service.resolve_secret_references(
        factory, workspace_id=row.workspace_id, text=row.target_url
    )
    engine = sa.create_engine(resolved_url)
    try:
        bound_value = _coerce_key_value(
            engine, target_table=row.target_table, key_column=candidate, key_value=key_value
        )
        statement = sa.text(
            f'SELECT * FROM "{row.target_table}" WHERE "{candidate}" = :key_value LIMIT :limit'
        )
        with engine.connect() as conn:
            records = conn.execute(
                statement, {"key_value": bound_value, "limit": bounded}
            ).mappings()
            results = [
                {column: _json_safe(value) for column, value in record.items()}
                for record in records
            ]
    finally:
        engine.dispose()
    return results


# ---------------------------------------------------------------------------
# Scheduler executor
# ---------------------------------------------------------------------------


async def sync_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Scheduler-side wrapper around :func:`sync_once`.

    Matches the
    :data:`pointlessql.services.scheduler.registry.JobExecutor`
    signature.  Reads ``synced_table_id`` from ``config``, resolves
    the source table's storage location through the UC facade, and
    runs the blocking sync off the loop.

    Exported only — registration is the integrating session's job
    (suggested kind: ``"synced_table_sync"`` in
    :func:`pointlessql.services.scheduler.registry.build_default_registry`).

    Args:
        job_run_id: Current ``JobRun.id``.  Unused — sync stats live
            on the synced-table row, not the run.
        user_info: The run-as user's ``UserInfo``.  Unused — the
            target write is credentialed by the row's target URL.
        config: Must carry ``synced_table_id``.
        uc_client: Principal-forwarded facade used to resolve the
            source table's ``storage_location``.

    Raises:
        ValidationError: When *config* is missing ``synced_table_id``,
            the row or source table is gone, or the source has no
            storage location.
    """
    del job_run_id, user_info
    raw_id = config.get("synced_table_id")
    if raw_id is None:
        raise ValidationError("synced-table job config must carry 'synced_table_id'.")
    synced_table_id = int(raw_id)

    from pointlessql.db import get_session_factory

    factory = get_session_factory()
    with factory() as session:
        row = session.get(SyncedTable, synced_table_id)
        if row is None:
            raise ValidationError(f"synced table {synced_table_id} not found.")
        source_fqn = row.source_fqn
    parts = source_fqn.split(".")
    if len(parts) != 3:
        raise ValidationError(f"source_fqn must be three parts, got {source_fqn!r}.")
    table_info = await uc_client.get_table(parts[0], parts[1], parts[2])
    storage = table_info.get("storage_location")
    if not storage or not isinstance(storage, str):
        raise ValidationError(f"source table {source_fqn!r} has no storage_location.")
    await asyncio.to_thread(
        sync_once, factory, synced_table_id=synced_table_id, storage_location=storage
    )
