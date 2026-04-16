"""Prometheus metrics for the PointlesSQL scheduler and runtime.

Exposes three metric objects the scheduler and the ``/metrics`` route
share:

* :data:`job_runs_total` — monotonic counter of finished :class:`~pointlessql.models.JobRun`
  rows, labelled by ``status`` (``succeeded`` | ``failed`` | ``skipped``)
  and ``job_name`` so dashboards can split per-job failure rates
  without cardinality exploding for a small number of jobs per install.
* :data:`job_run_duration_seconds` — histogram of end-to-end run
  durations in seconds. Buckets cover sub-second runs (most ``skipped``
  outcomes land here) up to multi-hour batch jobs without needing a
  custom exporter.
* :data:`scheduler_tick_lag_seconds` — gauge sampled each tick with
  the difference between the expected tick time and the actual tick
  arrival. A steadily growing lag indicates the scheduler loop is
  falling behind its configured ``tick_seconds`` cadence.

Lives in its own module instead of inside ``scheduler.py`` so the
FastAPI route (``api/main.py``) can import :func:`render_metrics`
without dragging in the scheduler's heavier dependencies, and so
tests can import the metric objects directly without spinning up a
session factory.

The metrics are always on — ``Counter.inc()`` on a no-op path is
measured in nanoseconds, not worth gating behind a feature flag.
"""

from __future__ import annotations

import logging

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client import REGISTRY as _DEFAULT_REGISTRY

logger = logging.getLogger(__name__)


# A dedicated registry so tests can reset state without touching the
# default global collector. The ``/metrics`` route renders this registry
# specifically; anyone who wants to scrape process metrics too can
# compose this with the default registry in their own exporter.
REGISTRY: CollectorRegistry = CollectorRegistry()


# Bucket selection for job durations.
#
# We span eight orders of magnitude — 50 ms up to ~1 h — because jobs
# in PointlesSQL cover the whole range: a ``skipped`` concurrency-cap
# outcome finishes in milliseconds, while a full ``pg_sync`` on a
# 1000-schema foreign catalog can take an hour. Buckets are roughly
# log-spaced so each order of magnitude gets at least one cut-point,
# and we include the Prometheus default 10-second boundary so
# alerts ported from other systems keep working without retuning.
_DURATION_BUCKETS: tuple[float, ...] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    300.0,
    900.0,
    1800.0,
    3600.0,
)


job_runs_total: Counter = Counter(
    "pointlessql_job_runs_total",
    "Total number of finished job runs, partitioned by terminal status.",
    labelnames=("status", "job_name"),
    registry=REGISTRY,
)

job_run_duration_seconds: Histogram = Histogram(
    "pointlessql_job_run_duration_seconds",
    "End-to-end duration of a job run in seconds (start → terminal).",
    labelnames=("job_name",),
    buckets=_DURATION_BUCKETS,
    registry=REGISTRY,
)

scheduler_tick_lag_seconds: Gauge = Gauge(
    "pointlessql_scheduler_tick_lag_seconds",
    "Difference between the expected and actual scheduler tick time, in seconds.",
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    """Serialize the scheduler metrics for the ``/metrics`` HTTP route.

    Returns:
        A ``(body, content_type)`` tuple whose content type is the
        Prometheus text exposition format (``version=0.0.4``). FastAPI
        forwards these verbatim as a :class:`~fastapi.responses.Response`.
    """
    body = generate_latest(REGISTRY)
    return body, CONTENT_TYPE_LATEST


def record_run(
    job_name: str,
    status: str,
    duration_seconds: float | None,
) -> None:
    """Emit counter + histogram samples for one finished run.

    Called from the scheduler at the moment a :class:`~pointlessql.models.JobRun`
    flips to a terminal status. The histogram observation is skipped
    when *duration_seconds* is ``None`` (which happens only for the
    synthetic ``skipped`` runs the scheduler inserts when the per-job
    cap is saturated — they have identical ``started_at`` and
    ``finished_at`` but we still count them as ``skipped`` in the
    counter so dashboards can show the skip rate).

    Args:
        job_name: The :attr:`~pointlessql.models.Job.name` column.
        status: Terminal status (``succeeded`` / ``failed`` / ``skipped``).
        duration_seconds: Wall-clock duration of the run, or ``None``
            when the run was skipped before launch.
    """
    job_runs_total.labels(status=status, job_name=job_name).inc()
    if duration_seconds is not None:
        job_run_duration_seconds.labels(job_name=job_name).observe(
            duration_seconds
        )


def observe_tick_lag(lag_seconds: float) -> None:
    """Record the drift between the expected and actual tick time.

    Args:
        lag_seconds: Actual tick time minus expected tick time. Can be
            negative if the loop wakes early; Prometheus gauges accept
            any real number so we don't clamp.
    """
    scheduler_tick_lag_seconds.set(lag_seconds)


# Silence unused-import warnings from tools that can't see the re-export
# used by ``render_metrics``.
_ = _DEFAULT_REGISTRY


__all__ = [
    "REGISTRY",
    "job_run_duration_seconds",
    "job_runs_total",
    "observe_tick_lag",
    "record_run",
    "render_metrics",
    "scheduler_tick_lag_seconds",
]
