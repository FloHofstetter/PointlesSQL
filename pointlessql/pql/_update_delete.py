"""Helpers for :meth:`PQL.update` and :meth:`PQL.delete`.

Thin wrappers around :meth:`deltalake.DeltaTable.update` and
:meth:`deltalake.DeltaTable.delete` that emit the same shape of
``agent_run_operations`` row as :func:`pointlessql.pql._write.write_table`
and :func:`pointlessql.pql._merge.merge_table`, so SQL-editor
DML executes through the dispatcher land in the audit trail with
no special casing downstream.

Both functions accept a SQL-string ``predicate`` (the dialect is
delta-rs / DataFusion, which is sqlglot-compatible enough that
the editor can pass the WHERE clause verbatim).  No PyArrow
expression translation is needed.

When ``track_value_changes=True`` on :func:`update_table`, the
helper reads the Delta Change Data Feed for the commit range and
records one ``lineage_value_changes`` row per actually-different
cell — exact mirror of the merge path's per-cell capture.  CDF
must already be enabled on the table; first writes via
:func:`pointlessql.pql._write.write_table` enable it
automatically.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.enums import OpName
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.identifiers import RunId
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._write import safe_delta_version
from pointlessql.services.agent_runs import operation_context

logger = logging.getLogger(__name__)


def update_table(
    *,
    client: Client,
    full_name: str,
    set_clause: dict[str, str],
    where: str | None,
    unreachable_msg: str,
    agent_run_id: str | None = None,
    track_value_changes: bool = False,
) -> dict[str, Any]:
    """Apply ``UPDATE target SET ... WHERE ...`` and emit the audit row.

    Args:
        client: Configured ``soyuz_catalog_client.Client`` (used
            only to resolve the table's storage location).
        full_name: Three-part name ``"catalog.schema.table"``.
        set_clause: Mapping ``column_name -> SQL-expression-string``.
            Passed straight to :meth:`deltalake.DeltaTable.update`'s
            ``updates`` kwarg.
        where: SQL WHERE clause as a string, or ``None`` for an
            unconditional update of every row.
        unreachable_msg: Pre-rendered "cannot reach catalog" message
            surfaced when soyuz HTTP fails.
        agent_run_id: When set, the call emits one
            ``agent_run_operations`` row.  ``None`` keeps the
            interactive path silent.
        track_value_changes: When ``True``, read the Change Data
            Feed for the update's commit range and record one
            ``lineage_value_changes`` row per actually-different
            cell.  Mirrors :meth:`PQL.merge`'s opt-in.  Silently
            no-ops on the first write where CDF was just enabled
            (no preimage stream yet).

    Returns:
        The deltalake metrics dict (``num_added_files``,
        ``num_removed_files``, ``num_updated_rows``,
        ``num_copied_rows``, ``execution_time_ms``,
        ``scan_time_ms``).

    Raises:
        ValidationError: If *full_name* does not have exactly three parts.
        CatalogNotFoundError: If the table does not exist in
            soyuz-catalog (UPDATE on missing table is invalid; use
            :meth:`PQL.write_table` to bootstrap).
        CatalogUnavailableError: If soyuz-catalog is unreachable.
        AuditUnavailableError: If *agent_run_id* is set and the
            ``agent_run_operations`` row cannot be persisted.
    """  # noqa: DOC503
    if not set_clause:
        msg = "pql.update: set_clause must not be empty."
        raise ValueError(msg)

    parse_full_name(full_name)
    location = _resolve_existing_location(client, full_name, unreachable_msg)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    extra_params: dict[str, Any] = {
        "set_columns": sorted(set_clause.keys()),
        "where": where,
    }

    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.UPDATE,
        params={"full_name": full_name, **extra_params},
        target_table=full_name,
    ) as recorder:
        if agent_run_id is not None:
            recorder.delta_version_before = safe_delta_version(location)
            recorder.extra_params = extra_params

        import deltalake

        dt = deltalake.DeltaTable(location)
        try:
            stats = dt.update(updates=set_clause, predicate=where)
        except Exception:
            # delta-rs failures (predicate parse error, type
            # mismatch, schema drift) propagate up so the dispatcher
            # surfaces them to the editor with a structured envelope.
            raise

        if agent_run_id is not None:
            recorder.delta_version_after = safe_delta_version(location)
            recorder.rows_affected = _coerce_int(stats.get("num_updated_rows"))
            if track_value_changes:
                from pointlessql.pql import _merge as _merge_module

                recorder.pending_value_changes = _merge_module._capture_value_changes(  # pyright: ignore[reportPrivateUsage]
                    target_location=location,
                    target=full_name,
                    version_before=recorder.delta_version_before,
                    version_after=recorder.delta_version_after,
                )

        return dict(stats)


def delete_table_rows(
    *,
    client: Client,
    full_name: str,
    where: str | None,
    unreachable_msg: str,
    agent_run_id: str | None = None,
) -> dict[str, Any]:
    """Apply ``DELETE FROM target WHERE ...`` and emit the audit row.

    A ``where`` of ``None`` deletes every row in the table.  The
    SQL-editor surface forces a confirmation modal for that case
    (Phase 63.7); the primitive itself does not refuse the call —
    Hermes-driven agents may legitimately need a full-table wipe.

    Args:
        client: Configured ``soyuz_catalog_client.Client`` (used
            only to resolve the table's storage location).
        full_name: Three-part name ``"catalog.schema.table"``.
        where: SQL WHERE clause as a string, or ``None`` for a
            full-table delete.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.
        agent_run_id: When set, the call emits one
            ``agent_run_operations`` row.

    Returns:
        The deltalake metrics dict (``num_added_files``,
        ``num_removed_files``, ``num_deleted_rows``,
        ``num_copied_rows``, ``execution_time_ms``,
        ``scan_time_ms``).

    Raises:
        ValidationError: If *full_name* does not have exactly three parts.
        CatalogNotFoundError: If the table does not exist.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
        AuditUnavailableError: If the audit row cannot be persisted.
    """  # noqa: DOC502,DOC503 — exceptions propagate from helpers
    parse_full_name(full_name)
    location = _resolve_existing_location(client, full_name, unreachable_msg)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if agent_run_id else None

    extra_params: dict[str, Any] = {"where": where}

    with operation_context(
        factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.DELETE,
        params={"full_name": full_name, **extra_params},
        target_table=full_name,
    ) as recorder:
        if agent_run_id is not None:
            recorder.delta_version_before = safe_delta_version(location)
            recorder.extra_params = extra_params

        import deltalake

        dt = deltalake.DeltaTable(location)
        stats = dt.delete(predicate=where)

        if agent_run_id is not None:
            recorder.delta_version_after = safe_delta_version(location)
            recorder.rows_affected = _coerce_int(stats.get("num_deleted_rows"))

        return dict(stats)


def _resolve_existing_location(
    client: Client, full_name: str, unreachable_msg: str
) -> str:
    """Return the Delta storage URI for an existing table.

    Args:
        client: Configured catalog client.
        full_name: Three-part UC name.
        unreachable_msg: Friendly error to surface on transport failures.

    Returns:
        The table's ``storage_location`` from soyuz-catalog.

    Raises:
        CatalogNotFoundError: When the table is unknown to soyuz.
        CatalogUnavailableError: When the catalog HTTP endpoint
            cannot be reached.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc

    if not isinstance(response, TableInfo):
        msg = f"Table not found: {full_name!r}"
        raise CatalogNotFoundError(msg)

    location = response.storage_location
    if isinstance(location, Unset) or not location:
        msg = f"Table {full_name!r} has no storage_location."
        raise CatalogNotFoundError(msg)
    return location


def _coerce_int(value: Any) -> int | None:
    """Best-effort coerce a deltalake-stats value to ``int``.

    Args:
        value: Raw value from a deltalake metrics dict.  Usually
            int but occasionally str.

    Returns:
        Int when conversion succeeds, ``None`` otherwise (so the
        recorder leaves ``rows_affected`` NULL rather than crashing
        on a stats-shape change).
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
