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
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select, update

from pointlessql.models import ApiKey

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
    workspace_id: int = 1


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


def parse_keys(raw: str | None) -> dict[str, tuple[str, bool, bool, bool]]:
    """Parse ``POINTLESSQL_API_KEYS`` env value.

    Format:

    - ``name:secret`` — non-privileged agent key (legacy default).
    - ``name:secret:supervisor`` — supervisor scope.
    - ``name:secret:auditor`` — auditor scope.
    - ``name:secret:lineage_inbound`` — Phase-40 federation scope.

    Anything else as the third token raises so a typo can't silently
    grant a privileged scope.  A single env entry maps to exactly one
    scope; a key needing multiple scopes is provisioned via the admin
    JSON CRUD instead.

    Args:
        raw: The raw env-var value, or ``None`` when unset.

    Returns:
        Mapping ``{name: (secret, supervisor, auditor, lineage_inbound)}``.
        Empty when *raw* is missing or whitespace-only.

    Raises:
        ValueError: When a pair lacks a colon, has empty name/secret,
            duplicates an earlier name, or carries an unknown third
            token.
    """
    if raw is None or not raw.strip():
        return {}
    out: dict[str, tuple[str, bool, bool, bool]] = {}
    for chunk in raw.replace(",", "\n").splitlines():
        pair = chunk.strip()
        if not pair:
            continue
        parts = pair.split(":")
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(
                f"POINTLESSQL_API_KEYS entry {pair!r} must be in "
                f"'name:secret', 'name:secret:supervisor', "
                f"'name:secret:auditor', or "
                f"'name:secret:lineage_inbound' form"
            )
        name = parts[0].strip()
        secret = parts[1].strip()
        if not name or not secret:
            raise ValueError(f"POINTLESSQL_API_KEYS entry {pair!r} has an empty name or secret")
        supervisor = False
        auditor = False
        lineage_inbound = False
        if len(parts) == 3:
            scope = parts[2].strip().lower()
            if scope == "supervisor":
                supervisor = True
            elif scope == "auditor":
                auditor = True
            elif scope == "lineage_inbound":
                lineage_inbound = True
            else:
                raise ValueError(
                    f"POINTLESSQL_API_KEYS entry {pair!r} has unknown "
                    f"scope {scope!r} — only 'supervisor', 'auditor', "
                    f"and 'lineage_inbound' are recognised"
                )
        if name in out:
            raise ValueError(f"POINTLESSQL_API_KEYS entry name {name!r} is duplicated")
        out[name] = (secret, supervisor, auditor, lineage_inbound)
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
        for name, (secret, supervisor, auditor, lineage_inbound) in parsed.items():
            if name in existing_names:
                continue
            session.add(
                ApiKey(
                    name=name,
                    secret_hash=_hash_secret(secret),
                    secret_prefix=secret[:8],
                    supervisor=supervisor,
                    auditor=auditor,
                    lineage_inbound=lineage_inbound,
                    created_at=datetime.now(UTC),
                    workspace_id=1,
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
    created_by_user_id: int | None = None,
    workspace_id: int = 1,
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
        created_by_user_id: Admin who created the key.  ``None`` for
            CLI-provisioned or env-var-bootstrapped keys.
        workspace_id: Workspace the key pins to.  Defaults to the
            seeded ``default`` workspace (id=1) so single-tenant
            installs and existing automation keep working without
            naming a workspace explicitly.  The admin UI exposes a
            chooser at creation time.

    Returns:
        ``(row, plaintext_secret)``.  The row is detached after
        commit so the caller can serialise it without holding the
        session open.

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
    plaintext = secrets.token_urlsafe(32)
    with session_factory() as session:
        existing = session.scalar(select(ApiKey).where(ApiKey.name == cleaned))
        if existing is not None:
            raise ValueError(f"API key {cleaned!r} already exists")
        row = ApiKey(
            name=cleaned,
            secret_hash=_hash_secret(plaintext),
            secret_prefix=plaintext[:8],
            supervisor=supervisor,
            auditor=auditor,
            lineage_inbound=lineage_inbound,
            created_at=datetime.now(UTC),
            created_by_user_id=created_by_user_id,
            workspace_id=workspace_id,
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
        unavailable.
    """
    if session_factory is None or not authorization_header:
        return None
    header = authorization_header.strip()
    if not header.lower().startswith("bearer "):
        return None
    presented = header[7:].strip()
    if not presented:
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
        entry = KeyEntry(
            name=row.name,
            supervisor=bool(row.supervisor),
            auditor=bool(row.auditor),
            lineage_inbound=bool(getattr(row, "lineage_inbound", False)),
            workspace_id=int(row.workspace_id),
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
