"""API-key CRUD, env-var bootstrap, rotation, and lifecycle writes.

Every mutating helper invalidates the shared verify cache from
:mod:`._cache` so a freshly-created / revoked / rotated key takes
effect on the next request.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select

from pointlessql.models import ApiKey
from pointlessql.services.api_keys._cache import (
    as_aware_utc,
    hash_secret,
    invalidate_cache,
)
from pointlessql.services.api_keys._token_format import (
    display_prefix_for,
    generate_v1_token,
    parse_v1_token,
)
from pointlessql.types import SessionFactory

logger = logging.getLogger(__name__)


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

def bootstrap_from_env(session_factory: SessionFactory, env: dict[str, str] | None = None) -> int:
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
                    secret_hash=hash_secret(secret),
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

def create_api_key(
    session_factory: SessionFactory,
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
            secret_hash=hash_secret(plaintext),
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

def revoke_api_key(session_factory: SessionFactory, *, name: str) -> bool:
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
    session_factory: SessionFactory, *, include_revoked: bool = False
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

def rotate_api_key(
    session_factory: SessionFactory,
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
            secret_hash=hash_secret(plaintext),
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
            expires_at=as_aware_utc(getattr(pred, "expires_at", None)),
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

def quarantine_api_key(session_factory: SessionFactory, *, name: str, reason: str) -> bool:
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

def unquarantine_api_key(session_factory: SessionFactory, *, name: str) -> bool:
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
    session_factory: SessionFactory,
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
