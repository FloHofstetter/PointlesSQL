"""Read-only canvas inspection routes: validate, ghost-diff, preview.

None of these write or bump a version — they compile / schema-flow the
document handed in the request body so the editor can surface schema
errors, wire colours, an agent-proposal overlay, or preview rows against
dirty unsaved state.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.canvas._helpers import (
    load_dp,
    raw_soyuz_client,
    resolve_dp_refs,
    seed_schemas_for_doc,
)
from pointlessql.api.data_products_routes.canvas._schemas import (
    CanvasGhostDiffRequest,
    CanvasGhostDiffResponse,
    CanvasPreviewRequest,
    CanvasPreviewResponse,
    CanvasValidateRequest,
    CanvasValidateResponse,
)
from pointlessql.api.dependencies import require_user
from pointlessql.services.dp_canvas import CanvasDoc, load_latest_graph, validate_schema_flow
from pointlessql.services.dp_canvas._diff import diff_docs
from pointlessql.services.dp_canvas._edge_types import categorize_pin_schema
from pointlessql.services.dp_canvas._preview import PreviewResult, preview_until

router = APIRouter(prefix="/api/dp", tags=["data-products-canvas"])


@router.post("/{dp_id}/canvas/validate", response_model=CanvasValidateResponse)
def validate_canvas(
    dp_id: int, body: CanvasValidateRequest, request: Request
) -> CanvasValidateResponse:
    """Run schema-flow validation against *body.document*.

    Looks up each ``InputPort`` block's ``table_fqn`` in UC so the
    propagation has real upstream schemas to chain against.
    """
    require_user(request)
    load_dp(request, dp_id)
    client = raw_soyuz_client(request)
    resolved_doc = resolve_dp_refs(request, body.document)
    seeds, seed_errors = seed_schemas_for_doc(resolved_doc, client)
    pin_schemas, flow_errors = validate_schema_flow(resolved_doc, seed_schemas=seeds)
    wire_schemas = {f"{node_id}:{pin}": schema for (node_id, pin), schema in pin_schemas.items()}
    edge_categories: dict[str, str] = {}
    for edge in resolved_doc.edges:
        source_schema = pin_schemas.get((edge.source_node_id, edge.source_pin))
        key = f"{edge.source_node_id}:{edge.source_pin}->{edge.target_node_id}:{edge.target_pin}"
        edge_categories[key] = categorize_pin_schema(source_schema)
    return CanvasValidateResponse(
        pin_schemas=wire_schemas,
        errors=[*seed_errors, *flow_errors],
        edge_categories=edge_categories,
    )


@router.post("/{dp_id}/canvas/ghost-diff", response_model=CanvasGhostDiffResponse)
def ghost_diff_canvas(
    dp_id: int, body: CanvasGhostDiffRequest, request: Request
) -> CanvasGhostDiffResponse:
    """Diff a proposed canvas against the saved one and validate it.

    Read-only: no save, no version bump.  Powers the agent-proposal ghost
    overlay — the editor paints the delta and surfaces the proposal's
    schema errors so a human can accept or reject it before committing.
    """
    require_user(request)
    load_dp(request, dp_id)
    factory = request.app.state.session_factory
    result = load_latest_graph(factory, data_product_id=dp_id)
    current = result[0] if result else CanvasDoc(nodes=[], edges=[])
    proposed = resolve_dp_refs(request, body.proposed_document)
    client = raw_soyuz_client(request)
    seeds, seed_errors = seed_schemas_for_doc(proposed, client)
    pin_schemas, flow_errors = validate_schema_flow(proposed, seed_schemas=seeds)
    wire_schemas = {f"{node_id}:{pin}": schema for (node_id, pin), schema in pin_schemas.items()}
    edge_categories: dict[str, str] = {}
    for edge in proposed.edges:
        source_schema = pin_schemas.get((edge.source_node_id, edge.source_pin))
        key = f"{edge.source_node_id}:{edge.source_pin}->{edge.target_node_id}:{edge.target_pin}"
        edge_categories[key] = categorize_pin_schema(source_schema)
    return CanvasGhostDiffResponse(
        diff=diff_docs(current, proposed),
        pin_schemas=wire_schemas,
        errors=[*seed_errors, *flow_errors],
        edge_categories=edge_categories,
    )


@router.post("/{dp_id}/canvas/preview", response_model=CanvasPreviewResponse)
def preview_canvas(
    dp_id: int,
    body: CanvasPreviewRequest,
    request: Request,
    bust: int = 0,
) -> CanvasPreviewResponse:
    """Compile the canvas slice ending at *upto_node_id* and return preview rows.

    Read-only: the request is rejected for ``OutputPort`` nodes (use
    materialise for that path), no Delta write happens, and the graph
    version is *not* bumped — the document is consumed verbatim from
    the request body so the editor can preview dirty unsaved state.

    The result is memoised in an in-process LRU keyed on the upstream
    slice's content hash so re-preview of the same node returns
    instantly.  Pass ``?bust=1`` to drop the cache for this DP before
    executing (used when an upstream Delta was rewritten out-of-band).
    """
    require_user(request)
    load_dp(request, dp_id)
    if bust:
        from pointlessql.services.dp_canvas import _preview_cache

        _preview_cache.clear_for_dp(dp_id)
    client = raw_soyuz_client(request)
    resolved_doc = resolve_dp_refs(request, body.document)
    seeds, _seed_errors = seed_schemas_for_doc(resolved_doc, client)
    result: PreviewResult = preview_until(
        resolved_doc,
        upto_node_id=body.upto_node_id,
        limit=body.limit,
        soyuz_client=client,
        upstream_seeds=seeds,
        cache_dp_id=dp_id,
    )
    return CanvasPreviewResponse(
        columns=list(result.columns),
        rows=[list(row) for row in result.rows],
        truncated=result.truncated,
        row_count=result.row_count,
        cache_hit=result.cache_hit,
        sql=result.sql,
        errors=list(result.errors),
    )
