# pyright: reportPrivateUsage=false
"""Backward-compat re-export shim for the Delta-branching primitives.

Implementation moved to :mod:`pointlessql.pql.branch` (split per
workflow: ``_create``, ``_discard``, ``_promote``, ``_common``).

Old import paths keep working — both the public API and the
underscore-prefixed helpers tests reach for are re-exported here.

Tests that ``patch.object(branch_mod._get_schema, "sync", ...)``
continue to work because Python module references are singletons —
patching ``.sync`` on the soyuz module here also affects the
re-imports inside the ``pql.branch`` subpackage.
"""

from __future__ import annotations

from pointlessql.pql.branch._common import (
    _create_schema,
    _create_table,
    _get_schema,
    _get_table,
    _update_schema,
    branch_tags,
)
from pointlessql.pql.branch._common import (
    classify_storage_scheme as _classify_storage_scheme,
)
from pointlessql.pql.branch._common import (
    derive_branch_storage_root as _derive_branch_storage_root,
)
from pointlessql.pql.branch._common import (
    ensure_source_schema as _ensure_source_schema,
)
from pointlessql.pql.branch._common import (
    record_branch_audit_log as _record_branch_audit_log,
)
from pointlessql.pql.branch._common import (
    resolve_storage_root as _resolve_storage_root,
)
from pointlessql.pql.branch._common import (
    split_two_part as _split_two_part,
)
from pointlessql.pql.branch._common import (
    uri_to_local_path as _uri_to_local_path,
)
from pointlessql.pql.branch._create import (
    _clone_table_local,
    _clone_table_local_deep_copy,
    _clone_table_local_symlink,
    _list_source_tables,
    _pick_strategy,
    _stats_from_action_row,
    create_branch_schema,
)
from pointlessql.pql.branch._discard import (
    _delete_branch_storage,
    discard_branch_schema,
)
from pointlessql.pql.branch._promote import (
    _check_promotion_conflicts,
    preview_promote_conflicts,
    promote_branch_schema,
)

__all__ = [
    "_check_promotion_conflicts",
    "_classify_storage_scheme",
    "_clone_table_local",
    "_clone_table_local_deep_copy",
    "_clone_table_local_symlink",
    "_create_schema",
    "_create_table",
    "_delete_branch_storage",
    "_derive_branch_storage_root",
    "_ensure_source_schema",
    "_get_schema",
    "_get_table",
    "_list_source_tables",
    "_pick_strategy",
    "_record_branch_audit_log",
    "_resolve_storage_root",
    "_split_two_part",
    "_stats_from_action_row",
    "_update_schema",
    "_uri_to_local_path",
    "branch_tags",
    "create_branch_schema",
    "discard_branch_schema",
    "preview_promote_conflicts",
    "promote_branch_schema",
]
