"""Tests for the Sprint 33.4 ``GET /admin/api-keys`` HTML page.

The JSON CRUD under ``/api/admin/api-keys`` already has its own
test suite (``test_admin_api_keys_routes.py``); this file exercises
only the HTML wrapper so any drift between the route and the
template surfaces in CI.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import _TEMPLATES, app
from pointlessql.config import Settings
from pointlessql.models import ApiKey, Base, Workspace
from pointlessql.services import auth


@pytest.fixture(autouse=True)
def _setup_app(tmp_path):
    """Wire an in-memory DB + templates onto the FastAPI app."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _seed_users(factory):
    """Create an admin and a regular user; return their session tokens."""
    auth.register(factory, "admin@pql.test", "Admin", "password123")
    auth.register(factory, "user@pql.test", "User", "password123")
    admin_token = auth.login(
        factory, "admin@pql.test", "password123", "test-secret-key-for-unit-tests!!"
    )
    user_token = auth.login(
        factory, "user@pql.test", "password123", "test-secret-key-for-unit-tests!!"
    )
    assert admin_token is not None
    assert user_token is not None
    return admin_token, user_token


def _seed_workspaces(factory):
    """Insert a default + secondary workspace so the dropdown has choices."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add_all(
            [
                Workspace(id=1, slug="default", name="Default", created_at=now),
                Workspace(id=2, slug="prod", name="Production", created_at=now),
            ]
        )
        session.commit()


def _seed_keys(factory):
    """Insert one active supervisor key + one revoked agent key."""
    now = datetime.datetime.now(datetime.UTC)
    revoked_at = now - datetime.timedelta(days=1)
    with factory() as session:
        session.add_all(
            [
                ApiKey(
                    name="ci-bot",
                    secret_hash="0" * 64,
                    secret_prefix="CIBOTpre",
                    supervisor=True,
                    auditor=False,
                    workspace_id=2,
                    created_at=now,
                ),
                ApiKey(
                    name="legacy-key",
                    secret_hash="1" * 64,
                    secret_prefix="LEGACYpr",
                    supervisor=False,
                    auditor=False,
                    workspace_id=1,
                    created_at=now - datetime.timedelta(days=30),
                    revoked_at=revoked_at,
                ),
            ]
        )
        session.commit()


class TestApiKeysPageAccess:
    """Auth + authorization gate."""

    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin/api-keys")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/auth/login"

    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self):
        factory = app.state.session_factory
        _admin_token, user_token = _seed_users(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: user_token},
        ) as client:
            resp = await client.get("/admin/api-keys")
        assert resp.status_code == 403


class TestApiKeysPageContent:
    """Row rendering + redaction + workspace surfacing."""

    @pytest.mark.asyncio
    async def test_empty_state_renders(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/api-keys")
        assert resp.status_code == 200
        body = resp.text
        assert "No API keys configured" in body
        assert "Create new key" in body
        # Workspace dropdown options visible.
        assert "default" in body
        assert "prod" in body

    @pytest.mark.asyncio
    async def test_active_only_by_default(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        _seed_keys(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/api-keys")
        assert resp.status_code == 200
        body = resp.text
        # Active key visible; revoked one filtered out.
        assert "ci-bot" in body
        assert "legacy-key" not in body
        # Secret hash is the 64-char load-bearing assertion: it must
        # NEVER reach the page.  The seed used "0" * 64 so a
        # regression that re-leaks the hash would surface here.
        assert "0" * 64 not in body
        # Prefix IS shown (8 chars, not the secret).
        assert "CIBOTpre" in body
        # Workspace slug rendered, not just the integer ID.
        assert "prod" in body
        # Supervisor scope badge.
        assert "supervisor" in body

    @pytest.mark.asyncio
    async def test_include_revoked_shows_revoked(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        _seed_keys(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/api-keys?include_revoked=1")
        assert resp.status_code == 200
        body = resp.text
        assert "ci-bot" in body
        assert "legacy-key" in body
        # Revoked-status badge surfaces.
        assert "revoked" in body
        # Hide-revoked link visible (we're showing them).
        assert "Hide revoked" in body


@pytest.mark.asyncio
async def test_detail_page_renders_for_existing_key() -> None:
    """per-key detail page renders + carries the key name."""
    factory = app.state.session_factory
    admin_token, _ = _seed_users(factory)
    _seed_workspaces(factory)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            ApiKey(
                name="detail-smoke",
                secret_hash="0" * 64,
                secret_prefix="pql_live_v1_xxxxxxxxxx",
                supervisor=False,
                auditor=False,
                workspace_id=1,
                created_at=now,
                token_format="v1",
                token_env="live",
            )
        )
        session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={auth.COOKIE_NAME: admin_token},
    ) as client:
        resp = await client.get("/admin/api-keys/detail-smoke")
    assert resp.status_code == 200, resp.text
    assert "detail-smoke" in resp.text
    assert "Catalog grants" in resp.text
    assert "IP allowlist" in resp.text


@pytest.mark.asyncio
async def test_detail_page_404_for_missing_key() -> None:
    factory = app.state.session_factory
    admin_token, _ = _seed_users(factory)
    _seed_workspaces(factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={auth.COOKIE_NAME: admin_token},
    ) as client:
        resp = await client.get("/admin/api-keys/nonexistent-key")
    assert resp.status_code == 404
