"""Behaviour tests that pin down observable dbt-service contracts.

These complement ``test_dbt_bridge.py`` / ``test_dbt_executor.py`` by
asserting the *exact* shapes that the manifest projection and the CLI
executor produce, rather than just spot-checking a couple of fields.
The three surfaces covered here are:

* :func:`pointlessql.services.dbt._bridge.project_models` — the
  canonical manifest → model-summary projection used by
  ``/api/dbt/manifest`` and ``/api/dbt/coverage``.  Every output key,
  the test-attachment fan-out, the severity default, and the
  ``unique_id`` sort order are nailed down.
* :func:`pointlessql.services.dbt._executor._truncate` — the
  stdout/stderr clamp.  The exact byte boundary and the
  ``errors="replace"`` decode contract are asserted via real invalid
  UTF-8 bytes.
* :class:`pointlessql.services.dbt._executor.DBTExecutor` argv +
  result wiring — every flag the executor composes and every field it
  copies onto :class:`DBTRunResult`, exercised through a stub
  ``create_subprocess_exec`` so no real dbt binary is needed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pointlessql.config import DBTSettings
from pointlessql.services.dbt import (
    DBTExecutor,
    DBTRunResult,
    project_models,
)
from pointlessql.services.dbt._executor import (  # noqa: PLC2701  # private helpers
    _MAX_OUTPUT_BYTES,
    _truncate,
)

# ---------------------------------------------------------------------------
# project_models — the manifest → model-summary projection
# ---------------------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    """Build a manifest whose insertion order differs from sorted order.

    ``silver`` is inserted before ``bronze`` so a projection that fails
    to sort by ``unique_id`` would return them in the wrong order.  The
    test node references ``bronze`` and carries an explicit ``warn``
    severity + a ``test_metadata.name`` that differs from the node
    ``name`` so the projection's field-selection logic is observable.
    """
    return {
        "nodes": {
            # Inserted first but sorts *after* bronze by unique_id.
            "model.proj.silver": {
                "resource_type": "model",
                "name": "silver",
                "schema": "silver_sch",
                "database": "maindb",
                # No relation_name → fallback to None.
                "config": {"materialized": "view"},
                "columns": {},
                "depends_on": {"nodes": ["model.proj.bronze"]},
            },
            "model.proj.bronze": {
                "resource_type": "model",
                "name": "bronze",
                "schema": "bronze_sch",
                "database": "maindb",
                "relation_name": "maindb.bronze_sch.bronze",
                "config": {"materialized": "table"},
                # Unsorted column keys → projection must sort them.
                "columns": {"id": {}, "amount": {}},
                "depends_on": {"nodes": ["seed.proj.orders"]},
            },
            "test.proj.not_null_bronze_id": {
                "resource_type": "test",
                "name": "not_null_bronze_id",
                "column_name": "id",
                "config": {"severity": "warn"},
                "test_metadata": {"name": "not_null"},
                "depends_on": {"nodes": ["model.proj.bronze"]},
            },
            # A test with no explicit severity → must default to "error".
            "test.proj.unique_bronze_id": {
                "resource_type": "test",
                "name": "unique_bronze_id",
                "config": {},
                "test_metadata": {"name": "unique"},
                "depends_on": {"nodes": ["model.proj.bronze"]},
            },
            # Non-model / non-test nodes must be filtered out entirely.
            "source.proj.raw": {"resource_type": "source", "name": "raw"},
        },
    }


def test_project_models_orders_by_unique_id() -> None:
    """Output is sorted by ``unique_id`` regardless of insertion order."""
    out = project_models(_manifest())
    assert [m["unique_id"] for m in out] == [
        "model.proj.bronze",
        "model.proj.silver",
    ]


def test_project_models_emits_exact_model_keys() -> None:
    """Each model row carries exactly the canonical projection keys."""
    out = project_models(_manifest())
    bronze = next(m for m in out if m["unique_id"] == "model.proj.bronze")
    assert set(bronze.keys()) == {
        "unique_id",
        "name",
        "schema",
        "database",
        "relation_name",
        "materialization",
        "depends_on",
        "columns",
        "tests",
    }


def test_project_models_copies_scalar_model_fields() -> None:
    """name / schema / database / relation_name / materialization map across."""
    out = project_models(_manifest())
    bronze = next(m for m in out if m["unique_id"] == "model.proj.bronze")
    assert bronze["name"] == "bronze"
    assert bronze["schema"] == "bronze_sch"
    assert bronze["database"] == "maindb"
    assert bronze["relation_name"] == "maindb.bronze_sch.bronze"
    assert bronze["materialization"] == "table"
    assert bronze["depends_on"] == ["seed.proj.orders"]


def test_project_models_sorts_column_names() -> None:
    """Column names come back sorted, not in dict-insertion order."""
    out = project_models(_manifest())
    bronze = next(m for m in out if m["unique_id"] == "model.proj.bronze")
    assert bronze["columns"] == ["amount", "id"]


def test_project_models_relation_name_falls_back_to_none() -> None:
    """A model without ``relation_name`` reports ``None`` (not "")."""
    out = project_models(_manifest())
    silver = next(m for m in out if m["unique_id"] == "model.proj.silver")
    assert silver["relation_name"] is None
    assert silver["materialization"] == "view"
    assert silver["columns"] == []


def test_project_models_attaches_tests_with_metadata_name() -> None:
    """Test rows attach to their parent model with exact field shapes.

    The attached test's ``name`` is taken from ``test_metadata.name``
    (``not_null``), *not* the node's own ``name``
    (``not_null_bronze_id``) — pins the field-selection logic.
    """
    out = project_models(_manifest())
    bronze = next(m for m in out if m["unique_id"] == "model.proj.bronze")
    tests = sorted(bronze["tests"], key=lambda t: t["unique_id"])
    assert tests == [
        {
            "unique_id": "test.proj.not_null_bronze_id",
            "name": "not_null",
            "column": "id",
            "severity": "warn",
        },
        {
            "unique_id": "test.proj.unique_bronze_id",
            "name": "unique",
            "column": None,
            "severity": "error",
        },
    ]


def test_project_models_default_severity_is_error() -> None:
    """A test with no explicit severity defaults to ``error``."""
    out = project_models(_manifest())
    bronze = next(m for m in out if m["unique_id"] == "model.proj.bronze")
    by_id = {t["unique_id"]: t for t in bronze["tests"]}
    assert by_id["test.proj.unique_bronze_id"]["severity"] == "error"


def test_project_models_column_none_when_absent() -> None:
    """A test without ``column_name`` reports ``column=None`` (not "")."""
    out = project_models(_manifest())
    bronze = next(m for m in out if m["unique_id"] == "model.proj.bronze")
    by_id = {t["unique_id"]: t for t in bronze["tests"]}
    assert by_id["test.proj.unique_bronze_id"]["column"] is None


def test_project_models_filters_non_models() -> None:
    """Only ``resource_type='model'`` nodes appear in the output."""
    out = project_models(_manifest())
    assert {m["unique_id"] for m in out} == {
        "model.proj.bronze",
        "model.proj.silver",
    }


def test_project_models_no_tests_when_no_match() -> None:
    """A model with no referencing test gets an empty ``tests`` list."""
    out = project_models(_manifest())
    silver = next(m for m in out if m["unique_id"] == "model.proj.silver")
    assert silver["tests"] == []


# ---------------------------------------------------------------------------
# _truncate — the stdout/stderr clamp + decode contract
# ---------------------------------------------------------------------------


def test_truncate_boundary_is_inclusive() -> None:
    """A buffer of exactly the cap size is NOT truncated.

    Pins the ``len(buf) <= _MAX_OUTPUT_BYTES`` boundary: a ``<``
    off-by-one would clip a buffer that fits exactly.
    """
    buf = b"x" * _MAX_OUTPUT_BYTES
    out, trunc = _truncate(buf)
    assert trunc is False
    assert out == "x" * _MAX_OUTPUT_BYTES


def test_truncate_one_over_boundary_clips() -> None:
    """One byte over the cap flips the truncated flag and appends marker."""
    buf = b"x" * (_MAX_OUTPUT_BYTES + 1)
    out, trunc = _truncate(buf)
    assert trunc is True
    assert out.endswith("... [truncated]")


def test_truncate_replaces_invalid_utf8_bytes() -> None:
    """Invalid UTF-8 bytes are replaced, never raised, under the cap.

    Drives the ``errors="replace"`` decode path: a strict decode or a
    bogus handler name would raise instead of substituting U+FFFD.
    """
    out, trunc = _truncate(b"ok\xff\xfe")
    assert trunc is False
    assert out.startswith("ok")
    assert "�" in out


def test_truncate_replaces_invalid_utf8_bytes_when_oversized() -> None:
    """The oversized branch also decodes with ``errors="replace"``."""
    buf = b"\xff" * (_MAX_OUTPUT_BYTES + 10)
    out, trunc = _truncate(buf)
    assert trunc is True
    assert "�" in out


# ---------------------------------------------------------------------------
# DBTExecutor argv + DBTRunResult wiring (stub subprocess)
# ---------------------------------------------------------------------------


class _StubProc:
    """Minimal stand-in for an ``asyncio.subprocess.Process``."""

    def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _patch_spawn(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: bytes = b"out",
    stderr: bytes = b"err",
) -> dict[str, Any]:
    """Install a stub ``create_subprocess_exec`` capturing its call.

    Returns a dict that, after the spawn, holds ``argv`` (positional
    args) and ``kwargs`` so a test can assert exactly what was spawned.
    """
    captured: dict[str, Any] = {}

    async def _spawn(*args: Any, **kwargs: Any) -> _StubProc:
        captured["argv"] = list(args)
        captured["kwargs"] = kwargs
        return _StubProc(returncode, stdout, stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return captured


@pytest.mark.asyncio
async def test_run_copies_returncode_to_exit_code_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-zero process returncode lands verbatim on ``exit_code``.

    ``returncode=5`` distinguishes the real ``proc.returncode or 0``
    from an ``and 0`` mutation (which would zero it out).
    """
    _patch_spawn(monkeypatch, returncode=5)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    result = await ex.run()
    assert isinstance(result, DBTRunResult)
    assert result.exit_code == 5


