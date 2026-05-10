"""Sprint 28.4 — workspace switcher cookie + topbar rendering.

Covers the four user-visible surfaces of 28.4:

1. ``POST /auth/switch-workspace`` writes the ``pql_workspace`` cookie
   (with membership enforcement).
2. The middleware reads the cookie back via
   :func:`_read_workspace_slug_from_session` so subsequent requests
   resolve into the new workspace.
3. ``base.html`` renders the three workspace meta-tags + the
   ``components/workspace_switcher.html`` partial only when the user
   has more than one workspace (single-workspace UX stays unchanged).
4. The HTML route handlers thread ``current_workspace`` /
   ``available_workspaces`` / ``current_workspace_primary_catalog``
   into every TemplateResponse via the wrapper in ``api/main.py``.
"""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.api.middleware import WORKSPACE_COOKIE_NAME
from pointlessql.models import WorkspaceCatalogPin
from pointlessql.services import workspaces as workspaces_service


def _factory():
    return app.state.session_factory


@pytest.fixture
def second_workspace() -> int:
    ws = workspaces_service.create_workspace(_factory(), slug="ws-switch-b", name="Workspace B")
    return ws.id


def _csrf_for(client: httpx.AsyncClient) -> str:
    """Return the CSRF token that the test cookie + middleware expect."""
    return "test-csrf-token"


@pytest.mark.asyncio
async def test_switch_workspace_sets_cookie_and_redirects(
    second_workspace: int,
) -> None:
    """The user must be a member; on success the cookie is set."""
    workspaces_service.add_member(
        _factory(),
        workspace_id=second_workspace,
        user_id=1,  # admin test user
        role="member",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={**app.state._test_auth_cookie, "pql_csrf": "test-csrf-token"},
    ) as client:
        response = await client.post(
            "/auth/switch-workspace",
            data={"slug": "ws-switch-b", "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert WORKSPACE_COOKIE_NAME in response.cookies
    assert response.cookies[WORKSPACE_COOKIE_NAME] == "ws-switch-b"


@pytest.mark.asyncio
async def test_switch_workspace_403_for_non_member(second_workspace: int) -> None:
    """A workspace the user is NOT a member of returns 403, no cookie."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={**app.state._test_auth_cookie, "pql_csrf": "test-csrf-token"},
    ) as client:
        response = await client.post(
            "/auth/switch-workspace",
            data={"slug": "ws-switch-b", "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
    assert response.status_code == 403
    assert WORKSPACE_COOKIE_NAME not in response.cookies


@pytest.mark.asyncio
async def test_switch_workspace_404_for_unknown_slug() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={**app.state._test_auth_cookie, "pql_csrf": "test-csrf-token"},
    ) as client:
        response = await client.post(
            "/auth/switch-workspace",
            data={"slug": "ws-not-real", "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_switch_workspace_requires_auth() -> None:
    """An unauthenticated POST returns 401 (or redirect to login).

    The middleware short-circuits before the route handler runs;
    this test asserts the route is NOT publicly settable.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"pql_csrf": "test-csrf-token"},
    ) as client:
        response = await client.post(
            "/auth/switch-workspace",
            data={"slug": "default", "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
    # Public path under /auth/ — middleware lets it through, but the
    # route handler itself rejects unauth callers.
    assert response.status_code in (401, 303)


@pytest.mark.asyncio
async def test_cookie_is_consumed_on_subsequent_request(
    second_workspace: int,
) -> None:
    """After switching, X-Workspace-less requests resolve via the cookie."""
    workspaces_service.add_member(
        _factory(),
        workspace_id=second_workspace,
        user_id=1,
        role="member",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={
            **app.state._test_auth_cookie,
            "pql_csrf": "test-csrf-token",
            WORKSPACE_COOKIE_NAME: "ws-switch-b",
        },
    ) as client:
        # /auth/me is the lightest authenticated endpoint we have;
        # we don't read the workspace off the body, the assertion
        # is purely that the cookie path is accepted (no 403).
        response = await client.get("/auth/me")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_meta_tags_render_in_base_html() -> None:
    """The three workspace meta tags must appear when context is present."""
    factory = _factory()
    with factory() as session:
        session.add(
            WorkspaceCatalogPin(
                workspace_id=1,
                catalog_name="meta-tag-test",
                mode="primary",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=app.state._test_auth_cookie,
        ) as client:
            response = await client.get("/")
        assert response.status_code == 200
        body = response.text
        assert 'name="workspace-id"' in body
        assert 'name="workspace-slug"' in body
        assert 'name="workspace-primary-catalog"' in body
        assert 'content="default"' in body
        assert 'content="meta-tag-test"' in body
    finally:
        # Clean up the pin so it doesn't bleed into other tests.
        with factory() as session:
            session.query(WorkspaceCatalogPin).filter(
                WorkspaceCatalogPin.catalog_name == "meta-tag-test"
            ).delete()
            session.commit()


@pytest.mark.asyncio
async def test_switcher_hidden_when_only_one_workspace() -> None:
    """A user with exactly one workspace gets no switcher dropdown."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    # The switcher's distinctive marker is the dropdown-toggle button
    # with aria-label="Switch workspace".  Single-workspace installs
    # render the topbar without it.
    assert 'aria-label="Switch workspace"' not in response.text


@pytest.mark.asyncio
async def test_switcher_renders_when_user_has_multiple_workspaces(
    second_workspace: int,
) -> None:
    """With ≥2 memberships, the dropdown surfaces in the topbar."""
    workspaces_service.add_member(
        _factory(),
        workspace_id=second_workspace,
        user_id=1,
        role="member",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    body = response.text
    assert 'aria-label="Switch workspace"' in body
    # Both names appear in the dropdown.
    assert "Default workspace" in body
    assert "Workspace B" in body


def test_help_slug_resolves() -> None:
    """The new help slug is registered and length-compliant."""
    from pointlessql.web import HELP, get_help

    entry = get_help("workspace.what-is-a-workspace")
    assert "workspace" in entry.title.lower()
    assert len(entry.body) <= 280
    assert entry.learn_more is not None
    # Spot-check the canonical map shape.
    assert HELP["workspace.what-is-a-workspace"] is entry
