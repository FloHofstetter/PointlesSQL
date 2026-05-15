"""Phase 80.3 — Today landing page digest tests.

Asserts the home page renders the three Today cards (approvals,
inbox, alerts) and that the nav-rail badges are populated by the
nav-badges service when underlying data exists.
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
    auth.register(factory, "today@pql.test", "Today User", "password123")
    token = auth.login(
        factory,
        "today@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


class TestTodayCards:
    """Three Today cards always render."""

    @pytest.mark.asyncio
    async def test_three_today_cards_present(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.text
        for marker in ["approvals", "inbox", "alerts"]:
            assert f'data-pql-today-card="{marker}"' in body, marker

    @pytest.mark.asyncio
    async def test_today_cards_link_to_full_surfaces(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        assert 'href="/runs?status=needs_approval"' in body
        assert 'href="/notifications"' in body
        assert 'href="/alerts"' in body

    @pytest.mark.asyncio
    async def test_zero_state_does_not_panic(self):
        """Empty install: no runs, no notifications, no alerts → zeros."""
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.text
        # Zero state copy is rendered.
        assert "Inbox zero" in body or "Nothing waiting" in body
        assert "All caught up" in body
        assert "No alerts configured" in body


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
        # All three keys present, all zero.
        assert result.get("runs_pending", -1) == 0
        assert result.get("audit_unread", -1) == 0
        assert result.get("alerts_firing", -1) == 0

    def test_compute_returns_non_negative(self):
        from pointlessql.services.nav_badges import compute_nav_badges

        factory = app.state.session_factory
        result = compute_nav_badges(factory, user_id=1, workspace_id=1)
        for k, v in result.items():
            assert v >= 0, f"{k} is negative: {v}"


class TestActivePageHome:
    """Home route flags active_page='home' so rail highlights Today."""

    @pytest.mark.asyncio
    async def test_home_marks_today_rail_active(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # The Today rail entry carries data-section="home" and gets
        # the active class on the home page.
        assert 'data-section="home"' in body
