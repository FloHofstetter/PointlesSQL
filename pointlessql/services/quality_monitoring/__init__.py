"""Data-quality monitoring — CRUD, scan engine, scheduler executor.

Package layout:

* ``_crud``     — monitor persistence, target validation, the hidden
  scheduler-Job lifecycle, and the snapshot / anomaly read paths.
* ``_engine``   — the synchronous scan engine: per-table profiling
  (row count + column metrics through the shared table-stats
  profiler) and the anomaly rules (volume drop, null spike, schema
  change, freshness) with dedup + auto-resolve.
* ``_executor`` — the ``"quality_monitor"`` scheduler executor that
  resolves the target through Unity Catalog, dispatches the engine,
  and fans new anomalies out to the monitor's creator.
"""

from __future__ import annotations

from pointlessql.services.quality_monitoring._crud import (
    create_monitor,
    delete_monitor,
    ensure_backing_job,
    get_monitor,
    list_anomalies,
    list_monitors,
    list_snapshots,
    serialize_anomaly,
    serialize_monitor,
    serialize_snapshot,
    update_monitor,
    validate_target,
)
from pointlessql.services.quality_monitoring._engine import (
    FRESHNESS_MAX_AGE_HOURS,
    NULL_SPIKE_CRITICAL_DELTA,
    NULL_SPIKE_WARN_DELTA,
    VOLUME_DROP_CRITICAL_RATIO,
    VOLUME_DROP_MIN_PREVIOUS_ROWS,
    VOLUME_DROP_WARN_RATIO,
    scan_monitor_sync,
)
from pointlessql.services.quality_monitoring._executor import quality_monitor_executor

__all__ = [
    "FRESHNESS_MAX_AGE_HOURS",
    "NULL_SPIKE_CRITICAL_DELTA",
    "NULL_SPIKE_WARN_DELTA",
    "VOLUME_DROP_CRITICAL_RATIO",
    "VOLUME_DROP_MIN_PREVIOUS_ROWS",
    "VOLUME_DROP_WARN_RATIO",
    "create_monitor",
    "delete_monitor",
    "ensure_backing_job",
    "get_monitor",
    "list_anomalies",
    "list_monitors",
    "list_snapshots",
    "quality_monitor_executor",
    "scan_monitor_sync",
    "serialize_anomaly",
    "serialize_monitor",
    "serialize_snapshot",
    "update_monitor",
    "validate_target",
]
