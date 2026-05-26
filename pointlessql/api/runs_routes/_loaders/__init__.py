"""Per-run data loaders — split into per-axis submodules.

The loaders are organised along the natural axes:

* :mod:`._runs`       — :func:`load_runs`, :func:`load_source_for_run`,
  :func:`load_events_for_run` (run-lifecycle axis).
* :mod:`._outputs`    — :func:`load_outputs_for_run`,
  :func:`load_cell_runs_for_run` (cell-output axis).
* :mod:`._operations` — :func:`load_operations_for_run`,
  :func:`load_tool_calls_for_run`,
  :func:`load_rewrite_attempts_for_run`,
  :func:`load_queries_for_run` (op-trace axis).
* :mod:`._audit`      — :func:`load_audit_entries_for_run`,
  :func:`load_uc_mutations_for_run` (audit axis).
* :mod:`._lineage`    — :func:`load_lineage_summary_for_run`,
  :func:`load_rejects_for_run`,
  :func:`load_unattributed_for_run` (lineage axis).

Every helper returns plain dicts (or detached ORM rows) shaped
for direct consumption by the Jinja templates and the JSON sibling
endpoints.  Three names are explicitly cross-imported by
:mod:`pointlessql.api.agent_runs_routes` so it can answer the
``/api/agent-runs/{id}/audit/*`` endpoints without re-implementing
the same SQL: :func:`load_lineage_summary_for_run`,
:func:`load_rejects_for_run`, :func:`load_unattributed_for_run`.

:func:`load_operations_for_run` is also imported by
:mod:`tests.test_runs_op_filter` because it covers the cross-axis
``?op_id=`` filter behaviour, and is re-exported from
:mod:`pointlessql.api.runs_routes.__init__` to keep that import
path stable.
"""

from __future__ import annotations

from pointlessql.api.runs_routes._loaders._audit import (
    load_audit_entries_for_run,
    load_uc_mutations_for_run,
)
from pointlessql.api.runs_routes._loaders._lineage import (
    load_lineage_summary_for_run,
    load_rejects_for_run,
    load_unattributed_for_run,
)
from pointlessql.api.runs_routes._loaders._operations import (
    load_operations_for_run,
    load_queries_for_run,
    load_rewrite_attempts_for_run,
    load_tool_calls_for_run,
)
from pointlessql.api.runs_routes._loaders._outputs import (
    load_cell_runs_for_run,
    load_outputs_for_run,
)
from pointlessql.api.runs_routes._loaders._runs import (
    load_events_for_run,
    load_runs,
    load_source_for_run,
)

__all__ = [
    "load_audit_entries_for_run",
    "load_cell_runs_for_run",
    "load_events_for_run",
    "load_lineage_summary_for_run",
    "load_operations_for_run",
    "load_outputs_for_run",
    "load_queries_for_run",
    "load_rejects_for_run",
    "load_rewrite_attempts_for_run",
    "load_runs",
    "load_source_for_run",
    "load_tool_calls_for_run",
    "load_uc_mutations_for_run",
    "load_unattributed_for_run",
]
