"""Time-travel value-read helpers for the PQL surface.

Module-level entry points for :meth:`PQL.table_at_version` /
:meth:`PQL.table_at_timestamp`.

Time-travel reads wrap the existing
:class:`deltalake.DeltaTable.load_as_version` /
``load_as_timestamp`` pathways with PointlesSQL's UC-resolution +
audit conventions:

* Resolve the three-part UC name to a storage location through the
  same generated client + facade ``read_table`` already uses.
* Emit a ``query_history`` row with ``read_kind =
  "pql_table_at_version"`` so the read shows up in ``/queries``
  and the run-detail Queries tab.
* Return the engine's native frame type, identical shape to
  :meth:`PQL.table`.

The function does not validate the version exists on the Delta log
in advance — ``deltalake`` raises a clear error for missing
versions, and the caller's error path already records that as a
failed read in ``query_history``.
"""

from __future__ import annotations

import datetime
import os
import time
from typing import TYPE_CHECKING, Any

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._parsing import parse_full_name
from pointlessql.services.read_audit import record_read

if TYPE_CHECKING:
    pass


def _resolve_storage_location(client: Client, full_name: str, unreachable_msg: str) -> str:
    """Return the storage location for *full_name* via the generated client.

    Args:
        client: A configured ``soyuz_catalog_client.Client``.
        full_name: Three-part name.
        unreachable_msg: Pre-rendered error string for transport
            failures.

    Returns:
        Storage location URI.

    Raises:
        ValidationError: If *full_name* is not three parts.
        CatalogNotFoundError: If the table does not exist or has no
            ``storage_location``.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
    """  # noqa: DOC503
    parse_full_name(full_name)
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        raise CatalogNotFoundError(f"Table not found: {full_name!r}")
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        raise CatalogNotFoundError(f"Table {full_name!r} has no storage_location")
    return location


def read_table_at_version(
    *,
    client: Client,
    full_name: str,
    version: int,
    unreachable_msg: str,
) -> Any:
    """Read *full_name* as it was at Delta version *N*.

    Args:
        client: A configured ``soyuz_catalog_client.Client``.
        full_name: Three-part name.
        version: Target Delta version.  Must be a non-negative
            integer; ``0`` is the initial commit.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        A pandas DataFrame.  Time-travel reads always materialise
        through pandas — the engine abstraction in :mod:`engine`
        targets current-version reads only and adding per-engine
        ``load_as_version`` would surface mostly identical code.

    Raises:
        ValidationError: If *full_name* is not three parts.
        CatalogNotFoundError: If the table does not exist.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
    """  # noqa: DOC503
    location = _resolve_storage_location(client, full_name, unreachable_msg)

    started_at = datetime.datetime.now(datetime.UTC)
    perf_start = time.perf_counter()
    try:
        import deltalake

        dt = deltalake.DeltaTable(location)
        dt.load_as_version(version)
        result = dt.to_pandas()
    except Exception as exc:
        finished_at = datetime.datetime.now(datetime.UTC)
        duration_ms = int((time.perf_counter() - perf_start) * 1000)
        _record(
            full_name=full_name,
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            row_count=None,
            duration_ms=duration_ms,
            error_message=f"version={version}: {exc!r}",
        )
        raise
    finished_at = datetime.datetime.now(datetime.UTC)
    duration_ms = int((time.perf_counter() - perf_start) * 1000)
    _record(
        full_name=full_name,
        started_at=started_at,
        finished_at=finished_at,
        status="succeeded",
        row_count=int(result.shape[0]) if hasattr(result, "shape") else None,
        duration_ms=duration_ms,
        error_message=None,
    )
    return result


def read_table_at_timestamp(
    *,
    client: Client,
    full_name: str,
    when: datetime.datetime,
    unreachable_msg: str,
) -> Any:
    """Read *full_name* as it was at the wall-clock instant *when*.

    Resolves to a Delta version via
    :class:`deltalake.DeltaTable.load_as_version` (the public API
    accepts a datetime alongside int).

    Args:
        client: A configured ``soyuz_catalog_client.Client``.
        full_name: Three-part name.
        when: Wall-clock timestamp.  Must be timezone-aware.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        A pandas DataFrame.

    Raises:
        ValidationError: If *full_name* is not three parts or the
            timestamp is naive.
        CatalogNotFoundError: If the table does not exist.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
    """  # noqa: DOC503
    if when.tzinfo is None:
        from pointlessql.exceptions import ValidationError

        raise ValidationError("table_at_timestamp requires a timezone-aware datetime")

    location = _resolve_storage_location(client, full_name, unreachable_msg)

    started_at = datetime.datetime.now(datetime.UTC)
    perf_start = time.perf_counter()
    try:
        import deltalake

        dt = deltalake.DeltaTable(location)
        dt.load_as_version(when)
        result = dt.to_pandas()
    except Exception as exc:
        finished_at = datetime.datetime.now(datetime.UTC)
        duration_ms = int((time.perf_counter() - perf_start) * 1000)
        _record(
            full_name=full_name,
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            row_count=None,
            duration_ms=duration_ms,
            error_message=f"timestamp={when.isoformat()}: {exc!r}",
        )
        raise
    finished_at = datetime.datetime.now(datetime.UTC)
    duration_ms = int((time.perf_counter() - perf_start) * 1000)
    _record(
        full_name=full_name,
        started_at=started_at,
        finished_at=finished_at,
        status="succeeded",
        row_count=int(result.shape[0]) if hasattr(result, "shape") else None,
        duration_ms=duration_ms,
        error_message=None,
    )
    return result


def _record(
    *,
    full_name: str,
    started_at: datetime.datetime,
    finished_at: datetime.datetime,
    status: str,
    row_count: int | None,
    duration_ms: int | None,
    error_message: str | None,
) -> None:
    """Forward a query_history row with ``read_kind="pql_table_at_version"``.

    Lazy-load the session factory so the helper stays usable in
    interactive PQL sessions where no FastAPI lifespan is bound.
    The audit row is best-effort — failures are silenced inside
    :func:`pointlessql.services.read_audit.record_read`.
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
        read_kind="pql_table_at_version",
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        row_count=row_count,
        duration_ms=duration_ms,
        error_message=error_message,
    )
