"""Tests for the admin landing card-grid (``GET /admin``)."""

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


class TestAdminIndexAccess:
    """Auth + authorization gate."""

    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin")
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
            resp = await client.get("/admin")
        assert resp.status_code == 403


class TestAdminIndexCards:
    """The card grid surfaces every admin sub-page."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_five_cards(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin")
        assert resp.status_code == 200
        body = resp.text

        # Every Sprint 33.x card must surface its data-admin-card
        # marker so the page test catches accidental drops in a
        # template merge.  The hrefs themselves are asserted so a
        # rename of the underlying admin route fails the gate.
        for marker, href in [
            ("audit-log", "/admin/audit"),
            ("external-writes", "/admin/external-writes"),
            ("workspaces", "/admin/workspaces"),
            ("audit-sinks", "/admin/audit-sinks"),
            ("review-destinations", "/admin/review-destinations"),
            ("secrets", "/admin/secrets"),
            ("cdf-subscriptions", "/admin/cdf-subscriptions"),
        ]:
            assert f'data-admin-card="{marker}"' in body, marker
            assert f'href="{href}"' in body, href

    @pytest.mark.asyncio
    async def test_card_renders_with_no_data(self):
        """Empty install: no workspaces row, no sinks, no destinations.

        The default workspace exists from the migration, so the
        active-workspace badge must surface a 1.  Sinks and
        destinations are zero-by-default, so their badges stay
        suppressed.
        """
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin")
        assert resp.status_code == 200
        body = resp.text

        # Rail-icon retarget assertion.  Sprint 33.1 changed the
        # admin rail link from /admin/audit → /admin so the landing
        # is the entry point.  Any future drift gets caught here.
        assert 'href="/admin"' in body
        assert 'data-section="admin"' in body
