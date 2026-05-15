"""Phase 80.7 — status footer bar tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import _TEMPLATES, app
from pointlessql.config import Settings
from pointlessql.models import Base
from pointlessql.services import auth


@pytest.fixture(autouse=True)
def _setup_app(tmp_path):
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


def _seed(factory) -> str:
    auth.register(factory, "footer@pql.test", "Footer User", "password123")
    token = auth.login(
        factory,
        "footer@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


class TestFooterBarRender:
    @pytest.mark.asyncio
    async def test_footer_renders_for_auth_user(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.text
        assert 'class="pql-footer-bar"' in body

    @pytest.mark.asyncio
    async def test_footer_carries_four_backend_pills(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # The four backend names are in the JS array.
        for backend in ["'soyuz'", "'mlflow'", "'dbt'", "'hermes'"]:
            assert backend in body, backend

    @pytest.mark.asyncio
    async def test_footer_shows_admin_chip(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # First user is auto-admin in the test fixture.
        assert "pql-footer-bar__chip--admin" in body
        assert ">admin<" in body

    @pytest.mark.asyncio
    async def test_anonymous_pages_do_not_render_footer(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/auth/login")
        body = resp.text
        # The footer partial guards on current_user; unauth page →
        # no footer markup.
        assert 'class="pql-footer-bar"' not in body


class TestHealthBackendsEndpoint:
    @pytest.mark.asyncio
    async def test_endpoint_returns_all_keys(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/health/backends")
        assert resp.status_code == 200
        data = resp.json()
        for key in ["soyuz", "mlflow", "dbt", "hermes"]:
            assert key in data, key
        # Hermes is always n/a.
        assert data["hermes"] == "na"

    @pytest.mark.asyncio
    async def test_endpoint_requires_auth(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/api/health/backends")
        # Either 401 or a redirect to login — middleware-dependent.
        assert resp.status_code in (401, 303, 307), resp.status_code
