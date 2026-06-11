"""Access-request routes for catalog tables + table certification.

Self-service "Request access" (the Unity Catalog *Discover* shape):
a user who lacks ``SELECT`` on a table files a request from the
table page; the table owner (or an admin) approves it from the
``/access-requests`` inbox, at which point the app issues the real
grant through the soyuz client.  PointlesSQL records the request in
its own metadata ledger and never writes lakehouse permissions
directly.  Both directions fan a notification out (to the owner on a
new request; to the requester on a decision) so the existing inbox
surfaces the work.

The certification endpoint rides along because it is the other half
of the discovery story: owners / admins mark a table ``certified``
or ``deprecated`` (stored as UC tags — see
``pointlessql.services.certifications``) and the table page renders
the badge next to the title.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_user,
)
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.access_requests import AccessRequest
from pointlessql.services import access_requests as access_requests_service
from pointlessql.services import certifications as certifications_service
from pointlessql.services.authorization import MANAGE_GRANTS, SELECT, has_privilege
from pointlessql.services.notifications.fanout import (
    fanout_event,
    resolve_user_id_by_email,
)
from pointlessql.types import TableFqn

if TYPE_CHECKING:
    from pointlessql.services.unitycatalog import UnityCatalogClient

router = APIRouter(tags=["access-requests"])


class CreateAccessRequestBody(BaseModel):
    """Input for filing an access request."""

    securable_type: str = Field(default="table", max_length=32)
    full_name: str = Field(min_length=1, max_length=256)
    privileges: list[str] = Field(default_factory=lambda: [SELECT])
    justification: str | None = Field(default=None, max_length=2000)


class DecisionBody(BaseModel):
    """Input for approving / denying an access request."""

    note: str | None = Field(default=None, max_length=2000)


class CertificationBody(BaseModel):
    """Input for setting / clearing a table certification."""

    status: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/api/access-requests")
async def api_create_access_request(
    request: Request, body: CreateAccessRequestBody
) -> dict[str, Any]:
    """File an access request for a table.

    Snapshots the table owner for the decider inbox, rejects callers
    who already hold every requested privilege, and notifies the
    owner through the notification fan-out.

    Args:
        request: Incoming FastAPI request.
        body: Securable reference, requested privileges, and an
            optional justification.

    Returns:
        The created request, serialized.

    Raises:
        ValidationError: When the securable type is unsupported, the
            name is not a three-part FQN, or a pending duplicate
            exists.
        CatalogNotFoundError: When the table does not exist.
        ConflictError: When the caller already holds every requested
            privilege.
    """
    require_user(request)
    user = get_user(request)
    if body.securable_type != "table":
        raise ValidationError("only securable_type 'table' is supported")
    fqn = TableFqn.parse(body.full_name)
    catalog_name, schema_name, table_name = str(fqn).split(".")

    client: UnityCatalogClient = request.app.state.uc_client
    table_info = await client.get_table(catalog_name, schema_name, table_name)
    if not table_info:
        raise CatalogNotFoundError(f"Table '{fqn}' not found.")

    privileges = [p.strip() for p in body.privileges if p and p.strip()] or [SELECT]
    # Effective permissions are a property of the securable, not the
    # caller, so the trusted app client reads them.  An unverifiable
    # lookup reads as "cannot confirm access" → the request may still
    # be filed rather than 500.
    try:
        effective = await client.get_effective_permissions("table", str(fqn))
    except CatalogUnavailableError:
        effective = []
    is_admin = bool(user.get("is_admin", False))
    email = user.get("email", "")
    if all(has_privilege(effective, email, is_admin, priv) for priv in privileges):
        raise ConflictError(f"you already have access to table '{fqn}'")

    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    owner_email = str(table_info.get("owner") or "")
    row = access_requests_service.create_request(
        factory,
        workspace_id=workspace_id,
        securable_type=body.securable_type,
        full_name=str(fqn),
        requester_user_id=int(user["id"]),
        requester_email=email,
        owner_email=owner_email,
        privileges=privileges,
        justification=body.justification,
    )
    _fanout_opened(request, row)
    return access_requests_service.serialize(row)


@router.get("/api/access-requests")
def api_list_access_requests(
    request: Request,
    role: str = Query(default="requester"),
) -> dict[str, Any]:
    """List access requests from one of the two inbox perspectives.

    Args:
        request: Incoming FastAPI request.
        role: ``requester`` for the caller's own history, ``decider``
            for the pending items the caller may decide (admins see
            all pending; owners see their snapshot matches).

    Returns:
        ``{"requests": [...]}``, serialized.

    Raises:
        ValidationError: When *role* is neither ``requester`` nor
            ``decider``.
    """
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    if role == "requester":
        rows = access_requests_service.list_for_requester(
            factory, workspace_id=workspace_id, user_id=int(user["id"])
        )
    elif role == "decider":
        rows = access_requests_service.list_pending_for_decider(
            factory,
            workspace_id=workspace_id,
            email=user.get("email", ""),
            is_admin=bool(user.get("is_admin", False)),
        )
    else:
        raise ValidationError("role must be 'requester' or 'decider'")
    return {"requests": [access_requests_service.serialize(row) for row in rows]}


@router.post("/api/access-requests/{request_id}/approve")
async def api_approve_access_request(
    request: Request, request_id: int, body: DecisionBody
) -> dict[str, Any]:
    """Approve a pending request: grant through UC, then flip the row.

    The grant happens first so a soyuz rejection leaves the request
    pending and retryable instead of recording an approval that
    never materialised.

    Args:
        request: Incoming FastAPI request.
        request_id: The access-request row id.
        body: Optional decision note.

    Returns:
        The approved request, serialized.
    """
    row = _load_decidable(request, request_id)
    user = get_user(request)
    privileges_raw: Any = json.loads(row.privileges or "[]")
    privileges: list[str] = [str(p) for p in privileges_raw] or [SELECT]
    client: UnityCatalogClient = request.app.state.uc_client
    await client.update_permissions(
        row.securable_type,
        row.full_name,
        [{"principal": row.requester_email, "add": privileges, "remove": []}],
    )
    updated = access_requests_service.approve(
        request.app.state.session_factory,
        request_id=request_id,
        decider_user_id=int(user["id"]),
        decider_email=user.get("email", ""),
        is_admin=bool(user.get("is_admin", False)),
        note=body.note,
    )
    _fanout_decision(request, updated, "approved")
    return access_requests_service.serialize(updated)


@router.post("/api/access-requests/{request_id}/deny")
async def api_deny_access_request(
    request: Request, request_id: int, body: DecisionBody
) -> dict[str, Any]:
    """Deny a pending request (no grant is issued; the note is mandatory).

    Args:
        request: Incoming FastAPI request.
        request_id: The access-request row id.
        body: The denial reason (required).

    Returns:
        The denied request, serialized.
    """
    _load_decidable(request, request_id)
    user = get_user(request)
    updated = access_requests_service.deny(
        request.app.state.session_factory,
        request_id=request_id,
        decider_user_id=int(user["id"]),
        decider_email=user.get("email", ""),
        is_admin=bool(user.get("is_admin", False)),
        note=body.note,
    )
    _fanout_decision(request, updated, "denied")
    return access_requests_service.serialize(updated)


@router.post("/api/access-requests/{request_id}/cancel")
async def api_cancel_access_request(request: Request, request_id: int) -> dict[str, Any]:
    """Withdraw the caller's own pending request.

    Args:
        request: Incoming FastAPI request.
        request_id: The access-request row id.

    Returns:
        The cancelled request, serialized.

    Raises:
        ResourceNotFoundError: When the id is unknown in the active
            workspace.
    """
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = access_requests_service.get_request(
        factory, workspace_id=workspace_id, request_id=request_id
    )
    if row is None:
        raise ResourceNotFoundError(f"Access request {request_id} not found.")
    updated = access_requests_service.cancel(
        factory, request_id=request_id, requester_user_id=int(user["id"])
    )
    return access_requests_service.serialize(updated)


@router.get("/access-requests", response_class=HTMLResponse)
async def access_requests_page(request: Request) -> Any:
    """Render the access-requests page (own history + decider inbox).

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered template response.
    """
    user = get_user(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/access_requests.html",
        {
            "active_page": "access_requests",
            "is_admin": bool(user.get("is_admin", False)),
        },
    )


@router.put("/api/tables/{full_name}/certification")
async def api_set_table_certification(
    request: Request, full_name: str, body: CertificationBody
) -> dict[str, Any]:
    """Set or clear a table's certification (admin / owner / MANAGE_GRANTS).

    Args:
        request: Incoming FastAPI request.
        full_name: Dotted three-part name of the table.
        body: New status (``certified`` / ``deprecated`` / ``null``
            to clear) and an optional note.

    Returns:
        ``{"full_name": ..., "certification": {...} | None}``.

    Raises:
        ValidationError: When the status value is unrecognised or the
            name is not a three-part FQN.
        CatalogNotFoundError: When the table does not exist.
        PermissionDeniedError: When the caller is neither an admin,
            the table owner, nor a MANAGE_GRANTS holder.
    """
    require_user(request)
    user = get_user(request)
    if body.status is not None and body.status not in certifications_service.CERTIFICATION_STATUSES:
        allowed = ", ".join(certifications_service.CERTIFICATION_STATUSES)
        raise ValidationError(f"certification status must be one of: {allowed} (or null)")
    fqn = TableFqn.parse(full_name)
    catalog_name, schema_name, table_name = str(fqn).split(".")
    client: UnityCatalogClient = request.app.state.uc_client
    table_info, effective = await asyncio.gather(
        client.get_table(catalog_name, schema_name, table_name),
        client.get_effective_permissions("table", str(fqn)),
    )
    if not table_info:
        raise CatalogNotFoundError(f"Table '{fqn}' not found.")
    email = user.get("email", "")
    is_admin = bool(user.get("is_admin", False))
    is_owner = bool(email) and table_info.get("owner") == email
    if not (is_admin or is_owner or has_privilege(effective, email, False, MANAGE_GRANTS)):
        raise PermissionDeniedError(
            "only an admin, the table owner, or a MANAGE_GRANTS holder can set certification"
        )
    certification = await certifications_service.set_certification(
        client, str(fqn), status=body.status, note=body.note
    )
    return {"full_name": str(fqn), "certification": certification}


# --- internals -------------------------------------------------------------


def _load_decidable(request: Request, request_id: int) -> AccessRequest:
    """Load a pending request and authorise the caller as its decider.

    Args:
        request: Incoming FastAPI request.
        request_id: The access-request row id.

    Returns:
        The detached pending row.

    Raises:
        ResourceNotFoundError: When the id is unknown in the active
            workspace.
        PermissionDeniedError: When the caller is neither an admin
            nor the snapshotted owner.
        ConflictError: When the row is no longer pending.
    """
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = access_requests_service.get_request(
        factory, workspace_id=workspace_id, request_id=request_id
    )
    if row is None:
        raise ResourceNotFoundError(f"Access request {request_id} not found.")
    is_admin = bool(user.get("is_admin", False))
    email = user.get("email", "")
    if not is_admin and (not email or email != row.owner_email_snapshot):
        raise PermissionDeniedError(
            "only the table owner or an admin can decide this access request"
        )
    if row.status != "pending":
        raise ConflictError(f"access request {request_id} is already {row.status}")
    return row


def _fanout_opened(request: Request, row: AccessRequest) -> None:
    """Notify the snapshotted owner that a request awaits a decision.

    Best-effort by design: the owner e-mail may not resolve to a
    user (foreign-owned or service-principal tables), in which case
    no notification is written — admins see the inbox page anyway.

    Args:
        request: Incoming FastAPI request.
        row: The freshly created request row.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        owner_user_id = resolve_user_id_by_email(session, row.owner_email_snapshot or None)
    if owner_user_id is None:
        return
    requester = row.requester_email or "A user"
    privileges = ", ".join(json.loads(row.privileges or "[]")) or SELECT
    fanout_event(
        factory,
        event_type="pointlessql.access_request.opened",
        entity_kind="table",
        entity_ref=row.full_name,
        workspace_id=row.workspace_id,
        actor_user_id=row.requester_user_id,
        source_url="/access-requests",
        summary_md=f"{requester} requested {privileges} on `{row.full_name}`",
        extra_recipients=[owner_user_id],
    )


def _fanout_decision(request: Request, row: AccessRequest, decision: str) -> None:
    """Notify the requester that their request was decided.

    Args:
        request: Incoming FastAPI request.
        row: The decided request row.
        decision: ``approved`` or ``denied`` — becomes the event-type
            suffix and the summary verb.
    """
    factory = request.app.state.session_factory
    user = get_user(request)
    tail = f": {row.decision_note}" if row.decision_note else ""
    fanout_event(
        factory,
        event_type=f"pointlessql.access_request.{decision}",
        entity_kind="table",
        entity_ref=row.full_name,
        workspace_id=row.workspace_id,
        actor_user_id=int(user["id"]),
        source_url="/access-requests",
        summary_md=f"Your access request for `{row.full_name}` was {decision}{tail}",
        extra_recipients=[row.requester_user_id],
    )
