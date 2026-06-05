"""Pure decision and formatting logic for scheduled-run execution.

The run orchestrators (``_execute_run_core``, ``_run_dag``,
``_run_one_task``) and the telemetry path interleave state-machine
decisions, retry arithmetic, message composition, and payload shaping
with their DB writes, executor dispatch, and webhook POSTs.  Every
I/O-free piece of that lives here so it can be unit-tested without a
session factory, a registry, or a network client.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from typing import Any

# Task outcomes that make a downstream dependant unrunnable.
_BLOCKING_UPSTREAM = frozenset({"failed", "skipped"})


def parse_config_json(raw: str | None) -> tuple[Any, str | None]:
    """Decode a job/task config JSON blob.

    Args:
        raw: The stored config JSON, or ``None`` (treated as ``"{}"``).

    Returns:
        A ``(value, error)`` pair.  On success ``value`` is the decoded
        JSON (normally a dict) and ``error`` is ``None``; on a decode
        failure ``value`` is ``None`` and ``error`` is the decoder's
        message (the caller wraps it with its own prefix).
    """
    try:
        return json.loads(raw or "{}"), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def select_max_attempts(max_retries: int) -> int:
    """Return the total attempt budget for a task (initial try + retries).

    Args:
        max_retries: The task's configured retry count.

    Returns:
        ``max_retries + 1``, floored at ``1`` so a negative or zero
        configuration still runs the task once.
    """
    return max(1, max_retries + 1)


def retry_delay_seconds(attempt: int, backoff_seconds: float) -> float:
    """Return the backoff delay before the next attempt.

    Args:
        attempt: The 1-based number of the attempt that just failed.
        backoff_seconds: The task's per-attempt backoff multiplier.

    Returns:
        ``attempt * backoff_seconds`` as a float (``0.0`` disables the
        sleep entirely).
    """
    return float(attempt * backoff_seconds)


def detect_upstream_failures(deps: list[int], results: Mapping[int, str]) -> list[int]:
    """Return the dependencies that failed or were skipped.

    Args:
        deps: Upstream task ids this task depends on.
        results: Map of already-resolved task id to terminal status.

    Returns:
        The subset of ``deps`` whose recorded status is ``"failed"`` or
        ``"skipped"`` (in ``deps`` order), which forces a skip.
    """
    return [d for d in deps if results.get(d) in _BLOCKING_UPSTREAM]


def upstream_skip_messages(task_name: str, failed_deps: list[int]) -> tuple[str, str]:
    """Compose the log line and TaskRun error for an upstream-forced skip.

    Args:
        task_name: The skipped task's name.
        failed_deps: The upstream ids that did not succeed.

    Returns:
        A ``(log_detail, task_error)`` pair — the verbose line for the
        job log and the terse string stored on the ``TaskRun``.
    """
    detail = f"task {task_name!r} skipped: upstream {failed_deps} did not succeed"
    error = f"upstream {failed_deps} failed"
    return detail, error


def compose_task_fail_message(task_name: str, err: str | None) -> str:
    """Render the run-level error string for a task's first failure.

    Args:
        task_name: The failing task's name.
        err: The executor's error message, if any.

    Returns:
        A message that appends ``err`` when present and omits it
        otherwise.
    """
    return f"task {task_name!r} failed: {err}" if err else f"task {task_name!r} failed"


def dag_run_status(ok: bool, err: str | None) -> tuple[str, str | None]:
    """Map a DAG walk's outcome to the run's terminal status + error.

    Args:
        ok: Whether every task in the DAG succeeded.
        err: The first failure message gathered during the walk.

    Returns:
        ``("succeeded", None)`` when ``ok``; otherwise ``("failed", err)``.
    """
    if ok:
        return "succeeded", None
    return "failed", err


def ensure_utc(dt: datetime.datetime) -> datetime.datetime:
    """Return *dt* as a UTC-aware datetime.

    SQLite drops ``tzinfo`` on roundtrip even for ``DateTime(timezone=True)``
    columns, so timestamps read back from the DB may be naive.  Attaching
    UTC keeps cron math and duration math uniform across dialects.

    Args:
        dt: A datetime that may be naive or aware.

    Returns:
        The same instant with ``tzinfo`` set to UTC when it was naive,
        otherwise ``dt`` unchanged.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.UTC)
    return dt


def duration_seconds(
    started: datetime.datetime,
    finished: datetime.datetime,
) -> float:
    """Return ``finished - started`` in seconds, tz-normalised.

    Args:
        started: Run start timestamp.
        finished: Run finish timestamp.

    Returns:
        The elapsed seconds (``0.0`` for a synthetic same-instant skip).
    """
    return (ensure_utc(finished) - ensure_utc(started)).total_seconds()


def should_emit_failure_webhook(status: str, on_failure_url: str | None) -> bool:
    """Decide whether the optional failure webhook should fire.

    Args:
        status: The run's terminal status.
        on_failure_url: The job's opt-in webhook URL, if configured.

    Returns:
        ``True`` only for a failed run that carries a non-empty URL.
    """
    return status == "failed" and bool(on_failure_url)


def build_failure_webhook_payload(
    *,
    job_id: int,
    job_name: str,
    run_id: int,
    status: str,
    error: str | None,
    started_at: datetime.datetime | None,
    finished_at: datetime.datetime | None,
) -> dict[str, Any]:
    """Build the JSON body POSTed to a job's failure webhook.

    Timestamps are pre-serialised to ISO-8601 (or ``None``) here so the
    dispatcher stays oblivious to the run's datetime representation.

    Args:
        job_id: Parent job id.
        job_name: Snapshot job name.
        run_id: The failed run's id.
        status: The terminal status (``"failed"``).
        error: The run's error message, if any.
        started_at: Run start, or ``None``.
        finished_at: Run finish, or ``None``.

    Returns:
        A JSON-ready dict with ISO-8601 timestamp strings.
    """
    return {
        "job_id": job_id,
        "job_name": job_name,
        "run_id": run_id,
        "status": status,
        "error": error,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
    }
