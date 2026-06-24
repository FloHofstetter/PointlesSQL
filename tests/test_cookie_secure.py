"""Auth/session cookies carry the Secure flag over HTTPS.

Session, CSRF, workspace and OIDC-state cookies were set without
``Secure`` so they leaked over any plain-HTTP hop.  The flag now
auto-detects from the request scheme (overridable via
``POINTLESSQL_AUTH_COOKIE_SECURE``).  These tests pin the resolver and
the end-to-end Set-Cookie headers over both schemes.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from pointlessql.api._cookie_security import resolve_cookie_secure
from pointlessql.api.main import app
from pointlessql.services import auth
from tests.conftest import seed_csrf


def _req(*, scheme: str, cookie_secure: bool | None) -> Any:
    """Build a request double exposing ``.url.scheme`` and the setting."""
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(auth=SimpleNamespace(cookie_secure=cookie_secure))
            )
        ),
        url=SimpleNamespace(scheme=scheme),
    )


def test_resolver_auto_detects_from_scheme() -> None:
    """Unset setting → Secure on https, not on http."""
    assert resolve_cookie_secure(_req(scheme="https", cookie_secure=None)) is True
    assert resolve_cookie_secure(_req(scheme="http", cookie_secure=None)) is False


def test_resolver_explicit_override_wins() -> None:
    """An explicit setting overrides scheme auto-detection."""
    assert resolve_cookie_secure(_req(scheme="http", cookie_secure=True)) is True
    assert resolve_cookie_secure(_req(scheme="https", cookie_secure=False)) is False


def _csrf_set_cookie(resp: httpx.Response) -> str:
    """Return the pql_csrf Set-Cookie header line from *resp*."""
    for line in resp.headers.get_list("set-cookie"):
        if line.startswith("pql_csrf="):
            return line
    raise AssertionError("no pql_csrf Set-Cookie issued")


@pytest.mark.asyncio
async def test_csrf_cookie_secure_over_https() -> None:
    """A fresh GET over https issues the CSRF cookie with Secure."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        resp = await client.get("/auth/login")
    assert "secure" in _csrf_set_cookie(resp).lower()


@pytest.mark.asyncio
async def test_csrf_cookie_not_secure_over_http() -> None:
    """Over plain http the CSRF cookie omits Secure (loopback dev)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/auth/login")
    assert "secure" not in _csrf_set_cookie(resp).lower()


@pytest.mark.asyncio
async def test_login_session_cookie_secure_over_https() -> None:
    """Logging in over https sets the session cookie with Secure."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        token = await seed_csrf(client)
        resp = await client.post(
            "/auth/login",
            data={"email": "test@test.com", "password": "password123", "csrf_token": token},
        )
    session_line = next(
        (
            line
            for line in resp.headers.get_list("set-cookie")
            if line.startswith(f"{auth.COOKIE_NAME}=")
        ),
        None,
    )
    assert session_line is not None
    assert "secure" in session_line.lower()
