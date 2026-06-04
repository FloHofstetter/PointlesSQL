"""Audit log service — append-only record of user actions.

Three shoreguard-fresh patterns underpin the implementation:

1. **Append-only ORM guards.** SQLAlchemy ``before_update`` and
   ``before_delete`` event listeners on :class:`AuditLog` raise
   :class:`AuditIntegrityError` so accidental row mutations from
   route handlers or migrations fail loudly. The guards honour a
   :class:`~contextvars.ContextVar` so the retention-cleanup code
   path can still delete rows during its tick. Raw SQL can still
   bypass the guard — use PostgreSQL row-level security or
   ``REVOKE DELETE`` if the deployment needs WORM semantics.

2. **Structured ``detail``.** The column was widened to ``Text``
   and :func:`log_action` now accepts an optional ``dict`` that is
   JSON-encoded before insertion. Plain-string ``detail`` still
   works for callers that have not migrated yet.

3. **Retention cleanup.** :func:`cleanup_old_entries` deletes every
   row older than ``retention_days`` inside the ContextVar bypass
   window. The scheduler invokes it on its own tick
   (``SchedulerSettings.enabled=True`` in production) so the audit
   table never grows unbounded.

``log_action`` itself stays synchronous; the API surface in
``pointlessql.api.main._audit`` is the one that pushes the call
onto :func:`asyncio.to_thread` so the HTTP request never blocks on
the insert.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event, select

from pointlessql.exceptions import PointlessSQLError
from pointlessql.models import AuditLog
from pointlessql.types import ErrorCode, SessionFactory

logger = logging.getLogger(__name__)


class AuditIntegrityError(PointlessSQLError):
    """Raised when a caller tries to mutate an :class:`AuditLog` row.

    ``AuditLog`` is append-only. ``UPDATE`` is never allowed.
    ``DELETE`` is only allowed inside :func:`_allow_audit_mutation`,
    which :func:`cleanup_old_entries` opens around its retention
    sweep. Every other ``session.delete(audit_entry)`` or
    ``session.commit()`` after an in-place attribute assignment
    raises this error.

    Reparented from :class:`Exception` to :class:`PointlessSQLError`
    so the centralised handler renders integrity violations as 500
    ``audit_integrity_error`` if they ever escape an internal catch.

    Attributes:
        status_code: Always 500.
        error_code: Always ``ErrorCode.AUDIT_INTEGRITY_ERROR``.
    """

    status_code: int = 500
    error_code: ErrorCode = ErrorCode.AUDIT_INTEGRITY_ERROR


_audit_mutation_allowed: ContextVar[bool] = ContextVar("_audit_mutation_allowed", default=False)


@contextlib.contextmanager
def _allow_audit_mutation() -> Iterator[None]:
    """Open a scope in which ``AuditLog`` DELETE is permitted.

    Used exclusively by :func:`cleanup_old_entries`. Reset on exit
    so the guard re-engages even if the body raised.
    """
    token = _audit_mutation_allowed.set(True)
    try:
        yield
    finally:
        _audit_mutation_allowed.reset(token)


@event.listens_for(AuditLog, "before_update", propagate=True)
def _block_audit_update(  # pyright: ignore[reportUnusedFunction]
    _mapper: Any, _conn: Any, _target: AuditLog
) -> None:
    """Forbid updates on audit rows at the ORM layer.

    Raised even inside :func:`_allow_audit_mutation` — retention
    cleanup deletes, it never rewrites.

    Args:
        _mapper: SQLAlchemy mapper (unused).
        _conn: SQLAlchemy connection (unused).
        _target: The :class:`AuditLog` row about to be flushed.

    Raises:
        AuditIntegrityError: Always.
    """
    raise AuditIntegrityError("AuditLog is append-only — UPDATE is not allowed")


@event.listens_for(AuditLog, "before_delete", propagate=True)
def _block_audit_delete(  # pyright: ignore[reportUnusedFunction]
    _mapper: Any, _conn: Any, _target: AuditLog
) -> None:
    """Forbid deletes on audit rows unless inside the cleanup scope.

    Args:
        _mapper: SQLAlchemy mapper (unused).
        _conn: SQLAlchemy connection (unused).
        _target: The :class:`AuditLog` row about to be deleted.

    Raises:
        AuditIntegrityError: When called outside
            :func:`_allow_audit_mutation`.
    """
    if not _audit_mutation_allowed.get():
        raise AuditIntegrityError(
            "AuditLog is append-only — DELETE only allowed via cleanup_old_entries()"
        )


def _encode_detail(detail: str | dict[str, Any] | None) -> str | None:
    """Normalise ``detail`` into the ``Text`` column representation.

    Args:
        detail: ``None``, a plain string (legacy call sites), or a
            JSON-encodable dict.

    Returns:
        str | None: JSON-encoded string for dict input, the raw
            string for string input, ``None`` passthrough.
    """
    if detail is None or isinstance(detail, str):
        return detail
    return json.dumps(detail, default=str, separators=(",", ":"))


def log_action(
    factory: SessionFactory,
    user_id: int,
    user_email: str,
    action: str,
    target: str,
    detail: str | dict[str, Any] | None = None,
    *,
    actor_role: str = "user",
    client_ip: str | None = None,
    workspace_id: int = 1,
) -> None:
    """Write a single audit entry.

    Synchronous quick INSERT. Call after a successful write
    operation. The HTTP-layer wrapper in
    :mod:`pointlessql.api.main` runs this via
    :func:`asyncio.to_thread` so the request coroutine is not
    blocked by the DB round-trip.

    Args:
        factory: SQLAlchemy session factory.
        user_id: ID of the acting user (``0`` for system-generated
            rows like rate-limit rejections).
        user_email: Email of the acting user (snapshot).
        action: Short verb (e.g. ``update_catalog``,
            ``grant_permission``).
        target: Identifier of the affected resource (e.g.
            ``catalog:my_catalog``).
        detail: Optional extra context. Dicts are JSON-encoded;
            strings are stored verbatim for backwards compatibility.
            When ``settings.audit.redact_detail_payloads`` is True
            the dict is piped through
            :func:`pointlessql.services.pii.redact_audit_detail`
            first so PII-keyed values land redacted at rest.
        actor_role: Role of the acting user at time of action —
            ``admin``, ``user``, or ``system`` (the last reserved
            for middleware-generated rows).
        client_ip: IPv4 or IPv6 address of the requesting client,
            or ``None`` for background / CLI operations.
        workspace_id: Workspace this action was taken in.  Defaults
            to ``1`` (seeded default workspace) so non-HTTP callers
            (CLI, scheduler, fixtures, tests) keep working without
            explicit threading; HTTP routes pass
            ``request.state.workspace_id`` for proper isolation.
    """
    from pointlessql.config import get_settings

    settings = get_settings()
    if settings.audit.redact_detail_payloads:
        from pointlessql.services.pii import redact_audit_detail

        detail = redact_audit_detail(
            detail,
            mode=settings.audit.pii_mode,
            session_factory=factory,
        )
    encoded = _encode_detail(detail)
    with factory() as session:
        entry = AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            user_email=user_email,
            actor_role=actor_role,
            action=action,
            target=target,
            client_ip=client_ip,
            detail=encoded,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(entry)
        session.commit()
        logger.debug("audit: %s %s %s", user_email, action, target)


def cleanup_old_entries(
    factory: SessionFactory,
    retention_days: int,
) -> int:
    """Delete audit rows older than ``retention_days``.

    Opens the :func:`_allow_audit_mutation` ContextVar scope so the
    ORM guard does not fire. Never raises — SQLAlchemy errors are
    logged and an exit code of ``0`` signals "kept zero rows"; this
    matches shoreguard-fresh's "audit writes must never take the
    app down" posture.

    Args:
        factory: SQLAlchemy session factory.
        retention_days: Maximum row age to keep. Rows whose
            ``created_at`` is strictly older than
            ``now - retention_days`` are deleted.

    Returns:
        int: Number of rows deleted (``0`` on error or when the
            table was already within the retention window).
    """
    if retention_days <= 0:
        # ``0`` or negative disables retention entirely — keep every
        # row forever.
        return 0
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=retention_days)
    try:
        with factory() as session, _allow_audit_mutation():
            stale = session.scalars(select(AuditLog).where(AuditLog.created_at < cutoff)).all()
            count = len(stale)
            for entry in stale:
                session.delete(entry)
            session.commit()
            if count:
                logger.info(
                    "audit: pruned %d row(s) older than %d day(s)",
                    count,
                    retention_days,
                )
            return count
    except Exception:  # noqa: BLE001 — cleanup must never crash the scheduler loop
        logger.warning(
            "audit: cleanup_old_entries failed (retention=%d)",
            retention_days,
            exc_info=True,
        )
        return 0
