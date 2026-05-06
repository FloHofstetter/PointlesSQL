"""Tests for the on-demand dbt CLI executor.

We never spawn the real dbt binary here — that would require dbt to
be on PATH and an actual project to compile.  Instead we exercise:

* path resolution (project_dir / profiles_dir / manifest_path)
* argv composition (``_base_args`` + ``_project_flags``)
* timeout + missing-binary error paths via monkeypatched
  ``asyncio.create_subprocess_exec`` stubs.

Real spawn coverage is the job of the e2e walkthrough in Sprint 36.7.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pointlessql.services.dbt_executor import (
    DBTExecutionError,
    DBTExecutor,
    DBTRunResult,
    _truncate,
)
from pointlessql.settings import DBTSettings


def test_path_resolution_relative_anchors_to_cwd(tmp_path: Path) -> None:
    """Relative project + profiles paths resolve against the executor cwd."""
    settings = DBTSettings()
    ex = DBTExecutor(settings, cwd=tmp_path)
    assert ex.project_dir == (tmp_path / "dbt_project").resolve()
    assert ex.profiles_dir == (tmp_path / "dbt_project" / "profiles").resolve()
    assert ex.manifest_path == (tmp_path / "dbt_project" / "target" / "manifest.json").resolve()
    assert (
        ex.run_results_path == (tmp_path / "dbt_project" / "target" / "run_results.json").resolve()
    )


def test_path_resolution_keeps_absolute(tmp_path: Path) -> None:
    """Absolute project_dir is returned unchanged."""
    abs_proj = tmp_path / "abs_proj"
    settings = DBTSettings(project_dir=abs_proj)
    ex = DBTExecutor(settings, cwd=tmp_path / "different")
    assert ex.project_dir == abs_proj


def test_base_args_includes_no_color_and_no_telemetry(tmp_path: Path) -> None:
    """Base args switch off colour codes + anonymous-stats phone-home."""
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    args = ex._base_args()
    assert args[0] == "dbt"
    assert "--no-use-colors" in args
    assert "--no-anonymous-usage-stats" in args


def test_project_flags_match_settings(tmp_path: Path) -> None:
    """Project-flags carry --project-dir / --profiles-dir / --target."""
    ex = DBTExecutor(DBTSettings(target="prod"), cwd=tmp_path)
    flags = ex._project_flags()
    assert "--project-dir" in flags
    assert "--profiles-dir" in flags
    assert flags[flags.index("--target") + 1] == "prod"


def test_truncate_passes_short_buffer_through() -> None:
    """Buffers under the cap come back verbatim, untruncated."""
    out, trunc = _truncate(b"hello world")
    assert out == "hello world"
    assert trunc is False


def test_truncate_clamps_oversized_buffer() -> None:
    """Buffers over the cap are clipped + flagged."""
    big = b"x" * (300 * 1024)
    out, trunc = _truncate(big)
    assert trunc is True
    assert out.endswith("[truncated]")


@pytest.mark.asyncio
async def test_run_raises_when_dbt_binary_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A FileNotFoundError on spawn surfaces as DBTExecutionError."""

    async def _spawn_raises(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("dbt: not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn_raises)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with pytest.raises(DBTExecutionError, match="dbt CLI not found"):
        await ex.run()


@pytest.mark.asyncio
async def test_run_captures_stub_subprocess_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful subprocess returns its stdout + exit code on the result."""

    class _StubProc:
        returncode: int = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"hello dbt", b""

        def kill(self) -> None:  # pragma: no cover — used only on timeout path
            pass

        async def wait(self) -> int:  # pragma: no cover
            return 0

    async def _spawn(*args: Any, **kwargs: Any) -> _StubProc:
        return _StubProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    result = await ex.run(models=["bronze_raw"], full_refresh=True)
    assert isinstance(result, DBTRunResult)
    assert result.exit_code == 0
    assert result.stdout == "hello dbt"
    # full_refresh adds the flag.
    assert "--full-refresh" in result.command
    # --select carries the model list.
    assert "--select" in result.command


@pytest.mark.asyncio
async def test_compile_does_not_carry_full_refresh_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compile() never emits ``--full-refresh`` (run-only flag)."""

    captured: dict[str, Sequence[Any]] = {}

    class _StubProc:
        returncode: int = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def _spawn(*args: Any, **kwargs: Any) -> _StubProc:
        captured["args"] = args
        return _StubProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    await ex.compile()
    assert "compile" in captured["args"]
    assert "--full-refresh" not in captured["args"]
