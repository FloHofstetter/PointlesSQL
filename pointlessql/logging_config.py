"""Centralized logging configuration for PointlesSQL.

Provides request/job-scoped correlation IDs via :data:`request_id_var`,
:data:`job_run_id_var`, and :data:`task_id_var`, a
:class:`RequestIdFilter` that stamps each record with the current IDs,
an opt-in :class:`JSONFormatter`, and an idempotent
:func:`configure_logging` function that wires the root logger and
uvicorn's three loggers with a shared handler.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_run_id_var: ContextVar[str | None] = ContextVar("job_run_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)

_HANDLER_MARKER = "_pointlessql_handler"
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")
_TEXT_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[req=%(request_id)s job=%(job_run_id)s task=%(task_id)s] %(message)s"
)


class RequestIdFilter(logging.Filter):
    """Stamp each log record with the request/job/task contextvar values.

    When no scope is active the value is rendered as ``"-"`` so the
    text formatter never shows a blank column and the JSON formatter
    never emits ``null``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach correlation ids to *record* and allow it to propagate."""
        record.request_id = request_id_var.get() or "-"
        record.job_run_id = job_run_id_var.get() or "-"
        record.task_id = task_id_var.get() or "-"
        return True


class JSONFormatter(logging.Formatter):
    """Emit each record as a single-line JSON document.

    Fields: ``timestamp`` (ISO 8601 UTC), ``level``, ``logger``,
    ``message``, ``request_id``, ``job_run_id``, ``task_id`` and
    ``exception`` (only when the record carries ``exc_info``). Extra
    attributes attached via ``logger.info(..., extra={...})`` are not
    serialized — keep them in the message for now.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialize *record* as a single-line JSON document."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "job_run_id": getattr(record, "job_run_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _build_handler(fmt: Literal["text", "json"]) -> logging.Handler:
    """Create the shared stderr handler with filter + formatter attached."""
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RequestIdFilter())
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))
    setattr(handler, _HANDLER_MARKER, True)
    return handler


def _strip_existing(logger: logging.Logger) -> None:
    """Remove any handlers previously installed by :func:`configure_logging`."""
    for h in list(logger.handlers):
        if getattr(h, _HANDLER_MARKER, False):
            logger.removeHandler(h)


_default_factory = logging.getLogRecordFactory()


def _request_id_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Extend the default LogRecord with correlation-id attributes.

    Installed globally by :func:`configure_logging` so handlers that
    bypass our stderr sink (notably pytest's ``caplog``) still see the
    request/job/task IDs on every record.
    """
    record = _default_factory(*args, **kwargs)
    record.request_id = request_id_var.get() or "-"
    record.job_run_id = job_run_id_var.get() or "-"
    record.task_id = task_id_var.get() or "-"
    return record


def configure_logging(
    level: str = "INFO",
    fmt: Literal["text", "json"] = "text",
) -> None:
    """Configure the root logger and uvicorn's loggers.

    Idempotent — a second call with different arguments replaces the
    handlers installed by the first call without disturbing handlers
    installed by anyone else (e.g. pytest's ``caplog``). Also installs
    a LogRecord factory that stamps the correlation ids on every
    record, so third-party handlers see them without any per-handler
    hookup.

    Args:
        level: Minimum level for the root logger, e.g. ``"INFO"`` or
            ``"DEBUG"``. Passed to :meth:`logging.Logger.setLevel`.
        fmt: ``"text"`` for human-readable single-line output,
            ``"json"`` for machine-parsable structured logs.
    """
    if logging.getLogRecordFactory() is not _request_id_record_factory:
        logging.setLogRecordFactory(_request_id_record_factory)

    root = logging.getLogger()
    _strip_existing(root)
    root.addHandler(_build_handler(fmt))
    root.setLevel(level.upper())

    # Uvicorn defines its own loggers that do not propagate to root by
    # default once touched. Attach the same handler to each and disable
    # propagation so every access/error line uses our format.
    for name in _UVICORN_LOGGERS:
        uv_logger = logging.getLogger(name)
        _strip_existing(uv_logger)
        uv_logger.addHandler(_build_handler(fmt))
        uv_logger.setLevel(level.upper())
        uv_logger.propagate = False
