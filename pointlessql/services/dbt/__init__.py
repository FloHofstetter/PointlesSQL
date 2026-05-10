"""dbt orchestration: subprocess + executor + bridge.

This package consolidates the three eng-coupled dbt service
modules (dbt_bridge 635 + dbt_executor 324 + dbt_subprocess 275
= 1234 LOC) that used to live as flat siblings at
``pointlessql/services/`` root.

Layered call shape (top → bottom):

* ``_subprocess`` — manages the dbt subprocess + http endpoint
  used by the embedded dbt-docs server.
* ``_executor``   — invokes ``dbt run/test/build`` via the
  subprocess and parses the manifest + run-results JSON files.
* ``_bridge``     — bookkeeping layer that fan-outs dbt run
  results into PointlesSQL audit events, lineage row edges,
  test-failure reject rows, and per-node operation rows.
"""

from __future__ import annotations

from pointlessql.services.dbt._bridge import (
    DBTNodeResult,
    DBTRunSummary,
    as_dict,
    as_list,
    capture_delta_versions,
    emit_operations_for_dbt_run,
    emit_test_failure_rejects,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
    project_models,
    summarise,
)
from pointlessql.services.dbt._executor import (
    DBTExecutionError,
    DBTExecutor,
    DBTRunResult,
)
from pointlessql.services.dbt._subprocess import (
    DBTStartupError,
    DBTSubprocess,
    dbt_duckdb_available,
)

__all__ = [
    "DBTExecutionError",
    "DBTExecutor",
    "DBTNodeResult",
    "DBTRunResult",
    "DBTRunSummary",
    "DBTStartupError",
    "DBTSubprocess",
    "as_dict",
    "as_list",
    "capture_delta_versions",
    "dbt_duckdb_available",
    "emit_operations_for_dbt_run",
    "emit_test_failure_rejects",
    "merge_manifest_and_results",
    "parse_manifest",
    "parse_run_results",
    "project_models",
    "summarise",
]
