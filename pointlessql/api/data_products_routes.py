"""JSON API for the data-product browse + diff surface (Phase 50.2).

Five endpoints:

* ``GET /api/data-products`` — list every cached product in the
  active workspace.
* ``GET /api/data-products/{catalog}/{schema}`` — per-product
  detail: tables, compliance summary, recent contract events.
* ``GET /api/data-products/{catalog}/{schema}/lineage`` — minimal
  cytoscape graph of the product's tables + 1-hop neighbours via
  ``lineage_row_edges`` (reuses the existing graph shape used by
  ``/api/models/.../lineage``).
* ``GET /api/data-products/{catalog}/{schema}/diff`` — live
  diff of yaml contract vs. on-disk Delta schema; reads
  ``DeltaTable.schema()`` per declared table.
* ``POST /api/data-products/reload`` — admin trigger to re-load
  every yaml under ``Settings.data_products.yaml_search_paths``.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_uc_client,
    require_admin,
)
from pointlessql.data_products import (
    DataProductContract,
    diff_contract_against_delta_table,
    load_contracts_from_paths,
)
from pointlessql.data_products._diff import ContractDiffResult
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import LineageRowEdge
from pointlessql.models.auth import User
from pointlessql.models.data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.settings import Settings

router = APIRouter(tags=["data-products"])


def _serialise_product(
    row: DataProduct,
    *,
    steward_email: str | None,
    steward_display_name: str | None,
) -> dict[str, Any]:
    """Render one cache row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "catalog": row.catalog_name,
        "schema": row.schema_name,
        "ref": f"{row.catalog_name}.{row.schema_name}",
        "version": row.version,
        "description": row.description,
        "sla_minutes": row.sla_minutes,
        "steward": {
            "user_id": row.steward_user_id,
            "email": steward_email,
            "display_name": steward_display_name,
        },
        "contract_yaml_hash": row.contract_yaml_hash,
        "last_loaded_at": row.last_loaded_at.isoformat(),
        "last_alerted_at": (
            row.last_alerted_at.isoformat() if row.last_alerted_at else None
        ),
    }


