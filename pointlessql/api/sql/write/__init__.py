# pyright: reportPrivateUsage=false
"""PQL write-side endpoints — split per route family.

The ``POST /api/pql/...`` write routes + their helpers are split
per route family:

* :mod:`._helpers`   — ``_approve_select_refs`` (SELECT auth gate),
  ``_check_write_target`` (MODIFY / USE SCHEMA gate),
  ``_materialise_select_to_pandas`` (DuckDB → pandas), ``_build_pql``
  (PQL factory).  These keep their leading underscore because three
  external callers (``sql.editor._batch``, ``sql._dispatcher._dml``,
  ``pql.sql_merge_translator``) cross-import them.
* :mod:`._autoload`  — ``POST /api/pql/autoload`` (file-to-bronze).
* :mod:`._table`     — ``POST /api/pql/write_table`` +
  ``POST /api/pql/merge`` (pandas-materialised SELECT → Delta).
* :mod:`._dml`       — ``POST /api/pql/drop_table`` + ``/update`` +
  ``/delete`` (direct DML).

``router`` mounts each sub-router under the shared ``pql-write`` tag.
The four helpers are re-exported so the three cross-module callers
that import them via ``pointlessql.api.sql.write`` keep working
unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.sql.write._autoload import router as _autoload_router
from pointlessql.api.sql.write._dml import router as _dml_router
from pointlessql.api.sql.write._helpers import (
    _approve_select_refs,
    _build_pql,
    _check_write_target,
    _materialise_select_to_pandas,
)
from pointlessql.api.sql.write._table import router as _table_router

router = APIRouter()
router.include_router(_autoload_router)
router.include_router(_table_router)
router.include_router(_dml_router)

__all__ = [
    "_approve_select_refs",
    "_build_pql",
    "_check_write_target",
    "_materialise_select_to_pandas",
    "router",
]
