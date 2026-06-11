"""Secret-scope CRUD + permission resolution over the Fernet vault.

Business logic behind the ``/api/secrets`` surface.  Values are
encrypted with :func:`pointlessql.services.secrets.encrypt_value`
before they touch the session and decrypted only by
:func:`get_secret_value` — the single audited runtime read path.

Permission model (mirrors the Databricks secrets ACL ladder):

* ``READ``   — list keys, read values at runtime.
* ``WRITE``  — ``READ`` plus put/delete secrets.
* ``MANAGE`` — ``WRITE`` plus ACL management and scope deletion.

Admins implicitly hold ``MANAGE`` on every scope; the creator of a
scope receives an explicit ``MANAGE`` grant in the same transaction.
The ``*`` principal extends a grant to every authenticated user of
the scope's workspace.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select

from pointlessql.models.secret_scopes import (
    SECRET_SCOPE_PERMISSIONS,
    SecretScope,
    SecretScopeAcl,
    SecretScopeSecret,
)
from pointlessql.services.secrets import decrypt_value, encrypt_value

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

MAX_SECRET_BYTES = 128 * 1024
"""Upper bound on a secret value's UTF-8 size (matches Databricks' 128 KiB)."""

SECRET_REFERENCE_RE = re.compile(r"\{\{\s*secrets/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\s*\}\}")
"""Pattern of ``{{secrets/<scope>/<key>}}`` placeholders inside config strings."""


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def validate_name(value: str, *, what: str) -> str:
    """Return *value* stripped, or raise on a malformed identifier.

    Args:
        value: Candidate scope or key name.
        what: Noun used in the error message (``"scope name"`` /
            ``"secret key"``).

    Returns:
        The stripped identifier.

    Raises:
        ValueError: When the identifier is empty, too long, or uses
            characters outside ``[A-Za-z0-9_.-]``.
    """
    candidate = value.strip()
    if not _NAME_RE.match(candidate):
        raise ValueError(f"{what} must be 1-128 characters from [A-Za-z0-9_.-], got {value!r}")
    return candidate


def permission_satisfies(have: str | None, need: str) -> bool:
    """Check *have* against the strict ``READ < WRITE < MANAGE`` ladder.

    Args:
        have: Permission held by the principal (``None`` = no grant).
        need: Permission level the operation requires.

    Returns:
        ``True`` when the held permission implies the needed one.
    """
    if have is None:
        return False
    ladder = SECRET_SCOPE_PERMISSIONS
    return ladder.index(have) >= ladder.index(need)


def create_scope(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: str,
    description: str | None,
    principal: str | None,
) -> SecretScope:
    """Create a scope and grant its creator ``MANAGE``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        name: Scope identifier (validated).
        description: Optional purpose note.
        principal: Creator e-mail; when set, a ``MANAGE`` ACL row is
            written in the same transaction.

    Returns:
        The persisted scope row (detached).

    Raises:
        ValueError: On a malformed name or a name already taken in
            the workspace.
    """
    scope_name = validate_name(name, what="scope name")
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(SecretScope).where(
                SecretScope.workspace_id == workspace_id,
                SecretScope.name == scope_name,
            )
        )
        if existing is not None:
            raise ValueError(f"secret scope {scope_name!r} already exists")
        row = SecretScope(
            workspace_id=workspace_id,
            name=scope_name,
            description=description,
            created_by=principal,
            created_at=now,
        )
        session.add(row)
        session.flush()
        if principal:
            session.add(
                SecretScopeAcl(
                    scope_id=row.id,
                    principal=principal,
                    permission="MANAGE",
                    created_at=now,
                )
            )
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def get_scope(
    factory: sessionmaker[Session], *, workspace_id: int, name: str
) -> SecretScope | None:
    """Return the workspace's scope by name, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        name: Scope identifier.

    Returns:
        The detached scope row, or ``None`` when absent.
    """
    with factory() as session:
        row = session.scalar(
            select(SecretScope).where(
                SecretScope.workspace_id == workspace_id,
                SecretScope.name == name,
            )
        )
        if row is not None:
            session.expunge(row)
    return row


def list_scopes(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    principal: str | None,
    is_admin: bool,
) -> list[tuple[SecretScope, str]]:
    """List scopes visible to *principal* with their effective permission.

    Admins see every scope of the workspace at ``MANAGE``; other
    principals see exactly the scopes they hold a grant on (directly
    or via ``*``).

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.
        principal: Caller e-mail (``None`` = unauthenticated).
        is_admin: Whether the caller is a tenant admin.

    Returns:
        ``(scope, effective_permission)`` pairs ordered by name.
    """
    with factory() as session:
        scopes = list(
            session.scalars(
                select(SecretScope)
                .where(SecretScope.workspace_id == workspace_id)
                .order_by(SecretScope.name)
            )
        )
        visible: list[tuple[SecretScope, str]] = []
        for scope in scopes:
            permission = _resolve_permission_in_session(
                session, scope_id=scope.id, principal=principal, is_admin=is_admin
            )
            if permission is not None:
                session.expunge(scope)
                visible.append((scope, permission))
    return visible


def delete_scope(factory: sessionmaker[Session], *, scope_id: int) -> bool:
    """Delete a scope together with its secrets and ACLs.

    Children are deleted explicitly in the same transaction rather
    than left to the FK ``ON DELETE CASCADE`` — SQLite only honours
    that with the foreign-key pragma enabled, and ciphertext rows
    surviving their scope would be a quiet liability.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.get(SecretScope, scope_id)
        if row is None:
            return False
        session.execute(delete(SecretScopeSecret).where(SecretScopeSecret.scope_id == scope_id))
        session.execute(delete(SecretScopeAcl).where(SecretScopeAcl.scope_id == scope_id))
        session.delete(row)
        session.commit()
    return True


