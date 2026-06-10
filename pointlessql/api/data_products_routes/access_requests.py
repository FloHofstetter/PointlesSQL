"""Self-service access-request routes for a data product.

A consumer who lacks ``SELECT`` files a request; the product steward (or
an admin) approves it, at which point the app grants ``SELECT`` on every
declared table through the soyuz client — PointlesSQL records the
request in its own metadata ledger and never writes lakehouse
permissions directly.  Both decisions fan a notification out (to the
steward + admins on a new request; to the requester on a decision) so
the existing inbox / feed surfaces the work without a bespoke channel.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.active_reviewer import (
    _require_steward_or_admin,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    effective_principal,
    get_user,
    require_user,
)
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_access_request import (
    DataProductAccessRequest,
)
from pointlessql.services.authorization import SELECT, has_privilege
from pointlessql.services.notifications.fanout import (
    fanout_event,
    resolve_user_id_by_email,
    resolve_workspace_admin_ids,
)

router = APIRouter(tags=["data-products"])


class RequestAccessBody(BaseModel):
    """Input for filing an access request."""

    note: str | None = Field(default=None, max_length=2000)


class DecisionBody(BaseModel):
    """Input for approving / denying an access request."""

    reason: str | None = Field(default=None, max_length=2000)


def _serialise(row: DataProductAccessRequest, requester: dict[str, Any] | None) -> dict[str, Any]:
    """Render an access-request row for the API."""
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "status": row.status,
        "request_note": row.request_note,
        "requester": requester,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_reason": row.decision_reason,
    }


async def _user_can_select(request: Request, user: Any, tables: list[str]) -> bool:
    """Return whether *user* already holds SELECT on every declared table.

    Reads effective permissions through the trusted app client (they are
    a property of the securable, not the caller) and matches the caller's
    email.  Admins short-circuit.  A lookup that fails (soyuz hiccup,
    unknown table) is treated as "cannot confirm access" → ``False``, so
    the consumer can still file a request rather than 500.
    """
    if not tables:
        return False
    if user.get("is_admin"):
        return True
    principal = effective_principal(request) or user.get("email", "")
    client = request.app.state.uc_client
    for fqn in tables:
        try:
            effective = await client.get_effective_permissions("table", fqn)
        except Exception:  # noqa: BLE001
            # bare-broad-ok: an unverifiable lookup reads as no-access so the
            # consumer can still file a request rather than hit a 500.
            return False
        if not has_privilege(effective, principal, False, SELECT):
            return False
    return True


@router.get("/api/data-products/{catalog}/{schema}/access-requests/status")
async def access_status(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the caller's access posture for this product.

    Drives the "Request access" affordance: whether the caller already
    has SELECT, and whether they have an open request pending.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"can_select": bool, "has_pending": bool, "is_steward": bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, contract, _e, _d = load_one(factory, workspace_id, catalog, schema)
    tables = [f"{catalog}.{schema}.{t.name}" for t in contract.tables]
    can_select = await _user_can_select(request, user, tables)
    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    with factory() as session:
        pending = session.scalar(
            select(DataProductAccessRequest.id).where(
                DataProductAccessRequest.data_product_id == dp_row.id,
                DataProductAccessRequest.requester_user_id == user["id"],
                DataProductAccessRequest.status == "pending",
            )
        )
    return {
        "can_select": can_select,
        "has_pending": pending is not None,
        "is_steward": bool(is_steward or user.get("is_admin")),
    }


@router.post("/api/data-products/{catalog}/{schema}/access-requests")
async def request_access(
    catalog: str, schema: str, request: Request, body: RequestAccessBody
) -> dict[str, Any]:
    """File a SELECT-access request for this product.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        body: Optional justification note.

    Returns:
        The created (or already-pending) request row.

    Raises:
        BadRequestError: When the caller already holds SELECT.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, contract, _e, _d = load_one(factory, workspace_id, catalog, schema)
    tables = [f"{catalog}.{schema}.{t.name}" for t in contract.tables]
    if await _user_can_select(request, user, tables):
        raise BadRequestError("you already have read access to this data product")

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(
            select(DataProductAccessRequest).where(
                DataProductAccessRequest.data_product_id == dp_row.id,
                DataProductAccessRequest.requester_user_id == user["id"],
                DataProductAccessRequest.status == "pending",
            )
        )
        if existing is not None:
            session.expunge(existing)
            return _serialise(existing, _requester_dict(user))
        row = DataProductAccessRequest(
            workspace_id=workspace_id,
            data_product_id=int(dp_row.id),
            requester_user_id=int(user["id"]),
            status="pending",
            request_note=(body.note or None),
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)

    _fanout_pending(request, dp_row, user, catalog, schema)
    return _serialise(row, _requester_dict(user))


