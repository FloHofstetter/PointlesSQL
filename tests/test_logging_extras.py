"""Sprint 44.1 — ``extra={...}`` propagation in :class:`JSONFormatter`.

Locks the contract that caller-supplied ``logger.info("...",
extra={"run_id": "abc"})`` lands the run_id as a top-level key in
the JSON envelope, while reserved ``LogRecord`` attrs stay
filtered (no shadowing of ``level`` / ``logger`` / etc.).
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from io import StringIO
from pathlib import Path

import pytest

from pointlessql.logging_config import (
    JSONFormatter,
    RequestIdFilter,
    job_run_id_var,
    request_id_var,
    task_id_var,
)


@pytest.fixture
def isolated_logger() -> logging.Logger:
    """Build a logger with a fresh JSONFormatter and a captured stream."""
    logger = logging.getLogger(f"pql_test.{uuid.uuid4().hex}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def _emit(
    logger: logging.Logger,
    level: int,
    msg: str,
    *,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Emit one log call through a JSONFormatter and return the parsed envelope."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    try:
        logger.log(level, msg, extra=extra)
    finally:
        logger.removeHandler(handler)
    raw = stream.getvalue().strip()
    parsed: dict[str, object] = json.loads(raw)
    return parsed


def test_extras_str_and_int_become_top_level_keys(isolated_logger: logging.Logger) -> None:
    """``extra={"run_id": "abc", "op_id": 5}`` lands as top-level JSON keys."""
    body = _emit(
        isolated_logger,
        logging.INFO,
        "scheduler tick",
        extra={"run_id": "abc-123", "op_id": 5},
    )
    assert body["run_id"] == "abc-123"
    assert body["op_id"] == 5
    # Base fields always present.
    assert body["level"] == "INFO"
    assert body["message"] == "scheduler tick"


def test_extras_nested_dict_serialises(isolated_logger: logging.Logger) -> None:
    """Nested-dict extras serialize via ``json.dumps`` natively."""
    body = _emit(
        isolated_logger,
        logging.WARNING,
        "audit emit",
        extra={"context": {"workspace_id": 1, "kind": "merge"}},
    )
    ctx = body["context"]
    assert isinstance(ctx, dict)
    assert ctx["workspace_id"] == 1
    assert ctx["kind"] == "merge"


def test_extras_datetime_falls_through_default_str(isolated_logger: logging.Logger) -> None:
    """``datetime`` extras serialize via the ``default=str`` fallback."""
    when = datetime.datetime(2026, 5, 7, 12, 30, tzinfo=datetime.UTC)
    body = _emit(
        isolated_logger,
        logging.INFO,
        "training_context",
        extra={"started_at": when},
    )
    assert isinstance(body["started_at"], str)
    assert "2026-05-07 12:30" in str(body["started_at"])


def test_extras_pathlib_falls_through_default_str(isolated_logger: logging.Logger) -> None:
    """``Path`` extras serialize via the ``default=str`` fallback."""
    body = _emit(
        isolated_logger,
        logging.WARNING,
        "notebook render",
        extra={"manifest_path": Path("/tmp/manifest.json")},
    )
    assert body["manifest_path"] == "/tmp/manifest.json"


def test_extras_with_reserved_key_is_rejected_by_stdlib(
    isolated_logger: logging.Logger,
) -> None:
    """Python's stdlib ``logging`` raises on reserved-name extras.

    First line of defence: ``logging.Logger.makeRecord`` itself
    refuses an ``extra={"asctime": ...}`` with KeyError.  Our
    ``_RESERVED_LOGRECORD_ATTRS`` filter is the second line — it
    strips the same keys out of ``record.__dict__`` if a future
    code path bypasses ``makeRecord`` (custom record factories,
    direct attribute injection in tests).
    """
    with pytest.raises(KeyError, match="overwrite"):
        _emit(
            isolated_logger,
            logging.ERROR,
            "boom",
            extra={"asctime": "2099-01-01"},
        )


def test_filter_strips_reserved_attrs_set_via_record_factory() -> None:
    """Defence in depth: the harvester filter excludes reserved keys.

    Bypasses ``extra=`` entirely by mutating a freshly-built
    ``LogRecord``.  This is the path a custom record factory could
    take; the filter must still keep base fields off the extras
    map.
    """
    from pointlessql.logging_config import _harvest_extras

    record = logging.LogRecord(
        name="pql_test.harvester",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="msg",
        args=None,
        exc_info=None,
    )
    # Inject a key that's already part of LogRecord's standard
    # surface — the harvester must filter it.
    record.__dict__["levelname"] = "EVIL"
    record.__dict__["request_id"] = "should-not-leak-as-extra"
    record.__dict__["my_app_field"] = "kept"
    extras = _harvest_extras(record)
    assert "levelname" not in extras
    assert "request_id" not in extras  # rendered separately
    assert extras["my_app_field"] == "kept"


def test_correlation_ids_still_render_under_extras(isolated_logger: logging.Logger) -> None:
    """Regression guard: contextvar correlation-ids land alongside extras."""
    token_req = request_id_var.set("req-xyz")
    token_job = job_run_id_var.set("job-7")
    token_task = task_id_var.set("task-9")
    try:
        body = _emit(
            isolated_logger,
            logging.INFO,
            "happens during request",
            extra={"run_id": "abc"},
        )
    finally:
        request_id_var.reset(token_req)
        job_run_id_var.reset(token_job)
        task_id_var.reset(token_task)
    assert body["request_id"] == "req-xyz"
    assert body["job_run_id"] == "job-7"
    assert body["task_id"] == "task-9"
    assert body["run_id"] == "abc"


def test_envelope_without_extras_keeps_legacy_shape(
    isolated_logger: logging.Logger,
) -> None:
    """No-extras call produces the seven-field legacy envelope (back-compat)."""
    body = _emit(isolated_logger, logging.INFO, "boring")
    expected_keys = {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "job_run_id",
        "task_id",
    }
    assert expected_keys.issubset(body.keys())
    # No surprise extras when the caller didn't pass any.
    actual_minus_expected = set(body.keys()) - expected_keys
    assert actual_minus_expected == set(), f"unexpected extras: {actual_minus_expected}"
