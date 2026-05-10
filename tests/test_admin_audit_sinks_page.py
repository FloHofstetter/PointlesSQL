"""Tests for the Sprint 33.2 ``GET /admin/audit-sinks`` HTML page.

The JSON CRUD under ``/api/admin/audit-sinks`` already has its own
test suite (``test_audit_sinks_routes.py``); this file exercises
only the HTML wrapper so any drift between the route and the
template surfaces in CI.
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import _TEMPLATES, app
from pointlessql.config import Settings
from pointlessql.models import Base
from pointlessql.models.audit._sinks import AuditSink
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


def _seed_sinks(factory):
    """Insert one webhook sink (with secret) and one s3 sink (inactive)."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add_all(
            [
                AuditSink(
                    name="prod-webhook",
                    type="webhook",
                    config_json=json.dumps(
                        {"url": "https://hooks.example.com/abc", "hmac_secret": "shh"}
                    ),
                    is_active=True,
                    event_types_json=json.dumps(["pointlessql.run.completed"]),
                    workspace_filter=None,
                    created_at=now,
                ),
                AuditSink(
                    name="archive-bucket",
                    type="s3",
                    config_json=json.dumps(
                        {
                            "bucket": "compliance-archive",
                            "region": "eu-central-1",
                            "access_key_id": "AKIA...",
                            "secret_access_key": "verysecret",
                        }
                    ),
                    is_active=False,
                    event_types_json=None,
                    workspace_filter=None,
                    created_at=now,
                ),
            ]
        )
        session.commit()


class TestAuditSinksPageAccess:
    """Auth + authorization gate."""

    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin/audit-sinks")
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
            resp = await client.get("/admin/audit-sinks")
        assert resp.status_code == 403


class TestAuditSinksPageContent:
    """Row rendering + redaction + form chrome."""

    @pytest.mark.asyncio
    async def test_empty_state_renders(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit-sinks")
        assert resp.status_code == 200
        body = resp.text
        assert "No audit sinks configured" in body
        # Create form is always present, even with zero sinks.
        assert "Create sink" in body
        # Three sink-type options must be selectable.
        assert 'value="webhook"' in body
        assert 'value="s3"' in body
        assert 'value="aws_cloudtrail"' in body

    @pytest.mark.asyncio
    async def test_seeded_sinks_render(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_sinks(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit-sinks")
        assert resp.status_code == 200
        body = resp.text
        # Both sink names appear.
        assert "prod-webhook" in body
        assert "archive-bucket" in body
        # Sensitive keys must be redacted to literal "<set>" — never
        # the cleartext value.  This is the only safety-net the page
        # has against accidental ``config_json`` exposure.
        assert "shh" not in body
        assert "verysecret" not in body
        assert "&lt;set&gt;" in body or "<set>" in body
        # Type badges present.
        assert "webhook" in body
        assert "s3" in body
        # Active / inactive distinguishable (toggle-checkbox markup).
        assert 'data-sink-id="1"' in body
        assert 'data-sink-id="2"' in body
