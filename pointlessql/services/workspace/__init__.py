"""Workspace CRUD + repo sync + governance + cascade helpers.

Four flat sibling modules (workspaces 414 + workspace_repos 658
+ governance_events 308 + cascade 167 = 1547 LOC) consolidated
into one ``pointlessql.services.workspace`` package whose
``__init__.py`` re-exports the workspace CRUD + cascade public
surface.

Layout:

* ``_crud``      — workspace CRUD + membership management.
* ``repos``      — workspace-repo (git-backed) registration,
                    secret rotation, sync.  Public-shaped because
                    consumers reach for several distinct surfaces
                    (CRUD vs. sync vs. webhooks).
* ``governance`` — governance-event emit / list helpers (the
                    audit-stream sibling concept; see
                    ``models.governance_events``).
* ``_cascade``   — downstream-table discovery for cascade-aware
                    workspace deletion.  Private helper.

The repos and governance modules keep their natural names (no
``_`` prefix) because external consumers reach into them as
modules: ``from pointlessql.services.workspace import repos`` is
the existing call shape.
"""

from __future__ import annotations

from pointlessql.services.workspace._cascade import (
    DownstreamSpec,
    find_downstream_tables,
)
from pointlessql.services.workspace._crud import (
    add_member,
    create_workspace,
    get_membership_role,
    get_workspace,
    get_workspace_by_slug,
    is_member,
    list_workspaces_for_user,
    resolve_workspace_id,
)

__all__ = [
    "DownstreamSpec",
    "add_member",
    "create_workspace",
    "find_downstream_tables",
    "get_membership_role",
    "get_workspace",
    "get_workspace_by_slug",
    "is_member",
    "list_workspaces_for_user",
    "resolve_workspace_id",
]
