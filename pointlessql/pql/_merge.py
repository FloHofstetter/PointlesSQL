"""``pql.merge()`` — Sprint 13.5.2 thin facade over Delta MERGE.

The merge primitive is one of the three Phase-13.5 building blocks
that turn an agent run into a Medallion lakehouse: ``autoload`` lifts
files into bronze, ``merge`` consolidates bronze → silver, and a SQL
aggregation produces gold.  Sprint 13.5.2 ships ``merge`` because
silver is where the upsert semantics matter — gold writes are
typically full-overwrite or append-truncate.

Two strategies in scope:

* ``upsert`` — match on the supplied keys; update all non-key
  columns from source on match, insert new rows otherwise.
  Standard SCD-1 semantics.
* ``scd2`` — append-only history.  Source rows are augmented with
  ``_valid_from`` / ``_valid_to`` / ``_is_current`` columns; a key
  match closes the currently-open target row (``_valid_to=now``,
  ``_is_current=false``) and appends a new current row.  Note:
  the MVP closes + reopens for *every* source row whose key
  matches a current target row, even when the values are
  unchanged.  Pre-filter the source to only "actually changed"
  rows if churn-free history matters — change detection inside
  the primitive would force schema-aware comparison and is
  deliberately deferred.

The audit column names are hardcoded here rather than read from
:mod:`pointlessql.conventions` because they are silver-layer
specific (audit columns in conventions are bronze-specific).  A
follow-up sprint may promote them to a configurable field on
:class:`pointlessql.conventions.LayerConvention` if a real
override case appears.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import pyarrow as pa
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql._hashing import arrow_ipc_sha256
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._read import read_table
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context

MergeStrategy = Literal["upsert", "scd2"]

SCD2_VALID_FROM = "_valid_from"
SCD2_VALID_TO = "_valid_to"
SCD2_IS_CURRENT = "_is_current"


def merge_table(
    *,
    client: Client,
    engine: Engine,
    source: Any,
    target: str,
    on: list[str],
    strategy: MergeStrategy,
    unreachable_msg: str,
    agent_run_id: str | None = None,
) -> dict[str, Any]:
    """Merge *source* into the existing Delta table at *target*.

    The target table must already exist in soyuz-catalog with a
    ``storage_location``; the primitive does not bootstrap a
    table — that is the autoload primitive's job.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        engine: Engine to read *source* with when it is a UC
            reference.  Ignored when *source* is already a frame.
        source: Either a pandas DataFrame (or any frame the engine
            knows how to read) **or** a UC ``"catalog.schema.table"``
            string that resolves through :func:`read_table`.
        target: UC ``"catalog.schema.table"`` string.  Must exist.
        on: Non-empty list of column names that together form the
            merge key.  Every key column must be present in the
            source frame.
        strategy: ``"upsert"`` or ``"scd2"``.
        unreachable_msg: Pre-rendered "cannot reach catalog"
            message — same hop the read/write helpers take.
        agent_run_id: Sprint 13.8 — when set, emits one
            ``agent_run_operations`` row capturing input SHA, Delta
            version pre/post, and merge stats.

    Returns:
        A dict carrying ``strategy`` and the deltalake merge stats
        (row counts).  SCD-2 also reports the appended-rows count.

    Raises:
        ValidationError: When ``on`` is empty, ``strategy`` is
            unknown, or a key column is missing from the source.
        CatalogNotFoundError: When *target* is unknown to
            soyuz-catalog or has no ``storage_location``.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        AuditUnavailableError: If *agent_run_id* is set and the
            ``agent_run_operations`` row cannot be persisted.
    """  # noqa: DOC503 — Catalog* errors propagate from helpers below
    if not on:
        raise ValidationError("merge requires at least one column in 'on'")
    if strategy not in ("upsert", "scd2"):
        raise ValidationError(
            f"strategy must be 'upsert' or 'scd2', got {strategy!r}"
        )

    parse_full_name(target)
    target_location = _resolve_target_location(client, target, unreachable_msg)
    source_frame = _resolve_source_frame(client, engine, source, unreachable_msg)

    arrow_source = _frame_to_arrow(source_frame)

    missing = [col for col in on if col not in arrow_source.schema.names]
    if missing:
        raise ValidationError(
            f"merge keys {missing!r} are not present in the source schema "
            f"({arrow_source.schema.names!r})"
        )

    from pointlessql.db import get_session_factory
    from pointlessql.pql._write import safe_delta_version

    factory = get_session_factory() if agent_run_id else None

    with operation_context(
        factory,
        agent_run_id=agent_run_id,
        op_name="merge",
        params={"target": target, "on": list(on), "strategy": strategy},
        target_table=target,
    ) as recorder:
        if agent_run_id is not None:
            recorder.delta_version_before = safe_delta_version(target_location)
            try:
                recorder.input_sha = arrow_ipc_sha256(arrow_source)
            except TypeError:
                recorder.input_sha = None

        if strategy == "upsert":
            stats = _do_upsert(target_location, arrow_source, on)
        else:
            stats = _do_scd2(target_location, arrow_source, on)

        if agent_run_id is not None:
            recorder.delta_version_after = safe_delta_version(target_location)
            recorder.rows_affected = _merge_rows_affected(stats)
            recorder.extra_params = {"stats": _stats_for_audit(stats)}

        return stats


def _merge_rows_affected(stats: dict[str, Any]) -> int | None:
    """Best-effort total row count from the deltalake merge stats.

    Args:
        stats: Return value from :func:`_do_upsert` or :func:`_do_scd2`.

    Returns:
        Sum of inserted + updated for upsert; appended + closed for
        SCD-2; ``None`` when the keys cannot be located.
    """
    try:
        if stats.get("strategy") == "upsert":
            inserted = int(stats.get("num_target_rows_inserted", 0) or 0)
            updated = int(stats.get("num_target_rows_updated", 0) or 0)
            return inserted + updated
        if stats.get("strategy") == "scd2":
            appended = int(stats.get("rows_appended", 0) or 0)
            closed = 0
            close_stats = stats.get("close_stats") or {}
            if isinstance(close_stats, dict):
                closed = int(close_stats.get("num_target_rows_updated", 0) or 0)
            return appended + closed
    except (TypeError, ValueError):
        return None
    return None


def _stats_for_audit(stats: dict[str, Any]) -> dict[str, Any]:
    """Strip non-JSON-serialisable bits from the merge stats payload.

    Args:
        stats: Return value from :func:`_do_upsert` or :func:`_do_scd2`.

    Returns:
        A dict whose values are JSON-encodable (numbers, strings,
        nested dicts, lists).  Anything else gets stringified.
    """
    out: dict[str, Any] = {}
    for key, value in stats.items():
        if isinstance(value, (int, float, str, bool, type(None))):
            out[key] = value
        elif isinstance(value, dict):
            out[key] = _stats_for_audit(value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            out[key] = [
                v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
                for v in value  # pyright: ignore[reportUnknownVariableType]
            ]
        else:
            out[key] = str(value)
    return out


def _resolve_target_location(
    client: Client, full_name: str, unreachable_msg: str
) -> str:
    """Look up *full_name* in soyuz-catalog and return its storage_location.

    Args:
        client: Configured catalog client.
        full_name: UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The Delta table's storage location URI.

    Raises:
        CatalogNotFoundError: Target is unknown or has no location.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        raise CatalogNotFoundError(
            f"merge target {full_name!r} not found in soyuz-catalog "
            "(merge does not bootstrap tables — write or autoload first)"
        )
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        raise CatalogNotFoundError(
            f"merge target {full_name!r} has no storage_location"
        )
    return location


