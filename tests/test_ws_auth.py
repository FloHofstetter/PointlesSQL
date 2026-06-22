"""Unit tests for the shared WebSocket auth resolver.

resolve_websocket_user is the only auth path for agent WebSocket clients
(cookie → JWT, else Bearer → synthetic UserInfo with scope flags). It had
no direct coverage, so a regression in the Bearer branch could silently
admit or reject agent connections.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pointlessql.api.main import app
from pointlessql.api.ws_auth import resolve_websocket_user
from pointlessql.services import auth as auth_service


def _ws(
    *,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    factory: Any = ...,
    settings: Any = ...,
) -> Any:
    """Build a WebSocket double exposing app.state, cookies and headers."""
    state = SimpleNamespace(
        session_factory=app.state.session_factory if factory is ... else factory,
        settings=app.state.settings if settings is ... else settings,
    )
    return SimpleNamespace(
        app=SimpleNamespace(state=state),
        cookies=cookies or {},
        headers=headers or {},
    )


def test_valid_cookie_resolves_user(auth_cookies: dict[str, str]) -> None:
    """A valid session cookie resolves to that user."""
    user = resolve_websocket_user(_ws(cookies=auth_cookies))
    assert user is not None
    assert user["email"] == "test@test.com"


def test_bearer_resolves_synthetic_supervisor(supervisor_secret: Any) -> None:
    """A Bearer key resolves to a synthetic UserInfo carrying its scope."""
    headers = {"authorization": f"Bearer {supervisor_secret.secret}"}
    user = resolve_websocket_user(_ws(headers=headers))
    assert user is not None
    assert user["id"] == 0
    assert user["email"] == "api_key:supervisor-fixture"
    assert user["is_supervisor"] is True
    assert user["is_auditor"] is False
    assert user["is_admin"] is False


def test_bearer_resolves_auditor_flag(auditor_secret: Any) -> None:
    """The auditor scope flag flows through to the synthetic user."""
    headers = {"authorization": f"Bearer {auditor_secret.secret}"}
    user = resolve_websocket_user(_ws(headers=headers))
    assert user is not None
    assert user["is_auditor"] is True
    assert user["is_supervisor"] is False


def test_invalid_cookie_and_no_bearer_is_none() -> None:
    """A bogus cookie with no Bearer fallback resolves to None."""
    ws = _ws(cookies={auth_service.COOKIE_NAME: "not-a-valid-jwt"})
    assert resolve_websocket_user(ws) is None


def test_no_identity_is_none() -> None:
    """No cookie and no Bearer → None (route closes 4401)."""
    assert resolve_websocket_user(_ws()) is None


def test_missing_factory_is_none() -> None:
    """Unwired session factory → None, never a crash."""
    assert resolve_websocket_user(_ws(factory=None)) is None


def test_missing_settings_is_none() -> None:
    """Unwired settings → None, never a crash."""
    assert resolve_websocket_user(_ws(settings=None)) is None
