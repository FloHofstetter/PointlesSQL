# pyright: reportPrivateUsage=false
"""``drop_table`` / ``update`` / ``delete`` — direct Delta DML routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit, effective_agent_run_id
from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.api.sql.write._helpers import _check_write_target
from pointlessql.exceptions import ValidationError
from pointlessql.types import TableFqn

router = APIRouter(tags=["pql-write"])


@router.post("/api/pql/drop_table", status_code=200, responses=STANDARD_ERROR_RESPONSES)
async def api_pql_drop_table(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Delete a Unity Catalog table — admin-only.

    Mirrors soyuz-catalog's
    ``DELETE /catalogs/{c}/schemas/{s}/tables/{t}`` route.  Wrapping
    it as ``POST /api/pql/drop_table`` keeps the agent's surface
    JSON-bodied (every other write tool POSTs JSON, so consistency
    matters more than REST verb purity here) and lets the
    :func:`require_admin` gate do the work — drops are destructive
    and not in the working-agent's privilege envelope.

    The Delta storage bytes underneath the catalog row are **not**
    removed by this route — that is soyuz's call, and the current
    soyuz behaviour is registry-only deletion.  An operator is still
    expected to clean up the storage directory manually if needed.

    Non-admin callers propagate the
    :class:`pointlessql.exceptions.AuthorizationError` raised by
    :func:`require_admin`; a target unknown to soyuz propagates the
    :class:`pointlessql.exceptions.CatalogNotFoundError` surfaced by
    the client call.

    Args:
        request: Incoming FastAPI request — must carry a cookie /
            api-key with admin role.
        body: JSON body with ``full_name`` (3-part UC name).

    Returns:
        ``{"target", "deleted": True}`` on success.

    Raises:
        ValidationError: When ``full_name`` is missing or malformed.
    """
    require_admin(request)

    full_name = (body or {}).get("full_name", "")
    if not isinstance(full_name, str) or not full_name.strip():
        raise ValidationError("full_name is required and must be a string.")
    catalog, schema_name, table_name = TableFqn.parse(full_name).parts()

    uc_client = get_uc_client(request)
    await uc_client.delete_table(catalog, schema_name, table_name)
    await audit(
        request,
        "pql.drop_table",
        f"table:{full_name}",
        {"deleted": True},
    )
    return {"target": full_name, "deleted": True}


@router.post("/api/pql/update", responses=STANDARD_ERROR_RESPONSES)
async def api_pql_update(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Apply ``UPDATE target SET ... WHERE ...`` against a Delta table.

    Mirrors :meth:`pointlessql.pql.pql.PQL.update` over HTTP.  The
    target must already exist; ``MODIFY`` privilege is enforced.
    The target check propagates
    :class:`pointlessql.exceptions.AuthorizationError` (principal
    lacks ``MODIFY``) and
    :class:`pointlessql.exceptions.CatalogNotFoundError` (target
    unknown) raised inside the shared write-target helper.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``target`` (3-part UC name),
            ``set_clause`` (mapping ``column_name -> SQL-expression-string``,
            non-empty), optional ``where`` (SQL WHERE clause string;
            ``None`` updates every row), and optional
            ``track_value_changes`` (boolean, opt-in CDF capture).

    Returns:
        ``{"target", "rows_affected", "stats"}`` where ``stats`` is the
        deltalake metrics dict.

    Raises:
        ValidationError: When required fields are missing or malformed.
    """
    target = (body or {}).get("target", "")
    set_clause_raw = (body or {}).get("set_clause", {})
    where_raw = (body or {}).get("where")
    track_value_changes = bool((body or {}).get("track_value_changes", False))

    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    if not isinstance(set_clause_raw, dict) or not set_clause_raw:
        raise ValidationError("set_clause must be a non-empty object.")
    set_clause: dict[str, str] = {}
    for key, value in set_clause_raw.items():  # type: ignore[reportUnknownVariableType]
        if not isinstance(key, str) or not key.strip():
            raise ValidationError("set_clause keys must be non-empty column-name strings.")
        if not isinstance(value, str):
            raise ValidationError(
                f"set_clause[{key!r}] must be a SQL-expression string.",
            )
        set_clause[key] = value
    where: str | None = None
    if where_raw is not None:
        if not isinstance(where_raw, str):
            raise ValidationError("where must be a string when provided.")
        where = where_raw

    await _check_write_target(request, target, must_exist=True)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql import write as _write_pkg

        pql = _write_pkg._build_pql(request, principal=email, agent_run_id=agent_run_id)
        return pql.update(
            target,
            set_clause=set_clause,
            where=where,
            track_value_changes=track_value_changes,
        )

    stats = await asyncio.to_thread(_run)
    rows_affected = stats.get("num_updated_rows")
    await audit(
        request,
        "pql.update",
        f"table:{target}",
        {
            "set_columns": sorted(set_clause.keys()),
            "where": where,
            "rows_affected": rows_affected,
        },
    )
    return {"target": target, "rows_affected": rows_affected, "stats": stats}


@router.post("/api/pql/delete", responses=STANDARD_ERROR_RESPONSES)
async def api_pql_delete(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Apply ``DELETE FROM target WHERE ...`` against a Delta table.

    Mirrors :meth:`pointlessql.pql.pql.PQL.delete` over HTTP.  ``where``
    omitted or ``None`` triggers a full-table delete; the SQL editor
    surface forces a confirmation modal in that case but
    the route itself does not refuse the call — Hermes-driven agents
    may legitimately need a full-table wipe.  The target check
    propagates :class:`pointlessql.exceptions.AuthorizationError`
    (principal lacks ``MODIFY``) and
    :class:`pointlessql.exceptions.CatalogNotFoundError` (target
    unknown) raised inside the shared write-target helper.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``target`` (3-part UC name) and optional
            ``where`` (SQL WHERE clause string).

    Returns:
        ``{"target", "rows_affected", "stats"}`` where ``stats`` is the
        deltalake metrics dict.

    Raises:
        ValidationError: When required fields are missing or malformed.
    """
    target = (body or {}).get("target", "")
    where_raw = (body or {}).get("where")

    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    where: str | None = None
    if where_raw is not None:
        if not isinstance(where_raw, str):
            raise ValidationError("where must be a string when provided.")
        where = where_raw

    await _check_write_target(request, target, must_exist=True)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql import write as _write_pkg

        pql = _write_pkg._build_pql(request, principal=email, agent_run_id=agent_run_id)
        return pql.delete(target, where=where)

    stats = await asyncio.to_thread(_run)
    rows_affected = stats.get("num_deleted_rows")
    await audit(
        request,
        "pql.delete",
        f"table:{target}",
        {"where": where, "rows_affected": rows_affected},
    )
    return {"target": target, "rows_affected": rows_affected, "stats": stats}
