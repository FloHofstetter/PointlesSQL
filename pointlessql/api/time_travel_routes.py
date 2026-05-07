"""Time-travel value-query routes.

Three endpoints surface the version arithmetic
:class:`pointlessql.models.AgentRunOperation.delta_version_after`
already captures:

* ``GET /api/tables/{full_name}/versions`` — list of historical Delta
  versions for *full_name*, joined against
  :class:`AgentRunOperation` so each version names the originating
  run when the write came from PointlesSQL.
* ``GET /api/tables/{full_name}/preview-at-version`` — paged rows
  at a chosen version.  Wraps
  :class:`deltalake.DeltaTable.load_as_version`.
* ``GET /api/lineage/row-at-version`` — single-row state at a
  chosen version.  Admin-only, since arbitrary historic reads
  bypass the row-trace's "this row was here at all" gate.

All three sit at read-only routes; no schema changes.  The
``preview-at-version`` route returns the engine's pandas frame
projected to JSON-safe dicts, matching the existing table-detail
preview shape.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import deltalake
from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.exceptions import (
    EngineError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models import AgentRunOperation
from pointlessql.services.authorization import SELECT, check_privilege

logger = logging.getLogger(__name__)

router = APIRouter(tags=["time-travel"])

_MAX_PREVIEW_ROWS = 200


async def _resolve_storage(request: Request, full_name: str) -> str:
    """Resolve *full_name* to a storage location with the same SELECT gate.

    Args:
        request: Incoming FastAPI request (for the user + UC client).
        full_name: Three-part UC name.

    Returns:
        The storage location URI.

    Raises:
        ValidationError: 422 when ``full_name`` isn't 3-part.
        ResourceNotFoundError: 404 when the table has no
            ``storage_location`` registered.

    Note:
        ``CatalogNotFoundError`` (404) / ``CatalogUnavailableError``
        (502) propagate from :meth:`UnityCatalogClient.get_table`;
        ``AuthorizationError`` (403) propagates from
        :func:`check_privilege`.
    """
    user = get_user(request)
    uc = get_uc_client(request)
    parts = full_name.split(".")
    if len(parts) != 3:
        raise ValidationError(
            f"full_name must be three parts: 'catalog.schema.table', got {full_name!r}"
        )
    cat, sch, tbl = parts
    # CatalogUnavailableError / CatalogNotFoundError flow through the
    # centralised handler (502 / 404) — no inline translation needed.
    table_info = await uc.get_table(cat, sch, tbl)
    storage = table_info.get("storage_location") if isinstance(table_info, dict) else None
    if not storage or not isinstance(storage, str):
        raise ResourceNotFoundError(f"Table {full_name!r} has no storage_location")
    await check_privilege(uc, user["email"], bool(user.get("is_admin")), "table", full_name, SELECT)
    return storage


@router.get("/api/tables/{full_name}/versions")
async def api_table_versions(request: Request, full_name: str) -> dict[str, Any]:
    """Return the history of Delta versions for *full_name*.

    Each entry includes ``{version, timestamp, operation, run_id}``.
    ``run_id`` is populated from
    :class:`AgentRunOperation.delta_version_after` when the write
    originated in PointlesSQL; ``None`` for external writes (Sprint
    14.3 already detects those).

    Args:
        request: Incoming FastAPI request.
        full_name: Three-part UC name.

    Returns:
        ``{full_name, versions: [{version, timestamp, operation,
        run_id}]}``.

    Raises:
        EngineError: 500 when the Delta history read fails (table
            absent / corrupt).  4xx / 5xx errors from
            :func:`_resolve_storage` propagate.
    """
    storage = await _resolve_storage(request, full_name)
    try:
        table = deltalake.DeltaTable(storage)
        history = table.history()
    except Exception as exc:  # noqa: BLE001 — Delta absent / corrupt
        raise EngineError(f"Could not read Delta history: {exc}") from exc

    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(AgentRunOperation).where(
                    AgentRunOperation.target_table == full_name,
                    AgentRunOperation.delta_version_after.is_not(None),
                )
            ).all()
        )
        version_to_run: dict[int, str] = {
            int(op.delta_version_after): op.agent_run_id
            for op in rows
            if op.delta_version_after is not None
        }

    versions: list[dict[str, Any]] = []
    for entry in history:
        version_raw = entry.get("version") if isinstance(entry, dict) else None
        if not isinstance(version_raw, int):
            continue
        ts = entry.get("timestamp")
        if isinstance(ts, int | float):
            timestamp = datetime.datetime.fromtimestamp(ts / 1000.0, tz=datetime.UTC).isoformat()
        elif isinstance(ts, str):
            timestamp = ts
        else:
            timestamp = None
        versions.append(
            {
                "version": version_raw,
                "timestamp": timestamp,
                "operation": entry.get("operation"),
                "run_id": version_to_run.get(version_raw),
            }
        )
    versions.sort(key=lambda r: r["version"], reverse=True)
    return {"full_name": full_name, "versions": versions}


def _frame_rows_to_dicts(frame: Any, limit: int) -> tuple[list[dict[str, Any]], int]:
    """Convert a pandas frame slice to JSON-safe dicts + total count.

    Args:
        frame: pandas DataFrame.
        limit: Caller-bound row cap.

    Returns:
        ``(rows, total)`` — ``rows`` capped at ``limit``, ``total``
        is ``len(frame)`` before slicing.
    """
    total = int(frame.shape[0])
    head = frame.head(limit)
    rows: list[dict[str, Any]] = []
    for raw in head.to_dict(orient="records"):
        normalised: dict[str, Any] = {}
        for key, value in raw.items():
            if isinstance(value, datetime.datetime):
                normalised[str(key)] = value.isoformat()
            elif isinstance(value, datetime.date):
                normalised[str(key)] = value.isoformat()
            elif hasattr(value, "item"):
                try:
                    normalised[str(key)] = value.item()
                except Exception:  # noqa: BLE001 — non-numpy types fall through
                    # bare-broad-ok: ``.item()`` may raise on non-scalar; str() is fallback
                    normalised[str(key)] = str(value)
            else:
                normalised[str(key)] = value
        rows.append(normalised)
    return rows, total


@router.get("/api/tables/{full_name}/preview-at-version")
async def api_table_preview_at_version(
    request: Request,
    full_name: str,
    version: int = Query(..., ge=0),
    limit: int = Query(50, ge=1, le=_MAX_PREVIEW_ROWS),
) -> dict[str, Any]:
    """Preview the table at a chosen historical Delta version.

    Args:
        request: Incoming FastAPI request.
        full_name: Three-part UC name.
        version: Target Delta version.
        limit: Row cap (default 50, max 200).

    Returns:
        ``{full_name, version, columns, rows, total}``.

    Raises:
        ValidationError: 422 when the Delta load fails (version
            absent / table corrupt).  4xx / 5xx errors from
            :func:`_resolve_storage` propagate.
    """
    from pointlessql.api.catalog_routes import humanize_preview_error

    storage = await _resolve_storage(request, full_name)
    try:
        table = deltalake.DeltaTable(storage)
        table.load_as_version(version)
        frame = table.to_pandas()
    except Exception as exc:  # noqa: BLE001 — Delta absent / version invalid
        detail, _kind = humanize_preview_error(exc)
        raise ValidationError(f"Could not load v{version}: {detail}") from exc

    rows, total = _frame_rows_to_dicts(frame, limit)
    return {
        "full_name": full_name,
        "version": version,
        "columns": [str(c) for c in frame.columns.tolist()],
        "rows": rows,
        "total": total,
    }


@router.get("/api/lineage/row-at-version")
async def api_row_at_version(
    request: Request,
    table: str = Query(..., description="Three-part UC name"),
    row_id: str = Query(..., description="``_lineage_row_id`` of the row"),
    version: int = Query(..., ge=0),
) -> dict[str, Any]:
    """Return the single-row state of *table* at *version* matching *row_id*.

    Admin-only — arbitrary historic reads bypass the per-row trace's
    "this row was here" implicit existence check, and a row's
    historical values can carry PII the row-trace masks at
    render-time.   redaction still applies on the API
    boundary; admins see cleartext, non-admins see the masked
    rendition.

    Args:
        request: Incoming FastAPI request.
        table: Three-part UC name.
        row_id: ``_lineage_row_id`` of the target row.
        version: Target Delta version.

    Returns:
        ``{table, version, row_id, found, row}``.

    Raises:
        ValidationError: 422 when the Delta load fails (version
            absent / table corrupt).  ``AuthorizationError`` (403)
            propagates from :func:`require_admin`; 4xx / 5xx errors
            from :func:`_resolve_storage` propagate.
    """
    require_admin(request)
    storage = await _resolve_storage(request, table)
    try:
        dt = deltalake.DeltaTable(storage)
        dt.load_as_version(version)
        frame = dt.to_pandas()
    except Exception as exc:  # noqa: BLE001 — Delta absent / version invalid
        raise ValidationError(f"Could not load v{version}: {exc}") from exc

    if "_lineage_row_id" not in frame.columns:
        return {
            "table": table,
            "version": version,
            "row_id": row_id,
            "found": False,
            "row": None,
            "note": "Table has no _lineage_row_id column at this version",
        }
    matching = frame.loc[frame["_lineage_row_id"] == row_id]
    if matching.empty:
        return {
            "table": table,
            "version": version,
            "row_id": row_id,
            "found": False,
            "row": None,
        }
    rows, _total = _frame_rows_to_dicts(matching, limit=1)
    return {
        "table": table,
        "version": version,
        "row_id": row_id,
        "found": True,
        "row": rows[0],
    }
