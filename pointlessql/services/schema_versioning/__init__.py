"""Output-port schema-contract versioning + breaking-change enforcement.

Public surface:

* :mod:`_diff` — pure-Python diff between two schema JSON shapes that
  classifies the change into a ``major`` / ``minor`` / ``patch`` /
  ``none`` bucket according to a fixed rule set.
* :mod:`_bumper` — proposes the next semver given a current semver and
  a diff.
* :mod:`_enforcer` — write-time hook that compares an incoming schema
  to the registered version and raises
  :class:`SchemaBreakingChangeError` when the policy mode says
  ``block``.
* :mod:`_crud` — list / append history rows, fetch the current
  schema_json for a port.
"""

from __future__ import annotations

from pointlessql.services.schema_versioning._bootstrap import (
    register_schema_versioning_hooks,
)
from pointlessql.services.schema_versioning._bumper import (
    propose_bump,
)
from pointlessql.services.schema_versioning._crud import (
    bump_port_version,
    current_schema,
    get_version_history,
    list_versions,
)
from pointlessql.services.schema_versioning._diff import (
    SchemaDiff,
    compute_diff,
)
from pointlessql.services.schema_versioning._enforcer import (
    SchemaBreakingChangeError,
    assert_schema_compatibility,
)

__all__ = [
    "SchemaBreakingChangeError",
    "SchemaDiff",
    "assert_schema_compatibility",
    "bump_port_version",
    "compute_diff",
    "current_schema",
    "get_version_history",
    "list_versions",
    "propose_bump",
    "register_schema_versioning_hooks",
]
