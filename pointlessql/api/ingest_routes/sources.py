"""CRUD endpoints for IngestSource rows.

* ``GET /api/ingest/sources`` — list workspace-scoped sources.
* ``POST /api/ingest/sources`` — create a new source.
* ``GET /api/ingest/sources/{id}`` — fetch one (secrets redacted).
* ``PATCH /api/ingest/sources/{id}`` — partial update; secrets sent
  back as ``"***"`` are treated as no-ops.
* ``DELETE /api/ingest/sources/{id}`` — soft-delete by flipping
  ``is_active`` to ``False`` (preserves run history); hard delete is
  the admin-only path in :mod:`pointlessql.api.admin.ingest_sources`
  (Phase 82.5).

Workspace scoping comes from the resolved request workspace, not
the body — a user in workspace A cannot reach into workspace B by
hand-crafting the payload.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Body, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.api.ingest_routes._serializers import (
    merge_patch_secrets,
    serialize_source,
)
from pointlessql.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from pointlessql.models import IngestSource
from pointlessql.models.ingest import INGEST_SOURCE_KINDS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest", "sources"])


def _validate_create_body(body: dict[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    """Pull name/kind/config/secrets from the body with type checks.

    Args:
        body: JSON body from the POST request.

    Returns:
        ``(name, kind, config, secrets)`` tuple.

    Raises:
        ValidationError: When a required field is missing or kind is
            unknown.
    """
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValidationError("name is required.")
    if len(name) > 200:
        raise ValidationError("name must be at most 200 characters.")
    kind = str(body.get("kind") or "").strip()
    if kind not in INGEST_SOURCE_KINDS:
        raise ValidationError(
            f"kind must be one of {INGEST_SOURCE_KINDS}, got {kind!r}."
        )
    config_raw: object = body.get("config") or {}
    if not isinstance(config_raw, dict):
        raise ValidationError("config must be an object.")
    secrets_raw: object = body.get("secrets") or {}
    if not isinstance(secrets_raw, dict):
        raise ValidationError("secrets must be an object.")
    config: dict[str, Any] = {
        str(k): v for k, v in cast(dict[Any, Any], config_raw).items()
    }
    secrets: dict[str, Any] = {
        str(k): v for k, v in cast(dict[Any, Any], secrets_raw).items()
    }
    return name, kind, config, secrets


@router.get("/api/ingest/sources")
async def api_list_sources(request: Request) -> dict[str, Any]:
    """List ingest sources visible to the caller's workspace.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"sources": [{...}, ...]}`` sorted newest-first.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            select(IngestSource)
            .where(IngestSource.workspace_id == workspace_id)
            .order_by(IngestSource.created_at.desc())
        )
        rows = list(session.scalars(stmt).all())
        out = [serialize_source(r) for r in rows]
    return {"sources": out}


@router.post("/api/ingest/sources")
async def api_create_source(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create one ingest source under the caller's workspace.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``name``, ``kind``, ``config``, ``secrets``.

    Returns:
        ``{"source": {...}}`` for the freshly-created row.

    Raises:
        ConflictError: On duplicate ``(workspace_id, name)``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    name, kind, config, secrets = _validate_create_body(body)

    now = datetime.datetime.now(datetime.UTC)
    source = IngestSource(
        workspace_id=workspace_id,
        owner_user_id=int(user["id"]),
        name=name,
        kind=kind,
        config=json.dumps(config),
        secrets=json.dumps(secrets),
        table_mappings="[]",
        job_id=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    factory = request.app.state.session_factory
    with factory() as session:
        session.add(source)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ConflictError(
                f"A source named {name!r} already exists in this workspace.",
            ) from exc
        session.refresh(source)
        out = serialize_source(source)
    return {"source": out}


@router.get("/api/ingest/sources/{source_id}")
async def api_get_source(request: Request, source_id: int) -> dict[str, Any]:
    """Fetch one source by id.

    Args:
        request: Incoming FastAPI request.
        source_id: Primary key of the source.

    Returns:
        ``{"source": {...}}`` with secrets redacted.

    Raises:
        ResourceNotFoundError: When the source doesn't exist in this
            workspace.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")
        return {"source": serialize_source(row)}


@router.patch("/api/ingest/sources/{source_id}")
async def api_patch_source(
    request: Request,
    source_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Partial update.

    Mutable fields: ``name``, ``config``, ``secrets``, ``is_active``.
    Immutable: ``kind``, ``workspace_id``, ``owner_user_id`` — those
    are baked at create.

    Args:
        request: Incoming FastAPI request.
        source_id: Primary key.
        body: Patch dict.

    Returns:
        ``{"source": {...}}`` after the update.

    Raises:
        ValidationError: On invalid patch fields.
        ResourceNotFoundError: When the source doesn't exist.
        ConflictError: On duplicate ``(workspace_id, name)``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")
        if "name" in body:
            name = str(body.get("name") or "").strip()
            if not name or len(name) > 200:
                raise ValidationError("name must be 1-200 characters.")
            row.name = name
        if "config" in body:
            cfg = body["config"]
            if not isinstance(cfg, dict):
                raise ValidationError("config must be an object.")
            row.config = json.dumps(cfg)
        if "secrets" in body:
            patch_secrets_raw = body["secrets"]
            if patch_secrets_raw is not None and not isinstance(
                patch_secrets_raw, dict
            ):
                raise ValidationError("secrets must be an object.")
            patch_secrets: dict[str, Any] | None
            if patch_secrets_raw is None:
                patch_secrets = None
            else:
                patch_secrets = {
                    str(k): v
                    for k, v in cast(dict[Any, Any], patch_secrets_raw).items()
                }
            merged = merge_patch_secrets(row.secrets or "{}", patch_secrets)
            row.secrets = json.dumps(merged)
        if "is_active" in body:
            row.is_active = bool(body["is_active"])
        row.updated_at = datetime.datetime.now(datetime.UTC)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ConflictError(
                "A source with this name already exists in this workspace.",
            ) from exc
        session.refresh(row)
        return {"source": serialize_source(row)}


@router.delete("/api/ingest/sources/{source_id}")
async def api_delete_source(request: Request, source_id: int) -> dict[str, Any]:
    """Soft-delete by flipping ``is_active`` to false.

    Hard delete is reserved for the admin route (Phase 82.5).

    Args:
        request: Incoming FastAPI request.
        source_id: Primary key.

    Returns:
        ``{"deleted": True}`` on success.

    Raises:
        ResourceNotFoundError: When the source doesn't exist.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")
        row.is_active = False
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
    return {"deleted": True}
