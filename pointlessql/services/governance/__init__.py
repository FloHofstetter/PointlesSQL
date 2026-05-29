"""Computational-governance service layer — policy, masking, control-port.

Re-exports the per-product policy resolver, the column-classification
CRUD, the masking sidecar, the right-to-be-forgotten primitives, the
compliance scanner, and the aggregate-ownership heuristic so callers do
``from pointlessql.services import governance`` without reaching into
the private sub-modules.
"""

from __future__ import annotations

from pointlessql.services.governance._classifications import (
    DEFAULT_STRATEGY_BY_CLASS,
    add_classification,
    classifications_for_schema,
    delete_classification,
    effective_strategy,
    list_classifications,
)
from pointlessql.services.governance._compliance import (
    COMPLIANCE_VIOLATION_ACTION,
    retention_findings,
    scan_workspace,
    unclassified_pii_findings,
)
from pointlessql.services.governance._forget import (
    execute_forget,
    list_forget_requests,
    propose_forget,
)
from pointlessql.services.governance._masking import (
    mask_cell,
    mask_dataframe,
    mask_sql_rows,
    viewer_sees_clear,
)
from pointlessql.services.governance._ownership import suggest_domain_for_aggregate
from pointlessql.services.governance._policy import (
    POLICY_FIELDS,
    get_effective_policy,
    get_product_policy,
    get_workspace_policy,
    set_product_policy,
    set_workspace_policy,
)

__all__ = [
    "COMPLIANCE_VIOLATION_ACTION",
    "DEFAULT_STRATEGY_BY_CLASS",
    "POLICY_FIELDS",
    "add_classification",
    "classifications_for_schema",
    "delete_classification",
    "effective_strategy",
    "execute_forget",
    "get_effective_policy",
    "get_product_policy",
    "get_workspace_policy",
    "list_classifications",
    "list_forget_requests",
    "mask_cell",
    "mask_dataframe",
    "mask_sql_rows",
    "propose_forget",
    "retention_findings",
    "scan_workspace",
    "set_product_policy",
    "set_workspace_policy",
    "suggest_domain_for_aggregate",
    "unclassified_pii_findings",
    "viewer_sees_clear",
]
