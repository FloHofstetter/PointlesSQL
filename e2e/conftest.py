"""End-to-end test fixtures — live uvicorn server + headless Chromium.

introduces a parallel test tree at ``e2e/`` (sibling of
``tests/``, not a child) for headless-browser tests that drive the
real Phase-105 multi-tab co-edit flow.

Why the sibling layout: ``tests/conftest.py`` runs autouse fixtures
that short-circuit the FastAPI lifespan, rebind ``app.state`` to an
ASGI-transport in-memory factory, and re-seed users per test.  Those
fixtures actively fight a port-bound uvicorn server — the server
needs the *production* lifespan to run (so ``KernelRegistry`` and the
Phase-103 ``ReplayWorker`` actually exist) and a stable on-disk DB
the running uvicorn process can keep reading.  Pulling e2e tests out
from under ``tests/`` is the cleanest way to escape that cascade;
the ``[tool.pytest.ini_options] testpaths = ["tests"]`` setting keeps
the default ``pytest`` run focused on the unit suite, and CI invokes
``pytest e2e/ -m e2e`` explicitly in its own job.

Fixture stack:

* :func:`live_server_url` — session-scope.  Picks a free TCP port,
  routes the production lifespan against a tempfile SQLite (via
  ``POINTLESSQL_DB_URL``), runs ``alembic upgrade head``, seeds one
  admin test user, and boots uvicorn in a background thread.  Probes
  ``/healthz`` until the server answers 200, then yields the base
  URL.  Tears the server down by setting ``server.should_exit``.
* :func:`admin_session_cookies` — session-scope.  Performs the
  full CSRF + form-encoded ``/auth/login`` dance against the live
  server and returns the resulting cookie jar as a dict.
* :func:`playwright_browser` — session-scope.  Headless bundled
  Chromium via the ``playwright`` Python package; CI installs the
  matching browser binary with ``playwright install chromium``.
* :func:`playwright_context` — function-scope.  Fresh
  ``BrowserContext`` with the admin auth + CSRF cookies pre-injected;
  closes on teardown so per-test state never leaks across cases.

Anything that needs ``app.state`` directly should live under
``tests/`` instead — e2e tests must only reach the server over the
network.
"""

from __future__ import annotations

import datetime
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    """Return an unused TCP port on ``127.0.0.1``.

    Binds to port 0 and reads the OS-assigned port back via
    ``getsockname`` before closing the socket.  There is a small race
    between the close and the uvicorn ``listen`` call; in practice it
    is negligible on a CI runner where nothing else is binding.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run_alembic_upgrade(db_url: str) -> None:
    """Apply ``alembic upgrade head`` against *db_url*.

    The repo's ``pointlessql/alembic/env.py`` already honours
    ``POINTLESSQL_DB_URL`` — we set the env var around this call so
    autogenerate-context and run-online both pick up the e2e tempfile
    DB instead of the default repo-root sqlite.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_REPO_ROOT / "pointlessql" / "alembic"))
    command.upgrade(cfg, "head")


