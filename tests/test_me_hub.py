"""/me consolidated hub tests."""

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
    auth.register(factory, "hub@pql.test", "Hub User", "password123")
    token = auth.login(
        factory,
        "hub@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


class TestMeHub:
    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/me")
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_renders_six_cards_for_admin(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/me")
        assert resp.status_code == 200
        body = resp.text
        # First user is auto-admin → all seven cards visible
        # (six base cards + API keys card).
        for marker in [
            "profile",
            "inbox",
            "my-work",
            "subscriptions",
            "notification-settings",
            "account-settings",
            "api-keys",
        ]:
            assert f'data-pql-me-card="{marker}"' in body, marker

    @pytest.mark.asyncio
    async def test_rail_marks_me_active(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/me")
        body = resp.text
        # /me rail entry isn't in the rail itself, but the section
        # ('me') is what me_sidebar dispatches on.
        assert 'aria-label="Me hub"' in body

    @pytest.mark.asyncio
    async def test_user_menu_links_to_me(self):
        factory = app.state.session_factory
        token = _seed(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # User menu has the /me entry now.
        assert 'href="/me"' in body
        assert "Me overview" in body
