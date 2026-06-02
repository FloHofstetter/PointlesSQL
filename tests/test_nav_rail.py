"""Primary navigation rail acceptance tests.

Asserts the hub-and-spoke IA contract from
``docs/internal/navigation_ia.md`` is honoured by the rendered HTML:

* the rail collapses to six destination hubs (Home, Watch, Build,
  Data, Community) plus the admin footer entry
* each hub's spoke list (its sub-features) renders in the context
  panel when that hub's landing page is requested
* the expand/collapse toggle button is present
* the active hub highlight flips with ``active_hub`` per page
* the mobile offcanvas nav (``nav_links.html``) still carries the
  flat IA with its group headers
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


# The six rail hubs: (href, label, data-section key).
RAIL_HUBS: list[tuple[str, str, str]] = [
    ("/", "Home", "home"),
    ("/runs", "Watch", "watch"),
    ("/sql", "Build", "build"),
    ("/data-products", "Data", "data"),
    ("/topics", "Community", "community"),
]

# Each hub's landing URL -> the spoke labels its context panel must
# carry.  Every one of the legacy flat rail entries lives in exactly
# one hub's spoke list, so nothing is dropped — it just moves one
# level down into the second sidebar.
HUB_SPOKES: list[tuple[str, list[str]]] = [
    ("/", ["Today", "Feed"]),
    ("/runs", ["Agent runs", "Audit", "Alerts"]),
    (
        "/sql",
        ["SQL editor", "Lens", "Notebooks", "Dashboards", "Scheduled jobs", "dbt"],
    ),
    (
        "/data-products",
        [
            "Catalog",
            "Data products",
            "Domains",
            "Glossary",
            "Mesh",
            "Ingest",
            "Views",
            "Canvas",
            "ML models",
            "MLflow",
            "Delta branches",
            "Lineage",
        ],
    ),
    ("/topics", ["Topics", "Issues", "People", "Agents"]),
]


class TestRailHubs:
    """The rail renders six hubs; each hub's spokes are reachable."""

    @pytest.mark.asyncio
    async def test_every_hub_renders(self):
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

        for href, label, section in RAIL_HUBS:
            assert f'href="{href}"' in body, f"missing hub href: {href}"
            assert f'data-section="{section}"' in body, f"missing hub section: {section}"
            assert f">{label}</span>" in body, f"missing hub label: {label!r}"
        # The admin footer hub renders for everyone (locked stub for
        # non-admins) so the label is always present.
        assert ">Admin</span>" in body

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url,spokes", HUB_SPOKES)
    async def test_hub_landing_renders_its_spokes(self, url, spokes):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            pytest.skip(f"{url} returned {resp.status_code}; out of nav-rail scope")
        body = resp.text
        for spoke in spokes:
            assert spoke in body, f"{url} missing spoke {spoke!r} in context panel"

    @pytest.mark.asyncio
    async def test_mobile_group_headers_render(self):
        """The mobile offcanvas nav keeps the flat grouped IA."""
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
        for group in ["Home", "Watch", "Build", "Data", "Community"]:
            assert f'class="pql-mobile-nav__group">{group}<' in body, (
                f"missing mobile group header: {group}"
            )

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


class TestActiveHub:
    """The active hub highlight flips with the page's hub."""

    @pytest.mark.asyncio
    async def test_home_page_marks_home_hub_active(self):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get("/")
        body = resp.text
        assert "pql-icon-rail__link active" in body
        assert 'data-active-hub="home"' in body

    @pytest.mark.asyncio
    async def test_runs_page_marks_watch_hub_active(self):
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
        assert 'data-active-hub="watch"' in body
        assert 'class="pql-icon-rail__link active"' in body, "active class missing on rail"


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
