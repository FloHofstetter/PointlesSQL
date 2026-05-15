"""Phase 80.4 — /users People index page tests."""

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
    auth.register(factory, "people@pql.test", "People User", "password123")
    token = auth.login(
        factory,
        "people@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


class TestUsersIndex:
    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/users")
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_renders_index_with_seeded_user(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/users")
        assert resp.status_code == 200
        body = resp.text
        # Page chrome + table marker.
        assert 'data-pql-page="users-index"' in body
        # The seeded user appears.
        assert "People User" in body
        assert "people@pql.test" in body

    @pytest.mark.asyncio
    async def test_role_filter_renders_filter_badge(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/users?role=auditor")
        assert resp.status_code == 200
        body = resp.text
        # Filter chip surfaced + clear-filter link.
        assert "filter: auditor" in body
        assert 'href="/users"' in body
        # Seeded user is not an auditor → empty filtered list copy.
        assert "No members match" in body

    @pytest.mark.asyncio
    async def test_rail_marks_people_active(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/users")
        body = resp.text
        assert 'data-section="people"' in body