@router.get("/api/data-products")
async def list_data_products(request: Request) -> dict[str, Any]:
    """Return every cached data product in the active workspace.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"workspace_id": int, "data_products": [...]}`` ordered by
        catalog/schema name.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    items: list[dict[str, Any]] = []
    with factory() as session:
        rows = (
            session.execute(
                select(DataProduct)
                .where(DataProduct.workspace_id == workspace_id)
                .order_by(DataProduct.catalog_name, DataProduct.schema_name)
            )
            .scalars()
            .all()
        )
        steward_ids = [r.steward_user_id for r in rows if r.steward_user_id is not None]
        steward_map: dict[int, tuple[str, str]] = {}
        if steward_ids:
            users = (
                session.execute(select(User).where(User.id.in_(steward_ids)))
                .scalars()
                .all()
            )
            steward_map = {u.id: (u.email, u.display_name) for u in users}

        for row in rows:
            email, display = (
                steward_map.get(row.steward_user_id, (None, None))
                if row.steward_user_id is not None
                else (None, None)
            )
            items.append(
                _serialise_product(row, steward_email=email, steward_display_name=display)
            )

    return {"workspace_id": workspace_id, "data_products": items}


def _load_one(
    session_factory: Any,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> tuple[DataProduct, DataProductContract, str | None, str | None]:
    """Look up the product + parsed contract; raise 404 when missing."""
    with session_factory() as session:
        row = session.execute(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFoundError(
                f"data product {catalog}.{schema!r} not found"
            )
        contract = DataProductContract.model_validate(json.loads(row.contract_json))
        if row.steward_user_id is not None:
            user = session.get(User, row.steward_user_id)
            steward_email = user.email if user else None
            steward_display = user.display_name if user else None
        else:
            steward_email = None
            steward_display = None
        return row, contract, steward_email, steward_display


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
    row, contract, steward_email, steward_display = _load_one(
        factory, workspace_id, catalog, schema
    )

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

    tables_payload = [
        {
            "name": t.name,
            "primary_key": list(t.primary_key) if t.primary_key else [],
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "description": c.description,
                }
                for c in t.columns
            ],
        }
        for t in contract.tables
    ]

    return {
        "product": _serialise_product(
            row,
            steward_email=steward_email,
            steward_display_name=steward_display,
        ),
        "name": contract.name,
        "tables": tables_payload,
        "recent_events": events_payload,
    }


def _diff_to_payload(
    table_name: str, diff: ContractDiffResult | str
) -> dict[str, Any]:
    """Render a diff result (or error string) as a JSON-friendly dict."""
    if isinstance(diff, str):
        return {"name": table_name, "error": diff}
    return {"name": table_name, **diff.as_dict()}


@router.get("/api/data-products/{catalog}/{schema}/diff")
async def diff_data_product(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Live-diff every declared table's contract against on-disk Delta schema.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"product_ref": "cat.sch", "tables": [{name, ...diff} | {error}]}``
        per declared table.  Tables not on disk surface ``error`` rather
        than failing the whole call.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    _row, contract, _email, _display = _load_one(
        factory, workspace_id, catalog, schema
    )
    uc = get_uc_client(request)

    table_diffs: list[dict[str, Any]] = []
    for table_contract in contract.tables:
        full_name = f"{catalog}.{schema}.{table_contract.name}"
        try:
            uc_table = await uc.get_table(full_name)
        except Exception:  # noqa: BLE001 — UC unreachable / 404 / etc.
            # bare-broad-ok: live-diff degrades to per-table error
            # surface when UC misses; a single bad table must not
            # break the page render.
            table_diffs.append(_diff_to_payload(table_contract.name, "table not in UC"))
            continue
        storage = uc_table.get("storage_location")
        if not isinstance(storage, str) or not storage:
            table_diffs.append(_diff_to_payload(table_contract.name, "no storage_location"))
            continue
        try:
            diff_result = diff_contract_against_delta_table(table_contract, storage)
        except Exception as exc:  # noqa: BLE001 — Delta read failure
            # bare-broad-ok: same reasoning as the UC branch above —
            # a single Delta unreadable surfaces per-table without
            # blocking the rest.
            table_diffs.append(_diff_to_payload(table_contract.name, f"delta read failed: {exc!r}"))
            continue
        table_diffs.append(_diff_to_payload(table_contract.name, diff_result))

    return {"product_ref": f"{catalog}.{schema}", "tables": table_diffs}


@router.get("/api/data-products/{catalog}/{schema}/lineage")
async def get_data_product_lineage(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return a minimal cytoscape graph of the product's tables + neighbours.

    Each declared table becomes a node; one-hop producers (via
    ``lineage_row_edges.source_table``) and consumers (via
    ``target_table``) are included so the steward sees what flows
    into and out of the product.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"nodes": [...], "edges": [...]}`` in the cytoscape data
        shape (same as ``/api/models/.../lineage``).
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    _row, contract, _email, _display = _load_one(
        factory, workspace_id, catalog, schema
    )

    table_fqns = {f"{catalog}.{schema}.{t.name}" for t in contract.tables}
    nodes: dict[str, dict[str, Any]] = {
        fqn: {
            "data": {
                "id": fqn,
                "label": fqn.split(".")[-1],
                "kind": "product_table",
            }
        }
        for fqn in table_fqns
    }
    edges: list[dict[str, Any]] = []

    if not table_fqns:
        return {"nodes": [], "edges": []}

    with factory() as session:
        # Producers (rows where target is one of ours).
        inbound = (
            session.execute(
                select(LineageRowEdge.source_table, LineageRowEdge.target_table)
                .where(LineageRowEdge.target_table.in_(table_fqns))
                .distinct()
            )
            .all()
        )
        for src, tgt in inbound:
            if src and src not in nodes:
                nodes[src] = {
                    "data": {"id": src, "label": src.split(".")[-1], "kind": "producer"}
                }
            edges.append(
                {"data": {"source": src, "target": tgt, "kind": "produces"}}
            )

        # Consumers (rows where source is one of ours).
        outbound = (
            session.execute(
                select(LineageRowEdge.source_table, LineageRowEdge.target_table)
                .where(LineageRowEdge.source_table.in_(table_fqns))
                .distinct()
            )
            .all()
        )
        for src, tgt in outbound:
            if tgt and tgt not in nodes:
                nodes[tgt] = {
                    "data": {"id": tgt, "label": tgt.split(".")[-1], "kind": "consumer"}
                }
            edges.append(
                {"data": {"source": src, "target": tgt, "kind": "consumed_by"}}
            )

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }


@router.post("/api/data-products/reload")
async def reload_data_products(request: Request) -> dict[str, Any]:
    """Reload every yaml under ``Settings.data_products.yaml_search_paths``.

    Admin-gated.  Re-runs :func:`load_contracts_from_paths` for the
    current workspace; failures on individual yamls propagate as
    ``DataProductYamlInvalid`` and surface as a 400 response.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"loaded": int, "paths": [...]}`` with the count of
        contracts UPSERTed and the resolved yaml paths.

    Raises:
        HTTPException: When ``yaml_search_paths`` is empty
            (admins must configure the search roots before calling
            this endpoint).
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings: Settings = request.app.state.settings
    paths = settings.data_products.yaml_search_paths
    if not paths:
        # bare-http-ok: pure-config error; the operator hasn't set the
        # search paths yet so there's no domain exception to map to.
        raise HTTPException(
            status_code=400,
            detail=(
                "data_products.yaml_search_paths is empty; set "
                "POINTLESSQL_DATA_PRODUCTS_YAML_SEARCH_PATHS to a "
                "comma-separated list of directories or yaml files."
            ),
        )

    contracts = load_contracts_from_paths(
        list(paths),
        factory=factory,
        workspace_id=workspace_id,
        now=datetime.datetime.now(datetime.UTC),
    )
    return {
        "loaded": len(contracts),
        "paths": [str(p) for p in paths],
    }
