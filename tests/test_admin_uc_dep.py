"""``admin_uc`` combined dependency."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pointlessql.api.dependencies import admin_uc, get_uc_client
from pointlessql.exceptions import AuthorizationError
from pointlessql.types import UserInfo


def _build_request(is_admin: bool, uc_client: object = "uc-sentinel") -> MagicMock:
    """Construct a minimal Request stub with the required state."""
    request = MagicMock()
    request.state.user = UserInfo(
        id=1,
        email="admin@example.com" if is_admin else "user@example.com",
        display_name="Test",
        is_admin=is_admin,
        is_supervisor=False,
        is_auditor=False,
    )
    request.headers = {}
    request.app.state.uc_client = uc_client
    request.app.state.settings = MagicMock()
    # Real dict so the per-principal client cache works (a MagicMock would
    # auto-create a truthy attribute and short-circuit the lookup).
    request.app.state.principal_uc_clients = {}
    return request


def test_admin_uc_returns_app_state_facade_for_anonymous_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no principal is bound to the request, returns the app-state client."""
    request = _build_request(is_admin=True, uc_client="uc-sentinel")
    # Strip the user-email path so effective_principal returns None and
    # get_uc_client returns app.state.uc_client unchanged.
    request.state.user = UserInfo(
        id=1,
        email="",
        display_name="",
        is_admin=True,
        is_supervisor=False,
        is_auditor=False,
    )
    request.headers = {}
    result = admin_uc(request)
    assert result == "uc-sentinel"


def test_admin_uc_raises_for_non_admin() -> None:
    """Non-admin caller surfaces AuthorizationError (from require_admin)."""
    request = _build_request(is_admin=False)
    with pytest.raises(AuthorizationError):
        admin_uc(request)


def test_admin_uc_matches_explicit_couplet() -> None:
    """``admin_uc`` returns the same kind of object as ``get_uc_client``."""
    request = _build_request(is_admin=True, uc_client="uc-x")
    legacy = get_uc_client(request)
    new = admin_uc(request)
    # Both go through the same UC factory; type identity is the contract.
    assert type(new) is type(legacy)


def test_admin_uc_forwards_principal_via_get_uc_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Principal forwarding still works — admin_uc just composes get_uc_client."""
    request = _build_request(is_admin=True, uc_client="default-client")
    request.headers = {"x-principal": "principal@example.com"}

    captured: dict[str, object] = {}

    class _UCStub:
        @classmethod
        def for_principal(cls, settings: object, principal: str) -> str:
            captured["settings"] = settings
            captured["principal"] = principal
            return f"forwarded:{principal}"

    monkeypatch.setattr("pointlessql.api.dependencies._principal.UnityCatalogClient", _UCStub)
    result = admin_uc(request)
    assert result == "forwarded:principal@example.com"
    assert captured["principal"] == "principal@example.com"
