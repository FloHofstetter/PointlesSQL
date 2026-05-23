"""ORM models for the workspace governance container.

Three flat sibling modules consolidated into one
``pointlessql.models.workspace`` package whose ``__init__.py``
re-exports the 9 public symbols.

Layout:

* ``_core``     — :class:`Workspace`, :class:`WorkspaceMember`,
                  :class:`WorkspaceCatalogPin` + ``WORKSPACE_ROLES`` /
                  ``WORKSPACE_PIN_MODES`` constants.
* ``_repos``    — :class:`WorkspaceRepo`, :class:`WorkspaceRepoSecret`
                  + the three ``WORKSPACE_REPO_*`` constants.
* ``_api_keys`` — :class:`ApiKey` (workspace-scoped API keys).
"""

from __future__ import annotations

from pointlessql.models.workspace._api_keys import ApiKey
from pointlessql.models.workspace._core import (
    WORKSPACE_PIN_MODES,
    WORKSPACE_ROLES,
    Workspace,
    WorkspaceCatalogPin,
    WorkspaceMember,
)
from pointlessql.models.workspace._repos import (
    WORKSPACE_REPO_PROVIDER_KINDS,
    WORKSPACE_REPO_SECRET_KINDS,
    WORKSPACE_REPO_SYNC_STATES,
    WorkspaceRepo,
    WorkspaceRepoSecret,
)
from pointlessql.models.workspace._sql_statements import (
    SQL_STATEMENT_STATES,
    SqlStatement,
)

__all__ = [
    "SQL_STATEMENT_STATES",
    "WORKSPACE_PIN_MODES",
    "WORKSPACE_REPO_PROVIDER_KINDS",
    "WORKSPACE_REPO_SECRET_KINDS",
    "WORKSPACE_REPO_SYNC_STATES",
    "WORKSPACE_ROLES",
    "ApiKey",
    "SqlStatement",
    "Workspace",
    "WorkspaceCatalogPin",
    "WorkspaceMember",
    "WorkspaceRepo",
    "WorkspaceRepoSecret",
]
