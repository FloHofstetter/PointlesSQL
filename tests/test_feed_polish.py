"""Feed visual + social polish.

Covers the pieces of the social-quality feed rework that are testable
server-side:

* ``composer_target_refs`` — the data-product list the composer's
  "post to" pills render from.
* ``row_from_pending_run`` — the approval card resolves its principal
  email to a display name + id so it reads as a person.
* The feed shell renders the composer, the engagement footer, the
  initials-avatar markup, and the muted view-link — and no longer ships
  the dismissible first-run welcome card.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.feed_routes._serializers import (
    composer_target_refs,
    row_from_pending_run,
)
from pointlessql.api.main import _TEMPLATES, app
from pointlessql.config import Settings
from pointlessql.models import Base
from pointlessql.models.agent._runs import STATUS_NEEDS_APPROVAL, AgentRun
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services import auth

_NOW = datetime.datetime(2026, 6, 2, 12, 0, tzinfo=datetime.UTC)


def _dp(ws: int, catalog: str, schema: str) -> DataProduct:
    """Build a minimally-valid DataProduct row for seeding."""
    return DataProduct(
        workspace_id=ws,
        catalog_name=catalog,
        schema_name=schema,
        version="v1",
        contract_yaml_hash="hash",
        contract_json="{}",
        last_loaded_at=_NOW,
        created_at=_NOW,
    )


class TestComposerTargetRefs:
    """The composer picker lists every DP in the caller's workspace."""

    def test_returns_sorted_workspace_refs(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        with factory() as s:
            s.add_all(
                [
                    _dp(1, "demo", "sales"),
                    _dp(1, "demo", "hr"),
                    _dp(2, "other", "ws"),  # different workspace — excluded
                ]
            )
            s.commit()
            refs = composer_target_refs(s, 1)
        # Sorted by catalog then schema, scoped to workspace 1.
        assert refs == ["demo.hr", "demo.sales"]
        engine.dispose()

    def test_empty_workspace_returns_empty(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        with factory() as s:
            assert composer_target_refs(s, 1) == []
        engine.dispose()


class TestRowFromPendingRun:
    """The approval card resolves its principal to a person."""

    def _run(self) -> AgentRun:
        return AgentRun(
            id="abcd1234-0000-0000-0000-000000000000",
            agent_id="agent-x",
            principal="mara@pql.test",
            notebook_path="notebooks/x.py",
            status=STATUS_NEEDS_APPROVAL,
            started_at=_NOW,
            workspace_id=1,
        )

    def test_resolves_principal_display_name(self):
        row = row_from_pending_run(self._run(), {"mara@pql.test": (5, "Mara Lindqvist")})
        assert row["render_kind"] == "approval"
        assert row["actor_display_name"] == "Mara Lindqvist"
        assert row["actor_user_id"] == 5
        # The entity is the run, so the avatar can colour by a real user.
        assert row["entity_kind"] == "run"

    def test_falls_back_to_principal_email(self):
        row = row_from_pending_run(self._run(), {})
        assert row["actor_display_name"] == "mara@pql.test"
        assert row["actor_user_id"] is None

    def test_falls_back_to_agent_id_without_principal(self):
        run = self._run()
        run.principal = None
        row = row_from_pending_run(run, {})
        assert row["actor_display_name"] == "agent-x"


class TestFeedRenderMarkers:
    """The feed shell ships the new social-quality markup."""

    @pytest.fixture(autouse=True)
    def _setup_app(self):
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

    def _client(self) -> httpx.AsyncClient:
        auth.register(app.state.session_factory, "p@pql.test", "Polish User", "password123")
        token = auth.login(
            app.state.session_factory,
            "p@pql.test",
            "password123",
            "test-secret-key-for-unit-tests!!",
        )
        assert token is not None
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        )

    @pytest.mark.asyncio
    async def test_composer_and_social_markup_present(self):
        async with self._client() as client:
            body = (await client.get("/")).text
        # Composer.
        assert "pql-feed-composer" in body
        assert "Share an update" in body
        assert "postComposer()" in body
        # Engagement footer (reactions + reply).
        assert "canReact(r)" in body
        assert "pql-feed-react-chip" in body
        assert "toggleReaction(r" in body
        assert "toggleReply(r)" in body
        # Avatar redesign + sentence grammar.
        assert "pql-feed-item__avatar--initials" in body
        assert "rowAvatar(r)" in body
        assert "laneEyebrow(r)" in body
        # Quiet view-link replaced the button-styled link.
        assert "pql-feed-viewlink" in body

    @pytest.mark.asyncio
    async def test_dismissible_welcome_card_retired(self):
        async with self._client() as client:
            body = (await client.get("/")).text
        # The first-run welcome card + its dismiss machinery are gone; the
        # quick-starts now live inside the empty state instead.
        assert "dismissWelcome" not in body
        assert "welcomeVisible" not in body

    @pytest.mark.asyncio
    async def test_feed_alias_renders_same_composer(self):
        async with self._client() as client:
            feed = (await client.get("/feed")).text
        assert "pql-feed-composer" in feed
        assert "Share an update" in feed
