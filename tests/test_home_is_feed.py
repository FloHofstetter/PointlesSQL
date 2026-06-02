"""The home surface is the activity feed.

``GET /`` renders the same feed shell as ``GET /feed`` (the overview
dashboard was retired) and the rail highlights the Home hub.  The
nav-badges aggregator that powers the right-rail "Needs your
attention" counts is exercised here too.
"""

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
    mock_uc.list_connections.return_value = []
    app.state.uc_client = mock_uc

    yield

    engine.dispose()


def _seed_user(factory) -> str:
    auth.register(factory, "home@pql.test", "Home User", "password123")
    token = auth.login(
        factory,
        "home@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


def _client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={auth.COOKIE_NAME: token},
    )


class TestHomeIsFeed:
    """``/`` renders the feed; ``/feed`` is an alias of the same shell."""

    @pytest.mark.asyncio
    async def test_root_renders_feed_shell(self):
        token = _seed_user(app.state.session_factory)
        async with _client(token) as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.text
        # The Alpine feed factory mounts (with the is-admin arg) and the
        # right rail teleports into the meta panel.
        assert 'x-data="feedPage(' in body
        assert 'x-teleport="#pql-meta-panel .pql-meta-panel__inner"' in body
        assert "Needs your attention" in body

    @pytest.mark.asyncio
    async def test_root_and_feed_render_same_shell(self):
        token = _seed_user(app.state.session_factory)
        async with _client(token) as client:
            root = await client.get("/")
            feed = await client.get("/feed")
        assert root.status_code == 200
        assert feed.status_code == 200
        for marker in ['x-data="feedPage(', "Needs your attention"]:
            assert marker in root.text, marker
            assert marker in feed.text, marker

    @pytest.mark.asyncio
    async def test_root_marks_home_hub_active(self):
        token = _seed_user(app.state.session_factory)
        async with _client(token) as client:
            resp = await client.get("/")
        # The feed is the Home hub, so the rail highlights it.
        assert 'data-active-hub="home"' in resp.text

    @pytest.mark.asyncio
    async def test_anonymous_redirected_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/", follow_redirects=False)
        # Unauthenticated lands on the login flow (303 from the route or
        # the auth middleware), never a 200 feed.
        assert resp.status_code in (302, 303, 307)


class TestNavBadgesService:
    """The nav-badges aggregator is best-effort and returns ints."""

    def test_compute_returns_empty_for_no_factory(self):
        from pointlessql.services.nav_badges import compute_nav_badges

        result = compute_nav_badges(None, user_id=1, workspace_id=1)
        assert result == {}

    def test_compute_returns_zero_keys_on_empty_db(self):
        from pointlessql.services.nav_badges import compute_nav_badges

        factory = app.state.session_factory
        result = compute_nav_badges(factory, user_id=0, workspace_id=0)
        assert result.get("runs_pending", -1) == 0
        assert result.get("audit_unread", -1) == 0
        assert result.get("alerts_firing", -1) == 0

    def test_compute_returns_non_negative(self):
        from pointlessql.services.nav_badges import compute_nav_badges

        factory = app.state.session_factory
        result = compute_nav_badges(factory, user_id=1, workspace_id=1)
        for k, v in result.items():
            assert v >= 0, f"{k} is negative: {v}"
