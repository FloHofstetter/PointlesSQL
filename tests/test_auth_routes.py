"""Tests for auth routes — register, login, logout, middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.models import Base
from pointlessql.services import auth
from tests.conftest import seed_csrf


@pytest.fixture(autouse=True)
def _setup_app(tmp_path):
    """Set up app state with an in-memory auth DB for every test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app.state.session_factory = factory
    app.state.settings = MagicMock(
        secret_key="test-secret-key-for-unit-tests!!",
        jwt_expiry_hours=168,
        soyuz_catalog_url="http://localhost:8080",
        jupyter_enabled=False,
        jupyter_port=8888,
        database_url="sqlite:///:memory:",
    )

    # Mock UC client so catalog routes don't fail.
    mock_uc = AsyncMock()
    mock_uc.list_catalogs.return_value = []
    mock_uc.get_tree.return_value = []
    app.state.uc_client = mock_uc
    app.state.templates = app.state.templates if hasattr(app.state, "templates") else None

    yield

    engine.dispose()


@pytest.fixture
def secret():
    return "test-secret-key-for-unit-tests!!"


@pytest.fixture
def factory():
    return app.state.session_factory


class TestLoginPage:
    """GET /auth/login renders the login form."""

    @pytest.mark.asyncio
    async def test_login_page_renders(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/login")
        assert resp.status_code == 200
        assert "Sign in" in resp.text


class TestRegisterFlow:
    """Register → login → access protected route → logout."""

    @pytest.mark.asyncio
    async def test_register_page_renders(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/register")
        assert resp.status_code == 200
        assert "Create Account" in resp.text

    @pytest.mark.asyncio
    async def test_register_first_user_info(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/register")
        assert "admin privileges" in resp.text

    @pytest.mark.asyncio
    async def test_register_and_login(self, factory, secret):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            token = await seed_csrf(client)
            # Register.
            resp = await client.post(
                "/auth/register",
                data={
                    "email": "user@test.com",
                    "display_name": "Test User",
                    "password": "password123",
                    "password_confirm": "password123",
                    "csrf_token": token,
                },
            )
            assert resp.status_code == 303
            assert resp.headers["location"] == "/auth/login"

            # Login.
            resp = await client.post(
                "/auth/login",
                data={
                    "email": "user@test.com",
                    "password": "password123",
                    "csrf_token": token,
                },
            )
            assert resp.status_code == 303
            assert resp.headers["location"] == "/"
            assert auth.COOKIE_NAME in resp.cookies

    @pytest.mark.asyncio
    async def test_password_mismatch(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            token = await seed_csrf(client)
            resp = await client.post(
                "/auth/register",
                data={
                    "email": "user@test.com",
                    "display_name": "Test",
                    "password": "password123",
                    "password_confirm": "different",
                    "csrf_token": token,
                },
            )
        assert resp.status_code == 400
        assert "do not match" in resp.text

    @pytest.mark.asyncio
    async def test_password_too_short(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            token = await seed_csrf(client)
            resp = await client.post(
                "/auth/register",
                data={
                    "email": "user@test.com",
                    "display_name": "Test",
                    "password": "short",
                    "password_confirm": "short",
                    "csrf_token": token,
                },
            )
        assert resp.status_code == 400
        assert "at least 8" in resp.text


class TestMiddleware:
    """Auth middleware blocks unauthenticated requests."""

    @pytest.mark.asyncio
    async def test_redirect_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/auth/login"

    @pytest.mark.asyncio
    async def test_api_returns_401(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_access(self, factory, secret):
        # Register and login to get a cookie.
        auth.register(factory, "user@test.com", "Test User", "password123")
        token = auth.login(factory, "user@test.com", "password123", secret)
        assert token is not None

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        assert resp.status_code == 200


class TestAuthMe:
    """GET /auth/me returns current user as JSON."""

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/me")
        # /auth/ is a public prefix so middleware lets it through,
        # but the route handler returns 401 when no user is attached.
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_authenticated(self, factory, secret):
        auth.register(factory, "me@test.com", "Me", "password123")
        token = auth.login(factory, "me@test.com", "password123", secret)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "me@test.com"
        assert data["display_name"] == "Me"


class TestLogout:
    """POST /auth/logout clears cookie."""

    @pytest.mark.asyncio
    async def test_logout_redirects(self, factory, secret):
        auth.register(factory, "user@test.com", "User", "password123")
        token = auth.login(factory, "user@test.com", "password123", secret)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
            follow_redirects=False,
        ) as client:
            csrf_token = await seed_csrf(client)
            resp = await client.post(
                "/auth/logout",
                data={"csrf_token": csrf_token},
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/auth/login"
        # Cookie should be deleted (set to empty or max_age=0).
        set_cookie = resp.headers.get("set-cookie", "")
        assert auth.COOKIE_NAME in set_cookie
