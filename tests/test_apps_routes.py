"""Hosted-apps routes: pages, lifecycle JSON surface, and the proxy.

The apps routers ship unregistered (the navigation integration wires
them into the bootstrap block later), so this module mounts them onto
the app for its own duration and removes the routes on teardown — the
session-global app stays pristine for other test modules, and the
fixture no-ops once the routers are registered for real.

The proxy's upstream worker is mocked via ``httpx.MockTransport`` on
``app.state.apps_proxy_transport`` (same seam as the MLflow proxy
tests) so forwarding behaviour is asserted without a real subprocess.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from pointlessql.api import apps_html_routes, apps_proxy, apps_routes
from pointlessql.api.main import app
from pointlessql.models import User
from pointlessql.models.hosted_apps import HostedApp
from pointlessql.services import app_hosting, secret_scopes
from pointlessql.services.app_hosting import AppsConfig, AppsManager


@pytest.fixture(autouse=True, scope="module")
def _mount_apps_routers() -> Iterator[None]:
    """Mount the three apps routers for this module only."""
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/apps" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(apps_routes.router)
    app.include_router(apps_proxy.router)
    app.include_router(apps_html_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


@pytest.fixture(autouse=True)
def _no_manager_by_default() -> Iterator[None]:
    """Each test starts without a wired manager; reset on exit."""
    app.state.apps_manager = None
    yield
    app.state.apps_manager = None


@pytest.fixture
def apps_manager() -> AppsManager:
    """Install a real (never-spawning) manager on the app state."""
    manager = AppsManager(AppsConfig())
    app.state.apps_manager = manager
    return manager


@pytest.fixture
def mock_upstream() -> Iterator[dict[str, Any]]:
    """Capture the proxy's outbound request via ``httpx.MockTransport``."""
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            content=b'{"app":"ok"}',
            headers={"content-type": "application/json"},
        )

    app.state.apps_proxy_transport = httpx.MockTransport(_handler)
    try:
        yield captured
    finally:
        app.state.apps_proxy_transport = None


def _admin_user_id() -> int:
    """Return the seeded admin's user id."""
    factory = app.state.session_factory
    with factory() as session:
        user = session.scalars(select(User).where(User.email == "test@test.com")).first()
        assert user is not None
        return user.id


def _create_app(**overrides: Any) -> HostedApp:
    """Create an app row through the service layer."""
    kwargs: dict[str, Any] = {
        "workspace_id": 1,
        "title": "Demo",
        "description": None,
        "kind": "fastapi",
        "source_code": "app = None",
        "command_override": None,
        "env": None,
        "created_by_user_id": _admin_user_id(),
    }
    kwargs.update(overrides)
    return app_hosting.create_app(app.state.session_factory, **kwargs)


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


