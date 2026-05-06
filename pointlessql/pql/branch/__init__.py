"""Delta-branching primitives split per workflow.

Public surface:

* :func:`create_branch_schema` — clone a UC schema + tables into a branch.
* :func:`discard_branch_schema` — tear down a branch's storage and UC namespace.
* :func:`promote_branch_schema` — pointer-swap promote a branch to parent.
* :func:`preview_promote_conflicts` — dry-run conflict report for the UI.

Implementation lives in the per-workflow private modules
(:mod:`pointlessql.pql.branch._create`,
:mod:`pointlessql.pql.branch._discard`,
:mod:`pointlessql.pql.branch._promote`).  Shared helpers and the soyuz-API
module references that tests patch live in
:mod:`pointlessql.pql.branch._common`.
"""

from __future__ import annotations

from pointlessql.pql.branch._create import create_branch_schema
from pointlessql.pql.branch._discard import discard_branch_schema
from pointlessql.pql.branch._promote import (
    preview_promote_conflicts,
    promote_branch_schema,
)

__all__ = [
    "create_branch_schema",
    "discard_branch_schema",
    "preview_promote_conflicts",
    "promote_branch_schema",
]