def _seed_admin_user(db_url: str, email: str, password: str) -> int:
    """Insert one admin workspace + user into the e2e tempfile DB.

    Mirrors :func:`tests.conftest._seed_test_users` shape but writes
    directly via SQLAlchemy so the e2e tree does not import the unit
    suite's conftest (which has destructive autouse side effects).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from pointlessql.models import User, Workspace, WorkspaceMember
    from pointlessql.services import auth as auth_service

    engine = create_engine(db_url)
    factory = sessionmaker(bind=engine)
    now = datetime.datetime.now(datetime.UTC)
    try:
        with factory() as session:
            # Alembic upgrade head ships a data-migration that creates
            # the default workspace (slug=``default``); reuse it if
            # present, otherwise insert one with the test description.
            workspace = session.query(Workspace).filter_by(slug="default").one_or_none()
            if workspace is None:
                workspace = Workspace(
                    slug="default",
                    name="Default workspace",
                    description="Phase 108 e2e fixture seed.",
                    created_at=now,
                )
                session.add(workspace)
                session.flush()
            user = User(
                email=email,
                display_name="E2E Admin",
                password_hash=auth_service.hash_password(password),
                is_admin=True,
                default_workspace_id=workspace.id,
                created_at=now,
            )
            session.add(user)
            session.flush()
            session.add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="admin",
                    created_at=now,
                )
            )
            session.commit()
            return int(user.id)
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def live_server_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Boot a real uvicorn server on a free port and yield its base URL.

    The fixture intentionally does **not** set
    ``POINTLESSQL_TEST_LIFESPAN_FAST=1`` — the e2e tests need the full
    production lifespan so :class:`KernelRegistry` and the Phase-103
    :class:`ReplayWorker` exist on ``app.state``.  Optional
    subprocesses (JupyterLab, MLflow, dbt-docs, scheduler) are
    disabled because they are not exercised by the multi-tab co-edit
    scenario and would slow the boot significantly.

    The DB is a per-session tempfile so ``alembic upgrade head`` runs
    against a clean schema and the live server's writes do not leak
    into the unit-test default ``pointlessql.db``.
    """
    port = _free_port()
    db_dir = tmp_path_factory.mktemp("e2e_db")
    db_path = db_dir / "pointlessql.db"
    db_url = f"sqlite:///{db_path}"
    notebooks_dir = tmp_path_factory.mktemp("e2e_notebooks")

    env_overrides = {
        # Real lifespan — KernelRegistry + ReplayWorker need to spin up.
        "POINTLESSQL_TEST_LIFESPAN_FAST": "0",
        "POINTLESSQL_DB_URL": db_url,
        # Disable optional subprocesses; the multi-tab scenario does
        # not touch JupyterLab / MLflow / dbt and they slow boot.
        "POINTLESSQL_JUPYTER_ENABLED": "0",
        "POINTLESSQL_MLFLOW_ENABLED": "0",
        "POINTLESSQL_DBT_ENABLED": "0",
        # Scheduler off — only the replay worker is exercised here.
        "POINTLESSQL_SCHEDULER_ENABLED": "0",
        # Stable auth signing key for the session.
        "POINTLESSQL_AUTH_SECRET_KEY": "phase-108-e2e-secret-key-not-real-prod",
        # Replay worker stays on so Phase 103 endpoints behave
        # production-like.  Opt-out via the existing env var if a
        # specific test ever needs to disable it.
        "POINTLESSQL_REPLAY_WORKER_DISABLED": "0",
        # Pin notebook directory to a tempfile location so created
        # notebooks do not collide with the dev tree.
        "POINTLESSQL_JUPYTER_NOTEBOOKS_DIR": str(notebooks_dir),
        # Forward the soyuz-catalog URL to the booted server so
        # ``requires_soyuz`` journeys reach a live catalog.  Honour an
        # ambient override (CI service / a non-default local port) and fall
        # back to the documented localhost default.  When soyuz is *down*
        # the ``requires_soyuz`` marker skips those journeys (see the
        # ``soyuz_available`` probe below), so the default is harmless.
        "POINTLESSQL_SOYUZ_CATALOG_URL": os.environ.get(
            "POINTLESSQL_SOYUZ_CATALOG_URL", "http://127.0.0.1:8080"
        ),
    }
    saved_env: dict[str, str | None] = {k: os.environ.get(k) for k in env_overrides}
    for key, value in env_overrides.items():
        os.environ[key] = value

    _run_alembic_upgrade(db_url)
    _seed_admin_user(db_url, "test@test.com", "password123")

    # Import the app AFTER env vars are set — Settings() snapshots
    # the env at construction time.
    import uvicorn

    from pointlessql.api.main import app as _app

    config = uvicorn.Config(
        _app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="e2e-uvicorn", daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20.0
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=1.0)
            if r.status_code == 200:
                break
        except httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout:
            pass
        time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=3.0)
        raise RuntimeError(f"Phase 108 e2e live server did not become ready at {base_url}")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
        for key, original in saved_env.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


@pytest.fixture(scope="session")
def admin_session_cookies(live_server_url: str) -> dict[str, str]:
    """POST to ``/auth/login`` as the seeded admin; return cookie jar.

    The CSRF middleware (``pointlessql/api/csrf_middleware.py``)
    requires the POST to carry both the ``pql_csrf`` cookie and a
    matching ``csrf_token`` form field.  We acquire the cookie via a
    GET to ``/auth/login`` first and echo it back in the POST body.
    """
    with httpx.Client(base_url=live_server_url, follow_redirects=False) as client:
        page = client.get("/auth/login")
        if page.status_code not in (200, 302, 303):
            raise RuntimeError(f"GET /auth/login failed: {page.status_code}")
        csrf_token = client.cookies.get("pql_csrf")
        if not csrf_token:
            raise RuntimeError("CSRF cookie was not issued on GET /auth/login")

        login_resp = client.post(
            "/auth/login",
            data={
                "email": "test@test.com",
                "password": "password123",
                "csrf_token": csrf_token,
            },
        )
        if login_resp.status_code not in (200, 302, 303):
            raise RuntimeError(
                f"POST /auth/login failed: {login_resp.status_code} body={login_resp.text[:200]!r}"
            )
        return {name: value for name, value in client.cookies.items()}


