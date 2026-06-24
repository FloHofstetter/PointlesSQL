"""Per-request dependency-injection helpers for the API layer.

Every route in the FastAPI app reaches for one of these to recover
the principal-forwarded :class:`UnityCatalogClient`
(``get_uc_client``), the authenticated :class:`UserInfo`
(``get_user``), the admin gate (``require_admin``), or the client
IP for audit rows (``client_ip``).

The helpers are grouped into focused sub-modules — pagination,
principal/client/user, role gates, workspace context, and
template/HTMX rendering — and re-exported here so the historical
``from pointlessql.api.dependencies import X`` import path keeps
resolving unchanged across every route module.
"""

from __future__ import annotations

from ._pagination import PaginationParams, pagination
from ._principal import (
    client_ip,
    effective_principal,
    get_optional_user,
    get_uc_client,
    get_user,
    uc_client_for_principal,
)
from ._rendering import (
    get_templates,
    is_htmx_boosted,
    is_htmx_partial,
    is_htmx_request,
    render_page_with_fallback,
    wants_json,
)
from ._roles import (
    admin_uc,
    require_admin,
    require_analyst,
    require_auditor,
    require_lineage_inbound,
    require_role,
    require_sql_execute,
    require_supervisor,
    require_user,
)
from ._workspace import (
    current_workspace,
    current_workspace_id,
    get_authoring_product,
    require_workspace_admin,
)

__all__ = [
    "PaginationParams",
    "admin_uc",
    "client_ip",
    "current_workspace",
    "current_workspace_id",
    "effective_principal",
    "get_authoring_product",
    "get_optional_user",
    "get_templates",
    "get_uc_client",
    "get_user",
    "is_htmx_boosted",
    "is_htmx_partial",
    "is_htmx_request",
    "pagination",
    "render_page_with_fallback",
    "require_admin",
    "require_analyst",
    "require_auditor",
    "require_lineage_inbound",
    "require_role",
    "require_sql_execute",
    "require_supervisor",
    "require_user",
    "require_workspace_admin",
    "uc_client_for_principal",
    "wants_json",
]
