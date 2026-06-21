"""Computational policy-as-code engine + CRUD + hook integration.

Public surface for the Cedar-backed policy module subsystem.  Routes
use :mod:`_crud` for module lifecycle and :mod:`_engine` for ad-hoc
test / dry-run evaluations.  Hook integration via :mod:`_bootstrap`
wires the engine into the PQL hook registry once at boot.
"""

from __future__ import annotations

from pointlessql.services.policy_as_code._audit import (
    persist_decision,
)
from pointlessql.services.policy_as_code._bootstrap import (
    register_cedar_hooks,
)
from pointlessql.services.policy_as_code._crud import (
    create_module,
    delete_module,
    get_module,
    link_modules_to_product,
    link_modules_to_workspace,
    list_decisions,
    list_modules,
    set_module_enabled,
    update_module,
)
from pointlessql.services.policy_as_code._engine import (
    CEDAR_DEFAULT_DENY_REASON,
    Decision,
    cedar_evaluate,
    invalidate_cache,
)
from pointlessql.services.policy_as_code._guardrails import (
    GUARDRAIL_CONTENT_FLAGS,
    evaluate_agent_action,
)
from pointlessql.services.policy_as_code._loader import (
    load_active_modules_for_workspace,
    load_linked_modules_for_product,
)
from pointlessql.services.policy_as_code._translator import (
    build_resource_id,
    cedar_action,
    principal_uid,
)

__all__ = [
    "CEDAR_DEFAULT_DENY_REASON",
    "GUARDRAIL_CONTENT_FLAGS",
    "Decision",
    "build_resource_id",
    "cedar_action",
    "cedar_evaluate",
    "create_module",
    "evaluate_agent_action",
    "delete_module",
    "get_module",
    "invalidate_cache",
    "link_modules_to_product",
    "link_modules_to_workspace",
    "list_decisions",
    "list_modules",
    "load_active_modules_for_workspace",
    "load_linked_modules_for_product",
    "persist_decision",
    "principal_uid",
    "register_cedar_hooks",
    "set_module_enabled",
    "update_module",
]
