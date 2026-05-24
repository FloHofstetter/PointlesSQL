"""GET /api/lens/provenance — unified row+column+value lineage trace.

Direct browser invocation surface for the Sprint 65.1 provenance
service.  The same logic backs the Lens MCP / chat ``provenance``
tool.

Workspace isolation: the table_fqn is not workspace-checked here
because UC tables are not workspace-namespaced; lineage rows always
carry the writing op's workspace_id implicitly via the FK chain, and
``require_analyst`` already gates the route.  Cross-workspace
information leak is theoretically possible if an analyst guesses a
``table_fqn`` they should not see, but UC permission checks at the
catalog/schema/table layer (existing today) catch that on the
follow-up data read.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pointlessql.api.dependencies import require_analyst
from pointlessql.services.lens.provenance import (
    DEFAULT_MAX_HOPS,
    MAX_ALLOWED_HOPS,
    ProvenanceQuery,
    ProvenanceTrace,
    provenance,
)

router = APIRouter()


@router.get(
    "/provenance",
    response_model=ProvenanceTrace,
    dependencies=[Depends(require_analyst)],
)
def provenance_endpoint(
    request: Request,
    table_fqn: str,
    row_id: str | None = None,
    column: str | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> ProvenanceTrace:
    """Return a unified provenance trace for the requested scope.

    Three modes resolved by which optional params are populated:

    * ``table_fqn`` only          → table-scope (metadata only)
    * ``+ column``                → column-trace
    * ``+ row_id``                → row walkback
    * ``+ row_id + column``       → row walkback + value changes

    Args:
        request: Incoming FastAPI request (for app.state.session_factory).
        table_fqn: Fully-qualified UC table name.
        row_id: Optional ``_lineage_row_id`` of the row to trace.
        column: Optional column name to narrow the trace.
        max_hops: Walkback depth limit, capped at
            :data:`MAX_ALLOWED_HOPS`.

    Returns:
        :class:`ProvenanceTrace` with mode-specific payload sections
        populated.
    """
    capped = min(max(max_hops, 1), MAX_ALLOWED_HOPS)
    query = ProvenanceQuery(
        table_fqn=table_fqn,
        row_id=row_id,
        column=column,
        max_hops=capped,
    )
    factory = request.app.state.session_factory
    return provenance(factory, query)
