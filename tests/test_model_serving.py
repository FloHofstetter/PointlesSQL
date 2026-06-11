"""Tests for the model-serving service + worker manager (spawn stubbed)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pointlessql.api.main import app
from pointlessql.services import model_serving as svc
from pointlessql.services.model_serving import ServingManager


def _factory():
    return app.state.session_factory


# ---------------------------------------------------------------------------
# endpoint CRUD
# ---------------------------------------------------------------------------


def test_create_list_delete_roundtrip() -> None:
    row = svc.create_endpoint(
        _factory(),
        workspace_id=1,
        name="churn-prod",
        model_name="churn",
        model_version="3",
        principal="ml@test.com",
    )
    assert row.state == "stopped"
    names = [e.name for e in svc.list_endpoints(_factory(), workspace_id=1)]
    assert "churn-prod" in names
    assert svc.delete_endpoint(_factory(), endpoint_id=row.id)
    assert svc.get_endpoint(_factory(), workspace_id=1, name="churn-prod") is None


def test_create_rejects_duplicates_and_bad_names() -> None:
    svc.create_endpoint(
        _factory(),
        workspace_id=1,
        name="dup-ep",
        model_name="m",
        model_version="1",
        principal=None,
    )
    with pytest.raises(ValueError, match="already exists"):
        svc.create_endpoint(
            _factory(),
            workspace_id=1,
            name="dup-ep",
            model_name="m",
            model_version="1",
            principal=None,
        )
    with pytest.raises(ValueError, match="endpoint name"):
        svc.create_endpoint(
            _factory(),
            workspace_id=1,
            name="has space",
            model_name="m",
            model_version="1",
            principal=None,
        )
    with pytest.raises(ValueError, match="non-empty"):
        svc.create_endpoint(
            _factory(),
            workspace_id=1,
            name="ok-name",
            model_name=" ",
            model_version="1",
            principal=None,
        )


def test_state_transitions_and_boot_reset() -> None:
    row = svc.create_endpoint(
        _factory(),
        workspace_id=1,
        name="state-ep",
        model_name="m",
        model_version="@champion",
        principal=None,
    )
    svc.set_state(_factory(), endpoint_id=row.id, state="ready")
    refreshed = svc.get_endpoint(_factory(), workspace_id=1, name="state-ep")
    assert refreshed is not None and refreshed.state == "ready"
    assert svc.reset_states_on_boot(_factory()) >= 1
    refreshed = svc.get_endpoint(_factory(), workspace_id=1, name="state-ep")
    assert refreshed is not None and refreshed.state == "stopped"


def test_record_invocation_bumps_counter() -> None:
    row = svc.create_endpoint(
        _factory(),
        workspace_id=1,
        name="count-ep",
        model_name="m",
        model_version="1",
        principal=None,
    )
    svc.record_invocation(_factory(), endpoint_id=row.id)
    svc.record_invocation(_factory(), endpoint_id=row.id)
    refreshed = svc.get_endpoint(_factory(), workspace_id=1, name="count-ep")
    assert refreshed is not None
    assert refreshed.invocation_count == 2
    assert refreshed.last_invoked_at is not None


# ---------------------------------------------------------------------------
# worker manager (subprocess + health stubbed)
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


def _manager(monkeypatch, *, healthy: bool = True, max_endpoints: int = 2) -> ServingManager:
    manager = ServingManager(app.state.settings)
    manager._settings.serving.max_endpoints = max_endpoints

    async def _fake_spawn(command: list[str], env: dict[str, str], stderr_path: Path) -> Any:
        _fake_spawn.calls.append((command, env))
        return _FakeProcess()

    _fake_spawn.calls = []

    async def _fake_health(port: int, process: Any) -> None:
        if not healthy:
            raise RuntimeError("worker did not become healthy")

    monkeypatch.setattr(manager, "_spawn", _fake_spawn)
    monkeypatch.setattr(manager, "_wait_healthy", _fake_health)
    manager._fake_spawn = _fake_spawn
    return manager


def _endpoint(name: str, version: str = "2") -> Any:
    return svc.create_endpoint(
        _factory(),
        workspace_id=1,
        name=name,
        model_name="churn",
        model_version=version,
        principal=None,
    )


@pytest.mark.asyncio
async def test_manager_start_allocates_ports_and_builds_model_uri(monkeypatch) -> None:
    manager = _manager(monkeypatch)
    first = _endpoint("mgr-a")
    second = _endpoint("mgr-b", version="@champion")
    port_a = await manager.start(first)
    port_b = await manager.start(second)
    assert port_a != port_b
    assert manager.port_for(first.id) == port_a
    # idempotent start returns the same port
    assert await manager.start(first) == port_a
    commands = [" ".join(cmd) for cmd, _env in manager._fake_spawn.calls]
    assert any("models:/churn/2" in c for c in commands)
    assert any("models:/churn@champion" in c for c in commands)
    await manager.stop_all()
    assert manager.port_for(first.id) is None


@pytest.mark.asyncio
async def test_manager_slot_exhaustion(monkeypatch) -> None:
    manager = _manager(monkeypatch, max_endpoints=1)
    await manager.start(_endpoint("slot-a"))
    with pytest.raises(RuntimeError, match="slots"):
        await manager.start(_endpoint("slot-b"))
    await manager.stop_all()


@pytest.mark.asyncio
async def test_manager_unhealthy_start_cleans_up(monkeypatch, tmp_path) -> None:
    manager = _manager(monkeypatch, healthy=False)
    endpoint = _endpoint("sick-ep")
    with pytest.raises(RuntimeError, match="healthy"):
        await manager.start(endpoint)
    assert manager.port_for(endpoint.id) is None


@pytest.mark.asyncio
async def test_manager_stop_terminates_process(monkeypatch) -> None:
    manager = _manager(monkeypatch)
    endpoint = _endpoint("stop-ep")
    await manager.start(endpoint)
    worker = manager._workers[endpoint.id]
    assert await manager.stop(endpoint.id) is True
    assert worker.process.terminated is True
    assert await manager.stop(endpoint.id) is False


def test_serving_settings_defaults() -> None:
    assert app.state.settings.serving.port_range_start == 9100
    assert asyncio.iscoroutinefunction(ServingManager.stop_all)
