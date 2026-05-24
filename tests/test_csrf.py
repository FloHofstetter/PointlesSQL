"""Tests for the Sprint 42 CSRF middleware and token rotation.

Covers the double-submit-cookie enforcement on the three HTML form
routes (``/auth/login``, ``/auth/register``, ``/auth/logout``),
the header-based (HTMX) path, the ``/api/*`` exemption, and body
re-injection so the downstream route still sees posted fields.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import _TEMPLATES, app
from pointlessql.config import Settings
from pointlessql.models import Base
from pointlessql.services import auth, csrf


@pytest.fixture(autouse=True)
def _setup_app():
    """Wire an in-memory DB + templates onto the FastAPI app."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app.state.session_factory = factory
    app.state.settings = Settings(
        auth={"secret_key": "test-secret-key-for-unit-tests!!"},
        soyuz={"catalog_url": "http://localhost:8080"},
        jupyter={"enabled": False, "port": 8888},
        db={"url": "sqlite:///:memory:"},
        scheduler={"enabled": False},
    )
    app.state.templates = _TEMPLATES

    mock_uc = AsyncMock()
    mock_uc.list_catalogs.return_value = []
    mock_uc.get_tree.return_value = []
    app.state.uc_client = mock_uc

    yield

    engine.dispose()


def _client(**kwargs) -> httpx.AsyncClient:
    """Return an AsyncClient bound to the app with sensible defaults."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
        **kwargs,
    )


class TestCookieIssuance:
    """GET requests seed a ``pql_csrf`` cookie and render matching HTML."""

    @pytest.mark.asyncio
    async def test_get_login_issues_cookie(self):
        async with _client() as client:
            resp = await client.get("/auth/login")
        assert resp.status_code == 200
        assert csrf.COOKIE_NAME in resp.cookies
        token = resp.cookies[csrf.COOKIE_NAME]
        # Hidden input and meta tag both echo the cookie value so a
        # non-JS form submit or an HTMX-driven one land on the same
        # token.
        assert f'name="csrf_token" value="{token}"' in resp.text
        assert f'<meta name="csrf-token" content="{token}">' in resp.text

    @pytest.mark.asyncio
    async def test_cookie_persists_across_requests(self):
        async with _client() as client:
            first = await client.get("/auth/login")
            second = await client.get("/auth/login")
        # httpx's cookie jar re-sends the cookie on the second GET,
        # so the middleware does not re-mint it.
        assert first.cookies[csrf.COOKIE_NAME] == client.cookies[csrf.COOKIE_NAME]
        assert "set-cookie" not in (second.headers.get("set-cookie") or "").lower() or (
            csrf.COOKIE_NAME not in (second.headers.get("set-cookie") or "")
        )


class TestFormValidation:
    """POST /auth/login rejects mismatched/missing tokens, accepts matching ones."""

    @pytest.mark.asyncio
    async def test_post_without_token_is_403(self):
        async with _client() as client:
            # No preflight GET → client has no cookie at all, so any
            # token we submit cannot match. This mirrors the attack
            # case where a cross-origin form submits without the
            # victim's cookie.
            resp = await client.post(
                "/auth/login",
                data={"email": "x@x.com", "password": "y"},
            )
        assert resp.status_code == 403
        assert "CSRF" in resp.text

    @pytest.mark.asyncio
    async def test_post_with_mismatched_token_is_403(self):
        async with _client() as client:
            await client.get("/auth/login")  # seed cookie
            resp = await client.post(
                "/auth/login",
                data={
                    "email": "x@x.com",
                    "password": "y",
                    "csrf_token": "not-the-real-token",
                },
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_matching_form_token_passes_csrf(self):
        # Happy path: seed the cookie, echo the same value in the
        # form, login handler receives the body normally.
        factory = app.state.session_factory
        auth.register(factory, "u@u.com", "U", "password123")

        async with _client() as client:
            get_resp = await client.get("/auth/login")
            token = get_resp.cookies[csrf.COOKIE_NAME]
            resp = await client.post(
                "/auth/login",
                data={
                    "email": "u@u.com",
                    "password": "password123",
                    "csrf_token": token,
                },
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_post_with_matching_header_token_passes_csrf(self):
        # HTMX path: token in the X-CSRF-Token header, no form field.
        factory = app.state.session_factory
        auth.register(factory, "u@u.com", "U", "password123")

        async with _client() as client:
            get_resp = await client.get("/auth/login")
            token = get_resp.cookies[csrf.COOKIE_NAME]
            resp = await client.post(
                "/auth/login",
                data={"email": "u@u.com", "password": "password123"},
                headers={csrf.HEADER_NAME: token},
            )
        assert resp.status_code == 303


class TestRotation:
    """Successful login and logout rotate the CSRF cookie."""

    @pytest.mark.asyncio
    async def test_login_rotates_csrf_cookie(self):
        factory = app.state.session_factory
        auth.register(factory, "rot@r.com", "Rot", "password123")

        async with _client() as client:
            get_resp = await client.get("/auth/login")
            pre = get_resp.cookies[csrf.COOKIE_NAME]
            post = await client.post(
                "/auth/login",
                data={
                    "email": "rot@r.com",
                    "password": "password123",
                    "csrf_token": pre,
                },
            )
            assert post.status_code == 303
            # The response carries a fresh Set-Cookie for pql_csrf with a
            # different value than the one we just submitted.
            new_token = post.cookies[csrf.COOKIE_NAME]
            assert new_token != pre

    @pytest.mark.asyncio
    async def test_logout_rotates_csrf_cookie(self):
        factory = app.state.session_factory
        auth.register(factory, "out@o.com", "Out", "password123")
        jwt = auth.login(factory, "out@o.com", "password123", "test-secret-key-for-unit-tests!!")

        async with _client(cookies={auth.COOKIE_NAME: jwt}) as client:
            get_resp = await client.get("/auth/login")
            pre = get_resp.cookies[csrf.COOKIE_NAME]
            post = await client.post(
                "/auth/logout",
                data={"csrf_token": pre},
            )
        assert post.status_code == 303
        assert post.cookies[csrf.COOKIE_NAME] != pre


class TestExemptions:
    """``/api/*`` routes stay reachable without a CSRF token."""

    @pytest.mark.asyncio
    async def test_api_post_not_blocked_by_csrf(self):
        # /api/jobs rejects unauthenticated calls with 401 (from
        # auth_middleware), NOT 403 (from csrf_middleware). Use this
        # signal to prove the csrf check is skipped on /api/*.
        async with _client() as client:
            resp = await client.post(
                "/api/jobs",
                json={"name": "x", "notebook_path": "/n.ipynb", "schedule": "0 0 * * *"},
            )
        assert resp.status_code == 401


class TestBodyReplay:
    """Middleware must re-inject the request body after parsing it."""

    @pytest.mark.asyncio
    async def test_form_fields_reach_handler_after_csrf_parse(self):
        # After the middleware reads ``request.form()`` to extract
        # ``csrf_token``, the downstream ``Form(...)`` dependency has
        # to see the same fields. Register requires four form fields;
        # if body replay is broken the handler will 422 on missing
        # ``password_confirm``.
        factory = app.state.session_factory
        _ = factory  # sanity — fixture ran

        async with _client() as client:
            get_resp = await client.get("/auth/register")
            token = get_resp.cookies[csrf.COOKIE_NAME]
            resp = await client.post(
                "/auth/register",
                data={
                    "email": "replay@r.com",
                    "display_name": "Replay",
                    "password": "password123",
                    "password_confirm": "password123",
                    "csrf_token": token,
                },
            )
        assert resp.status_code == 303
        # Redirect carries a ``?flash=account_created`` query param now;
        # the body-replay contract only cares that the handler completed
        # the registration round-trip, not the exact query string.
        assert resp.headers["location"].startswith("/auth/login")


class TestTokenHelpers:
    """Direct unit tests for :mod:`pointlessql.services.csrf`."""

    def test_generate_token_is_random(self):
        a = csrf.generate_token()
        b = csrf.generate_token()
        assert a != b
        assert len(a) >= 32

    def test_tokens_match_rejects_none_and_empty(self):
        assert not csrf.tokens_match(None, "x")
        assert not csrf.tokens_match("x", None)
        assert not csrf.tokens_match("", "")
        assert not csrf.tokens_match("a", "b")

    def test_tokens_match_accepts_equal_strings(self):
        t = csrf.generate_token()
        assert csrf.tokens_match(t, t)
