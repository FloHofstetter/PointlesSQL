"""Strict per-operation trail for agent runs.

Every PQL primitive call inside an agent run emits one row into the
``agent_run_operations`` table.  This package provides the helper
:func:`record_operation` plus a context-manager
:func:`operation_context` that primitives wrap their work in.

The mode is **strict**: if the trail row cannot be persisted (DB
down, FK miss because the run id is unknown to the registry), the
primitive raises :class:`pointlessql.exceptions.AuditUnavailableError`
*before* touching DuckDB or deltalake.  The contract is "no write
without a trail"; best-effort would defeat the forced-audit
guarantee.

Ordinal allocation is a SELECT-MAX-then-INSERT inside one
transaction.  SQLite's default WAL + serialised writers make this
race-safe enough for one-runtime-per-run; for parallel writers
within the same run, switch to a server-side
``COALESCE(MAX(ordinal), 0) + 1`` UPDATE/INSERT pattern.

This was a single 917-LOC file the public surface
is unchanged.  Imports of the original module path keep working
because every public symbol is re-exported here.
"""

from pointlessql.services.agent_runs.operations._common import (
    VALID_OP_NAMES,
    OperationRecorder,
)
from pointlessql.services.agent_runs.operations._lifecycle import (
    operation_context,
    record_operation,
)
from pointlessql.services.agent_runs.operations._rollback import (
    RollbackAmbiguous,
    RollbackError,
    RollbackInvalid,
    RollbackStale,
    RollbackTargetNotFound,
)
from pointlessql.services.agent_runs.operations._vector_rebuild import (
    rebuild_vss_indices_after_commit,
)

__all__ = [
    "OperationRecorder",
    "RollbackAmbiguous",
    "RollbackError",
    "RollbackInvalid",
    "RollbackStale",
    "RollbackTargetNotFound",
    "VALID_OP_NAMES",
    "operation_context",
    "rebuild_vss_indices_after_commit",
    "record_operation",
]