def _resolve_source_frame(
    client: Client, engine: Engine, source: Any, unreachable_msg: str
) -> Any:
    """Return *source* as a frame, resolving UC references through the engine.

    Args:
        client: Configured catalog client (only used when *source* is a string).
        engine: Engine used to materialise UC references.
        source: Either a frame or a UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The source frame in the engine's native type.

    Raises:
        CatalogNotFoundError: When *source* is a UC reference that
            cannot be resolved.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """  # noqa: DOC502 — both errors propagate from read_table
    if isinstance(source, str):
        return read_table(
            client=client,
            engine=engine,
            full_name=source,
            unreachable_msg=unreachable_msg,
        )
    return source


def _frame_to_arrow(frame: Any) -> pa.Table:
    """Coerce a frame into a PyArrow Table for ``DeltaTable.merge``.

    Accepts pandas DataFrames (the default engine output) and any
    object that already exposes an Arrow conversion via
    ``to_arrow`` (Polars / DuckDB relations).  PyArrow Tables pass
    through unchanged.

    Args:
        frame: Source frame in the engine's native type.

    Returns:
        A PyArrow Table backing the merge source side.

    Raises:
        ValidationError: When the frame cannot be converted.
    """
    if isinstance(frame, pa.Table):
        return frame
    if hasattr(frame, "to_arrow"):
        return pa.Table.from_pandas(frame.to_arrow())  # type: ignore[no-any-return]
    try:
        return pa.Table.from_pandas(frame)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"merge source must be a pandas DataFrame, PyArrow Table, or "
            f"frame with .to_arrow(); got {type(frame).__name__}"
        ) from exc