@pytest.mark.asyncio
async def test_run_zero_returncode_stays_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero returncode stays zero (not coerced to 1)."""
    _patch_spawn(monkeypatch, returncode=0)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    result = await ex.run()
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_run_populates_result_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every captured field is copied onto the result, not left ``None``."""
    _patch_spawn(monkeypatch, returncode=0, stdout=b"hello", stderr=b"warn")
    ex = DBTExecutor(DBTSettings(target="prod"), cwd=tmp_path)
    result = await ex.run()
    assert result.stdout == "hello"
    assert result.stderr == "warn"
    assert result.manifest_path == ex.manifest_path
    assert result.run_results_path == ex.run_results_path
    assert result.truncated_stdout is False
    assert result.truncated_stderr is False
    # duration is a real (non-None) measurement.
    assert isinstance(result.duration_seconds, float)
    assert result.duration_seconds >= 0.0


@pytest.mark.asyncio
async def test_run_spawns_pipes_and_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subprocess is spawned with PIPE stdout/stderr and a real env."""
    captured = _patch_spawn(monkeypatch)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    await ex.run()
    assert captured["kwargs"]["stdout"] == asyncio.subprocess.PIPE
    assert captured["kwargs"]["stderr"] == asyncio.subprocess.PIPE
    # env is the copied process environment, not None.
    assert captured["kwargs"]["env"] is not None
    assert isinstance(captured["kwargs"]["env"], dict)


@pytest.mark.asyncio
async def test_run_command_carries_project_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composed argv carries resolved project/profiles dirs + target.

    Pins ``_project_flags``: a ``str(None)`` mutation on the dir paths
    would put the literal ``"None"`` into the command instead of the
    resolved filesystem path.
    """
    _patch_spawn(monkeypatch)
    ex = DBTExecutor(DBTSettings(target="prod"), cwd=tmp_path)
    result = await ex.run()
    cmd = result.command
    assert cmd[cmd.index("--project-dir") + 1] == str(ex.project_dir)
    assert cmd[cmd.index("--profiles-dir") + 1] == str(ex.profiles_dir)
    assert cmd[cmd.index("--target") + 1] == "prod"
    assert "None" not in cmd


@pytest.mark.asyncio
async def test_compile_select_flag_carries_joined_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compile() keeps the ``compile`` verb and joins models with a space.

    Pins the ``args += [...]`` accumulation and the ``" ".join``
    separator: dropping the verb or changing the join char are both
    observable on ``result.command``.
    """
    _patch_spawn(monkeypatch)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    result = await ex.compile(models=["bronze", "silver"])
    cmd = result.command
    assert "compile" in cmd
    assert cmd[cmd.index("--select") + 1] == "bronze silver"


@pytest.mark.asyncio
async def test_compile_without_models_has_no_select(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compile() with no models omits ``--select`` but keeps ``compile``."""
    _patch_spawn(monkeypatch)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    result = await ex.compile()
    assert "compile" in result.command
    assert "--select" not in result.command
