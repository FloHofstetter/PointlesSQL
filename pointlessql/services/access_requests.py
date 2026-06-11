"""Lifecycle logic for table access requests.

The service owns the request ledger's state machine — create,
approve, deny, cancel — plus the two inbox queries (requester view
and decider view).  It deliberately knows nothing about Unity
Catalog: the *actual* grant on approval is issued by the route layer
through the soyuz client, so this module stays synchronous, easy to
unit-test, and safe to call from background contexts.

Decision rights follow the ``owner_email_snapshot`` taken at request
time (or the admin flag); the requester may withdraw a pending
request but never decide it.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, select

from pointlessql.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.access_requests import AccessRequest

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def serialize(row: AccessRequest) -> dict[str, Any]:
    """Convert a row to the JSON-friendly dict used in API responses.

    Args:
        row: The access-request row.

    Returns:
        A plain dict with scalar keys ready for ``JSONResponse``;
        ``privileges`` is decoded back into a list.
    """
    try:
        privileges = json.loads(row.privileges or "[]")
    except ValueError:
        privileges = []
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "securable_type": row.securable_type,
        "full_name": row.full_name,
        "requester_user_id": row.requester_user_id,
        "requester_email": row.requester_email,
        "owner_email_snapshot": row.owner_email_snapshot,
        "privileges": privileges,
        "justification": row.justification,
        "status": row.status,
        "decided_by_user_id": row.decided_by_user_id,
        "decision_note": row.decision_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def create_request(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    securable_type: str,
    full_name: str,
    requester_user_id: int,
    requester_email: str,
    owner_email: str,
    privileges: list[str],
    justification: str | None,
) -> AccessRequest:
    """Insert a new pending access request.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Tenant scope of the request.
        securable_type: Kind of securable (``table`` for now).
        full_name: Dotted UC name of the securable.
        requester_user_id: ID of the asking user.
        requester_email: E-mail snapshot of the requester (becomes
            the grant principal on approval).
        owner_email: Owner of the securable at request time —
            snapshotted so the decider inbox stays stable.
        privileges: Requested privilege strings; empty input
            defaults to ``["SELECT"]``.
        justification: Optional free-form reason.

    Returns:
        The persisted, detached row.

    Raises:
        ValidationError: When the requester already has a pending
            request for the same securable in this workspace, or a
            privilege entry is blank.
    """
    if any(not (p or "").strip() for p in privileges):
        raise ValidationError("privileges must be non-empty strings")
    clean_privileges = [p.strip() for p in privileges] or ["SELECT"]
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(
            select(AccessRequest.id).where(
                AccessRequest.workspace_id == workspace_id,
                AccessRequest.securable_type == securable_type,
                AccessRequest.full_name == full_name,
                AccessRequest.requester_user_id == requester_user_id,
                AccessRequest.status == "pending",
            )
        )
        if existing is not None:
            raise ValidationError(
                f"you already have a pending access request for {securable_type} '{full_name}'"
            )
        row = AccessRequest(
            workspace_id=workspace_id,
            securable_type=securable_type,
            full_name=full_name,
            requester_user_id=requester_user_id,
            requester_email=requester_email,
            owner_email_snapshot=owner_email or "",
            privileges=json.dumps(clean_privileges),
            justification=(justification or "").strip() or None,
            status="pending",
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def has_pending_request(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    securable_type: str,
    full_name: str,
    requester_user_id: int,
) -> bool:
    """Whether the user already has a pending request for a securable.

    The same predicate the create-time duplicate guard uses, exposed
    for render-time checks — the table page swaps its "Request
    access" button for an "Access requested" state off this flag.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Tenant scope.
        securable_type: Kind of securable (``table`` for now).
        full_name: Dotted UC name of the securable.
        requester_user_id: The asking user's id.

    Returns:
        ``True`` when a pending row exists for this requester and
        securable in the workspace.
    """
    with factory() as session:
        existing = session.scalar(
            select(AccessRequest.id).where(
                AccessRequest.workspace_id == workspace_id,
                AccessRequest.securable_type == securable_type,
                AccessRequest.full_name == full_name,
                AccessRequest.requester_user_id == requester_user_id,
                AccessRequest.status == "pending",
            )
        )
        return existing is not None


def get_request(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    request_id: int,
) -> AccessRequest | None:
    """Return one workspace-scoped request row, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Tenant scope the row must belong to.
        request_id: Primary key of the row.

    Returns:
        The detached row, or ``None`` when the id is unknown or
        belongs to another workspace (indistinguishable on purpose).
    """
    with factory() as session:
        row = session.get(AccessRequest, request_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        session.expunge(row)
        return row


def list_for_requester(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    user_id: int,
    limit: int = 200,
) -> list[AccessRequest]:
    """Return the user's own requests, newest first.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Tenant scope.
        user_id: The requester's user id.
        limit: Maximum rows to return.

    Returns:
        List of detached rows (all statuses — the requester sees
        their full history, not just open items).
    """
    stmt = (
        select(AccessRequest)
        .where(
            AccessRequest.workspace_id == workspace_id,
            AccessRequest.requester_user_id == user_id,
        )
        .order_by(desc(AccessRequest.created_at), desc(AccessRequest.id))
        .limit(limit)
    )
    with factory() as session:
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


def list_pending_for_decider(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    email: str,
    is_admin: bool,
    limit: int = 200,
) -> list[AccessRequest]:
    """Return the pending requests the caller may decide, oldest first.

    Admins see every pending request in the workspace; everyone else
    only sees the rows whose owner snapshot matches their e-mail.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Tenant scope.
        email: The caller's e-mail (matched against the owner
            snapshot for non-admins).
        is_admin: Whether the caller is an administrator.
        limit: Maximum rows to return.

    Returns:
        List of detached pending rows.
    """
    stmt = (
        select(AccessRequest)
        .where(
            AccessRequest.workspace_id == workspace_id,
            AccessRequest.status == "pending",
        )
        .order_by(AccessRequest.created_at.asc(), AccessRequest.id.asc())
        .limit(limit)
    )
    if not is_admin:
        if not email:
            return []
        stmt = stmt.where(AccessRequest.owner_email_snapshot == email)
    with factory() as session:
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


def _decide(
    factory: sessionmaker[Session],
    *,
    request_id: int,
    decider_user_id: int,
    decider_email: str,
    is_admin: bool,
    note: str | None,
    new_status: str,
) -> AccessRequest:
    """Flip one pending row to a decided status and stamp the decider.

    Shared body of :func:`approve` and :func:`deny` — the only
    difference between the two is the target status and deny's
    mandatory note, which the wrappers enforce.

    Args:
        factory: SQLAlchemy session factory.
        request_id: Primary key of the row.
        decider_user_id: User id stamped as the decider.
        decider_email: E-mail of the decider; must match the owner
            snapshot unless *is_admin*.
        is_admin: Whether the decider is an administrator.
        note: Optional decision note.
        new_status: Either ``approved`` or ``denied``.

    Returns:
        The refreshed, detached row.

    Raises:
        ResourceNotFoundError: When no row exists at *request_id*.
        PermissionDeniedError: When the decider is neither an admin
            nor the snapshotted owner.
        ConflictError: When the row is no longer pending.
    """
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.get(AccessRequest, request_id)
        if row is None:
            raise ResourceNotFoundError(f"Access request {request_id} not found.")
        if not is_admin and (not decider_email or decider_email != row.owner_email_snapshot):
            raise PermissionDeniedError(
                "only the table owner or an admin can decide this access request"
            )
        if row.status != "pending":
            raise ConflictError(f"access request {request_id} is already {row.status}")
        row.status = new_status
        row.decided_by_user_id = decider_user_id
        row.decision_note = (note or "").strip() or None
        row.decided_at = now
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def approve(
    factory: sessionmaker[Session],
    *,
    request_id: int,
    decider_user_id: int,
    decider_email: str,
    is_admin: bool,
    note: str | None,
) -> AccessRequest:
    """Mark a pending request approved (status flip + stamp only).

    The actual UC grant is issued by the caller *before* this flip —
    the route layer holds the soyuz client, and flipping last means
    a failed grant leaves the request pending and retryable.
    Not-found, permission, and conflict errors raised by the shared
    decision flip propagate unchanged.

    Args:
        factory: SQLAlchemy session factory.
        request_id: Primary key of the row.
        decider_user_id: User id stamped as the decider.
        decider_email: E-mail of the decider.
        is_admin: Whether the decider is an administrator.
        note: Optional decision note.

    Returns:
        The refreshed, detached row.
    """
    return _decide(
        factory,
        request_id=request_id,
        decider_user_id=decider_user_id,
        decider_email=decider_email,
        is_admin=is_admin,
        note=note,
        new_status="approved",
    )


def deny(
    factory: sessionmaker[Session],
    *,
    request_id: int,
    decider_user_id: int,
    decider_email: str,
    is_admin: bool,
    note: str | None,
) -> AccessRequest:
    """Mark a pending request denied; a non-empty note is mandatory.

    Not-found, permission, and conflict errors raised by the shared
    decision flip propagate unchanged.

    Args:
        factory: SQLAlchemy session factory.
        request_id: Primary key of the row.
        decider_user_id: User id stamped as the decider.
        decider_email: E-mail of the decider.
        is_admin: Whether the decider is an administrator.
        note: The denial reason shown to the requester.

    Returns:
        The refreshed, detached row.

    Raises:
        ValidationError: When *note* is empty — a denial without a
            reason gives the requester nothing to act on.
    """
    if not (note or "").strip():
        raise ValidationError("a decision note is required to deny an access request")
    return _decide(
        factory,
        request_id=request_id,
        decider_user_id=decider_user_id,
        decider_email=decider_email,
        is_admin=is_admin,
        note=note,
        new_status="denied",
    )


def cancel(
    factory: sessionmaker[Session],
    *,
    request_id: int,
    requester_user_id: int,
) -> AccessRequest:
    """Withdraw a pending request (requester only).

    Args:
        factory: SQLAlchemy session factory.
        request_id: Primary key of the row.
        requester_user_id: Must match the row's requester.

    Returns:
        The refreshed, detached row.

    Raises:
        ResourceNotFoundError: When no row exists at *request_id*.
        PermissionDeniedError: When the caller is not the requester.
        ConflictError: When the row is no longer pending.
    """
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.get(AccessRequest, request_id)
        if row is None:
            raise ResourceNotFoundError(f"Access request {request_id} not found.")
        if row.requester_user_id != requester_user_id:
            raise PermissionDeniedError("only the requester can cancel an access request")
        if row.status != "pending":
            raise ConflictError(f"access request {request_id} is already {row.status}")
        row.status = "cancelled"
        row.decided_at = now
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row
