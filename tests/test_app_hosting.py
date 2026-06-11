"""Hosted-apps service: CRUD + the worker manager with stubbed seams.

The manager tests replace the ``_spawn`` / ``_wait_healthy`` seams so
no real subprocess is launched — what's asserted is the argv
composition per kind, the env merge, port allocation, and the
lifecycle bookkeeping around start / stop / boot reset.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.models import Base, User
from pointlessql.models.hosted_apps import HostedApp
from pointlessql.services import app_hosting
from pointlessql.services.app_hosting import (
    AppRuntimeMissingError,
    AppsConfig,
    AppsManager,
)

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)

FASTAPI_EXAMPLE = (
    "from fastapi import FastAPI\n"
    "\n"
    "app = FastAPI()\n"
    "\n"
    "\n"
    '@app.get("/")\n'
    "def home() -> dict[str, str]:\n"
    '    return {"hello": "from a hosted app"}\n'
)


@pytest.fixture
def factory() -> Any:
    """In-memory session factory seeded with one creator user."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="creator@test.com",
                display_name="Creator",
                password_hash="x",
                is_admin=True,
                created_at=_NOW,
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _create(factory: Any, **overrides: Any) -> HostedApp:
    """Create an app row with sane defaults, overridable per test."""
    kwargs: dict[str, Any] = {
        "workspace_id": 1,
        "title": "Demo App",
        "description": None,
        "kind": "fastapi",
        "source_code": FASTAPI_EXAMPLE,
        "command_override": None,
        "env": None,
        "created_by_user_id": 1,
    }
    kwargs.update(overrides)
    return app_hosting.create_app(factory, **kwargs)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_app_defaults(factory: Any) -> None:
    """A fresh app lands stopped, slugged from its title."""
    row = _create(factory)
    assert row.state == "stopped"
    assert row.slug.startswith("demo-app-")
    assert row.kind == "fastapi"
    assert row.env_json == "{}"
    assert row.source_code == FASTAPI_EXAMPLE


def test_create_app_validation(factory: Any) -> None:
    """Empty titles, unknown kinds, and bad env mappings are rejected."""
    with pytest.raises(ValueError, match="title"):
        _create(factory, title="   ")
    with pytest.raises(ValueError, match="kind must be one of"):
        _create(factory, kind="php")
    with pytest.raises(ValueError, match="command apps need"):
        _create(factory, kind="command", command_override="   ")
    with pytest.raises(ValueError, match="env must map"):
        _create(factory, env={"PORT_COUNT": 3})


def test_list_apps_is_workspace_scoped(factory: Any) -> None:
    """Listing only returns the active workspace's rows."""
    mine = _create(factory, title="Mine", workspace_id=1)
    _create(factory, title="Theirs", workspace_id=2)
    rows = app_hosting.list_apps(factory, workspace_id=1)
    assert [row.slug for row in rows] == [mine.slug]


def test_get_app_by_slug(factory: Any) -> None:
    """Lookups are (workspace, slug)-scoped; misses return ``None``."""
    row = _create(factory)
    found = app_hosting.get_app(factory, workspace_id=1, slug=row.slug)
    assert found is not None and found.id == row.id
    assert app_hosting.get_app(factory, workspace_id=2, slug=row.slug) is None
    assert app_hosting.get_app(factory, workspace_id=1, slug="nope") is None


def test_update_app_patches_fields_but_not_slug(factory: Any) -> None:
    """Updates patch the given fields only; the slug is immutable."""
    row = _create(factory)
    updated = app_hosting.update_app(
        factory,
        app_id=row.id,
        title="Renamed",
        source_code="print('v2')",
        env={"A": "1"},
    )
    assert updated is not None
    assert updated.title == "Renamed"
    assert updated.slug == row.slug
    assert updated.source_code == "print('v2')"
    assert updated.env_json == '{"A": "1"}'
    assert app_hosting.update_app(factory, app_id=99_999, title="X") is None


def test_update_command_app_cannot_clear_command(factory: Any) -> None:
    """A command app must keep a non-empty command line."""
    row = _create(factory, kind="command", command_override="python -m http.server {port}")
    with pytest.raises(ValueError, match="command apps need"):
        app_hosting.update_app(factory, app_id=row.id, command_override="  ")


