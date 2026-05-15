"""Phase 80.8 — topbar quick-create menu tests."""

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
    auth.register(factory, "qc@pql.test", "QuickCreate User", "password123")
    token = auth.login(
        factory,
        "qc@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


class TestQuickCreateMenu:
    @pytest.mark.asyncio
    async def test_topbar_renders_quick_create_trigger(self):
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
        assert "pql-quick-create-trigger" in body
        assert 'aria-label="Create new"' in body

    @pytest.mark.asyncio
    async def test_menu_lists_six_base_options(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        for kind in [
            "notebook",
            "sql-query",
            "dashboard",
            "topic",
            "issue",
            "alert",
        ]:
            assert f'data-pql-quick-create="{kind}"' in body, kind

    @pytest.mark.asyncio
    async def test_admin_sees_extra_options(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # First user is auto-admin → admin-gated entries surface.
        assert 'data-pql-quick-create="data-product"' in body
        assert 'data-pql-quick-create="job"' in body

    @pytest.mark.asyncio
    async def test_anonymous_does_not_see_menu(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/auth/login")
        body = resp.text
        assert "pql-quick-create-trigger" not in body
