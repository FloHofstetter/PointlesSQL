"""Phase 80.6 — /api/search expanded entity coverage tests.

Seeds one entity of each new kind and asserts ``/api/search?q=``
returns at least one hit of that kind.  Also asserts the @user /
#topic operator prefixes narrow results to the right kind.
"""

from __future__ import annotations

import datetime as dt
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
    mock_uc.list_credentials.return_value = []
    mock_uc.list_external_locations.return_value = []
    app.state.uc_client = mock_uc

    yield

    engine.dispose()


def _seed_user(factory) -> str:
    auth.register(factory, "search@pql.test", "Search User", "password123")
    token = auth.login(
        factory,
        "search@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


def _seed_topic(factory, name: str, slug: str) -> None:
    from pointlessql.models import Topic

    with factory() as session:
        topic = Topic(
            workspace_id=1,
            slug=slug,
            display_name=name,
            description_md=f"About {name}",
            created_by_user_id=1,
            created_at=dt.datetime.now(dt.UTC),
        )
        session.add(topic)
        session.commit()


def _seed_issue(factory, title: str) -> int:
    """Seed an Issue with the minimum FK plumbing.

    Issues need a parent ``social_target`` row, so we materialise one
    of kind=``workspace`` pointing at the default workspace.
    """
    from pointlessql.models.social._issue import Issue
    from pointlessql.models.social._social_target import SocialTarget

    with factory() as session:
        # Reuse or create a workspace-anchored SocialTarget so the
        # FK constraints on Issue.social_target_id and
        # Issue.parent_social_target_id are satisfied.
        target = SocialTarget(
            workspace_id=1,
            entity_kind="workspace",
            entity_ref="default",
            created_at=dt.datetime.now(dt.UTC),
        )
        session.add(target)
        session.flush()
        issue = Issue(
            workspace_id=1,
            social_target_id=target.id,
            parent_social_target_id=target.id,
            title=title,
            body_md="seed",
            state="open",
            opened_by_user_id=1,
            opened_at=dt.datetime.now(dt.UTC),
        )
        session.add(issue)
        session.commit()
        return int(issue.id)


class TestPaletteCoverage:
    """At least one hit per Phase-80.6 entity kind."""

    @pytest.mark.asyncio
    async def test_user_kind_returned(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/search?q=Search")
        assert resp.status_code == 200
        hits = resp.json()
        assert any(h["type"] == "user" for h in hits), hits

    @pytest.mark.asyncio
    async def test_topic_kind_returned(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        _seed_topic(factory, "Finance Analytics", "finance")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/search?q=Finance")
        assert resp.status_code == 200
        hits = resp.json()
        topic_hits = [h for h in hits if h["type"] == "topic"]
        assert len(topic_hits) >= 1, hits

    @pytest.mark.asyncio
    async def test_issue_kind_returned(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        _seed_issue(factory, "Stale data product")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/search?q=stale")
        assert resp.status_code == 200
        hits = resp.json()
        issue_hits = [h for h in hits if h["type"] == "issue"]
        assert len(issue_hits) >= 1, hits

    @pytest.mark.asyncio
    async def test_workspace_kind_returned(self):
        from pointlessql.models import Workspace

        factory = app.state.session_factory
        # Seed workspace row id=1 (Base.metadata.create_all only
        # builds the schema; the workspace seed normally comes from
        # an Alembic migration that doesn't run in unit tests).
        with factory() as session:
            ws = Workspace(
                id=1,
                slug="default",
                name="Default workspace",
                created_at=dt.datetime.now(dt.UTC),
            )
            session.merge(ws)
            session.commit()
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/search?q=default")
        assert resp.status_code == 200
        hits = resp.json()
        ws_hits = [h for h in hits if h["type"] == "workspace"]
        assert len(ws_hits) >= 1, hits


class TestPaletteOperators:
    """``@user`` and ``#topic`` narrow to a single kind."""

    @pytest.mark.asyncio
    async def test_at_user_operator_filters_to_users(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        _seed_topic(factory, "Search Topic", "search-topic")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/search?q=@Search")
        assert resp.status_code == 200
        hits = resp.json()
        # Every hit must be type=user (even though a topic also
        # contains "Search").
        assert hits, "expected at least one hit"
        assert all(h["type"] == "user" for h in hits), hits

    @pytest.mark.asyncio
    async def test_hash_topic_operator_filters_to_topics(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        _seed_topic(factory, "Finance Topic", "finance")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/api/search?q=%23Finance")
        assert resp.status_code == 200
        hits = resp.json()
        assert hits, "expected at least one hit"
        assert all(h["type"] == "topic" for h in hits), hits


class TestPaletteCopy:
    """The placeholder copy mentions the new operators."""

    @pytest.mark.asyncio
    async def test_placeholder_text_updated(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        assert "@user" in body
        assert "#topic" in body