def test_delete_app(factory: Any) -> None:
    """Delete reports whether a row was removed."""
    row = _create(factory)
    assert app_hosting.delete_app(factory, app_id=row.id) is True
    assert app_hosting.delete_app(factory, app_id=row.id) is False


def test_set_state_records_error(factory: Any) -> None:
    """Failed transitions persist the error; others clear it."""
    row = _create(factory)
    app_hosting.set_state(factory, app_id=row.id, state="failed", error="boom")
    refreshed = app_hosting.get_app(factory, workspace_id=1, slug=row.slug)
    assert refreshed is not None
    assert (refreshed.state, refreshed.last_error) == ("failed", "boom")
    app_hosting.set_state(factory, app_id=row.id, state="ready")
    refreshed = app_hosting.get_app(factory, workspace_id=1, slug=row.slug)
    assert refreshed is not None
    assert (refreshed.state, refreshed.last_error) == ("ready", None)


def test_reset_states_on_boot(factory: Any) -> None:
    """Every non-stopped row resets to stopped exactly once."""
    rows = [_create(factory, title=f"App {i}") for i in range(4)]
    app_hosting.set_state(factory, app_id=rows[0].id, state="ready")
    app_hosting.set_state(factory, app_id=rows[1].id, state="starting")
    app_hosting.set_state(factory, app_id=rows[2].id, state="failed", error="x")
    assert app_hosting.reset_states_on_boot(factory) == 3
    states = {row.state for row in app_hosting.list_apps(factory, workspace_id=1)}
    assert states == {"stopped"}
    assert app_hosting.reset_states_on_boot(factory) == 0


def test_read_log_tail_caps_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The log tail returns at most ``max_lines``, newest last."""
    monkeypatch.setattr(app_hosting.tempfile, "gettempdir", lambda: str(tmp_path))
    assert app_hosting.read_log_tail(7) == []
    app_hosting.stderr_log_path(7).write_text(
        "\n".join(f"line {i}" for i in range(300)), encoding="utf-8"
    )
    lines = app_hosting.read_log_tail(7, max_lines=200)
    assert len(lines) == 200
    assert lines[-1] == "line 299"


# ---------------------------------------------------------------------------
# Worker manager
# ---------------------------------------------------------------------------


class _FakeProcess:
    """Subprocess stand-in: alive until terminated."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


