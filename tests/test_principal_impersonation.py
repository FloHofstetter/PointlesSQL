"""The X-Principal override is gated to trusted callers.

A normal non-admin cookie session must not be able to set ``X-Principal``
to a higher-privileged identity — doing so would bypass grants (the UC
client is built for the effective principal) and forge the audit trail.
Only API-key callers (Hermes / ops) and admin cookie sessions may
impersonate.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pointlessql.api.dependencies._principal import (  # pyright: ignore[reportPrivateUsage]
    _caller_may_impersonate,
    effective_principal,
)


def _req(
    *, header: str | None = None, user: dict[str, Any] | None = None, api_key_id: int | None = None
) -> Any:
    """Build a minimal request double for the principal resolver.

    Args:
        header: Value of the ``X-Principal`` header, or ``None`` to omit.
        user: ``request.state.user`` dict, or ``None`` for anonymous.
        api_key_id: ``request.state.api_key_id``, set for API-key auth.

    Returns:
        An object exposing ``.headers`` and ``.state`` like a Request.
    """
    headers: dict[str, str] = {"x-principal": header} if header is not None else {}
    state = SimpleNamespace()
    if user is not None:
        state.user = user
    if api_key_id is not None:
        state.api_key_id = api_key_id
    return SimpleNamespace(headers=headers, state=state)


def test_non_admin_cannot_impersonate_via_header() -> None:
    """A non-admin's X-Principal is ignored; they stay themselves."""
    req = _req(header="admin@corp.example", user={"email": "bob@corp.example", "is_admin": False})
    assert effective_principal(req) == "bob@corp.example"


def test_admin_may_impersonate() -> None:
    """An admin cookie session may act as another principal."""
    req = _req(header="target@corp.example", user={"email": "root@corp.example", "is_admin": True})
    assert effective_principal(req) == "target@corp.example"


def test_api_key_caller_may_impersonate() -> None:
    """An API-key request (Hermes/ops) may act on behalf of a user."""
    req = _req(
        header="target@corp.example",
        user={"email": "api_key:hermes", "is_admin": False},
        api_key_id=7,
    )
    assert effective_principal(req) == "target@corp.example"


def test_anonymous_header_is_ignored() -> None:
    """An anonymous request with X-Principal resolves to None."""
    assert effective_principal(_req(header="someone@corp.example")) is None


def test_non_admin_without_header_uses_own_email() -> None:
    """No header → the non-admin's own cookie email."""
    req = _req(user={"email": "bob@corp.example", "is_admin": False})
    assert effective_principal(req) == "bob@corp.example"


def test_caller_may_impersonate_predicate() -> None:
    """The trust predicate: admin or API-key only."""
    assert _caller_may_impersonate(_req(user={"email": "a", "is_admin": True}))
    assert _caller_may_impersonate(_req(user={"email": "k", "is_admin": False}, api_key_id=1))
    assert not _caller_may_impersonate(_req(user={"email": "b", "is_admin": False}))
    assert not _caller_may_impersonate(_req())
