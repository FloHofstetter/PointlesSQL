# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Run telemetry: Prometheus metrics + best-effort failure webhook.

The webhook is advisory — a receiver being down, slow, or misconfigured
must never affect the scheduler's own bookkeeping. The 5-second timeout
caps the wait so a stalled receiver cannot wedge the loop, and there are
no retries: the caller owns the canonical run state via the DB row.

Test hooks ``_WEBHOOK_TIMEOUT_SECONDS`` and ``_webhook_client_factory``
are module-level so tests can monkeypatch them via
``scheduler_service.runs._webhook_client_factory``.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import Job, JobRun
from pointlessql.services import metrics as metrics_service

logger = logging.getLogger(__name__)


# Failure-webhook tuning.
#
# 5-second timeout: long enough to ride over a GC-pause or TLS
# handshake on a well-behaved receiver, short enough that a broken
# endpoint never wedges the scheduler. No retries — this is a
# best-effort notification, not a durable queue; the caller owns the
# canonical run state via the DB row.
_WEBHOOK_TIMEOUT_SECONDS: float = 5.0

# httpx client factory kept as a module-level callable so tests can
# monkeypatch it in place of a real network client. Any callable
# returning an object with ``post(url, json=..., timeout=...)`` works.
_WebhookClientFactory = Callable[[], httpx.AsyncClient]
_webhook_client_factory: _WebhookClientFactory = httpx.AsyncClient


def _duration_seconds(run: JobRun) -> float | None:
    """Return ``finished_at - started_at`` as seconds, or ``None``.

    Synthetic ``skipped`` rows share a single timestamp so the
    difference is exactly ``0.0``; we still return that as a valid
    observation so dashboards see the skip in the duration histogram's
    smallest bucket. ``None`` is only returned when ``finished_at`` is
    still missing (running or uninitialised row) — the schema makes
    ``started_at`` non-nullable so it can be taken at face value.
    """
    if run.finished_at is None:
        return None
    started = run.started_at
    finished = run.finished_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=datetime.UTC)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=datetime.UTC)
    return (finished - started).total_seconds()


def _load_job_name_and_webhook(
    factory: sessionmaker[Session], job_id: int
) -> tuple[str, str | None]:
    """Snapshot ``(name, on_failure_url)`` for *job_id*.

    Kept separate from the main :func:`execute_run` body so the webhook
    dispatcher does not re-hit the DB for every failure path. Returns
    ``("", None)`` when the job row has disappeared (race with a
    concurrent delete), which means the caller emits metrics with an
    empty ``job_name`` label and skips the webhook.
    """
    with factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return "", None
        return job.name, job.on_failure_url


async def _post_failure_webhook(
    url: str,
    payload: dict[str, Any],
) -> None:
    """POST *payload* to *url*, logging and swallowing any failure.

    The webhook is advisory — a receiver being down, slow, or
    misconfigured must never affect the scheduler's own bookkeeping.
    :data:`_WEBHOOK_TIMEOUT_SECONDS` caps the wait so a stalled
    receiver cannot wedge the scheduler loop. Uses the module-level
    :data:`_webhook_client_factory` so tests can swap in a stub.

    Args:
        url: Opt-in endpoint taken from :attr:`pointlessql.models.Job.on_failure_url`.
        payload: JSON body — timestamps are pre-serialised ISO-8601
            strings by the caller so this function is oblivious to
            the run's internal datetime representation.
    """
    try:
        async with _webhook_client_factory() as client:
            await client.post(url, json=payload, timeout=_WEBHOOK_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("scheduler: on_failure_url webhook to %s failed: %s", url, exc)
    except Exception:  # noqa: BLE001 — webhook boundary
        logger.exception("scheduler: on_failure_url webhook to %s raised", url)


async def _emit_run_telemetry(
    factory: sessionmaker[Session],
    job_id: int,
    run: JobRun,
) -> None:
    """Emit Prometheus metrics + the optional failure webhook for *run*.

    Single bookkeeping path so every call site through
    :func:`execute_run` and :func:`tick_once` shares the same rules —
    there is no code path where a terminal state is written but the
    metrics/webhook are missed.

    Args:
        factory: Session factory for the job-name + URL snapshot.
        job_id: Parent job id (passed in so we don't rely on the
            detached run still knowing its owning row).
        run: Detached terminal :class:`JobRun`.
    """
    job_name, on_failure_url = _load_job_name_and_webhook(factory, job_id)
    duration = _duration_seconds(run)
    metrics_service.record_run(job_name, run.status, duration)

    if run.status != "failed" or not on_failure_url:
        return

    payload: dict[str, Any] = {
        "job_id": job_id,
        "job_name": job_name,
        "run_id": run.id,
        "status": run.status,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    await _post_failure_webhook(on_failure_url, payload)
