"""Second-pass mutation-killing tests for the dbt CLI executor.

Overflow companion to ``test_dbt_mutkill.py`` (kept under the per-file
LOC budget).  These pin two observable surfaces the first pass left
gapped:

* the spawn-failure message body (plain hint text, not a wrapped
  literal), and
* the completion log record the executor emits after every run — its
  verb slot, its format string, and the exit code it renders.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from pointlessql.config import DBTSettings
from pointlessql.services.dbt import DBTExecutor
from pointlessql.services.dbt._executor import (  # noqa: PLC2701  # private symbol
    DBTExecutionError,
)

_EXECUTOR_LOGGER = "pointlessql.services.dbt._executor"


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
) -> None:
    """Install a stub ``create_subprocess_exec`` returning a fixed proc."""

    async def _spawn(*_args: Any, **_kwargs: Any) -> _StubProc:
        return _StubProc(returncode, stdout, stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


def _last_executor_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """Return the executor's completion log record from a caplog capture."""
    records = [rec for rec in caplog.records if rec.name == _EXECUTOR_LOGGER]
    assert records, "executor emitted no completion log record"
    return records[-1]


# ---------------------------------------------------------------------------
# Missing-binary message body — plain text, not marker-wrapped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_missing_binary_message_is_plain_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The missing-binary message is the plain hint, not a wrapped literal.

    Substring checks alone survive a marker-wrapped string mutation
    (``"XXdbt CLI not found…XX"`` still *contains* ``"dbt CLI not
    found"``).  Pinning the leading text kills the wrap: the original
    starts with ``"dbt"``, the wrapped form with ``"XX"``.
    """

    async def _spawn(*_args: Any, **_kwargs: Any) -> Any:
        raise FileNotFoundError("no dbt")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with pytest.raises(DBTExecutionError) as excinfo:
        await ex.run()
    msg = str(excinfo.value)
    assert msg.startswith("dbt CLI not found")
    assert "XX" not in msg


# ---------------------------------------------------------------------------
# Completion log record — verb / exit-code / format string
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_log_names_subcommand_verb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The completion log renders the subcommand verb, not a ``None`` slot.

    Pins ``args[0] if args else "?"`` in the ``_logger.info`` call: a
    ``None`` mutation renders ``"dbt None exited…"`` instead of the
    actual verb.
    """
    _patch_spawn(monkeypatch, returncode=0)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with caplog.at_level(logging.INFO, logger=_EXECUTOR_LOGGER):
        await ex.run()
    msg = _last_executor_record(caplog).getMessage()
    assert "dbt run exited" in msg


@pytest.mark.asyncio
async def test_run_log_format_string_is_plain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The completion log format string is plain text, not marker-wrapped.

    Pins the ``"dbt %s exited with code %d in %.2fs"`` literal: a
    marker-wrapped mutation surfaces ``"XX"`` in the rendered record.
    """
    _patch_spawn(monkeypatch, returncode=0)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with caplog.at_level(logging.INFO, logger=_EXECUTOR_LOGGER):
        await ex.run()
    msg = _last_executor_record(caplog).getMessage()
    assert msg.startswith("dbt ")
    assert "exited with code" in msg
    assert "XX" not in msg


@pytest.mark.asyncio
async def test_run_log_empty_args_uses_question_mark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With no positional args the log uses a bare ``?`` placeholder.

    Pins the ``else "?"`` branch of the verb slot: a marker-wrapped
    placeholder mutation renders ``"dbt XX?XX exited…"`` instead of
    ``"dbt ? exited…"`` when ``_run`` is driven with no subcommand.
    """
    _patch_spawn(monkeypatch, returncode=0)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with caplog.at_level(logging.INFO, logger=_EXECUTOR_LOGGER):
        await ex._run()
    msg = _last_executor_record(caplog).getMessage()
    assert "dbt ? exited" in msg


@pytest.mark.asyncio
async def test_run_log_renders_actual_nonzero_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The completion log renders the real non-zero exit code.

    Pins ``proc.returncode or 0`` in the ``_logger.info`` call against a
    ``proc.returncode and 0`` mutation, which would zero out the logged
    code (``5 and 0`` is ``0``).
    """
    _patch_spawn(monkeypatch, returncode=5)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with caplog.at_level(logging.INFO, logger=_EXECUTOR_LOGGER):
        await ex.run()
    msg = _last_executor_record(caplog).getMessage()
    assert "exited with code 5" in msg


@pytest.mark.asyncio
async def test_run_log_renders_zero_exit_code_as_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A zero exit code is logged as ``0``, not coerced to ``1``.

    Pins ``proc.returncode or 0`` in the ``_logger.info`` call against a
    ``proc.returncode or 1`` mutation, which would log ``1`` for a clean
    run (``0 or 1`` is ``1``).
    """
    _patch_spawn(monkeypatch, returncode=0)
    ex = DBTExecutor(DBTSettings(), cwd=tmp_path)
    with caplog.at_level(logging.INFO, logger=_EXECUTOR_LOGGER):
        await ex.run()
    msg = _last_executor_record(caplog).getMessage()
    assert "exited with code 0" in msg
