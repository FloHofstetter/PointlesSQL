"""Discovery contract endpoint — the product's machine-readable port.

``GET /api/data-products/{catalog}/{schema}/discovery`` returns a
standardized, stable self-description: identity + a durable URI, the
declared semantic model + example query, output/input ports, table
contracts, SLOs, and the latest self-generated statistics.  It is the
single entry point an external tool or a supervised agent reads to
*understand* and *address* a product.

The URI is ``urn:pointlessql:product:{workspace_slug}:{catalog}:{schema}``.
The workspace slug is immutable and install-portable (unlike the
numeric ``data_products.id``); the URN keys on the product's actual
identity triple ``(workspace, catalog, schema)``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes._shared import (
    load_one,
    resolve_domain,
    serialise_product,
    serialise_table_contracts,
)
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.config import Settings
from pointlessql.models import Workspace
from pointlessql.services import data_product_ports as ports_service
from pointlessql.services import data_product_semantic as semantic_service
from pointlessql.services import governance as governance_service
from pointlessql.services import mesh as mesh_service
from pointlessql.services import slo as slo_service
from pointlessql.services.data_product_stats import read_latest_statistics

router = APIRouter(tags=["data-products"])


def _workspace_slug(factory: Any, workspace_id: int) -> str:
    """Return the workspace slug, falling back to the id as a string."""
    with factory() as session:
        ws = session.get(Workspace, workspace_id)
        return ws.slug if ws is not None else str(workspace_id)


@router.get("/api/data-products/{catalog}/{schema}/discovery")
async def get_discovery_contract(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the product's machine-readable discovery contract.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        The discovery envelope (see module docstring).  Aggregate
        collections are empty when the owner has not declared them
        yet — the endpoint never 404s except when the product itself
        is missing.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, contract, steward_email, steward_display = load_one(factory, workspace_id, catalog, schema)

    slug = _workspace_slug(factory, workspace_id)
    uri = f"urn:pointlessql:product:{slug}:{catalog}:{schema}"

    output_ports = ports_service.list_output_ports(factory, data_product_id=row.id)
    input_ports = ports_service.list_input_ports(factory, data_product_id=row.id)
    concepts = semantic_service.list_concepts(factory, data_product_id=row.id)
    statistics = read_latest_statistics(factory, data_product_id=row.id)
    effective_policy = governance_service.get_effective_policy(
        factory, data_product_id=row.id, workspace_id=workspace_id
    )
    classifications = governance_service.list_classifications(factory, data_product_id=row.id)
    slos = slo_service.list_slos(factory, data_product_id=row.id)
    entity_index = mesh_service.entities_for_schema(factory, catalog=catalog, schema=schema)
    settings: Settings = request.app.state.settings

    base = f"/api/data-products/{catalog}/{schema}"
    return {
        "discovery_version": "1.0",
        "uri": uri,
        "identity": serialise_product(
            row,
            steward_email=steward_email,
            steward_display_name=steward_display,
            domain=resolve_domain(factory, row.domain_id),
        ),
        "semantics": {
            "model": [
                {"concept": c.concept, "description": c.description, "maps_to": c.maps_to}
                for c in concepts
            ],
            "sample_sql": row.sample_sql,
        },
        "output_ports": [
            {
                "name": p.name,
                "kind": p.kind,
                "format": p.format,
                "location": p.location,
                "description": p.description,
            }
            for p in output_ports
        ],
        "input_ports": [
            {
                "name": p.name,
                "kind": p.kind,
                "source_ref": p.source_ref,
                "description": p.description,
            }
            for p in input_ports
        ],
        "tables": serialise_table_contracts(contract),
        "policies": {
            "retention_days": effective_policy["retention_days"]["value"],
            "encryption_class": effective_policy["encryption_class"]["value"],
            "residency_region": effective_policy["residency_region"]["value"],
            "consent_required": bool(effective_policy["consent_required"]["value"]),
            "classifications": [
                {
                    "table": c.table_name,
                    "column": c.column_name,
                    "classification": c.classification,
                    "masking_strategy": governance_service.effective_strategy(
                        c.classification, c.masking_strategy
                    ),
                }
                for c in classifications
            ],
        },
        "slos": {
            "sla_minutes": row.sla_minutes,
            "additional": [
                {
                    "slo_kind": s.slo_kind,
                    "table": s.table_name,
                    "target_value": s.target_value,
                    "comparator": s.comparator,
                    "unit": s.unit,
                    "enabled": s.enabled,
                }
                for s in slos
            ],
        },
        "entities": [
            {"table": table, "column": column, "entities": slugs}
            for (table, column), slugs in sorted(entity_index.items())
        ],
        "bitemporal": {
            "inject_processing_time": settings.bitemporal.inject_processing_time,
            "processing_time_column": settings.bitemporal.processing_time_column,
            "event_time_column": settings.bitemporal.event_time_column,
        },
        "statistics": statistics,
        "links": {
            "self": base,
            "passport": f"{base}/passport",
            "lineage": f"{base}/lineage",
            "mesh": f"{base}/mesh-graph",
        },
    }
