"""Centralized logging configuration for PointlesSQL.

Provides request/job-scoped correlation IDs via :data:`request_id_var`,
:data:`job_run_id_var`, and :data:`task_id_var`, a
:class:`RequestIdFilter` that stamps each record with the current IDs,
an opt-in :class:`JSONFormatter` that propagates caller-supplied
``extra={...}`` fields as top-level JSON keys, and an idempotent
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
#: Cross-product trace id, shared across the operations of one logical
#: task even when they span several requests.  Set from the inbound
#: ``X-Correlation-ID`` header (falling back to the request id) and
#: stamped onto every ``agent_run_operations`` row for the mesh trace.
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_HANDLER_MARKER = "_pointlessql_handler"
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")
_TEXT_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[req=%(request_id)s job=%(job_run_id)s task=%(task_id)s] %(message)s"
)

# Hardcoded per-library quieting installed at startup so the
# application's structured logs aren't drowned by httpx-protocol-
# debug, sqlalchemy-engine-statement-spam, mlflow-client-info, or
# the dbt CLI's own progress chatter.  Operators override per-
# library via ``Settings.logging.third_party_levels`` (env var
# ``POINTLESSQL_LOG_THIRD_PARTY_LEVELS``); a global
# ``POINTLESSQL_LOG_LEVEL=DEBUG`` bypasses the defaults entirely
# (operator clearly wants every byte).
_THIRD_PARTY_DEFAULTS: dict[str, str] = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "urllib3": "WARNING",
    "sqlalchemy.engine": "WARNING",
    "mlflow": "INFO",
    "dbt": "INFO",
    "papermill": "INFO",
}

# Standard ``logging.LogRecord`` attribute names — anything in this
# set is part of the record's built-in surface and must not be re-
# emitted as an "extra" field by :class:`JSONFormatter`.  Lifted from
# CPython's ``logging`` module reference so a future stdlib change
# (rare) is the only way this can drift.  Includes the three
# correlation-id fields the request-id filter / record factory
# attach so they don't double-render.
_RESERVED_LOGRECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        # Correlation-id attrs already surfaced via dedicated payload
        # keys; merging them as extras would emit them twice.
        "request_id",
        "job_run_id",
        "task_id",
    }
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


def _harvest_extras(record: logging.LogRecord) -> dict[str, Any]:
    """Project ``record.__dict__`` into a JSON-safe extras subset.

    Reserved standard ``LogRecord`` attributes and the three
    correlation-id fields are filtered out so the JSON envelope's
    base shape stays stable.  Private attrs (``_foo``) are also
    skipped — they're an internal-state convention and
    serialising them would leak implementation details.

    Coercion of non-JSON-safe values (datetime, Path, UUID, …) is
    deferred to :func:`json.dumps`'s ``default=str`` fallback at
    serialisation time, so this helper stays a pure projection.

    Args:
        record: The :class:`logging.LogRecord` to harvest.

    Returns:
        Mapping of extra-field name → value, suitable for merging
        into the JSON payload.  Empty dict when no extras were
        attached.
    """
    out: dict[str, Any] = {}
    for k, v in record.__dict__.items():
        if k in _RESERVED_LOGRECORD_ATTRS:
            continue
        if k.startswith("_"):
            continue
        out[k] = v
    return out


class JSONFormatter(logging.Formatter):
    """Emit each record as a single-line JSON document.

    Base fields (always present): ``timestamp`` (ISO 8601 UTC),
    ``level``, ``logger``, ``message``, ``request_id``,
    ``job_run_id``, ``task_id``.  ``exception`` is added when the
    record carries ``exc_info``.

    Caller-supplied ``extra={...}`` fields are merged into the
    envelope as additional top-level keys via :func:`_harvest_extras`,
    which strips reserved ``LogRecord`` attrs and private (``_``-
    prefixed) keys.  A field passed via ``extra=`` cannot shadow a
    base field — the base layout always wins.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialize *record* as a single-line JSON document."""
        payload: dict[str, Any] = _harvest_extras(record)
        # Base fields override anything the caller may have stuffed
        # into ``extra`` so the envelope's shape stays stable.
        payload.update(
            {
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "request_id": getattr(record, "request_id", "-"),
                "job_run_id": getattr(record, "job_run_id", "-"),
                "task_id": getattr(record, "task_id", "-"),
            }
        )
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


def _quiet_third_parties(
    *,
    root_level: int,
    overrides: dict[str, str] | None,
) -> None:
    """Apply per-library log-level suppression for noisy upstreams.

    Effective level per library = ``overrides[name]`` when set,
    otherwise :data:`_THIRD_PARTY_DEFAULTS`.  When the root logger
    is at ``DEBUG`` the function short-circuits — operator clearly
    wants every byte from every library.

    Args:
        root_level: Numeric root-logger level after ``configure_logging``
            applied its setLevel call.
        overrides: Caller-supplied ``{library_name: level_name}`` map.
            Empty / ``None`` falls back to defaults.
    """
    if root_level <= logging.DEBUG:
        return
    overrides = overrides or {}
    merged: dict[str, str] = {**_THIRD_PARTY_DEFAULTS, **overrides}
    for name, level_name in merged.items():
        try:
            level_value = logging.getLevelNamesMapping()[level_name.upper()]
        except KeyError:
            # Unknown level name — skip rather than crash startup.
            continue
        logging.getLogger(name).setLevel(level_value)


def configure_logging(
    level: str = "INFO",
    fmt: Literal["text", "json"] = "text",
    *,
    third_party_levels: dict[str, str] | None = None,
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
        third_party_levels: Optional override map for the
            :data:`_THIRD_PARTY_DEFAULTS` quieting layer.  Falls back
            to defaults when ``None`` / empty.
    """
    if logging.getLogRecordFactory() is not _request_id_record_factory:
        logging.setLogRecordFactory(_request_id_record_factory)

    level_upper = level.upper()
    root = logging.getLogger()
    _strip_existing(root)
    root.addHandler(_build_handler(fmt))
    root.setLevel(level_upper)

    # Uvicorn defines its own loggers that do not propagate to root by
    # default once touched. Attach the same handler to each and disable
    # propagation so every access/error line uses our format.
    for name in _UVICORN_LOGGERS:
        uv_logger = logging.getLogger(name)
        _strip_existing(uv_logger)
        uv_logger.addHandler(_build_handler(fmt))
        uv_logger.setLevel(level_upper)
        uv_logger.propagate = False

    _quiet_third_parties(root_level=root.level, overrides=third_party_levels)