def _resolve_permission_in_session(
    session: Session, *, scope_id: int, principal: str | None, is_admin: bool
) -> str | None:
    """Resolve the effective permission inside an open session."""
    if is_admin:
        return "MANAGE"
    if not principal:
        return None
    rows = session.scalars(
        select(SecretScopeAcl).where(
            SecretScopeAcl.scope_id == scope_id,
            SecretScopeAcl.principal.in_([principal, "*"]),
        )
    )
    best: str | None = None
    for row in rows:
        if best is None or SECRET_SCOPE_PERMISSIONS.index(row.permission) > (
            SECRET_SCOPE_PERMISSIONS.index(best)
        ):
            best = row.permission
    return best


def resolve_permission(
    factory: sessionmaker[Session],
    *,
    scope_id: int,
    principal: str | None,
    is_admin: bool,
) -> str | None:
    """Return the strongest permission *principal* holds on a scope.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.
        principal: Caller e-mail (``None`` = unauthenticated).
        is_admin: Whether the caller is a tenant admin (implicit
            ``MANAGE``).

    Returns:
        ``"READ"`` / ``"WRITE"`` / ``"MANAGE"``, or ``None`` when the
        principal holds no grant.
    """
    with factory() as session:
        return _resolve_permission_in_session(
            session, scope_id=scope_id, principal=principal, is_admin=is_admin
        )


