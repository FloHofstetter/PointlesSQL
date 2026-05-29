"""``GET /api/data-products/{catalog}/{schema}`` — per-product detail."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import (
    load_one,
    resolve_domain,
    serialise_product,
    serialise_table_contracts,
)
from pointlessql.api.dependencies import current_workspace_id
from pointlessql.models.catalog._data_products import DataProductContractEvent
from pointlessql.services import glossary as glossary_service
from pointlessql.services.data_products import compute_badges_for_dp

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}")
async def get_data_product(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return one product with table contracts and recent compliance events.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        Detail dict with ``product``, ``tables`` (per-table contract
        summary), and ``recent_events`` (last 50 compliance rows).
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, contract, steward_email, steward_display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        events = (
            session.execute(
                select(DataProductContractEvent)
                .where(DataProductContractEvent.data_product_id == row.id)
                .order_by(DataProductContractEvent.created_at.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )
        badges = compute_badges_for_dp(session, workspace_id=workspace_id, dp=row)
        events_payload = [
            {
                "id": e.id,
                "agent_run_operation_id": e.agent_run_operation_id,
                "outcome": e.outcome,
                "details": json.loads(e.details_json),
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]

    tables_payload = serialise_table_contracts(contract)
    # Attach glossary term labels per column so the Contract tab can
    # badge each column with the shared vocabulary bound to it.
    term_map = glossary_service.terms_for_schema(
        factory, workspace_id=workspace_id, catalog=catalog, schema=schema
    )
    for table in tables_payload:
        for column in table["columns"]:
            column["glossary_terms"] = term_map.get(f"{table['name']}.{column['name']}", [])

    return {
        "product": serialise_product(
            row,
            steward_email=steward_email,
            steward_display_name=steward_display,
            domain=resolve_domain(factory, row.domain_id),
        ),
        "name": contract.name,
        "tables": tables_payload,
        "recent_events": events_payload,
        "badges": badges,
    }
