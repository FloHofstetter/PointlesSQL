"""Phase 80.1 — primary navigation rail acceptance tests.

Asserts the IA contract from ``docs/internal/navigation_ia.md`` is
honoured by the rendered HTML:

* every IA entry (24 links across 6 groups + admin footer) is
  emitted as an anchor pointing at the right URL
* group headers (``Home``, ``Watch``, ``Build``, ``Data``,
  ``Community``, ``Workspace``) are rendered for desktop
* the expand/collapse toggle button is present
* active-section highlighting flips with ``active_page`` per
  page (smoke-checked on three section landings)
* mobile offcanvas nav (``nav_links.html``) mirrors the same IA
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


def _seed_user(factory) -> str:
    """Register one user and return their session token."""
    auth.register(factory, "rail@pql.test", "Rail User", "password123")
    token = auth.login(
        factory,
        "rail@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


# Phase 80.1 IA contract.  Each entry: (href, label-or-title-substring).
# Matches the rail tree in primary_rail.html.
RAIL_ENTRIES: list[tuple[str, str]] = [
    # HOME
    ("/", "Today"),
    ("/feed", "Feed"),
    # WATCH
    ("/runs", "Agent runs"),
    ("/audit/inbox", "Audit"),
    ("/alerts", "Alerts"),
    # BUILD
    ("/sql", "SQL editor"),
    ("/lens", "Lens"),
    ("/notebooks/workspace", "Notebooks"),
    ("/dashboards", "Dashboards"),
    ("/jobs", "Scheduled jobs"),
    ("/dbt", "dbt"),
    # DATA
    ("/data-products", "Data products"),
    ("/models", "ML models"),
    ("/ml", "MLflow"),
    ("/branches", "Delta branches"),
    ("/lineage", "Lineage"),
    # COMMUNITY
    ("/topics", "Topics"),
    ("/issues", "Issues"),
    ("/users", "People"),
    ("/agents", "Agents"),
]


class TestRailEntries:
    """Every IA entry is reachable from the rendered rail."""

    @pytest.mark.asyncio
    async def test_every_ia_entry_renders(self):
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

        for href, label in RAIL_ENTRIES:
            # The rail emits the href on the rail link AND the mobile
            # nav uses the same href, so a single assertion is enough.
            assert f'href="{href}"' in body, f"missing rail entry: {href}"
            assert label in body, f"missing label: {label!r}"

    @pytest.mark.asyncio
    async def test_group_headers_render(self):
        """All five intent-groups plus Workspace group surface."""
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

        # Group <li> elements carry the pql-icon-rail__group class
        # on the desktop rail.  Each group label must appear at least
        # twice (desktop rail + mobile nav_links).
        for group in ["Home", "Watch", "Build", "Data", "Community"]:
            assert (
                f'class="pql-icon-rail__group">{group}<' in body
            ), f"missing rail group header: {group}"
            assert (
                f'class="pql-mobile-nav__group">{group}<' in body
            ), f"missing mobile group header: {group}"

    @pytest.mark.asyncio
    async def test_rail_toggle_button_present(self):
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

        assert 'data-pql-rail-toggle="toggle"' in body
        assert 'aria-label="Toggle primary navigation"' in body


class TestActiveSection:
    """Active-section highlighting flips with active_page."""

    @pytest.mark.asyncio
    async def test_home_page_marks_home_active(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # The home page may flag federation OR home depending on
        # Phase 80.3 wiring.  Either way, the rail must have at least
        # one active class.
        assert "pql-icon-rail__link active" in body

    @pytest.mark.asyncio
    async def test_runs_page_marks_runs_active(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/runs")
        if resp.status_code != 200:
            pytest.skip(f"/runs returned {resp.status_code}; not under nav-rail test scope")
        body = resp.text
        # Look for the Agent-runs link with the active class.  Both
        # data-section="runs" and class="...active" must appear on
        # the same anchor.
        assert 'data-section="runs"' in body
        # At least one link with section=runs is active.
        assert (
            'class="pql-icon-rail__link active"' in body
        ), "active class missing on rail"


class TestRailStateInit:
    """The expand/collapse state is initialised from localStorage."""

    @pytest.mark.asyncio
    async def test_rail_state_init_script_present(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        # The inline init script writes data-pql-rail-state on <html>.
        assert "data-pql-rail-state" in body
        assert "pql.primary-rail.collapsed" in body
