"""Tests for the Sprint 41 admin audit-log viewer route."""

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
from pointlessql.models import AuditLog, Base
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
    """Create an admin (first signup) and a regular user; return tokens."""
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


def _seed_rows(factory, now):
    """Insert a spread of audit rows across time windows and users."""
    with factory() as session:
        session.add_all(
            [
                AuditLog(
                    user_id=1,
                    user_email="admin@pql.test",
                    action="update_catalog",
                    target="catalog:demo",
                    detail='{"comment": "new"}',
                    created_at=now - datetime.timedelta(minutes=5),
                ),
                AuditLog(
                    user_id=1,
                    user_email="admin@pql.test",
                    action="sync_catalog",
                    target="catalog:demo",
                    detail=None,
                    created_at=now - datetime.timedelta(days=3),
                ),
                AuditLog(
                    user_id=2,
                    user_email="user@pql.test",
                    action="create_connection",
                    target="table:demo.sales.orders",
                    detail=None,
                    created_at=now - datetime.timedelta(days=10),
                ),
                AuditLog(
                    user_id=1,
                    user_email="admin@pql.test",
                    action="update_catalog",
                    target="catalog:other",
                    detail="not even json",
                    created_at=now - datetime.timedelta(days=45),
                ),
            ]
        )
        session.commit()


class TestAdminAuditAccess:
    """Auth + authorization gate."""

    @pytest.mark.asyncio
    async def test_anonymous_redirects_to_login(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/admin/audit")
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
            resp = await client.get("/admin/audit")
        assert resp.status_code == 403


class TestAdminAuditContent:
    """Row rendering, ordering, filters."""

    @pytest.mark.asyncio
    async def test_admin_sees_newest_first(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            # Default window is 7d — only the two fresh rows should appear.
            resp = await client.get("/admin/audit")
        assert resp.status_code == 200
        body = resp.text

        # Row actions render inside a badge span; use that marker so
        # the assertion doesn't get confused by the <option> list of
        # the server-side filter dropdown (which sorts alphabetically).
        def _badge(action: str) -> str:
            return f'<span class="badge bg-secondary font-monospace">{action}</span>'

        # Both recent rows present in the table body.
        assert _badge("update_catalog") in body
        assert _badge("sync_catalog") in body
        # Older row filtered out by default 7d window.
        assert _badge("create_connection") not in body
        # Newest row appears before the older one in the DOM.
        assert body.index(_badge("update_catalog")) < body.index(_badge("sync_catalog"))

    @pytest.mark.asyncio
    async def test_all_time_window_surfaces_older_rows(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit?since=all")
        assert resp.status_code == 200
        body = resp.text
        assert "create_connection" in body
        # Row with a non-JSON detail must still render (not crash
        # the page).
        assert "not even json" in body

    @pytest.mark.asyncio
    async def test_action_filter_narrows(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit?since=all&action=sync_catalog")
        assert resp.status_code == 200
        body = resp.text
        # Target cells get `font-monospace small` classes; that's how
        # we isolate table content from dropdown/sidebar text.
        assert '<td data-label="Target" class="font-monospace small">catalog:demo</td>' in body
        assert '<td data-label="Target" class="font-monospace small">catalog:other</td>' not in body
        assert (
            '<td data-label="Target" class="font-monospace small">table:demo.sales.orders</td>'
            not in body
        )

    @pytest.mark.asyncio
    async def test_target_filter_is_substring_match(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit?since=all&target=other")
        assert resp.status_code == 200
        body = resp.text
        assert '<td data-label="Target" class="font-monospace small">catalog:other</td>' in body
        assert '<td data-label="Target" class="font-monospace small">catalog:demo</td>' not in body


class TestAdminAuditExport:
    """Sprint 48: JSON + CSV export endpoint."""

    @pytest.mark.asyncio
    async def test_non_admin_export_denied(self):
        factory = app.state.session_factory
        _admin_token, user_token = _seed_users(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: user_token},
        ) as client:
            resp = await client.get("/admin/audit/export?fmt=json")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_json_export_returns_attachment(self):
        import json

        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit/export?fmt=json&since=all")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        cd = resp.headers["content-disposition"]
        assert cd.startswith("attachment;")
        assert "pql-audit-" in cd and cd.endswith('.json"')

        payload = json.loads(resp.text)
        assert "exported_at" in payload
        entries = payload["entries"]
        assert len(entries) == 4  # all four _seed_rows entries
        # Spot-check the row shape.
        sample = entries[0]
        for key in (
            "id",
            "created_at",
            "user_id",
            "user_email",
            "actor_role",
            "action",
            "target",
            "client_ip",
            "detail",
        ):
            assert key in sample

    @pytest.mark.asyncio
    async def test_csv_export_has_header_and_rows(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit/export?fmt=csv&since=all")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        lines = [line for line in resp.text.splitlines() if line]
        # Header + 4 data rows.
        assert len(lines) == 5
        assert lines[0].split(",")[:4] == ["id", "created_at", "user_id", "user_email"]
        # At least one action string from the seed shows up in the body.
        assert any("update_catalog" in line for line in lines[1:])

    @pytest.mark.asyncio
    async def test_export_respects_filters(self):
        factory = app.state.session_factory
        admin_token, _ = _seed_users(factory)
        now = datetime.datetime.now(datetime.UTC)
        _seed_rows(factory, now)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: admin_token},
        ) as client:
            resp = await client.get("/admin/audit/export?fmt=json&since=all&action=sync_catalog")

        assert resp.status_code == 200
        import json

        entries = json.loads(resp.text)["entries"]
        assert len(entries) == 1
        assert entries[0]["action"] == "sync_catalog"
