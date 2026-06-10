# pyright: reportPrivateUsage=false
"""``POST /api/pql/autoload`` — lift Volume files into a Delta target."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit, effective_agent_run_id
from pointlessql.api.dependencies import effective_principal, get_user
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.api.sql.write._helpers import _check_write_target
from pointlessql.exceptions import ValidationError

router = APIRouter(tags=["pql-write"])


@router.post("/api/pql/autoload", responses=STANDARD_ERROR_RESPONSES)
async def api_pql_autoload(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Lift files from a Volume directory into a Delta target.

    Mirrors :meth:`pointlessql.pql.pql.PQL.autoload` over HTTP.  Used
    by the ``pql_autoload`` Hermes tool so a working agent can fold a
    raw-drop directory into bronze without leaving the chat surface.

    Privilege model: when the target already exists the principal
    needs ``MODIFY`` on it; when the target is missing the route
    accepts ``USE SCHEMA`` on the parent schema, mirroring how the
    primitive itself bootstraps a fresh Delta log under the parent's
    ``storage_root`` on the first successful append.  A principal
    lacking those privileges propagates the
    :class:`pointlessql.exceptions.AuthorizationError` raised inside
    the privilege check.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``source_path``, ``target``,
            ``source_system`` (optional), and ``file_format`` (optional,
            default ``"auto"``).

    Returns:
        ``{"target", "files_scanned", "files_ingested", "files_skipped",
        "rows_ingested"}`` — the dict :meth:`PQL.autoload` returns.

    Raises:
        ValidationError: When required fields are missing or malformed.
    """
    source_path = (body or {}).get("source_path", "")
    target = (body or {}).get("target", "")
    source_system = (body or {}).get("source_system", "")
    file_format = (body or {}).get("file_format", "auto")

    if not isinstance(source_path, str) or not source_path.strip():
        raise ValidationError("source_path is required and must be a string.")
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target is required and must be a string.")
    if not isinstance(source_system, str):
        raise ValidationError("source_system must be a string when set.")
    if file_format not in ("auto", "parquet", "csv", "json"):
        raise ValidationError(
            "file_format must be one of 'auto', 'parquet', 'csv', 'json'.",
        )

    await _check_write_target(request, target, must_exist=False)

    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    agent_run_id = effective_agent_run_id(request)

    def _run() -> dict[str, Any]:
        # Lookup via the write package so monkeypatched ``_build_pql``
        # in tests is picked up at call time (the package re-export
        # binding wins over the direct submodule import).
        from pointlessql.api.sql import write as _write_pkg

        pql = _write_pkg._build_pql(request, principal=email, agent_run_id=agent_run_id)
        return pql.autoload(
            source_path=source_path,
            target=target,
            source_system=source_system,
            file_format=file_format,
        )

    result = await asyncio.to_thread(_run)
    await audit(
        request,
        "pql.autoload",
        f"table:{target}",
        {
            "source_path": source_path,
            "files_ingested": result.get("files_ingested"),
            "rows_ingested": result.get("rows_ingested"),
        },
    )
    return result
