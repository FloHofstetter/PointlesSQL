"""``/admin/*`` route surface, split per concern.

This package consolidates the eight flat ``admin_*_routes.py``
sibling modules that used to live at ``pointlessql/api/`` root.
The combined router is mounted by ``api.main`` exactly once via
``router = APIRouter(); router.include_router(...)`` in this
``__init__.py`` — callers no longer juggle eight individual router
references.

Layout (all per-concern, no internal coupling beyond shared
dependency injection):

* ``console``           — admin landing + system info.
* ``workspaces``        — workspace CRUD + group mappings.
* ``domains``           — data-mesh domain CRUD + members.
* ``workspace_pins``    — pinned-workspace bookmark management.
* ``repos``             — workspace-repo registration + sync.
* ``cdf_tail``          — Change Data Feed tail viewer.
* ``expected_producers`` — UC-mutation expected-producer registry.
* ``external_writes``   — external-write audit configuration.
* ``api_keys``          — API key issuance + revocation.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.admin.agent_gateway import router as _agent_gateway_router
from pointlessql.api.admin.agent_guardrails import router as _agent_guardrails_router
from pointlessql.api.admin.ai_gateway import router as _ai_gateway_router
from pointlessql.api.admin.api_keys import router as _api_keys_router
from pointlessql.api.admin.app_spaces import router as _app_spaces_router
from pointlessql.api.admin.cdf_tail import router as _cdf_tail_router
from pointlessql.api.admin.coedit_bus import router as _coedit_bus_router
from pointlessql.api.admin.console import router as _console_router
from pointlessql.api.admin.cost_routes import router as _cost_routes_router
from pointlessql.api.admin.domains import router as _domains_router
from pointlessql.api.admin.expected_producers import (
    router as _expected_producers_router,
)
from pointlessql.api.admin.external_writes import router as _external_writes_router
from pointlessql.api.admin.genie_connectors import router as _genie_connectors_router
from pointlessql.api.admin.glossary import router as _glossary_router
from pointlessql.api.admin.governance import router as _admin_governance_router
from pointlessql.api.admin.governance_hub import router as _governance_hub_router
from pointlessql.api.admin.ingest_sources import (
    router as _admin_ingest_sources_router,
)
from pointlessql.api.admin.lens_providers import router as _lens_providers_router
from pointlessql.api.admin.mcp_services import router as _mcp_services_router
from pointlessql.api.admin.mesh_entities import router as _mesh_entities_router
from pointlessql.api.admin.optimization import router as _optimization_router
from pointlessql.api.admin.policy_modules import router as _policy_modules_router
from pointlessql.api.admin.repos import router as _repos_router
from pointlessql.api.admin.secrets import router as _secrets_router
from pointlessql.api.admin.users import router as _users_router
from pointlessql.api.admin.workspace_pins import router as _workspace_pins_router
from pointlessql.api.admin.workspaces import router as _workspaces_router

router = APIRouter()
router.include_router(_console_router)
router.include_router(_users_router)
router.include_router(_workspaces_router)
router.include_router(_domains_router)
router.include_router(_glossary_router)
router.include_router(_admin_governance_router)
router.include_router(_governance_hub_router)
router.include_router(_mesh_entities_router)
router.include_router(_optimization_router)
router.include_router(_workspace_pins_router)
router.include_router(_repos_router)
router.include_router(_cdf_tail_router)
router.include_router(_expected_producers_router)
router.include_router(_external_writes_router)
router.include_router(_api_keys_router)
router.include_router(_secrets_router)
router.include_router(_lens_providers_router)
router.include_router(_admin_ingest_sources_router)
router.include_router(_coedit_bus_router)
router.include_router(_policy_modules_router)
router.include_router(_agent_guardrails_router)
router.include_router(_agent_gateway_router)
router.include_router(_app_spaces_router)
router.include_router(_genie_connectors_router)
router.include_router(_ai_gateway_router)
router.include_router(_mcp_services_router)
router.include_router(_cost_routes_router)

__all__ = ["router"]
