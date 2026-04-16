# Authoring custom job kinds

PointlesSQL's scheduler (see `pointlessql/services/scheduler.py`) walks
a small registry of **job kinds** — callables that know how to perform
one unit of work. Two kinds ship in-box:

- `pg_sync` — the Sprint 18 Postgres-to-UC mirror. This is the
  reference implementation. Read
  [`pointlessql/services/pg_sync.py`](../pointlessql/services/pg_sync.py)
  alongside the scheduler source to see how a real kind is wired.
- `python` — a loader that resolves a plugin entry point and hands it
  the full executor context (see below).

This document covers how to add your own kind via the `python` loader
+ a plugin entry point. If you need a brand-new registry key, see the
“Built-in kinds” section near the end.

## 1. The executor signature

Every kind is a coroutine with the `JobExecutor` signature:

```python
from typing import Any

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


async def run_my_job(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """One unit of work.

    Args:
        job_run_id: The current :class:`~pointlessql.models.JobRun`
            id. Use it when calling :func:`pointlessql.services.scheduler.log_job`
            to tag log rows with this run.
        user_info: The "run-as" user the scheduler resolved from the
            job row. Its ``email`` is the principal forwarded to
            soyuz-catalog.
        config: Deserialized JSON config from the task row (or the
            job row, for single-task jobs).
        uc_client: A Unity Catalog facade that already carries the
            ``X-Principal`` header for ``user_info["email"]``.
    """
    ...
```

Return `None` on success. Raise anything on failure — the scheduler
catches, writes the error to the `task_run` row, honours the per-task
retry policy, and moves on.

## 2. Publishing the kind via an entry point

Ship your code as a regular Python wheel and declare the executor
under the `pointlessql.jobs` entry point group:

```toml
# pyproject.toml of your plugin package
[project.entry-points."pointlessql.jobs"]
my_job = "my_pkg.jobs:run_my_job"
```

Install the wheel into the same Python environment as PointlesSQL.
The `python` kind loads entry points lazily at execute-time via
`importlib.metadata`, so no PointlesSQL restart is required after
a fresh `uv pip install` — as long as the process can see the wheel
on disk.

## 3. Scheduling a job that uses the entry point

Create a job via `POST /api/jobs` (admin-only) with `kind: "python"`
and the entry-point name in `config`:

```json
{
  "name": "summarise_events_daily",
  "cron_expr": "0 2 * * *",
  "kind": "python",
  "config": {"entry_point": "my_job", "catalog": "events"}
}
```

For multi-task DAGs, put the same shape under `tasks[].kind` /
`tasks[].config` and let the scheduler walk the graph.

`on_failure_url` (optional) is a per-job HTTPS URL the scheduler
POSTs a small JSON payload to when a run ends in `failed`. The
payload is:

```json
{
  "job_id": 42,
  "job_name": "summarise_events_daily",
  "run_id": 1337,
  "status": "failed",
  "error": "...",
  "started_at": "2026-04-16T02:00:00+00:00",
  "finished_at": "2026-04-16T02:00:03+00:00"
}
```

It is best-effort: a 5-second timeout, no retries, transport failures
log a single WARN line and are otherwise ignored. The run's own state
in the DB is the source of truth.

## 4. Worked example — write a PQL summary table

A small kind that reads an input Delta table through PQL, computes a
group-by summary, and writes it back to a different table. Shows off:

- using the run-as principal through `uc_client` (via `PQL(client=...)`)
- emitting `JobLog` rows that appear in the detail-page log panel
- pulling parameters from `config`

```python
# my_pkg/jobs.py
from typing import Any

import pandas as pd

from pointlessql.pql.pql import PQL
from pointlessql.services.scheduler import log_job
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


async def summarise_events(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Read events, aggregate, and write a summary table.

    Expects ``config`` with keys:

    * ``source_table``: three-part name to read
    * ``target_table``: three-part name to write
    * ``group_by``: column name to group on
    """
    from pointlessql.db import get_session_factory

    source = config["source_table"]
    target = config["target_table"]
    group_by = config["group_by"]

    # PQL works with the same generated soyuz-catalog client the
    # uc_client facade wraps, so reusing ``uc_client._client`` keeps
    # X-Principal forwarding consistent end-to-end.
    pql = PQL(client=uc_client._client)  # noqa: SLF001

    factory = get_session_factory()
    log_job(
        factory, job_run_id, None, "INFO",
        f"reading {source} as {user_info['email']}",
    )

    df = pql.table(source)
    if not isinstance(df, pd.DataFrame):
        raise RuntimeError("this job only supports the pandas engine")

    summary = (
        df.groupby(group_by)
        .size()
        .reset_index(name="n")
    )

    log_job(
        factory, job_run_id, None, "INFO",
        f"writing {len(summary)} rows to {target}",
    )
    pql.write_table(summary, target, mode="overwrite")
```

Register it:

```toml
[project.entry-points."pointlessql.jobs"]
summarise_events = "my_pkg.jobs:summarise_events"
```

And schedule it:

```json
{
  "name": "summarise_events_daily",
  "cron_expr": "0 2 * * *",
  "kind": "python",
  "config": {
    "entry_point": "summarise_events",
    "source_table": "events.raw.clicks",
    "target_table": "events.agg.clicks_daily",
    "group_by": "country"
  }
}
```

## 5. Logging, retries, concurrency

- Use `log_job(factory, job_run_id, task_id, level, message)` from
  `pointlessql.services.scheduler` for rows that show up in the log
  panel. `task_id=None` means run-scoped.
- Standard stdlib `logger.info(...)` also works — the scheduler sets
  `request_id_var`, `job_run_id_var`, and `task_id_var` around every
  executor call so correlation IDs flow through the `RequestIdFilter`
  automatically.
- Retry policy is a DB concern, not an executor one — set
  `max_retries` / `retry_backoff_seconds` on the task row. Raising
  in your executor is what triggers the retry.
- Concurrency is capped per-job (`max_parallel_runs`) and globally
  (`POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS`). Your executor does
  not need to reason about either.

## 6. Observability

The scheduler emits three Prometheus metrics via
`pointlessql/services/metrics.py`:

| Metric | Type | Labels |
|---|---|---|
| `pointlessql_job_runs_total` | Counter | `status`, `job_name` |
| `pointlessql_job_run_duration_seconds` | Histogram | `job_name` |
| `pointlessql_scheduler_tick_lag_seconds` | Gauge | — |

`GET /metrics` exposes the standard Prometheus text format (admin
users only).

## 7. Built-in kinds

If your job is generic enough that "ship a plugin wheel + use
`python`" feels heavy, you can instead open a PR that registers a
new kind directly on the default registry:

1. Add an `async` executor in `pointlessql/services/scheduler.py`
   (or a dedicated module under `pointlessql/services/`).
2. Wire it in `build_default_registry()` alongside `"pg_sync"` and
   `"python"`.
3. Add tests.

Use the `pg_sync` kind as the reference — it is deliberately the
simplest possible executor: resolve the catalog, call into the
existing service module, let the scheduler own run state.
