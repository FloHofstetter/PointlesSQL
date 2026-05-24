"""Admin CRUD endpoints for the CDF tail subscriptions.

Counterpart to :mod:`pointlessql.api.admin_expected_producers_routes`:
where that registry holds *push-modell* expectations (``producer X
should send inbound events to table T``), this registry holds
*pull-modell* opt-ins (``PointlesSQL should tail table T's CDF
periodically``).

Workspace scoping comes from the resolved request workspace, not the
body — admins working in workspace A cannot register subscriptions
against workspace B by hand-crafting the payload.

Includes a manual ``/run-now`` endpoint so admins can drive a tail
without flipping the global interval setting.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_templates, require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import CdfTailSubscription

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin", "cdf-tail"])


@router.get("/admin/cdf-subscriptions", response_class=HTMLResponse)
async def admin_cdf_subscriptions_index(
    request: Request,
    table_fqn_like: str | None = None,
    only_active: bool = False,
) -> HTMLResponse:
    """Render the CDF tail subscriptions admin page.

    Args:
        request: Incoming FastAPI request.
        table_fqn_like: Optional substring filter on ``table_full_name``.
        only_active: When True, omits paused subscriptions.

    Returns:
        The rendered HTML page.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    cleaned_like = (
        table_fqn_like.strip()
        if isinstance(table_fqn_like, str) and table_fqn_like.strip()
        else None
    )
    with factory() as session:
        stmt = select(CdfTailSubscription).where(CdfTailSubscription.workspace_id == workspace_id)
        if only_active:
            stmt = stmt.where(CdfTailSubscription.is_active.is_(True))
        if cleaned_like:
            stmt = stmt.where(CdfTailSubscription.table_full_name.like(f"%{cleaned_like}%"))
        rows = list(session.scalars(stmt.order_by(CdfTailSubscription.created_at.desc())).all())
        entries = [_serialize(r) for r in rows]
        with_errors = (
            session.scalar(
                select(func.count(CdfTailSubscription.id)).where(
                    CdfTailSubscription.workspace_id == workspace_id,
                    CdfTailSubscription.last_error.is_not(None),
                )
            )
            or 0
        )
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_cdf_tail.html",
        {
            "entries": entries,
            "table_fqn_like": cleaned_like or "",
            "only_active": only_active,
            "with_errors_total": with_errors,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


def _serialize(row: CdfTailSubscription) -> dict[str, Any]:
    """Project a subscription row into a JSON-safe dict."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "table_full_name": row.table_full_name,
        "row_id_column": row.row_id_column,
        "producer_label": row.producer_label,
        "last_version_processed": row.last_version_processed,
        "is_active": bool(row.is_active),
        "last_tailed_at": row.last_tailed_at.isoformat() if row.last_tailed_at else None,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/admin/cdf-subscriptions")
async def api_admin_list_cdf_subscriptions(
    request: Request, only_active: bool = False
) -> dict[str, Any]:
    """List CDF tail subscriptions for this workspace.

    Args:
        request: Incoming FastAPI request.
        only_active: When True, omits paused subscriptions.

    Returns:
        ``{"subscriptions": [{...}, ...]}`` ordered by
        ``created_at DESC``.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(CdfTailSubscription).where(CdfTailSubscription.workspace_id == workspace_id)
        if only_active:
            stmt = stmt.where(CdfTailSubscription.is_active.is_(True))
        rows = list(session.scalars(stmt.order_by(CdfTailSubscription.created_at.desc())).all())
        out = [_serialize(r) for r in rows]
    return {"subscriptions": out}


@router.post("/api/admin/cdf-subscriptions")
async def api_admin_create_cdf_subscription(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Register one CDF tail subscription.

    Args:
        request: Incoming FastAPI request.
        body: ``{table_full_name: str, row_id_column: str,
            producer_label?: str, is_active?: bool}``.  When
            ``producer_label`` is omitted or empty it defaults to
            ``cdf-tail:<table_full_name>``.

    Returns:
        The created row, serialized.

    Raises:
        ValidationError: When required fields are missing / invalid,
            or the (workspace, table) pair is already subscribed.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    table = body.get("table_full_name")
    row_id_column = body.get("row_id_column")
    producer_label_raw = body.get("producer_label")
    is_active = bool(body.get("is_active", True))
    if not isinstance(table, str) or not table.strip():
        raise ValidationError("table_full_name must be a non-empty string")
    if len(table.split(".")) != 3:
        raise ValidationError("table_full_name must be a three-part UC name")
    if not isinstance(row_id_column, str) or not row_id_column.strip():
        raise ValidationError("row_id_column must be a non-empty string")
    if producer_label_raw is None or (
        isinstance(producer_label_raw, str) and not producer_label_raw.strip()
    ):
        producer_label = f"cdf-tail:{table.strip()}"
    elif not isinstance(producer_label_raw, str):
        raise ValidationError("producer_label must be a string when supplied")
    else:
        producer_label = producer_label_raw.strip()

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = CdfTailSubscription(
            workspace_id=workspace_id,
            table_full_name=table.strip(),
            row_id_column=row_id_column.strip(),
            producer_label=producer_label,
            is_active=is_active,
            created_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValidationError(
                "subscription for this (workspace, table_full_name) already exists"
            ) from exc
        session.refresh(row)
        out = _serialize(row)
    await audit(
        request,
        "cdf_subscription.created",
        f"cdf_subscription:{table}",
        {"row_id_column": row_id_column, "is_active": is_active},
    )
    return out


@router.post("/api/admin/cdf-subscriptions/{subscription_id}/toggle")
async def api_admin_toggle_cdf_subscription(
    request: Request, subscription_id: int
) -> dict[str, Any]:
    """Flip the ``is_active`` flag on one subscription.

    Args:
        request: Incoming FastAPI request.
        subscription_id: ``CdfTailSubscription.id`` to toggle.

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
        row = session.get(CdfTailSubscription, subscription_id)
        if row is None or row.workspace_id != workspace_id:
            raise CatalogNotFoundError(f"cdf subscription {subscription_id} not found")
        row.is_active = not bool(row.is_active)
        session.commit()
        session.refresh(row)
        out = _serialize(row)
    await audit(
        request,
        "cdf_subscription.toggled",
        f"cdf_subscription:{out['table_full_name']}",
        {"is_active": out["is_active"]},
    )
    return out


@router.delete("/api/admin/cdf-subscriptions/{subscription_id}")
async def api_admin_delete_cdf_subscription(
    request: Request, subscription_id: int
) -> dict[str, Any]:
    """Delete one subscription (cascades into its captured events).

    Args:
        request: Incoming FastAPI request.
        subscription_id: ``CdfTailSubscription.id`` to delete.

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
        row = session.get(CdfTailSubscription, subscription_id)
        if row is None or row.workspace_id != workspace_id:
            raise CatalogNotFoundError(f"cdf subscription {subscription_id} not found")
        table = row.table_full_name
        session.delete(row)
        session.commit()
    await audit(
        request,
        "cdf_subscription.deleted",
        f"cdf_subscription:{table}",
    )
    return {"id": subscription_id, "deleted": True}


@router.post("/api/admin/cdf-subscriptions/run-now")
async def api_admin_cdf_subscriptions_run_now(request: Request) -> dict[str, Any]:
    """Run one CDF tail tick immediately, regardless of the loop interval.

    Mirrors the ``POST /api/admin/external-writes/scan`` admin
    affordance: lets an operator drive a tail in response to a
    just-registered subscription without waiting for the next loop
    tick.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"inserted": <int>}`` — the count of newly-persisted
        ``cdf_tail_events`` rows from this tick.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    uc = request.app.state.uc_client
    settings = request.app.state.settings
    history_limit = settings.cdf_tail.history_limit
    from pointlessql.services import cdf_tail as cdf_tail_service

    inserted = await cdf_tail_service.tail_all(factory, uc, history_limit=history_limit)
    await audit(
        request,
        "cdf_subscription.run_now",
        "cdf_subscription:*",
        {"inserted": inserted},
    )
    return {"inserted": inserted}


__all__ = ["router"]
