"""Postgres → Unity Catalog sync worker.

Bridges a live Postgres database (referenced by a soyuz-catalog
Connection) to a foreign UC catalog. Pipeline:

1. :class:`PsycopgIntrospector` reads ``information_schema`` and
   returns a normalised :class:`PostgresSnapshot`.  Pure SQL, no UC
   calls.  Kept pluggable via the :class:`PostgresIntrospector`
   Protocol so unit tests can stub it.
2. :func:`diff_snapshots` compares that snapshot against the current
   UC state (returned from the soyuz facade) and produces a
   :class:`SyncDiff`.  Pure — no HTTP, no mutation.
3. :func:`apply_diff` walks the diff and drives the facade's
   ``create_schema`` / ``create_table`` / ``delete_table`` methods.
   Wrapped in :func:`run_sync` which also writes the
   :class:`~pointlessql.models.SyncRun` row and updates its status.

The diff intentionally stays at the "which tables exist and what are
their columns" level — we do not try to migrate data, reconcile
primary keys, or propagate tag/comment edits back to Postgres.

The package is composed of five sibling modules: ``types``
(dataclasses + ``PG_TO_UC_TYPE`` + ``map_pg_type_to_uc`` +
``PostgresIntrospector`` Protocol), ``dsn`` (secret-aware options
merging + DSN building), ``snapshot`` (``PsycopgIntrospector``),
``diff`` (pure ``diff_snapshots`` + ``apply_diff`` + UC walking),
``runs`` (``run_sync`` orchestration + ``list_recent_runs``).  The
package re-exports the full public surface so existing
``from pointlessql.services import pg_sync`` and
``from pointlessql.services.pg_sync import X`` callers (API,
scheduler, tests) continue to resolve unchanged.

Renamed ``_effective_options`` → ``effective_options``: the leading
underscore conveyed file-private scope, which is no longer accurate
now that ``runs.py`` imports it across modules.  Tests updated to
match.
"""

from __future__ import annotations

from pointlessql.services.pg_sync.diff import (
    apply_diff,
    collect_uc_tables,
    diff_snapshots,
)
from pointlessql.services.pg_sync.dsn import build_dsn, effective_options
from pointlessql.services.pg_sync.runs import (
    list_recent_runs,
    run_sync,
)
from pointlessql.services.pg_sync.snapshot import PsycopgIntrospector
from pointlessql.services.pg_sync.types import (
    EXTERNAL_TABLE_TYPE,
    FOREIGN_DATA_SOURCE_FORMAT,
    PG_TO_UC_TYPE,
    PgColumn,
    PgTable,
    PostgresIntrospector,
    PostgresSnapshot,
    SyncDiff,
    UcColumn,
    UcTable,
    map_pg_type_to_uc,
)

__all__ = [
    "EXTERNAL_TABLE_TYPE",
    "FOREIGN_DATA_SOURCE_FORMAT",
    "PG_TO_UC_TYPE",
    "PgColumn",
    "PgTable",
    "PostgresIntrospector",
    "PostgresSnapshot",
    "PsycopgIntrospector",
    "SyncDiff",
    "UcColumn",
    "UcTable",
    "apply_diff",
    "build_dsn",
    "collect_uc_tables",
    "diff_snapshots",
    "effective_options",
    "list_recent_runs",
    "map_pg_type_to_uc",
    "run_sync",
]
