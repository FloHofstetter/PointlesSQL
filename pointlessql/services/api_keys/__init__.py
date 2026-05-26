"""DB-backed Bearer-token API-key store.

API keys are persisted in the ``api_keys`` table so admins can
rotate them without a process restart and so the ``supervisor``
scope gating supervisor-only routes lives next to the secret it
authorises.

The legacy ``POINTLESSQL_API_KEYS`` env var stays valid as a
*bootstrap* path: every server start spills declared
``name:secret[:supervisor]`` pairs into the table idempotently via
:func:`bootstrap_from_env`, so clean-machine ``docker-compose``
deployments without an admin UI mounted still work.

Token verification uses :func:`hashlib.sha256` on the presented
secret and compares against the indexed ``secret_hash`` column.
API keys are high-entropy random tokens; SHA-256 is enough — bcrypt
would only buy resistance against brute-force on weak secrets, and
we control the secrets here.

Cache layer: ``_resolve_cache`` is an in-memory ``dict`` mapping
the SHA-256 hex digest to a ``KeyEntry`` (TTL 60 s). Successful
auths reuse the cached entry so the hot path doesn't hit the DB
once per request. Cache is invalidated on
:func:`create_api_key`, :func:`revoke_api_key`, and process
restart.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from sqlalchemy import select, update

from pointlessql.models import ApiKey
from pointlessql.services.api_keys._token_format import (
    display_prefix_for,
    generate_v1_token,
    parse_v1_token,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeyEntry:
    """The fields the middleware needs to authorise a Bearer request.

    Every API key pins to exactly one workspace, and Bearer-authed
    requests inherit that workspace as their resolved context.
    Existing keys backfill to the default workspace (id=1) by the
    bootstrap migration so this attribute is always populated.
    """

    name: str
    supervisor: bool
    auditor: bool = False
    lineage_inbound: bool = False
    analyst: bool = False
    sql_execute: bool = False
    workspace_id: int = 1
    id: int = 0
    created_by_user_id: int | None = None


# ---------------------------------------------------------------------------
# Internal cache (TTL 60 s)
# ---------------------------------------------------------------------------


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


_CACHE_TTL_SECONDS = 60.0
_resolve_cache: dict[str, tuple[KeyEntry, float]] = {}


def _hash_secret(secret: str) -> str:
    """Return the SHA-256 hex digest of *secret* (UTF-8 encoded)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """Coerce a possibly-naive timestamp to a UTC-aware ``datetime``.

    SQLite returns ``DateTime(timezone=True)`` columns as naive ``datetime``
    on read; Postgres returns them aware.  lifecycle gates
    compare against ``datetime.now(UTC)`` (aware), which would raise
    ``TypeError`` on the SQLite path.  Treating naive timestamps as UTC
    matches what we wrote and unifies the two dialects.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _emit_auth_denied_audit(
    session_factory: _SessionFactory,
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
        # _SessionFactory is a runtime-compatible Protocol over
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


def invalidate_cache() -> None:
    """Clear the in-memory verify-bearer cache.

    Call after any admin write (:func:`create_api_key`,
    :func:`revoke_api_key`) so a freshly-rotated key takes effect on
    the next request rather than after the TTL.
    """
    _resolve_cache.clear()


# ---------------------------------------------------------------------------
# Env-var bootstrap (back-compat with the legacy env-var-only mode)
# ---------------------------------------------------------------------------


def parse_keys(raw: str | None) -> dict[str, tuple[str, bool, bool, bool, bool, bool]]:
    """Parse ``POINTLESSQL_API_KEYS`` env value.

    Format:

    - ``name:secret`` — non-privileged agent key (legacy default).
    - ``name:secret:supervisor`` — supervisor scope.
    - ``name:secret:auditor`` — auditor scope.
    - ``name:secret:lineage_inbound`` — federation scope.
    - ``name:secret:analyst`` — Lens read-only Q&A scope.
    - ``name:secret:sql_execute`` — public SQL API scope.

    Anything else as the third token raises so a typo can't silently
    grant a privileged scope.  A single env entry maps to exactly one
    scope; a key needing multiple scopes is provisioned via the admin
    JSON CRUD instead.

    Args:
        raw: The raw env-var value, or ``None`` when unset.

    Returns:
        Mapping ``{name: (secret, supervisor, auditor, lineage_inbound,
        analyst, sql_execute)}``.  Empty when *raw* is missing or
        whitespace-only.

    Raises:
        ValueError: When a pair lacks a colon, has empty name/secret,
            duplicates an earlier name, or carries an unknown third
            token.
    """
    if raw is None or not raw.strip():
        return {}
    out: dict[str, tuple[str, bool, bool, bool, bool, bool]] = {}
    for chunk in raw.replace(",", "\n").splitlines():
        pair = chunk.strip()
        if not pair:
            continue
        parts = pair.split(":")
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(
                f"POINTLESSQL_API_KEYS entry {pair!r} must be in "
                f"'name:secret', 'name:secret:supervisor', "
                f"'name:secret:auditor', "
                f"'name:secret:lineage_inbound', "
                f"'name:secret:analyst', or "
                f"'name:secret:sql_execute' form"
            )
        name = parts[0].strip()
        secret = parts[1].strip()
        if not name or not secret:
            raise ValueError(f"POINTLESSQL_API_KEYS entry {pair!r} has an empty name or secret")
        supervisor = False
        auditor = False
        lineage_inbound = False
        analyst = False
        sql_execute = False
        if len(parts) == 3:
            scope = parts[2].strip().lower()
            if scope == "supervisor":
                supervisor = True
            elif scope == "auditor":
                auditor = True
            elif scope == "lineage_inbound":
                lineage_inbound = True
            elif scope == "analyst":
                analyst = True
            elif scope == "sql_execute":
                sql_execute = True
            else:
                raise ValueError(
                    f"POINTLESSQL_API_KEYS entry {pair!r} has unknown "
                    f"scope {scope!r} — only 'supervisor', 'auditor', "
                    f"'lineage_inbound', 'analyst', and 'sql_execute' "
                    f"are recognised"
                )
        if name in out:
            raise ValueError(f"POINTLESSQL_API_KEYS entry name {name!r} is duplicated")
        out[name] = (secret, supervisor, auditor, lineage_inbound, analyst, sql_execute)
    return out


def bootstrap_from_env(session_factory: _SessionFactory, env: dict[str, str] | None = None) -> int:
    """Idempotently spill ``POINTLESSQL_API_KEYS`` pairs into the DB.

    Called once at server startup.  For each parsed pair, if no row
    exists with that name the key is inserted (with the supervisor
    flag from the env value).  When a row already exists the env-var
    is ignored — the DB is the single source of truth, so admins
    rotating via the UI are not silently overwritten by a stale env
    value.

    Args:
        session_factory: Sessionmaker callable bound to the metadata
            DB engine.
        env: Optional override for tests.  Defaults to
            :data:`os.environ`.

    Returns:
        Number of new rows inserted.  :func:`parse_keys` raises
        :class:`ValueError` for malformed env values; the call chain
        propagates so a typo fails fast at startup instead of
        mid-request.
    """
    source = env if env is not None else os.environ
    parsed = parse_keys(source.get("POINTLESSQL_API_KEYS"))
    if not parsed:
        return 0
    inserted = 0
    with session_factory() as session:
        existing_names = {n for (n,) in session.execute(select(ApiKey.name)).all()}
        for name, (
            secret,
            supervisor,
            auditor,
            lineage_inbound,
            analyst,
            sql_execute,
        ) in parsed.items():
            if name in existing_names:
                continue
            parsed_v1 = parse_v1_token(secret)
            if parsed_v1 is not None:
                token_env_for_row = parsed_v1[0]
                token_format_for_row = "v1"
            else:
                token_env_for_row = "legacy"
                token_format_for_row = "legacy"
            session.add(
                ApiKey(
                    name=name,
                    secret_hash=_hash_secret(secret),
                    secret_prefix=display_prefix_for(secret),
                    supervisor=supervisor,
                    auditor=auditor,
                    lineage_inbound=lineage_inbound,
                    analyst=analyst,
                    sql_execute=sql_execute,
                    created_at=datetime.now(UTC),
                    workspace_id=1,
                    token_format=token_format_for_row,
                    token_env=token_env_for_row,
                )
            )
            inserted += 1
        if inserted:
            session.commit()
    if inserted:
        invalidate_cache()
        logger.info("Bootstrapped %d API keys from POINTLESSQL_API_KEYS", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------


def create_api_key(
    session_factory: _SessionFactory,
    *,
    name: str,
    supervisor: bool = False,
    auditor: bool = False,
    lineage_inbound: bool = False,
    analyst: bool = False,
    sql_execute: bool = False,
    created_by_user_id: int | None = None,
    workspace_id: int = 1,
    env: Literal["live", "test"] = "live",
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """Generate + persist a fresh Bearer-token credential.

    The plaintext secret is returned exactly once — callers must
    surface it to the admin immediately because it isn't recoverable
    from the DB.

    Args:
        session_factory: Sessionmaker callable.
        name: Unique label (max 64 chars).
        supervisor: When ``True``, the key may invoke supervisor-scope
            routes.
        auditor: When ``True``, the key may invoke audit-read routes.
            Independent of ``supervisor``.
        lineage_inbound: When ``True``, the key may POST OpenLineage
            events to ``/api/lineage/openlineage``.  Independent of
            the other scopes.
        analyst: When ``True``, the key may invoke the Lens read-only
            Q&A surface (``/api/lens/*`` and the MCP server).
            Promotes up the ladder to also pass auditor gates.
        sql_execute: When ``True``, the key may invoke the public
            DBX-compatible SQL Statement Execution API
            (``/api/2.0/sql/statements``).  Independent of every
            other scope.
        created_by_user_id: Admin who created the key.  ``None`` for
            CLI-provisioned or env-var-bootstrapped keys.
        workspace_id: Workspace the key pins to.  Defaults to the
            seeded ``default`` workspace (id=1) so single-tenant
            installs and existing automation keep working without
            naming a workspace explicitly.  The admin UI exposes a
            chooser at creation time.
        env: One of ``'live'`` or ``'test'``.  Embedded in the v1
            token format (``pql_{env}_v1_...``) so test keys are
            visually distinct in audit logs and git leaks.  Defaults
            to ``'live'`` so existing call-sites keep producing
            production-grade keys without an explicit argument.
        expires_at: Optional TTL deadline.  ``None`` (the default)
            means the key never expires, matching the original
            no-expiry behaviour.  Aware ``datetime`` recommended;
            naive values
            are treated as UTC by the verify path.

    Returns:
        ``(row, plaintext_secret)``.  The row is detached after
        commit so the caller can serialise it without holding the
        session open.  The plaintext is the full
        ``pql_{env}_v1_{body40}_{crc8}`` token; persist it now or
        lose it.

    Raises:
        ValueError: When *name* is blank, longer than 64 chars, or
            already exists in the table (duplicate names would
            otherwise raise ``IntegrityError`` from the UNIQUE
            constraint, which is harder for the CLI / HTTP layer to
            present cleanly).
    """
    cleaned = name.strip()
    if not cleaned or len(cleaned) > 64:
        raise ValueError("API key name must be a non-empty string up to 64 chars")
    plaintext = generate_v1_token(env)
    with session_factory() as session:
        existing = session.scalar(select(ApiKey).where(ApiKey.name == cleaned))
        if existing is not None:
            raise ValueError(f"API key {cleaned!r} already exists")
        row = ApiKey(
            name=cleaned,
            secret_hash=_hash_secret(plaintext),
            secret_prefix=display_prefix_for(plaintext),
            supervisor=supervisor,
            auditor=auditor,
            lineage_inbound=lineage_inbound,
            analyst=analyst,
            sql_execute=sql_execute,
            created_at=datetime.now(UTC),
            created_by_user_id=created_by_user_id,
            workspace_id=workspace_id,
            token_format="v1",
            token_env=env,
            expires_at=expires_at,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    invalidate_cache()
    return row, plaintext


def revoke_api_key(session_factory: _SessionFactory, *, name: str) -> bool:
    """Mark *name* as revoked.  Returns ``True`` when a row was updated."""
    with session_factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(UTC)
        session.commit()
    invalidate_cache()
    return True


def list_api_keys(
    session_factory: _SessionFactory, *, include_revoked: bool = False
) -> list[ApiKey]:
    """Return all keys (newest first) for the admin listing page.

    Args:
        session_factory: Sessionmaker callable.
        include_revoked: When ``True`` revoked keys are included.

    Returns:
        Detached ORM rows ordered by ``created_at DESC``.
    """
    with session_factory() as session:
        stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
        if not include_revoked:
            stmt = stmt.where(ApiKey.revoked_at.is_(None))
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


# ---------------------------------------------------------------------------
# lifecycle admin helpers
# ---------------------------------------------------------------------------


def rotate_api_key(
    session_factory: _SessionFactory,
    *,
    name: str,
    successor_name: str | None = None,
    grace_seconds: int = 86_400,
    created_by_user_id: int | None = None,
) -> tuple[ApiKey, str] | None:
    """Mint a successor key with the predecessor's scopes + env.

    The predecessor row stays valid until ``now() + grace_seconds``
    so clients can pick up the new secret without an auth gap.  After
    the grace window closes the predecessor's auth path returns 401
    + ``api_key.auth_denied.rotated``.

    Args:
        session_factory: Sessionmaker callable.
        name: Predecessor key name.
        successor_name: Optional name for the successor; defaults to
            ``f"{name}-rotated-{epoch}"``.
        grace_seconds: Window in seconds during which the predecessor
            stays valid.  Defaults to 24 h.
        created_by_user_id: Admin who triggered the rotation.

    Returns:
        ``(successor_row, plaintext)`` when the predecessor was found
        and rotated; ``None`` when the predecessor doesn't exist or
        is already revoked / rotated.
    """
    with session_factory() as session:
        pred = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if pred is None or pred.revoked_at is not None or pred.rotated_at is not None:
            return None
        pred_env = getattr(pred, "token_env", "live") or "live"
        env_for_successor: Literal["live", "test"] = "test" if pred_env == "test" else "live"
        successor_name_resolved = successor_name or (
            f"{name}-rotated-{int(datetime.now(UTC).timestamp())}"
        )
        plaintext = generate_v1_token(env_for_successor)
        now_dt = datetime.now(UTC)
        successor = ApiKey(
            name=successor_name_resolved,
            secret_hash=_hash_secret(plaintext),
            secret_prefix=display_prefix_for(plaintext),
            supervisor=bool(pred.supervisor),
            auditor=bool(pred.auditor),
            lineage_inbound=bool(getattr(pred, "lineage_inbound", False)),
            analyst=bool(getattr(pred, "analyst", False)),
            sql_execute=bool(getattr(pred, "sql_execute", False)),
            created_at=now_dt,
            created_by_user_id=created_by_user_id,
            workspace_id=int(pred.workspace_id),
            token_format="v1",
            token_env=env_for_successor,
            expires_at=_as_aware_utc(getattr(pred, "expires_at", None)),
            rotated_from_id=int(pred.id),
        )
        session.add(successor)
        # Mark predecessor.  Grace window keeps it valid temporarily.
        pred.rotated_at = now_dt
        pred.grace_until = now_dt + timedelta(seconds=grace_seconds)
        session.commit()
        session.refresh(successor)
        session.expunge(successor)
    invalidate_cache()
    return successor, plaintext


def quarantine_api_key(session_factory: _SessionFactory, *, name: str, reason: str) -> bool:
    """Soft-disable a key.  Returns ``True`` when applied.

    Quarantined keys return 401 + ``api_key.auth_denied.quarantined``
    on every auth attempt, but the row is preserved so audit
    attribution keeps resolving and ``unquarantine_api_key`` can lift
    the block cleanly.

    Args:
        session_factory: Sessionmaker callable.
        name: Key name.
        reason: Short admin note (≤ 200 chars).  Required — the
            verify path treats ``quarantine_reason IS NULL`` as
            "not quarantined" so a stray timestamp doesn't lock out
            a key by accident.

    Returns:
        ``True`` on success; ``False`` when the key is missing,
        revoked, or already quarantined.

    Raises:
        ValueError: When *reason* is empty after trimming.
    """
    cleaned = reason.strip()[:200]
    if not cleaned:
        raise ValueError("quarantine reason must be a non-empty string")
    with session_factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if row is None or row.revoked_at is not None or row.quarantined_at is not None:
            return False
        row.quarantined_at = datetime.now(UTC)
        row.quarantine_reason = cleaned
        session.commit()
    invalidate_cache()
    return True


def unquarantine_api_key(session_factory: _SessionFactory, *, name: str) -> bool:
    """Clear quarantine on *name*.  Returns ``True`` when applied."""
    with session_factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if row is None or row.quarantined_at is None:
            return False
        row.quarantined_at = None
        row.quarantine_reason = None
        session.commit()
    invalidate_cache()
    return True


def update_api_key_ttl(
    session_factory: _SessionFactory,
    *,
    name: str,
    expires_at: datetime | None,
) -> bool:
    """Update a key's ``expires_at`` (None = no expiry).  ``True`` on success."""
    with session_factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if row is None or row.revoked_at is not None:
            return False
        row.expires_at = expires_at
        # Clear the expiry-warning dedup marker so the sweep can fire
        # again with the new deadline.
        row.expiry_warned_at = None
        session.commit()
    invalidate_cache()
    return True


# ---------------------------------------------------------------------------
# Verify (called by middleware)
# ---------------------------------------------------------------------------


def verify_bearer(
    authorization_header: str | None,
    session_factory: _SessionFactory | None,
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
    digest = _hash_secret(presented)

    cached = _resolve_cache.get(digest)
    now = time.monotonic()
    if cached is not None:
        entry, expires_at = cached
        if expires_at > now:
            return entry
        # Stale entry — drop and re-resolve so a revocation lands
        # within at most 60 s without an explicit invalidate.
        del _resolve_cache[digest]

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
        expires_at = _as_aware_utc(getattr(row, "expires_at", None))
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
        rotated_at = _as_aware_utc(getattr(row, "rotated_at", None))
        if rotated_at is not None:
            grace_until = _as_aware_utc(getattr(row, "grace_until", None))
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

    _resolve_cache[digest] = (entry, now + _CACHE_TTL_SECONDS)
    return entry


def is_supervisor(session_factory: _SessionFactory, *, name: str) -> bool:
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


def is_auditor(session_factory: _SessionFactory, *, name: str) -> bool:
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