def _do_upsert(
    target_location: str, arrow_source: pa.Table, on: list[str]
) -> dict[str, Any]:
    """Run an upsert MERGE against the Delta table at *target_location*.

    Args:
        target_location: Delta table URI.
        arrow_source: Source rows as a PyArrow Table.
        on: Merge-key column names.

    Returns:
        ``{"strategy": "upsert", **deltalake_merge_stats}``.
    """
    import deltalake

    dt = deltalake.DeltaTable(target_location)
    predicate = " AND ".join(f"target.{col} = source.{col}" for col in on)
    stats = (
        dt.merge(
            source=arrow_source,
            predicate=predicate,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )
    return {"strategy": "upsert", **stats}


def _do_scd2(
    target_location: str, arrow_source: pa.Table, on: list[str]
) -> dict[str, Any]:
    """Run an SCD-2 close-and-append against the Delta table.

    Two-phase: the merge step closes any currently-open target row
    that matches the source key (``_valid_to = now``,
    ``_is_current = false``).  An append step then writes every
    source row as a new current version with ``_valid_from = now``,
    ``_valid_to = null``, ``_is_current = true``.  See the module
    docstring for the no-change-detection caveat.

    Args:
        target_location: Delta table URI.
        arrow_source: Source rows as a PyArrow Table.
        on: Merge-key column names.

    Returns:
        ``{"strategy": "scd2", "rows_appended": int, "close_stats": {...}}``.
    """
    import deltalake

    now = datetime.now(UTC)
    augmented = _augment_for_scd2(arrow_source, now)

    dt = deltalake.DeltaTable(target_location)
    predicate_close = (
        " AND ".join(f"target.{col} = source.{col}" for col in on)
        + f" AND target.{SCD2_IS_CURRENT} = TRUE"
    )
    close_iso = now.isoformat()
    close_stats = (
        dt.merge(
            source=augmented,
            predicate=predicate_close,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update(
            updates={
                SCD2_VALID_TO: f"TIMESTAMP '{close_iso}'",
                SCD2_IS_CURRENT: "FALSE",
            }
        )
        .execute()
    )

    deltalake.write_deltalake(target_location, augmented, mode="append")
    return {
        "strategy": "scd2",
        "rows_appended": augmented.num_rows,
        "close_stats": close_stats,
    }


def _augment_for_scd2(arrow_source: pa.Table, now: datetime) -> pa.Table:
    """Add ``_valid_from`` / ``_valid_to`` / ``_is_current`` to *arrow_source*.

    Args:
        arrow_source: Source rows as a PyArrow Table.
        now: Wall-clock instant to stamp into ``_valid_from``.

    Returns:
        A new Arrow Table with the three SCD-2 columns appended at
        the end (key columns and existing fields are unchanged).
    """
    n = arrow_source.num_rows
    valid_from_col = pa.array([now] * n, type=pa.timestamp("us", tz="UTC"))
    valid_to_col = pa.array([None] * n, type=pa.timestamp("us", tz="UTC"))
    is_current_col = pa.array([True] * n, type=pa.bool_())
    augmented = arrow_source
    augmented = augmented.append_column(SCD2_VALID_FROM, valid_from_col)
    augmented = augmented.append_column(SCD2_VALID_TO, valid_to_col)
    augmented = augmented.append_column(SCD2_IS_CURRENT, is_current_col)
    return augmented