def _app_row(app_id: int, **overrides: Any) -> HostedApp:
    """Build a detached app row without touching a database."""
    kwargs: dict[str, Any] = {
        "id": app_id,
        "workspace_id": 1,
        "slug": f"demo-{app_id}",
        "title": "Demo",
        "kind": "fastapi",
        "source_code": FASTAPI_EXAMPLE,
        "command_override": None,
        "env_json": "{}",
        "state": "stopped",
        "created_by_user_id": 1,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    kwargs.update(overrides)
    return HostedApp(**kwargs)


@pytest.fixture
def manager(tmp_path: Path) -> AppsManager:
    """Manager with a tight port range rooted in the test tmpdir."""
    return AppsManager(
        AppsConfig(
            port_range_start=9300,
            max_apps=2,
            startup_timeout_seconds=1.0,
            apps_root=tmp_path,
        )
    )


@pytest.fixture
def spawned(manager: AppsManager, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stub the spawn + health seams; record every spawn call."""
    calls: list[dict[str, Any]] = []

    async def fake_spawn(
        command: list[str], env: dict[str, str], stderr_path: Path, cwd: Path
    ) -> _FakeProcess:
        process = _FakeProcess()
        calls.append(
            {
                "command": command,
                "env": env,
                "stderr_path": stderr_path,
                "cwd": cwd,
                "process": process,
            }
        )
        return process

    async def fake_wait(port: int, process: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_spawn", fake_spawn)
    monkeypatch.setattr(manager, "_wait_healthy", fake_wait)
    return calls


def test_apps_config_defaults() -> None:
    """The default pool is 8 workers starting at port 9200."""
    config = AppsConfig()
    assert config.port_range_start == 9200
    assert config.max_apps == 8


async def test_start_materializes_source_and_merges_env(
    manager: AppsManager,
    spawned: list[dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start writes app.py, builds the uvicorn argv, and merges env."""
    monkeypatch.setenv("PQL_HOST_VAR", "from-host")
    row = _app_row(1)
    port = await manager.start(row, env={"MY_TOKEN": "resolved"})
    assert port == 9300
    assert manager.port_for(1) == 9300

    app_dir = tmp_path / "1" / row.slug
    assert (app_dir / "app.py").read_text(encoding="utf-8") == FASTAPI_EXAMPLE

    call = spawned[0]
    assert call["cwd"] == app_dir
    assert call["command"] == [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "9300",
    ]
    env = call["env"]
    assert env["MY_TOKEN"] == "resolved"
    assert env["PQL_HOST_VAR"] == "from-host"
    assert env["POINTLESSQL_APP_BASE_PATH"] == f"/apps/{row.slug}"
    assert env["PORT"] == "9300"


async def test_double_start_is_idempotent(
    manager: AppsManager, spawned: list[dict[str, Any]]
) -> None:
    """A second start returns the live port without a second spawn."""
    row = _app_row(1)
    first = await manager.start(row, env={})
    second = await manager.start(row, env={})
    assert (first, second) == (9300, 9300)
    assert len(spawned) == 1


async def test_port_allocation_and_exhaustion(
    manager: AppsManager, spawned: list[dict[str, Any]]
) -> None:
    """Ports hand out sequentially and run dry at ``max_apps``."""
    assert await manager.start(_app_row(1), env={}) == 9300
    assert await manager.start(_app_row(2), env={}) == 9301
    with pytest.raises(RuntimeError, match="slots are in use"):
        await manager.start(_app_row(3), env={})


async def test_stop_frees_the_port(manager: AppsManager, spawned: list[dict[str, Any]]) -> None:
    """Stop terminates the worker and recycles its port."""
    await manager.start(_app_row(1), env={})
    await manager.start(_app_row(2), env={})
    assert await manager.stop(1) is True
    assert spawned[0]["process"].terminated is True
    assert manager.port_for(1) is None
    assert await manager.stop(1) is False
    assert await manager.start(_app_row(3), env={}) == 9300


async def test_stop_all_tears_down_every_worker(
    manager: AppsManager, spawned: list[dict[str, Any]]
) -> None:
    """The lifespan shutdown stops every live worker."""
    await manager.start(_app_row(1), env={})
    await manager.start(_app_row(2), env={})
    await manager.stop_all()
    assert manager.port_for(1) is None
    assert manager.port_for(2) is None


async def test_failed_health_check_cleans_up_and_carries_tail(
    manager: AppsManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker that never gets healthy is stopped; stderr tail surfaces."""

    async def fake_spawn(
        command: list[str], env: dict[str, str], stderr_path: Path, cwd: Path
    ) -> _FakeProcess:
        stderr_path.write_bytes(b"ModuleNotFoundError: nope")
        return _FakeProcess()

    async def fake_wait(port: int, process: Any) -> None:
        raise RuntimeError("worker did not become healthy")

    monkeypatch.setattr(manager, "_spawn", fake_spawn)
    monkeypatch.setattr(manager, "_wait_healthy", fake_wait)
    with pytest.raises(RuntimeError, match="ModuleNotFoundError"):
        await manager.start(_app_row(1), env={})
    assert manager.port_for(1) is None


async def test_command_kind_substitutes_port(
    manager: AppsManager, spawned: list[dict[str, Any]]
) -> None:
    """``{port}`` placeholders in command apps resolve to the real port."""
    row = _app_row(1, kind="command", command_override="python -m http.server {port}")
    await manager.start(row, env={})
    assert spawned[0]["command"] == ["python", "-m", "http.server", "9300"]


async def test_streamlit_command_carries_base_url_path(
    manager: AppsManager,
    spawned: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamlit workers serve under the public proxy prefix."""
    monkeypatch.setattr(app_hosting, "streamlit_available", lambda: True)
    row = _app_row(1, kind="streamlit")
    await manager.start(row, env={})
    command = spawned[0]["command"]
    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert command[command.index("--server.baseUrlPath") + 1] == f"/apps/{row.slug}"


async def test_streamlit_missing_is_a_runtime_gate(
    manager: AppsManager,
    spawned: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the streamlit package the start fails loudly with 503."""
    monkeypatch.setattr(app_hosting, "streamlit_available", lambda: False)
    with pytest.raises(AppRuntimeMissingError, match="streamlit is not installed"):
        await manager.start(_app_row(1, kind="streamlit"), env={})
    assert spawned == []
    assert manager.port_for(1) is None