@pytest.fixture(scope="session")
def playwright_browser() -> Iterator[Any]:
    """Headless Chromium browser shared across the e2e session.

    Requires ``playwright install chromium`` to have run first (CI
    handles this; locally run it once after ``uv sync``).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def playwright_context(
    playwright_browser: Any,
    admin_session_cookies: dict[str, str],
    live_server_url: str,
) -> Iterator[Any]:
    """Fresh BrowserContext per test with admin auth cookies injected.

    Function-scope: every test gets a clean context so a stale cookie
    or an open WebSocket from a previous test cannot leak forward.
    """
    parsed = httpx.URL(live_server_url)
    cookies_payload = [
        {
            "name": name,
            "value": value,
            "domain": parsed.host,
            "path": "/",
        }
        for name, value in admin_session_cookies.items()
    ]
    context = playwright_browser.new_context(viewport={"width": 1280, "height": 800})
    context.add_cookies(cookies_payload)
    try:
        yield context
    finally:
        context.close()


@pytest.fixture
def mobile_context(
    playwright_browser: Any,
    admin_session_cookies: dict[str, str],
    live_server_url: str,
) -> Iterator[Any]:
    """Fresh BrowserContext per test at a phone viewport (375x812).

    Same auth-cookie injection as :func:`playwright_context` but with a
    portrait phone viewport so the responsive-layout journeys assert the
    mobile breakpoint rather than the desktop one.
    """
    parsed = httpx.URL(live_server_url)
    cookies_payload = [
        {"name": name, "value": value, "domain": parsed.host, "path": "/"}
        for name, value in admin_session_cookies.items()
    ]
    context = playwright_browser.new_context(
        viewport={"width": 375, "height": 812},
        is_mobile=True,
    )
    context.add_cookies(cookies_payload)
    try:
        yield context
    finally:
        context.close()


def _soyuz_base_url() -> str:
    """Return the soyuz-catalog base URL the journeys probe / target."""
    return os.environ.get("POINTLESSQL_SOYUZ_CATALOG_URL", "http://127.0.0.1:8080").rstrip("/")


@pytest.fixture(scope="session")
def soyuz_available() -> bool:
    """Probe soyuz-catalog ``/healthz`` once per session.

    Returns ``True`` when a live soyuz answers 200 within a short timeout,
    ``False`` otherwise.  Journeys carrying the ``requires_soyuz`` marker
    auto-skip when this is ``False`` (see :func:`_skip_when_soyuz_required`),
    so the pure-UI suite stays green on a host with no catalog running.
    """
    url = f"{_soyuz_base_url()}/healthz"
    try:
        response = httpx.get(url, timeout=1.0)
    except httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.ConnectTimeout:
        return False
    return response.status_code == 200


@pytest.fixture(autouse=True)
def _skip_when_soyuz_required(request: pytest.FixtureRequest) -> None:
    """Skip ``requires_soyuz`` journeys when no live soyuz-catalog is reachable.

    Autouse so individual journeys never have to remember the guard: a test
    marked ``@pytest.mark.requires_soyuz`` is skipped (not failed) when the
    session-scoped :func:`soyuz_available` probe reports the catalog down.
    """
    if request.node.get_closest_marker("requires_soyuz") is None:
        return
    if not request.getfixturevalue("soyuz_available"):
        pytest.skip(f"soyuz-catalog not reachable at {_soyuz_base_url()}")


def _artifact_dir() -> Path:
    """Return (creating) the directory failure artifacts are written to."""
    target = Path(os.environ.get("E2E_ARTIFACT_DIR", str(_REPO_ROOT / "test-artifacts" / "e2e")))
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_node_name(nodeid: str) -> str:
    """Turn a pytest node id into a filesystem-safe artifact stem."""
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in nodeid)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    """Capture a screenshot + HTML dump for every open page on test failure.

    Wraps report creation: when the ``call`` phase fails and the test pulled
    in a ``playwright_context`` (or ``mobile_context``) fixture, every open
    page in that context is screenshotted and its HTML dumped under
    ``$E2E_ARTIFACT_DIR`` (default ``test-artifacts/e2e``).  Diagnostics only
    — failures swallowed so artifact capture never masks the real error.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    funcargs = getattr(item, "funcargs", {})
    contexts = [
        funcargs[name] for name in ("playwright_context", "mobile_context") if name in funcargs
    ]
    if not contexts:
        return
    stem = _safe_node_name(item.nodeid)
    out = _artifact_dir()
    for ctx in contexts:
        for index, page in enumerate(getattr(ctx, "pages", []) or []):
            try:
                page.screenshot(path=str(out / f"{stem}-{index}.png"), full_page=True)
                (out / f"{stem}-{index}.html").write_text(page.content(), encoding="utf-8")
            except Exception:  # noqa: BLE001 - diagnostics must never mask the failure
                continue
