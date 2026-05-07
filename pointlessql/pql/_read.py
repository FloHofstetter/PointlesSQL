"""Module-level helper for :meth:`PQL.table`."""

from __future__ import annotations

import datetime
import os
import time
from typing import Any

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.enums import QueryStatus, ReadKind
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine
from pointlessql.services.read_audit import record_read


def read_table(
    *,
    client: Client,
    engine: Engine,
    full_name: str,
    unreachable_msg: str,
) -> Any:
    """Read a Delta table registered in Unity Catalog.

    On success a ``query_history`` row with ``read_kind="pql_table"``
    is written via :func:`pointlessql.services.read_audit.record_read`
    so the DSGVO read-audit gap is closed for this
    bypass path.  The audit insert is best-effort — it runs only
    when a session factory is available and never raises into the
    read path.

    Args:
        client: A configured ``soyuz_catalog_client.Client`` instance.
        engine: The engine to materialise the Delta scan with.
        full_name: Three-part name ``"catalog.schema.table"``.
        unreachable_msg: Pre-rendered "cannot reach catalog" message
            so the caller controls how the URL appears (it lives on
            ``client._base_url`` which is private).

    Returns:
        The table contents in the engine's native frame type
        (e.g. pandas DataFrame, DuckDB relation).

    Raises:
        ValidationError: If *full_name* does not have exactly three parts.
        CatalogNotFoundError: If the table is not found or has no
            ``storage_location``.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
    """  # noqa: DOC503
    parse_full_name(full_name)  # validates format
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        msg = f"Table not found: {full_name!r}"
        raise CatalogNotFoundError(msg)

    location = response.storage_location
    if isinstance(location, Unset) or not location:
        msg = f"Table {full_name!r} has no storage_location"
        raise CatalogNotFoundError(msg)

    started_at = datetime.datetime.now(datetime.UTC)
    perf_start = time.perf_counter()
    try:
        result = engine.read(location)
    except Exception as exc:
        finished_at = datetime.datetime.now(datetime.UTC)
        duration_ms = int((time.perf_counter() - perf_start) * 1000)
        _record(
            full_name=full_name,
            started_at=started_at,
            finished_at=finished_at,
            status=QueryStatus.FAILED,
            row_count=None,
            duration_ms=duration_ms,
            error_message=repr(exc),
        )
        raise
    finished_at = datetime.datetime.now(datetime.UTC)
    duration_ms = int((time.perf_counter() - perf_start) * 1000)
    _record(
        full_name=full_name,
        started_at=started_at,
        finished_at=finished_at,
        status=QueryStatus.SUCCEEDED,
        row_count=None,
        duration_ms=duration_ms,
        error_message=None,
    )
    return result


def _record(
    *,
    full_name: str,
    started_at: datetime.datetime,
    finished_at: datetime.datetime,
    status: QueryStatus,
    row_count: int | None,
    duration_ms: int | None,
    error_message: str | None,
) -> None:
    """Look up the session factory lazily and forward to :func:`record_read`.

    Lazy import + try/except keeps :func:`read_table` decoupled from
    the metadata-DB lifecycle.  When the factory is unbound (pure
    interactive PQL with no FastAPI lifespan and no run-id env), the
    audit row is silently skipped — see
    :mod:`pointlessql.services.read_audit` for the contract.
    """
    if not os.environ.get("POINTLESSQL_AGENT_RUN_ID"):
        return
    try:
        from pointlessql.db import get_session_factory

        factory = get_session_factory()
    except Exception:  # noqa: BLE001 — DB might not be initialised
        # bare-broad-ok: read-audit lazy-init may raise pre-startup
        factory = None
    record_read(
        factory,
        table_fqn=full_name,
        read_kind=ReadKind.PQL_TABLE,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        row_count=row_count,
        duration_ms=duration_ms,
        error_message=error_message,
    )
