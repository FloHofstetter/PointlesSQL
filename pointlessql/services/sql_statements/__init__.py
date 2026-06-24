"""external SQL Statement Execution API services.

Per-axis split mirroring the route module:

* :mod:`._envelope`   — :class:`SQLResult` → DBX envelope serializer +
                        DuckDB type-name mapping.
* :mod:`._executor`   — ``_run_statement`` async coroutine + in-process
                        task registry (cancel routes itself through here).
* :mod:`._qualify`    — sqlglot-based default catalog / schema rewrite.
* :mod:`._parameters` — typed ``:name`` parameter binding via sqlglot.
* :mod:`._retention`  — periodic cleanup of stale rows + result_payload
                        bytes from the statement store.

Routes import the public helpers from this package facade.
"""

from __future__ import annotations

from pointlessql.services.sql_statements._envelope import (
    DBX_ERROR_CODES,
    build_dbx_envelope,
    duckdb_to_dbx_type,
    error_envelope,
)
from pointlessql.services.sql_statements._executor import (
    cancel_statement,
    fetch_statement,
    register_statement_task,
    run_statement,
    unregister_statement_task,
)
from pointlessql.services.sql_statements._parameters import (
    SUPPORTED_PARAM_TYPES,
    bind_parameters,
)
from pointlessql.services.sql_statements._qualify import qualify_sql
from pointlessql.services.sql_statements._retention import (
    cleanup_stale_statements,
)

__all__ = [
    "DBX_ERROR_CODES",
    "SUPPORTED_PARAM_TYPES",
    "bind_parameters",
    "build_dbx_envelope",
    "cancel_statement",
    "cleanup_stale_statements",
    "duckdb_to_dbx_type",
    "error_envelope",
    "fetch_statement",
    "qualify_sql",
    "register_statement_task",
    "run_statement",
    "unregister_statement_task",
]
