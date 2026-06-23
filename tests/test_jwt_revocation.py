"""Server-side JWT session revocation + audience/issuer pinning.

A stolen or leaked session token used to stay valid for its full 7-day
lifetime — logout and account changes could not invalidate it. Tokens now
carry an ``sv`` (session-version) claim checked against the user row, plus
pinned ``aud`` / ``iss`` claims, so logout / admin force-revoke kills every
outstanding token and a token minted for another audience is rejected.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import jwt
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import User
from pointlessql.services import auth, csrf

_AUD = "pointlessql"
_ISS = "pointlessql"


def _factory() -> Any:
    return app.state.session_factory


def _secret() -> str:
    return str(app.state.settings.auth.secret_key)


def _user_id(email: str) -> int:
    with _factory()() as session:
        uid = session.scalar(select(User.id).where(User.email == email))
        assert uid is not None, email
        return int(uid)


def _raw_token(secret: str, **claims: Any) -> str:
    """Hand-mint a token with an explicit claim set (bypassing create_jwt)."""
    now = datetime.datetime.now(datetime.UTC)
    payload = {"iat": now, "exp": now + datetime.timedelta(hours=1), **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def _client(cookies: dict[str, str] | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies or {},
    )


# --- session_version (sv claim) -------------------------------------------


def test_session_version_bump_rejects_old_token() -> None:
    """Bumping session_version invalidates tokens minted before the bump."""
    uid = _user_id("test@test.com")
    secret = _secret()
    token = auth.create_jwt(uid, "test@test.com", True, secret, session_version=0)
    assert auth.get_current_user(_factory(), token, secret) is not None

    assert auth.revoke_user_sessions(_factory(), uid) is True

    assert auth.get_current_user(_factory(), token, secret) is None
    fresh = auth.create_jwt(uid, "test@test.com", True, secret, session_version=1)
    assert auth.get_current_user(_factory(), fresh, secret) is not None


def test_token_without_sv_treated_as_version_0() -> None:
    """A legacy token with no sv claim is treated as version 0."""
    uid = _user_id("test@test.com")
    secret = _secret()
    token = _raw_token(
        secret, sub=str(uid), email="test@test.com", is_admin=True, aud=_AUD, iss=_ISS
    )
    # session_version is 0 for a fresh user, so the sv-less token validates.
    assert auth.get_current_user(_factory(), token, secret) is not None
    # ...until the first bump, after which version-0 no longer matches.
    auth.revoke_user_sessions(_factory(), uid)
    assert auth.get_current_user(_factory(), token, secret) is None


def test_revoke_unknown_user_returns_false() -> None:
    """Revoking a non-existent user is a no-op, not a crash."""
    assert auth.revoke_user_sessions(_factory(), 999_999) is False


# --- audience / issuer pinning --------------------------------------------


def test_valid_aud_iss_and_sv_claims_present() -> None:
    """create_jwt stamps aud/iss/sv and verify_jwt accepts them."""
    token = auth.create_jwt(1, "a@b.com", False, _secret())
    payload = auth.verify_jwt(token, _secret())
    assert payload is not None
    assert payload["aud"] == _AUD
    assert payload["iss"] == _ISS
    assert payload["sv"] == 0


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "1", "iss": _ISS},  # missing aud
        {"sub": "1", "aud": "other-service", "iss": _ISS},  # wrong aud
        {"sub": "1", "aud": _AUD},  # missing iss
        {"sub": "1", "aud": _AUD, "iss": "evil"},  # wrong iss
    ],
)
def test_bad_audience_or_issuer_rejected(claims: dict[str, Any]) -> None:
    """A token with absent/wrong aud or iss fails verification."""
    token = _raw_token(_secret(), **claims)
    assert auth.verify_jwt(token, _secret()) is None


# --- HTTP: logout + admin revoke ------------------------------------------


async def test_logout_revokes_outstanding_token(auth_cookies: dict[str, str]) -> None:
    """Logout is a real server-side revocation: the cleared token dies too."""
    token = auth_cookies[auth.COOKIE_NAME]
    async with _client() as client:
        seed = await client.get("/auth/login")
        csrf_token = seed.cookies[csrf.COOKIE_NAME]
        client.cookies.set(auth.COOKIE_NAME, token)

        before = await client.get("/auth/me")
        assert before.status_code == 200

        logout = await client.post(
            "/auth/logout", headers={csrf.HEADER_NAME: csrf_token}, follow_redirects=False
        )
        assert logout.status_code == 303

    # The captured token, presented after logout, no longer authenticates.
    async with _client({auth.COOKIE_NAME: token}) as client:
        after = await client.get("/auth/me")
    assert after.status_code == 401


async def test_admin_revoke_sessions_route(
    auth_cookies: dict[str, str], non_admin_cookies: dict[str, str]
) -> None:
    """An admin can force-log-out another user; non-admins cannot."""
    uid = _user_id("nonadmin@test.com")
    na_token = non_admin_cookies[auth.COOKIE_NAME]
    url = f"/api/admin/users/{uid}/revoke-sessions"

    async with _client(non_admin_cookies) as client:
        forbidden = await client.post(url)
    assert forbidden.status_code == 403

    async with _client(auth_cookies) as client:
        ok = await client.post(url)
    assert ok.status_code == 200, ok.text
    assert ok.json()["revoked"] is True

    async with _client({auth.COOKIE_NAME: na_token}) as client:
        after = await client.get("/auth/me")
    assert after.status_code == 401

    async with _client(auth_cookies) as client:
        missing = await client.post("/api/admin/users/999999/revoke-sessions")
    assert missing.status_code == 404
