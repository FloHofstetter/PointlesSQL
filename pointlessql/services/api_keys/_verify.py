"""Bearer-token verification + scope rechecks.

:func:`verify_bearer` is the request hot path; it reads/writes the
shared cache from :mod:`._cache`.  The two ``is_*`` helpers are
defensive scope rechecks used by the role dependencies when a cached
:class:`KeyEntry` is unavailable.
"""

from __future__ import annotations

import hmac
import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from pointlessql.models import ApiKey
from pointlessql.services.api_keys._cache import (
    CACHE_TTL_SECONDS,
    KeyEntry,
    as_aware_utc,
    hash_secret,
    resolve_cache,
)
from pointlessql.services.api_keys._token_format import parse_v1_token
from pointlessql.types import SessionFactory

logger = logging.getLogger(__name__)


def _emit_auth_denied_audit(
    session_factory: SessionFactory,
    row: ApiKey,
    action: str,
    detail: dict[str, Any],
) -> None:
    """Best-effort audit row for a rejected Bearer attempt.

    quarantine / expiry / post-grace-rotation rejections
    each emit a distinct ``api_key.auth_denied.*`` action so admins
    can debug "why is my key suddenly failing".  Audit failures are
    swallowed: a broken audit table must never break auth itself.

    Args:
        session_factory: Sessionmaker for the audit DB.
        row: The ``ApiKey`` row that was matched but rejected.
        action: Audit action verb, e.g. ``api_key.auth_denied.expired``.
        detail: JSON-serialisable extra context.
    """
    # Local import: services/audit pulls in the audit-write surface
    # which itself imports the api_keys service in some legacy paths;
    # top-level import would create a cycle on cold start.
    from pointlessql.services.audit import _core as audit_core

    try:
        # SessionFactory is a runtime-compatible Protocol over
        # ``sessionmaker[Session]`` (both produce a session when
        # called).  Pyright treats them as distinct nominal types;
        # ``cast`` is the boundary annotation, not a runtime change.
        from typing import cast as _cast

        from sqlalchemy.orm import Session, sessionmaker

        audit_core.log_action(
            _cast(sessionmaker[Session], session_factory),
            user_id=0,
            user_email=f"api_key:{row.name}",
            action=action,
            target=f"api_key:{row.name}",
            detail=detail,
            actor_role="system",
            workspace_id=int(row.workspace_id),
        )
    except Exception:  # noqa: BLE001 — audit must never break auth
        logger.debug(
            "Failed to emit auth-denied audit for api_key %s (%s)",
            row.name,
            action,
            exc_info=True,
        )

