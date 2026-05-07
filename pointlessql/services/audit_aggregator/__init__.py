"""SQL aggregation backbone for the Audit Cockpit.

Three pure-SQL aggregations compose every cockpit surface:

* :func:`summary` — single-dict counts for the four "is anything
  exploding right now?" personas.
* :func:`timeseries` — point-list binned over time, optionally
  grouped by ``table`` or ``principal``.
* :func:`anomalies` — same shape as ``timeseries`` plus a
  ``baseline_mean``/``baseline_std``/``sigma``/``severity`` per
  point computed against an N-day rolling window.

All three share a single filter helper so a future
``/api/audit/<surface>`` route can re-use the same WHERE clause.
The filter helper is timestamp-column-aware: each metric points at
its own ``timestamp_col`` (``started_at`` for runs/ops,
``created_at`` for lineage tables, ``detected_at`` for
``unattributed_writes``, ``called_at`` for tool calls).

No new persistence — the service queries the existing tables
directly.  The roadmap revisit threshold for materialising results
is >100M datapoints/year *or* >2s p95 on
``/api/audit/anomalies``.

This was a single 913-LOC file until Phase 49b; the public surface
is unchanged.  Imports of the original module path keep working
because every public symbol is re-exported here.
"""

from pointlessql.services.audit_aggregator._anomaly import (
    RUN_ANOMALY_METRICS,
    anomalies,
    backfill_run_anomalies,
    compute_run_anomaly,
)
from pointlessql.services.audit_aggregator._query_builder import (
    VALID_BINS,
    VALID_GROUP_BY,
    VALID_METRICS,
    Bin,
    GroupBy,
    Metric,
    MetricSpec,
    Severity,
    metric_spec,
)
from pointlessql.services.audit_aggregator._summary import summary
from pointlessql.services.audit_aggregator._timeseries import timeseries

__all__ = [
    "Bin",
    "GroupBy",
    "Metric",
    "MetricSpec",
    "RUN_ANOMALY_METRICS",
    "Severity",
    "VALID_BINS",
    "VALID_GROUP_BY",
    "VALID_METRICS",
    "anomalies",
    "backfill_run_anomalies",
    "compute_run_anomaly",
    "metric_spec",
    "summary",
    "timeseries",
]
