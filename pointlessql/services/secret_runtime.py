"""In-kernel secrets getter — ACL-checked, audited, decrypt-on-read.

Notebook kernels are ipykernel subprocesses sharing the app's
interpreter and environment, so they can import ``pointlessql``
directly but run outside any HTTP request.  This module is the
kernel-side counterpart of the ``/api/secrets/.../value`` endpoint:
it resolves the caller from ``POINTLESSQL_PRINCIPAL`` /
``POINTLESSQL_WORKSPACE_ID`` (both injected at kernel start), walks
the same ACL ladder, decrypts through the same service, and writes
the same ``secret.accessed`` audit row — with ``via: kernel`` so
the cockpit can tell browser reads from notebook reads apart.

Surfaced in notebooks as ``pql_secrets.get("scope", "key")`` by the
kernel bootstrap.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.services import secret_scopes as scopes_service

_factory: sessionmaker[Session] | None = None


def _get_factory() -> sessionmaker[Session]:
    """Return a session factory, building a kernel-local one on demand.

    Inside the app process :func:`pointlessql.db.get_session_factory`
    is already initialised and reused; inside a kernel subprocess no
    ``init_db`` ever ran, so a plain engine is built straight from
    the configured DB URL (no migration run — the app owns those).

    Returns:
        A cached session factory bound to the metadata DB.
    """
    global _factory  # noqa: PLW0603 — process-lifetime cache
    if _factory is not None:
        return _factory
    try:
        from pointlessql.db import get_session_factory

        _factory = get_session_factory()
    except RuntimeError:
        from pointlessql.config import get_settings

        engine = create_engine(get_settings().db.url)
        _factory = sessionmaker(bind=engine)
    return _factory


def get_secret(scope: str, key: str) -> str:
    """Decrypt one secret value for the kernel's principal.

    Args:
        scope: Secret-scope name inside the kernel's workspace.
        key: Secret name inside the scope.

    Returns:
        The plaintext value.

    Raises:
        PermissionError: When the kernel carries no
            ``POINTLESSQL_PRINCIPAL`` identity.
        LookupError: When the scope is invisible to the principal
            (absent or ungranted — indistinguishable on purpose) or
            the key does not exist.
    """
    principal = os.environ.get("POINTLESSQL_PRINCIPAL", "").strip()
    if not principal:
        raise PermissionError("no POINTLESSQL_PRINCIPAL identity in this kernel")
    workspace_id = int(os.environ.get("POINTLESSQL_WORKSPACE_ID", "1") or "1")
    factory = _get_factory()

    from sqlalchemy import select

    from pointlessql.models.auth import User

    with factory() as session:
        user = session.scalar(select(User).where(User.email == principal))
        user_id = user.id if user is not None else 0
        is_admin = bool(user.is_admin) if user is not None else False

    scope_row = scopes_service.get_scope(factory, workspace_id=workspace_id, name=scope)
    permission = (
        None
        if scope_row is None
        else scopes_service.resolve_permission(
            factory, scope_id=scope_row.id, principal=principal, is_admin=is_admin
        )
    )
    if scope_row is None or permission is None:
        raise LookupError(f"secret scope {scope!r} not found")
    value = scopes_service.get_secret_value(factory, scope_id=scope_row.id, key=key)
    if value is None:
        raise LookupError(f"secret key {key!r} not found in scope {scope!r}")

    from pointlessql.services.audit import log_action

    log_action(
        factory,
        user_id,
        principal,
        "secret.accessed",
        f"secret_scope:{scope}",
        {"key": key, "via": "kernel"},
        actor_role="admin" if is_admin else "user",
        workspace_id=workspace_id,
    )
    return value