def verify_bearer(
    authorization_header: str | None,
    session_factory: SessionFactory | None,
) -> KeyEntry | None:
    """Match an ``Authorization: Bearer <secret>`` header against the store.

    Cache-aware: a successful resolution is cached for 60 s keyed on
    the SHA-256 of the presented secret, so repeated requests from
    the same Bearer don't roundtrip the DB.

    Args:
        authorization_header: Raw value of the ``Authorization``
            header, or ``None`` when absent.
        session_factory: Sessionmaker callable.  ``None`` short-circuits
            to ``None`` (gate disabled / app not yet wired).

    Returns:
        The matching :class:`KeyEntry` or ``None`` when the header is
        missing, malformed, secret unknown, key revoked, or factory
        unavailable.  Tokens that match the v1 prefix shape but carry
        a wrong CRC are rejected before any DB roundtrip.
    """
    if session_factory is None or not authorization_header:
        return None
    header = authorization_header.strip()
    if not header.lower().startswith("bearer "):
        return None
    presented = header[7:].strip()
    if not presented:
        return None
    # short-circuit v1-shaped tokens with bad CRC before
    # the DB lookup.  A v1 prefix means the issuer is unambiguous; a
    # mismatched CRC is a typo / truncation / tampered token, never a
    # legacy key.  Legacy tokens (no ``pql_*_v1_`` prefix) are
    # detected by ``parse_v1_token`` returning ``None`` and fall
    # through to the SHA-256 lookup path unchanged.
    if presented.startswith("pql_") and "_v1_" in presented[:14]:
        if parse_v1_token(presented) is None:
            return None
    digest = hash_secret(presented)

    cached = resolve_cache.get(digest)
    now = time.monotonic()
    if cached is not None:
        entry, expires_at = cached
        if expires_at > now:
            return entry
        # Stale entry — drop and re-resolve so a revocation lands
        # within at most 60 s without an explicit invalidate.
        del resolve_cache[digest]

    with session_factory() as session:
        row = session.scalar(
            select(ApiKey).where(ApiKey.secret_hash == digest, ApiKey.revoked_at.is_(None))
        )
        if row is None:
            return None
        # Constant-time double-check on the hash even though SQL did
        # equality — keeps the surface uniform with the env-var path.
        if not hmac.compare_digest(row.secret_hash, digest):
            return None
        # lifecycle gates.  Each returns ``None`` (i.e. 401
        # at the middleware) and emits an audit row so admins can
        # debug rejected requests.  Audit failures are swallowed so a
        # broken audit table can never break auth.
        now_dt = datetime.now(UTC)
        if getattr(row, "quarantined_at", None) is not None and getattr(
            row, "quarantine_reason", None
        ):
            _emit_auth_denied_audit(
                session_factory,
                row,
                "api_key.auth_denied.quarantined",
                {"quarantine_reason": str(row.quarantine_reason)},
            )
            return None
        expires_at = as_aware_utc(getattr(row, "expires_at", None))
        if expires_at is not None and expires_at <= now_dt:
            _emit_auth_denied_audit(
                session_factory,
                row,
                "api_key.auth_denied.expired",
                {"expired_at": expires_at.isoformat()},
            )
            return None
        # Rotation: a predecessor key (rotated_at set) is valid only
        # while inside its grace window.  After the window closes, it
        # behaves like a soft-revoked key.
        rotated_at = as_aware_utc(getattr(row, "rotated_at", None))
        if rotated_at is not None:
            grace_until = as_aware_utc(getattr(row, "grace_until", None))
            if grace_until is None or grace_until <= now_dt:
                _emit_auth_denied_audit(
                    session_factory,
                    row,
                    "api_key.auth_denied.rotated",
                    {
                        "rotated_at": rotated_at.isoformat(),
                        "grace_until": grace_until.isoformat() if grace_until else None,
                    },
                )
                return None
        entry = KeyEntry(
            name=row.name,
            supervisor=bool(row.supervisor),
            auditor=bool(row.auditor),
            lineage_inbound=bool(getattr(row, "lineage_inbound", False)),
            analyst=bool(getattr(row, "analyst", False)),
            sql_execute=bool(getattr(row, "sql_execute", False)),
            workspace_id=int(row.workspace_id),
            id=int(row.id),
            created_by_user_id=row.created_by_user_id,
        )
        # Best-effort last-used update — failures don't affect auth.
        try:
            session.execute(
                update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=datetime.now(UTC))
            )
            session.commit()
        except Exception:  # noqa: BLE001 — auditing is non-critical
            session.rollback()
            logger.debug(
                "Failed to update last_used_at for api_key %s",
                row.name,
                exc_info=True,
            )

    resolve_cache[digest] = (entry, now + CACHE_TTL_SECONDS)
    return entry

def is_supervisor(session_factory: SessionFactory, *, name: str) -> bool:
    """Return ``True`` when the named key carries the supervisor scope.

    Used by :func:`pointlessql.api.dependencies.require_supervisor`
    when the request was authenticated via a Bearer key but the
    cached entry isn't available (defensive recheck).

    Args:
        session_factory: Sessionmaker callable.
        name: API-key name.

    Returns:
        ``True`` when the key exists, is not revoked, and has
        ``supervisor=True``.
    """
    with session_factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name, ApiKey.revoked_at.is_(None)))
        return bool(row and row.supervisor)

def is_auditor(session_factory: SessionFactory, *, name: str) -> bool:
    """Return ``True`` when the named key carries the auditor scope.

     sibling to :func:`is_supervisor`.  Defensive recheck
    used by :func:`pointlessql.api.dependencies.require_auditor` when
    the cached :class:`KeyEntry` is unavailable.

    Args:
        session_factory: Sessionmaker callable.
        name: API-key name.

    Returns:
        ``True`` when the key exists, is not revoked, and has
        ``auditor=True``.
    """
    with session_factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name, ApiKey.revoked_at.is_(None)))
        return bool(row and row.auditor)
