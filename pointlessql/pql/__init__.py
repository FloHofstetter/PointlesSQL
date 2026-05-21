"""Sync helper library for reading and writing Delta tables through UC metadata.

This module is the **public surface** of the ``pql`` subsystem.
First-party callers (``pointlessql.api.*``, ``pointlessql.services.*``)
and any downstream consumer SHOULD import from here rather than
reaching into private submodules — direct ``from pointlessql.pql.<x>
import …`` is allowed but counts as opting into a non-public path
that can rotate without notice.

Categories of the public surface:

DataFrame bridge:

* :class:`PQL` — main facade (read / write / merge / aggregate /
  branch / rollback orchestrator).

Engine abstraction:

* :class:`Engine` — Protocol every backend implements.
* :class:`PandasEngine`, :class:`DuckDBEngine`, :class:`PolarsEngine`
  — concrete implementations.
* :func:`make_engine` — name-keyed factory.
* :func:`register_delta_view` — register a Delta table as a view in
  a DuckDB connection (used by SQL routes + table-stats services).

SQL parsing:

* :func:`prepare_sql`, :class:`SQLParseError`, :class:`PreparedSQL`
  — parse + validate a user-submitted SQL string into a
  ``PreparedSQL`` envelope.
* :class:`StmtType`, :func:`classify`, :func:`parse_and_classify`,
  :func:`parse_batch` — AST classification + multi-statement parse.
* :func:`extract_source_refs`, :func:`extract_write_target`,
  :func:`extract_table_refs`, :func:`extract_column_lineage`
  — AST inspection helpers.
* :func:`translate_merge_ast`, :class:`MergeCallSpec`,
  :class:`SQLMergeUnsupportedError` — sqlglot MERGE AST → PQL.merge
  translator (used by sql_dispatcher).

Branch primitives:

* :func:`create_branch_schema`, :func:`discard_branch_schema`,
  :func:`promote_branch_schema`, :func:`preview_promote_conflicts`
  — Delta-branching operations on UC schemas.

Branch error family:

* :class:`BranchError` (base) and the seven domain-named subclasses:
  :class:`BranchAlreadyExistsError`, :class:`BranchNotFoundError`,
  :class:`BranchInUseError`, :class:`BranchPromotionConflictError`,
  :class:`BranchOfBranchError`, :class:`BranchCloudUnsupportedError`,
  and `BranchTagsCorruptError` (when present).

Write-side helpers:

* :func:`write_table` — direct table write without going through
  the ``PQL`` facade (used by data-product enforcement tests).
* :func:`safe_delta_version` — current Delta version of a storage
  path (or ``None`` if missing) without instantiating a full PQL.
"""

from pointlessql.pql import context, memory, widgets
from pointlessql.pql._branch_errors import (
    BranchAlreadyExistsError,
    BranchCloudUnsupportedError,
    BranchError,
    BranchInUseError,
    BranchNotFoundError,
    BranchOfBranchError,
    BranchPromotionConflictError,
)
from pointlessql.pql._contracts import DraftContract, contract
from pointlessql.pql._types import SQLResult
from pointlessql.pql._write import safe_delta_version, write_table
from pointlessql.pql.branch import (
    create_branch_schema,
    discard_branch_schema,
    preview_promote_conflicts,
    promote_branch_schema,
)
from pointlessql.pql.engine import (
    DuckDBEngine,
    Engine,
    PandasEngine,
    PolarsEngine,
    make_engine,
    register_delta_view,
)
from pointlessql.pql.pql import PQL
from pointlessql.pql.sql_merge_translator import (
    MergeCallSpec,
    SQLMergeUnsupportedError,
    translate_merge_ast,
)
from pointlessql.pql.sql_parser import (
    PreparedSQL,
    SQLParseError,
    StmtType,
    classify,
    extract_column_lineage,
    extract_source_refs,
    extract_table_refs,
    extract_write_target,
    parse_and_classify,
    parse_batch,
    prepare_sql,
)

__all__ = [
    "PQL",
    "BranchAlreadyExistsError",
    "BranchCloudUnsupportedError",
    "BranchError",
    "BranchInUseError",
    "BranchNotFoundError",
    "BranchOfBranchError",
    "BranchPromotionConflictError",
    "DraftContract",
    "DuckDBEngine",
    "Engine",
    "MergeCallSpec",
    "PandasEngine",
    "PolarsEngine",
    "PreparedSQL",
    "SQLMergeUnsupportedError",
    "SQLParseError",
    "SQLResult",
    "StmtType",
    "classify",
    "context",
    "contract",
    "create_branch_schema",
    "discard_branch_schema",
    "extract_column_lineage",
    "extract_source_refs",
    "extract_table_refs",
    "extract_write_target",
    "make_engine",
    "memory",
    "parse_and_classify",
    "parse_batch",
    "prepare_sql",
    "preview_promote_conflicts",
    "promote_branch_schema",
    "register_delta_view",
    "safe_delta_version",
    "translate_merge_ast",
    "widgets",
    "write_table",
]
