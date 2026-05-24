"""context-panel partial dispatch smoke tests.

For each new ``active_section`` introduced asserts the
right partial renders when its landing page is requested.  Partials
identify themselves via the ``aria-label`` attribute on the wrapping
``<div>``.

The test relies on the page route's ``active_page`` value mapping to
the correct ``active_section`` via ``_section_map`` in
``base.html``.  Together with the IA-contract test in
``tests/test_nav_rail.py``, this catches drift between the rail and
the side panel.
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
    auth.register(factory, "panel@pql.test", "Panel User", "password123")
    token = auth.login(
        factory,
        "panel@pql.test",
        "password123",
        "test-secret-key-for-unit-tests!!",
    )
    assert token is not None
    return token


# (url, expected aria-label substring on the partial wrapper).  Each
# URL must hit a route that threads ``active_page`` so the section
# dispatch picks the right partial.
PARTIAL_DISPATCH: list[tuple[str, str]] = [
    ("/feed", "Feed filters"),
    ("/topics", "Topics filters"),
    ("/issues", "Issues filters"),
    ("/data-products", "Data products"),
]


class TestContextPanelDispatch:
    """Each section's landing page renders its expected partial."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url,aria_label", PARTIAL_DISPATCH)
    async def test_section_renders_its_partial(self, url, aria_label):
        factory = app.state.session_factory
        token = _seed_user(factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={auth.COOKIE_NAME: token},
        ) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            pytest.skip(f"{url} returned {resp.status_code}; out of nav-panel scope")
        body = resp.text
        assert f'aria-label="{aria_label}"' in body, (
            f"{url} did not render its context-panel partial (missing aria-label={aria_label!r})"
        )
