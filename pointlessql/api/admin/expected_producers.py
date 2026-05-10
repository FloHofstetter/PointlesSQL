"""Admin CRUD + freshness-status endpoints for expected upstream producers.

Phase 40 Sprint 40.4: registers ``(target_table, producer,
max_silence_minutes)`` triples in ``expected_lineage_inbound`` and
exposes a freshness-status JSON endpoint that drives the table-detail
"Expected upstream" widget.

Workspace scoping comes from the resolved request workspace, not
the body — admins working in workspace A cannot register
expectations against workspace B by hand-crafting the payload.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import ExpectedLineageInbound
from pointlessql.services.lineage import freshness as freshness_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin", "expected-producers"])


def _serialize(row: ExpectedLineageInbound) -> dict[str, Any]:
    """Project a registry row into a JSON-safe dict."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "target_table_full_name": row.target_table_full_name,
        "producer": row.producer,
        "max_silence_minutes": row.max_silence_minutes,
        "is_active": bool(row.is_active),
        "last_alerted_at": row.last_alerted_at.isoformat() if row.last_alerted_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_status(row: dict[str, Any]) -> dict[str, Any]:
    """Project a freshness-compute row into a JSON-safe dict."""
    last_seen = row.get("last_seen_at")
    last_alerted = row.get("last_alerted_at")
    return {
        "id": row.get("id"),
        "target_table_full_name": row.get("target_table_full_name"),
        "producer": row.get("producer"),
        "max_silence_minutes": row.get("max_silence_minutes"),
        "is_active": bool(row.get("is_active", True)),
        "status": row.get("status"),
        "last_seen_at": last_seen.isoformat() if last_seen else None,
        "stale_minutes": row.get("stale_minutes"),
        "last_alerted_at": last_alerted.isoformat() if last_alerted else None,
    }


@router.get("/api/admin/expected-producers")
async def api_admin_list_expected_producers(
    request: Request, only_active: bool = False
) -> dict[str, Any]:
    """List registered upstream-producer expectations for this workspace.

    Args:
        request: Incoming FastAPI request.
        only_active: When True, omits ``is_active=False`` rows.

    Returns:
        ``{"expectations": [{...}, ...]}`` ordered by ``created_at DESC``.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(ExpectedLineageInbound).where(
            ExpectedLineageInbound.workspace_id == workspace_id
        )
        if only_active:
            stmt = stmt.where(ExpectedLineageInbound.is_active.is_(True))
        rows = list(session.scalars(stmt.order_by(ExpectedLineageInbound.created_at.desc())).all())
        out = [_serialize(r) for r in rows]
    return {"expectations": out}


@router.post("/api/admin/expected-producers")
async def api_admin_create_expected_producer(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Register one ``(table, producer, max_silence_minutes)`` expectation.

    Args:
        request: Incoming FastAPI request.
        body: ``{target_table_full_name: str, producer: str,
            max_silence_minutes: int, is_active?: bool}``.

    Returns:
        The created row, serialized.

    Raises:
        ValidationError: When required fields are missing / invalid,
            or when the triple is already registered.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    target = body.get("target_table_full_name")
    producer = body.get("producer")
    max_silence = body.get("max_silence_minutes")
    is_active = bool(body.get("is_active", True))
    if not isinstance(target, str) or not target.strip():
        raise ValidationError("target_table_full_name must be a non-empty string")
    if not isinstance(producer, str) or not producer.strip():
        raise ValidationError("producer must be a non-empty string")
    if not isinstance(max_silence, int) or max_silence <= 0:
        raise ValidationError("max_silence_minutes must be a positive integer")
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = ExpectedLineageInbound(
            workspace_id=workspace_id,
            target_table_full_name=target.strip(),
            producer=producer.strip(),
            max_silence_minutes=max_silence,
            is_active=is_active,
            created_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValidationError(
                "expectation for this (target_table, producer) already exists"
            ) from exc
        session.refresh(row)
        out = _serialize(row)
    await audit(
        request,
        "expected_producer.created",
        f"expected_producer:{producer}@{target}",
        {"max_silence_minutes": max_silence, "is_active": is_active},
    )
    return out


@router.post("/api/admin/expected-producers/{expectation_id}/toggle")
async def api_admin_toggle_expected_producer(
    request: Request, expectation_id: int
) -> dict[str, Any]:
    """Flip the ``is_active`` flag on one expectation row.

    Args:
        request: Incoming FastAPI request.
        expectation_id: ``ExpectedLineageInbound.id`` to toggle.

    Returns:
        The updated row, serialized.

    Raises:
        CatalogNotFoundError: When the row does not exist or belongs
            to a different workspace.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(ExpectedLineageInbound, expectation_id)
        if row is None or row.workspace_id != workspace_id:
            raise CatalogNotFoundError(f"expectation {expectation_id} not found")
        row.is_active = not bool(row.is_active)
        session.commit()
        session.refresh(row)
        out = _serialize(row)
    await audit(
        request,
        "expected_producer.toggled",
        f"expected_producer:{out['producer']}@{out['target_table_full_name']}",
        {"is_active": out["is_active"]},
    )
    return out


@router.delete("/api/admin/expected-producers/{expectation_id}")
async def api_admin_delete_expected_producer(
    request: Request, expectation_id: int
) -> dict[str, Any]:
    """Delete one expectation row.

    Args:
        request: Incoming FastAPI request.
        expectation_id: ``ExpectedLineageInbound.id`` to delete.

    Returns:
        ``{"id": ..., "deleted": True}``.

    Raises:
        CatalogNotFoundError: When the row does not exist or belongs
            to a different workspace.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(ExpectedLineageInbound, expectation_id)
        if row is None or row.workspace_id != workspace_id:
            raise CatalogNotFoundError(f"expectation {expectation_id} not found")
        target = row.target_table_full_name
        producer = row.producer
        session.delete(row)
        session.commit()
    await audit(
        request,
        "expected_producer.deleted",
        f"expected_producer:{producer}@{target}",
    )
    return {"id": expectation_id, "deleted": True}


@router.get("/api/admin/expected-producers/freshness")
async def api_admin_expected_producers_freshness(
    request: Request,
    target_table_full_name: str | None = None,
    only_active: bool = True,
) -> dict[str, Any]:
    """Return per-expectation freshness verdicts in this workspace.

    Args:
        request: Incoming FastAPI request.
        target_table_full_name: When supplied, restricts the report
            to one table's expectations.
        only_active: When True (default), omits paused expectations.

    Returns:
        ``{"now": <iso>, "rows": [{...}, ...]}`` — the timestamp
        anchors the freshness compute so a stale-snapshot UI knows
        when "now" was.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        rows = freshness_service.compute_freshness(
            session,
            workspace_id=workspace_id,
            now=now,
            target_table_full_name=target_table_full_name,
            only_active=only_active,
        )
    return {"now": now.isoformat(), "rows": [_serialize_status(r) for r in rows]}


__all__ = ["router"]
