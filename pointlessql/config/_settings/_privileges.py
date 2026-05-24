"""Feature-flag scaffolding for the privilege subsystem.

introduces ``enforce_global_privilege_gate`` as the
opt-in switch for future per-action privilege gates.  The codebase
currently uses seven hand-rolled ``require_*`` gates for static role
checks (``require_admin`` / ``require_supervisor`` /
``require_auditor`` / ``require_analyst`` / ``require_sql_execute``
/ ``require_lineage_inbound`` / ``require_workspace_admin``).  Future
work may add a uniform ``require_privilege(privilege, securable_type)``
dep that consults
:func:`pointlessql.services.authorization.check_privilege` at request
time for per-securable USE_CATALOG / SELECT / MODIFY gates.

This setting gates that future plumbing — flipping it ON has no
effect until the privilege dep itself lands.  Default ``False``
preserves current behaviour for every existing route.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PrivilegeSettings(BaseSettings):
    """Feature flags for the privilege-gate subsystem."""

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_PRIVILEGE_")

    enforce_global_privilege_gate: bool = Field(
        default=False,
        description=(
            "When True, routes opt into the future require_privilege() "
            "dep which consults services/authorization.check_privilege "
            "at request time for per-securable USE_CATALOG / SELECT / "
            "MODIFY gates.  Default False — current routes keep using "
            "inline check_privilege() calls."
        ),
    )