def put_secret(
    factory: sessionmaker[Session],
    *,
    scope_id: int,
    key: str,
    value: str,
    principal: str | None,
) -> SecretScopeSecret:
    """Create or overwrite the secret under ``(scope, key)``.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.
        key: Secret name (validated).
        value: Plaintext value; encrypted before persistence.
        principal: Writer e-mail recorded on the row.

    Returns:
        The persisted secret row (detached; carries the ciphertext).

    Raises:
        ValueError: On a malformed key or a value beyond
            :data:`MAX_SECRET_BYTES`.
    """
    secret_key = validate_name(key, what="secret key")
    if len(value.encode("utf-8")) > MAX_SECRET_BYTES:
        raise ValueError(f"secret value exceeds {MAX_SECRET_BYTES} bytes")
    token = encrypt_value(value, session_factory=factory)
    now = _utcnow()
    with factory() as session:
        row = session.scalar(
            select(SecretScopeSecret).where(
                SecretScopeSecret.scope_id == scope_id,
                SecretScopeSecret.key == secret_key,
            )
        )
        if row is None:
            row = SecretScopeSecret(
                scope_id=scope_id,
                key=secret_key,
                encrypted_value=token,
                created_by=principal,
                updated_by=principal,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.encrypted_value = token
            row.updated_by = principal
            row.updated_at = now
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_secret(factory: sessionmaker[Session], *, scope_id: int, key: str) -> bool:
    """Delete the secret under ``(scope, key)``.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.
        key: Secret name.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.scalar(
            select(SecretScopeSecret).where(
                SecretScopeSecret.scope_id == scope_id,
                SecretScopeSecret.key == key,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


def list_secret_keys(factory: sessionmaker[Session], *, scope_id: int) -> list[SecretScopeSecret]:
    """List a scope's secrets (metadata only — ciphertext stays inside).

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.

    Returns:
        Detached secret rows ordered by key.  Callers serialize the
        metadata columns and must never ship ``encrypted_value``.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(SecretScopeSecret)
                .where(SecretScopeSecret.scope_id == scope_id)
                .order_by(SecretScopeSecret.key)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def get_secret_value(factory: sessionmaker[Session], *, scope_id: int, key: str) -> str | None:
    """Decrypt and return the value under ``(scope, key)``.

    The single plaintext read path — every caller must emit a
    ``secret.accessed`` audit event.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.
        key: Secret name.

    Returns:
        The plaintext value, or ``None`` when the key is absent.
    """
    with factory() as session:
        row = session.scalar(
            select(SecretScopeSecret).where(
                SecretScopeSecret.scope_id == scope_id,
                SecretScopeSecret.key == key,
            )
        )
        token = row.encrypted_value if row is not None else None
    if token is None:
        return None
    return decrypt_value(token, session_factory=factory)


def put_acl(
    factory: sessionmaker[Session],
    *,
    scope_id: int,
    principal: str,
    permission: str,
) -> SecretScopeAcl:
    """Create or overwrite *principal*'s grant on a scope.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.
        principal: User e-mail or ``*``.
        permission: One of :data:`SECRET_SCOPE_PERMISSIONS`.

    Returns:
        The persisted ACL row (detached).

    Raises:
        ValueError: On an empty principal or an unknown permission.
    """
    cleaned = principal.strip()
    if not cleaned:
        raise ValueError("principal must be a non-empty string")
    if permission not in SECRET_SCOPE_PERMISSIONS:
        raise ValueError(f"permission must be one of {', '.join(SECRET_SCOPE_PERMISSIONS)}")
    with factory() as session:
        row = session.scalar(
            select(SecretScopeAcl).where(
                SecretScopeAcl.scope_id == scope_id,
                SecretScopeAcl.principal == cleaned,
            )
        )
        if row is None:
            row = SecretScopeAcl(
                scope_id=scope_id,
                principal=cleaned,
                permission=permission,
                created_at=_utcnow(),
            )
            session.add(row)
        else:
            row.permission = permission
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_acl(factory: sessionmaker[Session], *, scope_id: int, principal: str) -> bool:
    """Remove *principal*'s grant from a scope.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.
        principal: User e-mail or ``*``.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        row = session.scalar(
            select(SecretScopeAcl).where(
                SecretScopeAcl.scope_id == scope_id,
                SecretScopeAcl.principal == principal,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


def list_acls(factory: sessionmaker[Session], *, scope_id: int) -> list[SecretScopeAcl]:
    """List a scope's ACL rows.

    Args:
        factory: SQLAlchemy session factory.
        scope_id: Primary key of the scope.

    Returns:
        Detached ACL rows ordered by principal.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(SecretScopeAcl)
                .where(SecretScopeAcl.scope_id == scope_id)
                .order_by(SecretScopeAcl.principal)
            )
        )
        for row in rows:
            session.expunge(row)
    return rows


def resolve_secret_references(
    factory: sessionmaker[Session], *, workspace_id: int, text: str
) -> str:
    """Replace every ``{{secrets/<scope>/<key>}}`` placeholder in *text*.

    Connector configs (ingest sources, sync targets, LLM providers)
    store the placeholder instead of the credential; the runtime
    swaps in the plaintext immediately before use so the value never
    rests in a config row.

    A reference to a scope or key that does not exist propagates a
    :class:`ValueError` out of the substitution — failing loudly
    beats wiring a connector with a literal placeholder as its
    password.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace whose scopes are consulted.
        text: Config string possibly containing placeholders.

    Returns:
        *text* with every placeholder replaced.
    """

    def _substitute(match: re.Match[str]) -> str:
        scope_name, key = match.group(1), match.group(2)
        scope = get_scope(factory, workspace_id=workspace_id, name=scope_name)
        if scope is None:
            raise ValueError(f"unknown secret scope {scope_name!r}")
        value = get_secret_value(factory, scope_id=scope.id, key=key)
        if value is None:
            raise ValueError(f"unknown secret key {key!r} in scope {scope_name!r}")
        return value

    return SECRET_REFERENCE_RE.sub(_substitute, text)


def resolve_references_in_tree(
    factory: sessionmaker[Session], *, workspace_id: int, data: object
) -> object:
    """Resolve placeholders in every string of a JSON-shaped tree.

    Connector configs arrive as parsed JSON (nested dicts / lists /
    strings); this walks the tree and pipes each string through
    :func:`resolve_secret_references`, leaving every other node
    untouched.  Unknown references propagate the same
    :class:`ValueError`.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace whose scopes are consulted.
        data: Parsed JSON value (dict / list / str / scalar).

    Returns:
        The tree with every placeholder-bearing string resolved.
    """
    if isinstance(data, str):
        return resolve_secret_references(factory, workspace_id=workspace_id, text=data)
    if isinstance(data, dict):
        mapping = cast("dict[str, object]", data)
        return {
            k: resolve_references_in_tree(factory, workspace_id=workspace_id, data=v)
            for k, v in mapping.items()
        }
    if isinstance(data, list):
        items = cast("list[object]", data)
        return [
            resolve_references_in_tree(factory, workspace_id=workspace_id, data=item)
            for item in items
        ]
    return data