async def test_apps_page_redirects_anonymous(anonymous_client: httpx.AsyncClient) -> None:
    """Anonymous HTML traffic bounces to the login page."""
    res = await anonymous_client.get("/apps", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login"


async def test_apps_page_renders_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    """Any signed-in user reaches the list; the x-data stays single-quoted."""
    res = await non_admin_client.get("/apps")
    assert res.status_code == 200
    body = res.text
    assert 'data-pql-entry="apps.js' in body
    assert "x-data='hostedApps(" in body
    # Non-admins must not see the create form.
    assert "New app" not in body


async def test_apps_page_shows_create_form_for_admin(admin_client: httpx.AsyncClient) -> None:
    """Admins get the create card on the same page."""
    res = await admin_client.get("/apps")
    assert res.status_code == 200
    assert "New app" in res.text


async def test_app_detail_page_renders(admin_client: httpx.AsyncClient) -> None:
    """The detail page seeds the Alpine factory with the app row."""
    row = _create_app(title="Detail Demo")
    res = await admin_client.get(f"/apps/{row.slug}")
    assert res.status_code == 200
    body = res.text
    assert 'data-pql-entry="app_detail.js' in body
    assert "x-data='hostedAppDetail(" in body
    assert "Detail Demo" in body


async def test_app_detail_page_unknown_slug_404(admin_client: httpx.AsyncClient) -> None:
    """Unknown slugs answer 404, not an empty cockpit."""
    res = await admin_client.get("/apps/nope")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Lifecycle JSON surface
# ---------------------------------------------------------------------------


async def test_create_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    """Members cannot create apps — they run code on the host."""
    res = await non_admin_client.post(
        "/api/apps",
        json={"title": "Nope", "kind": "fastapi", "source_code": ""},
    )
    assert res.status_code == 403


async def test_admin_creates_and_lists_apps(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Admins create; every signed-in user can list."""
    res = await admin_client.post(
        "/api/apps",
        json={
            "title": "Churn Explorer",
            "kind": "fastapi",
            "source_code": "app = None",
            "env": {"API_TOKEN": "plain"},
        },
    )
    assert res.status_code == 200
    created = res.json()
    assert created["state"] == "stopped"
    assert created["port"] is None
    assert created["slug"].startswith("churn-explorer-")

    listed = await non_admin_client.get("/api/apps")
    assert listed.status_code == 200
    slugs = [item["slug"] for item in listed.json()["apps"]]
    assert created["slug"] in slugs


async def test_create_rejects_bad_kind(admin_client: httpx.AsyncClient) -> None:
    """Unknown kinds answer 422 with the validation message."""
    res = await admin_client.post(
        "/api/apps",
        json={"title": "Bad", "kind": "php", "source_code": ""},
    )
    assert res.status_code == 422


async def test_patch_requires_admin_and_updates_source(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Source edits are admin-only and round-trip through the PATCH."""
    row = _create_app()
    denied = await non_admin_client.patch(
        f"/api/apps/{row.slug}", json={"source_code": "print('x')"}
    )
    assert denied.status_code == 403
    res = await admin_client.patch(f"/api/apps/{row.slug}", json={"source_code": "print('x')"})
    assert res.status_code == 200
    assert res.json()["source_code"] == "print('x')"


async def test_start_without_manager_is_503(admin_client: httpx.AsyncClient) -> None:
    """With hosted apps unwired the start fails loudly."""
    row = _create_app()
    res = await admin_client.post(f"/api/apps/{row.slug}/start")
    assert res.status_code == 503


async def test_start_resolves_secrets_and_reaches_ready(
    admin_client: httpx.AsyncClient,
    apps_manager: AppsManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start resolves ``{{secrets/...}}`` refs and lands in ``ready``."""
    factory = app.state.session_factory
    scope = secret_scopes.create_scope(
        factory,
        workspace_id=1,
        name="apps",
        description=None,
        principal="test@test.com",
    )
    secret_scopes.put_secret(
        factory,
        scope_id=scope.id,
        key="token",
        value="s3cr3t",
        principal="test@test.com",
    )
    row = _create_app(env={"API_TOKEN": "{{secrets/apps/token}}", "PLAIN": "1"})

    captured: dict[str, Any] = {}

    async def fake_start(app_row: HostedApp, *, env: dict[str, str]) -> int:
        captured["app_id"] = app_row.id
        captured["env"] = env
        return 9200

    monkeypatch.setattr(apps_manager, "start", fake_start)
    res = await admin_client.post(f"/api/apps/{row.slug}/start")
    assert res.status_code == 200
    assert res.json()["state"] == "ready"
    assert captured["app_id"] == row.id
    assert captured["env"] == {"API_TOKEN": "s3cr3t", "PLAIN": "1"}
    # The stored row still carries the placeholder, never the secret.
    refreshed = app_hosting.get_app(factory, workspace_id=1, slug=row.slug)
    assert refreshed is not None
    assert "s3cr3t" not in refreshed.env_json

    stopped = await admin_client.post(f"/api/apps/{row.slug}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"


async def test_failed_start_records_failed_state(
    admin_client: httpx.AsyncClient,
    apps_manager: AppsManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker that never gets healthy lands in ``failed`` + error."""
    row = _create_app()

    async def fake_start(app_row: HostedApp, *, env: dict[str, str]) -> int:
        raise RuntimeError("worker exited with code 1")

    monkeypatch.setattr(apps_manager, "start", fake_start)
    res = await admin_client.post(f"/api/apps/{row.slug}/start")
    assert res.status_code == 422
    refreshed = app_hosting.get_app(app.state.session_factory, workspace_id=1, slug=row.slug)
    assert refreshed is not None
    assert refreshed.state == "failed"
    assert "worker exited" in (refreshed.last_error or "")


async def test_start_requires_admin(
    non_admin_client: httpx.AsyncClient, apps_manager: AppsManager
) -> None:
    """Members cannot start workers."""
    row = _create_app()
    res = await non_admin_client.post(f"/api/apps/{row.slug}/start")
    assert res.status_code == 403


async def test_delete_removes_the_app(admin_client: httpx.AsyncClient) -> None:
    """Delete answers the deletion flag and the row disappears."""
    row = _create_app()
    res = await admin_client.delete(f"/api/apps/{row.slug}")
    assert res.status_code == 200
    assert res.json() == {"deleted": True}
    assert app_hosting.get_app(app.state.session_factory, workspace_id=1, slug=row.slug) is None


async def test_logs_tail_returns_lines(admin_client: httpx.AsyncClient) -> None:
    """The log route tails the worker's stderr capture file."""
    row = _create_app()
    log_path = app_hosting.stderr_log_path(row.id)
    log_path.write_text("boot\nready\n", encoding="utf-8")
    try:
        res = await admin_client.get(f"/api/apps/{row.slug}/logs")
        assert res.status_code == 200
        assert res.json() == {"slug": row.slug, "lines": ["boot", "ready"]}
    finally:
        log_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Reverse-proxy
# ---------------------------------------------------------------------------


class _ReadyManager:
    """Manager stand-in exposing one live worker port."""

    def __init__(self, app_id: int, port: int) -> None:
        self.config = AppsConfig()
        self._ports = {app_id: port}

    def port_for(self, app_id: int) -> int | None:
        return self._ports.get(app_id)


async def test_proxy_redirects_anonymous(anonymous_client: httpx.AsyncClient) -> None:
    """No auth cookie → the auth middleware bounces to login first."""
    res = await anonymous_client.get("/apps/whatever/proxy/", follow_redirects=False)
    assert res.status_code == 303
    assert "/auth/login" in res.headers.get("location", "")


async def test_proxy_unknown_slug_404(admin_client: httpx.AsyncClient) -> None:
    """Unknown slugs answer 404 before any upstream call."""
    res = await admin_client.get("/apps/nope/proxy/")
    assert res.status_code == 404


async def test_proxy_foreign_workspace_slug_404(admin_client: httpx.AsyncClient) -> None:
    """Apps of other workspaces look absent on purpose."""
    row = _create_app(workspace_id=2)
    res = await admin_client.get(f"/apps/{row.slug}/proxy/")
    assert res.status_code == 404


async def test_proxy_not_ready_503(admin_client: httpx.AsyncClient) -> None:
    """A stopped app answers 503 with its state in the detail."""
    row = _create_app()
    res = await admin_client.get(f"/apps/{row.slug}/proxy/")
    assert res.status_code == 503
    assert "stopped" in res.text


async def test_proxy_ready_without_worker_port_503(admin_client: httpx.AsyncClient) -> None:
    """A ready row whose worker died answers 503, not a hang."""
    row = _create_app()
    app_hosting.set_state(app.state.session_factory, app_id=row.id, state="ready")
    app.state.apps_manager = _ReadyManager(app_id=-1, port=9999)
    res = await admin_client.get(f"/apps/{row.slug}/proxy/")
    assert res.status_code == 503


async def test_proxy_forwards_and_injects_headers(
    admin_client: httpx.AsyncClient,
    mock_upstream: dict[str, Any],
) -> None:
    """Auth'd traffic forwards with user + prefix headers injected."""
    row = _create_app()
    app_hosting.set_state(app.state.session_factory, app_id=row.id, state="ready")
    app.state.apps_manager = _ReadyManager(app_id=row.id, port=9876)

    res = await admin_client.get(f"/apps/{row.slug}/proxy/api/data?limit=5")
    assert res.status_code == 200
    assert res.json() == {"app": "ok"}

    assert mock_upstream["method"] == "GET"
    assert mock_upstream["url"] == "http://127.0.0.1:9876/api/data?limit=5"
    headers_lower = {k.lower(): v for k, v in mock_upstream["headers"].items()}
    assert headers_lower.get("x-forwarded-user") == "test@test.com"
    assert headers_lower.get("x-forwarded-prefix") == f"/apps/{row.slug}/proxy"
    # The incoming Host header was stripped; httpx re-derives it from
    # the loopback target.
    assert headers_lower.get("host", "").startswith("127.0.0.1")


async def test_proxy_forwards_post_bodies(
    admin_client: httpx.AsyncClient,
    mock_upstream: dict[str, Any],
) -> None:
    """Methods other than GET pass through with their bodies."""
    row = _create_app()
    app_hosting.set_state(app.state.session_factory, app_id=row.id, state="ready")
    app.state.apps_manager = _ReadyManager(app_id=row.id, port=9876)

    res = await admin_client.post(f"/apps/{row.slug}/proxy/submit", json={"a": 1})
    assert res.status_code == 200
    assert mock_upstream["method"] == "POST"
    assert mock_upstream["url"].endswith("/submit")


# ---------------------------------------------------------------------------
# WebSocket bridge — close codes (the happy path needs a live worker)
# ---------------------------------------------------------------------------


def test_proxy_ws_anonymous_closes_4401() -> None:
    """No cookie + no Bearer → close 4401 before any upstream connect."""
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/apps/whatever/proxy/ws") as ws:
                ws.receive_bytes()
    assert exc_info.value.code == 4401


def test_proxy_ws_unknown_slug_closes_4404(auth_cookies: dict[str, str]) -> None:
    """Authenticated but the slug doesn't resolve → 4404."""
    with TestClient(app, cookies=auth_cookies) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/apps/nope/proxy/ws") as ws:
                ws.receive_bytes()
    assert exc_info.value.code == 4404


def test_proxy_ws_not_ready_closes_4503(auth_cookies: dict[str, str]) -> None:
    """A stopped app refuses the upgrade with 4503."""
    row = _create_app()
    with TestClient(app, cookies=auth_cookies) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/apps/{row.slug}/proxy/ws") as ws:
                ws.receive_bytes()
    assert exc_info.value.code == 4503