@router.get("/api/data-products/{catalog}/{schema}/access-requests")
def list_access_requests(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """List pending access requests for a product (steward / admin).

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"requests": [...]}`` with the requester resolved.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)
    with factory() as session:
        rows = list(
            session.scalars(
                select(DataProductAccessRequest)
                .where(
                    DataProductAccessRequest.data_product_id == dp_row.id,
                    DataProductAccessRequest.status == "pending",
                )
                .order_by(DataProductAccessRequest.created_at.asc())
            ).all()
        )
        ids = {r.requester_user_id for r in rows}
        users = {
            u.id: u
            for u in (session.scalars(select(User).where(User.id.in_(ids))).all() if ids else [])
        }
        out = [
            _serialise(
                r,
                {
                    "user_id": r.requester_user_id,
                    "email": getattr(users.get(r.requester_user_id), "email", None),
                    "display_name": getattr(users.get(r.requester_user_id), "display_name", None),
                },
            )
            for r in rows
        ]
    return {"requests": out}


@router.post("/api/data-products/{catalog}/{schema}/access-requests/{request_id}/approve")
async def approve_access_request(
    catalog: str, schema: str, request_id: int, request: Request, body: DecisionBody
) -> dict[str, Any]:
    """Approve a request and grant SELECT through the soyuz client.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request_id: The access-request row id.
        request: Incoming FastAPI request.
        body: Optional decision note.

    Returns:
        ``{"status": "approved", "granted": [...], "failed": [...]}`` —
        per-table grant outcomes; the request is marked approved even
        when a table grant is rejected so the decision is recorded.
    """
    dp_row, _req_row, requester = _load_decidable(request, catalog, schema, request_id)

    tables = _contract_tables(request, catalog, schema)
    full_names = [f"{catalog}.{schema}.{t.name}" for t in tables]
    granted, failed = await _grant_select(request, requester["email"], full_names)

    now = datetime.datetime.now(datetime.UTC)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(DataProductAccessRequest, request_id)
        if row is not None:
            row.status = "approved"
            row.decided_at = now
            row.decided_by_user_id = int(user["id"])
            row.decision_reason = body.reason or None
            session.commit()
    _fanout_decision(request, dp_row, requester, catalog, schema, "approved", body.reason)
    return {"status": "approved", "granted": granted, "failed": failed}


@router.post("/api/data-products/{catalog}/{schema}/access-requests/{request_id}/deny")
def deny_access_request(
    catalog: str, schema: str, request_id: int, request: Request, body: DecisionBody
) -> dict[str, Any]:
    """Deny a request (no grant is issued).

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request_id: The access-request row id.
        request: Incoming FastAPI request.
        body: Optional decision note.

    Returns:
        ``{"status": "denied"}``.
    """
    dp_row, _req_row, requester = _load_decidable(request, catalog, schema, request_id)
    now = datetime.datetime.now(datetime.UTC)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(DataProductAccessRequest, request_id)
        if row is not None:
            row.status = "denied"
            row.decided_at = now
            row.decided_by_user_id = int(user["id"])
            row.decision_reason = body.reason or None
            session.commit()
    _fanout_decision(request, dp_row, requester, catalog, schema, "denied", body.reason)
    return {"status": "denied"}


# --- internals -------------------------------------------------------------


def _requester_dict(user: Any) -> dict[str, Any]:
    return {
        "user_id": user.get("id"),
        "email": user.get("email"),
        "display_name": user.get("display_name"),
    }


def _contract_tables(request: Request, catalog: str, schema: str) -> list[Any]:
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    _dp, contract, _e, _d = load_one(factory, workspace_id, catalog, schema)
    return list(contract.tables)


def _load_decidable(
    request: Request, catalog: str, schema: str, request_id: int
) -> tuple[Any, Any, dict[str, Any]]:
    """Load + authorise a pending request for a decision; resolve requester."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)
    with factory() as session:
        row = session.get(DataProductAccessRequest, request_id)
        if row is None or row.data_product_id != dp_row.id or row.workspace_id != workspace_id:
            raise ResourceNotFoundError(f"access request {request_id} not found")
        if row.status != "pending":
            raise BadRequestError(f"access request {request_id} is already {row.status}")
        requester = session.get(User, row.requester_user_id)
        requester_dict = {
            "user_id": row.requester_user_id,
            "email": requester.email if requester else "",
            "display_name": requester.display_name if requester else None,
        }
        session.expunge(row)
    return dp_row, row, requester_dict


async def _grant_select(
    request: Request, principal_email: str, full_names: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    """Grant SELECT on each table via the trusted app UC client.

    Best-effort: a table soyuz rejects (e.g. an unknown principal) is
    captured in ``failed`` with its error, while the rest still grant —
    the caller records the approval regardless and surfaces the misses.
    """
    client = request.app.state.uc_client
    granted: list[str] = []
    failed: list[dict[str, str]] = []
    if not principal_email:
        return granted, [{"table": fn, "error": "requester has no email"} for fn in full_names]
    for fqn in full_names:
        try:
            await client.update_permissions(
                "table",
                fqn,
                [{"principal": principal_email, "add": [SELECT], "remove": []}],
            )
            granted.append(fqn)
        except Exception as exc:  # noqa: BLE001
            # bare-broad-ok: best-effort grant — a soyuz-rejected table is
            # captured in failed[] and surfaced to the approver, not swallowed.
            failed.append({"table": fqn, "error": str(exc)})
    return granted, failed


def _fanout_pending(
    request: Request, dp_row: Any, requester: Any, catalog: str, schema: str
) -> None:
    """Notify the steward + admins that a request is awaiting a decision."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    name = requester.get("display_name") or requester.get("email") or "A user"
    with factory() as session:
        recipients = set(resolve_workspace_admin_ids(session))
        if dp_row.steward_user_id is not None:
            recipients.add(int(dp_row.steward_user_id))
    fanout_event(
        factory,
        event_type="pointlessql.data_product.access_request.pending",
        entity_kind="dp",
        entity_ref=str(dp_row.id),
        workspace_id=workspace_id,
        actor_user_id=int(requester.get("user_id") or 0) or None,
        source_url=f"/data-products/{catalog}/{schema}",
        summary_md=f"{name} requested access to {catalog}.{schema}",
        data_product_id=int(dp_row.id),
        extra_recipients=sorted(recipients),
    )


def _fanout_decision(
    request: Request,
    dp_row: Any,
    requester: dict[str, Any],
    catalog: str,
    schema: str,
    decision: str,
    reason: str | None,
) -> None:
    """Notify the requester that their request was approved / denied."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    requester_id = requester.get("user_id")
    if requester_id is None:
        with factory() as session:
            requester_id = resolve_user_id_by_email(session, requester.get("email"))
    if requester_id is None:
        return
    tail = f": {reason}" if reason else ""
    fanout_event(
        factory,
        event_type=f"pointlessql.data_product.access_request.{decision}",
        entity_kind="dp",
        entity_ref=str(dp_row.id),
        workspace_id=workspace_id,
        actor_user_id=int(user["id"]),
        source_url=f"/data-products/{catalog}/{schema}",
        summary_md=f"Your access request for {catalog}.{schema} was {decision}{tail}",
        data_product_id=int(dp_row.id),
        extra_recipients=[int(requester_id)],
    )
