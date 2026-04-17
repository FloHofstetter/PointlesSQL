"""Tests for the Sprint 24 papermill executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pointlessql.exceptions import EngineError, ValidationError
from pointlessql.services.scheduler import (
    _papermill_executor,
    build_default_registry,
    resolve_notebook_path,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


@pytest.fixture
def notebooks_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the executor at an isolated notebooks directory and seed a stub."""
    root = tmp_path / "notebooks"
    root.mkdir()
    (root / "smoke.ipynb").write_text("{}\n")
    monkeypatch.setenv("POINTLESSQL_NOTEBOOKS_DIR", str(root))
    return root


@pytest.fixture
def user_info() -> UserInfo:
    return UserInfo(
        id=1,
        email="runner@test.com",
        display_name="Runner",
        is_admin=False,
    )


@pytest.fixture
def uc_client() -> UnityCatalogClient:
    return MagicMock(spec=UnityCatalogClient)


def test_registry_includes_papermill() -> None:
    """``build_default_registry`` exposes ``papermill`` alongside the old kinds."""
    registry = build_default_registry()
    assert registry.get("papermill") is _papermill_executor
    assert registry.get("pg_sync") is not None
    assert registry.get("python") is not None


def test_resolve_rejects_absolute_path(tmp_path: Path) -> None:
    """Absolute paths never escape the notebooks directory."""
    with pytest.raises(ValidationError, match="must be relative"):
        resolve_notebook_path(tmp_path, "/etc/passwd")


def test_resolve_rejects_traversal(tmp_path: Path) -> None:
    """``..``-relative paths that escape the root are rejected."""
    root = tmp_path / "notebooks"
    root.mkdir()
    with pytest.raises(ValidationError, match="escapes the notebooks directory"):
        resolve_notebook_path(root, "../outside.ipynb")


def test_resolve_rejects_missing_file(tmp_path: Path) -> None:
    """Non-existent notebook inside the root is a validation error."""
    root = tmp_path / "notebooks"
    root.mkdir()
    with pytest.raises(ValidationError, match="notebook not found"):
        resolve_notebook_path(root, "does_not_exist.ipynb")


async def test_missing_notebook_path_raises(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
) -> None:
    """Config without ``notebook_path`` raises ``ValidationError`` at entry."""
    with pytest.raises(ValidationError, match="notebook_path"):
        await _papermill_executor(1, user_info, {}, uc_client)


async def test_non_dict_parameters_raises(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
) -> None:
    """``parameters`` must be an object."""
    with pytest.raises(ValidationError, match="parameters"):
        await _papermill_executor(
            1,
            user_info,
            {"notebook_path": "smoke.ipynb", "parameters": ["not", "a", "dict"]},
            uc_client,
        )


async def test_invalid_timeout_raises(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
) -> None:
    """Non-positive ``timeout_seconds`` is a validation error."""
    with pytest.raises(ValidationError, match="timeout_seconds"):
        await _papermill_executor(
            1,
            user_info,
            {"notebook_path": "smoke.ipynb", "timeout_seconds": 0},
            uc_client,
        )


async def test_executor_writes_output_and_forwards_principal(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stubbed papermill touches the output path and sees ``POINTLESSQL_PRINCIPAL``."""
    import os

    captured: dict[str, Any] = {}

    def fake_execute(
        input_path: str,
        output_path: str,
        parameters: dict[str, Any],
        kernel_name: str,
        cwd: str,
        execution_timeout: int,
        progress_bar: bool,
    ) -> None:
        captured["input_path"] = input_path
        captured["output_path"] = output_path
        captured["parameters"] = parameters
        captured["cwd"] = cwd
        captured["execution_timeout"] = execution_timeout
        captured["principal"] = os.environ.get("POINTLESSQL_PRINCIPAL")
        Path(output_path).write_text("{}\n")

    fake_module = MagicMock()
    fake_module.execute_notebook = fake_execute
    monkeypatch.setitem(__import__("sys").modules, "papermill", fake_module)

    fake_exc_module = MagicMock()

    class _FakeErr(Exception):
        pass

    fake_exc_module.PapermillExecutionError = _FakeErr
    monkeypatch.setitem(
        __import__("sys").modules, "papermill.exceptions", fake_exc_module
    )

    await _papermill_executor(
        42,
        user_info,
        {"notebook_path": "smoke.ipynb", "parameters": {"date": "2026-04-17"}},
        uc_client,
    )

    assert captured["parameters"] == {"date": "2026-04-17"}
    assert captured["principal"] == "runner@test.com"
    assert captured["output_path"].endswith("/runs/42.ipynb")
    assert captured["input_path"].endswith("/smoke.ipynb")
    # Env var is restored after the run.
    assert "POINTLESSQL_PRINCIPAL" not in os.environ or (
        os.environ.get("POINTLESSQL_PRINCIPAL") != "runner@test.com"
    )
    assert (notebooks_dir / "runs" / "42.ipynb").is_file()


async def test_executor_papermill_execution_error_becomes_engine_error(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PapermillExecutionError`` from a failing cell is re-raised as ``EngineError``."""

    class _FakeErr(Exception):
        def __init__(self) -> None:
            self.exec_count = 3
            self.ename = "ZeroDivisionError"
            self.evalue = "division by zero"

    fake_exc_module = MagicMock()
    fake_exc_module.PapermillExecutionError = _FakeErr
    monkeypatch.setitem(
        __import__("sys").modules, "papermill.exceptions", fake_exc_module
    )

    def failing_execute(**_: Any) -> None:
        raise _FakeErr()

    fake_module = MagicMock()
    fake_module.execute_notebook = failing_execute
    monkeypatch.setitem(__import__("sys").modules, "papermill", fake_module)

    with pytest.raises(EngineError, match="cell 3.*ZeroDivisionError"):
        await _papermill_executor(
            99,
            user_info,
            {"notebook_path": "smoke.ipynb"},
            uc_client,
        )


