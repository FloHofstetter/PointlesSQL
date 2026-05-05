"""Tests for the Sprint 33.3 ``GET /admin/review-destinations`` HTML page.

The JSON CRUD under ``/api/admin/review-destinations`` already has
its own test suite; this file exercises only the HTML wrapper so
any drift between the route and the template surfaces in CI.
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
from pointlessql.models import Base
from pointlessql.models.agent_reviews import ReviewDestination
from pointlessql.services import auth
from pointlessql.settings import Settings


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


def _seed_destinations(factory):
    """Insert two destinations: one signed + active warn, one unsigned + inactive critical."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add_all(
            [
                ReviewDestination(
                    name="ops-slack",
                    webhook_url="https://hooks.slack.com/services/T0/B0/abc",
                    hmac_secret="topsecret",
                    is_active=True,
                    min_severity="warn",
                    workspace_filter=None,
                    created_at=now,
                ),
                ReviewDestination(
                    name="security-pager",
                    webhook_url="https://pager.example.com/notify",
                    hmac_secret=None,
                    is_active=False,
                    min_severity="critical",
                    workspace_filter=None,
                    created_at=now,
                ),
            ]
        )
        session.commit()


class TestReviewDestPageAccess:
    """Auth + authorization gate."""

    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin/review-destinations")
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
            resp = await client.get("/admin/review-destinations")
        assert resp.status_code == 403


class TestReviewDestPageContent:
    """Row rendering + secret hiding + form chrome."""

    @pytest.mark.asyncio
    async def test_empty_state_renders(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/review-destinations")
        assert resp.status_code == 200
        body = resp.text
        assert "No review destinations configured" in body
        assert "Create destination" in body
        # Three severity options must render in the form select.
        for sev in ("ok", "warn", "critical"):
            assert f'value="{sev}"' in body

    @pytest.mark.asyncio
    async def test_seeded_destinations_render(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_destinations(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/review-destinations")
        assert resp.status_code == 200
        body = resp.text
        # Both destinations surface.
        assert "ops-slack" in body
        assert "security-pager" in body
        # Webhook URLs are visible (they are not secret per Phase 19.2).
        assert "hooks.slack.com" in body
        # The HMAC secret string must NEVER reach the page.  This is
        # the load-bearing assertion of this test file — a regression
        # that re-leaks the secret would otherwise stay invisible.
        assert "topsecret" not in body
        # HMAC presence indicator: signed → "set", unsigned → "none".
        assert ">set<" in body
        assert ">none<" in body
        # Row markers for Alpine-bound JS.
        assert 'data-destination-id="1"' in body
        assert 'data-destination-id="2"' in body
