"""Tests for the ``GET /admin/system-info`` HTML page.

Read-only panel covering PII mode, OIDC group mapping, system_keys
inventory, and API-key scope counts.  All values come from
``Settings`` (env-var driven) or read-only DB queries; nothing is
writable here, so the tests focus on (a) the load-bearing
assertion that the PII hash secret value never reaches the page
and (b) that env-var-driven config surfaces correctly.
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
from pointlessql.models.system_keys import SystemKey
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
        oidc={
            "discovery_url": "https://idp.example.com/.well-known/openid-configuration",
            "client_id": "pql-test",
            "group_map_raw": ("ops:ws=2,scopes=admin;auditors:ws=1,scopes=auditor"),
        },
    )
    app.state.templates = _TEMPLATES

    mock_uc = AsyncMock()
    mock_uc.list_catalogs.return_value = []
    mock_uc.get_tree.return_value = []
    app.state.uc_client = mock_uc

    yield

    engine.dispose()


def _seed_users(factory):
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
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add_all(
            [
                Workspace(id=1, slug="default", name="Default", created_at=now),
                Workspace(id=2, slug="prod", name="Production", created_at=now),
            ]
        )
        session.commit()


def _seed_pii_hash_secret(factory, value="should-never-leak-to-page"):
    """Seed a system_keys row mirroring a real lazy-generated PII hash."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(SystemKey(name="pii_hash", value=value, created_at=now))
        session.commit()


def _seed_api_keys(factory):
    """Seed varied keys so the count panel has non-zero rows."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add_all(
            [
                ApiKey(
                    name="agent-key",
                    secret_hash="2" * 64,
                    secret_prefix="agent...",
                    supervisor=False,
                    auditor=False,
                    workspace_id=1,
                    created_at=now,
                ),
                ApiKey(
                    name="supervisor-key",
                    secret_hash="3" * 64,
                    secret_prefix="super...",
                    supervisor=True,
                    auditor=False,
                    workspace_id=1,
                    created_at=now,
                ),
                ApiKey(
                    name="auditor-key",
                    secret_hash="4" * 64,
                    secret_prefix="audit...",
                    supervisor=False,
                    auditor=True,
                    workspace_id=2,
                    created_at=now,
                ),
            ]
        )
        session.commit()


class TestSystemInfoPageAccess:
    """Auth + authorization gate."""

    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin/system-info")
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
            resp = await client.get("/admin/system-info")
        assert resp.status_code == 403


class TestSystemInfoPageContent:
    """Section rendering + secret hiding."""

    @pytest.mark.asyncio
    async def test_pii_section_renders_active_mode(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        _seed_pii_hash_secret(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/system-info")
        assert resp.status_code == 200
        body = resp.text
        # Active mode chip + env var hint.
        assert "hash_only" in body
        assert "POINTLESSQL_AUDIT_PII_MODE" in body
        # Hash-secret presence indicator.
        assert "present" in body
        # Load-bearing: the PII hash secret VALUE must never reach
        # the page.  Only the literal "present" badge + a creation
        # date are surfaced.
        assert "should-never-leak-to-page" not in body

    @pytest.mark.asyncio
    async def test_oidc_mapping_renders_read_only(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/system-info")
        assert resp.status_code == 200
        body = resp.text
        # Group names from the env-driven group map surface.
        assert "ops" in body
        assert "auditors" in body
        # Restart-required hint visible.
        assert "POINTLESSQL_OIDC_GROUP_MAP" in body
        # No <input> / <textarea> for OIDC map editing.
        # (we still have inputs for the create form on api-keys but
        # this is a different page; assert no editable mapping).
        assert 'name="group_map' not in body.lower()

    @pytest.mark.asyncio
    async def test_api_key_counts_render(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        _seed_api_keys(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/system-info")
        assert resp.status_code == 200
        body = resp.text
        # The "Manage keys" CTA is the entry point to /admin/api-keys.
        assert "Manage keys" in body
        assert "/admin/api-keys" in body

    @pytest.mark.asyncio
    async def test_system_keys_inventory_renders_names_only(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        _seed_workspaces(factory)
        _seed_pii_hash_secret(factory, value="another-secret-shape")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/system-info")
        assert resp.status_code == 200
        body = resp.text
        # Name surfaced.
        assert "pii_hash" in body
        # Value never surfaced — second load-bearing assertion.
        assert "another-secret-shape" not in body
