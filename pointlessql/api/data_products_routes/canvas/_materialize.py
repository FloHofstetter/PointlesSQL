"""Materialise route: compile + execute the canvas, write Delta, upsert ports."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.canvas._helpers import (
    load_dp,
    raw_soyuz_client,
    require_dp_write,
    resolve_dp_refs,
)
from pointlessql.api.data_products_routes.canvas._schemas import (
    CanvasMaterializeRequest,
    CanvasMaterializeResponse,
    CanvasMaterializeSink,
)
from pointlessql.api.dependencies import get_user, require_user
from pointlessql.exceptions import ValidationError
from pointlessql.services.dp_canvas import (
    MultiExecuteResult,
    execute_canvas,
    load_latest_graph,
)

router = APIRouter(prefix="/api/dp", tags=["data-products-canvas"])


@router.post("/{dp_id}/canvas/materialize", response_model=CanvasMaterializeResponse)
def materialize_canvas(
    dp_id: int, body: CanvasMaterializeRequest, request: Request
) -> CanvasMaterializeResponse:
    """Compile + execute the canvas; write Delta + upsert the output port."""
    require_user(request)
    user = get_user(request)
    row = load_dp(request, dp_id)
    require_dp_write(user, row)
    factory = request.app.state.session_factory
    actor_id = int(user["id"]) if user["id"] > 0 else None

    if body.document is not None:
        if body.expected_base_version is not None:
            existing = load_latest_graph(factory, data_product_id=dp_id)
            existing_version = existing[1] if existing else 0
            if existing_version != body.expected_base_version:
                raise ValidationError(
                    f"canvas materialise conflict: caller expected "
                    f"v{body.expected_base_version} but latest is v{existing_version}"
                )
        # execute_canvas stamps the single authoritative graph version
        # after a successful run, so we deliberately do not pre-save the
        # document here: pre-saving double-bumps the version on success
        # and — worse — leaves a bumped version behind on a *failed* run,
        # which desyncs the client and blocks the retry with a phantom
        # version conflict.
        doc = resolve_dp_refs(request, body.document)
    else:
        loaded = load_latest_graph(factory, data_product_id=dp_id)
        if loaded is None:
            raise ValidationError(f"data product {dp_id} has no saved canvas to materialise")
        doc = loaded[0]

    client = raw_soyuz_client(request)
    result: MultiExecuteResult = execute_canvas(
        factory,
        doc=doc,
        data_product_id=dp_id,
        soyuz_client=client,
        actor_user_id=actor_id,
    )
    return CanvasMaterializeResponse(
        sinks=[
            CanvasMaterializeSink(
                port_name=sink.port_name,
                target_fqn=sink.target_fqn,
                rows_written=sink.rows_written,
                output_port_id=sink.output_port_id,
                status=sink.status,
                error=sink.error,
            )
            for sink in result.sinks
        ],
        graph_version=result.graph_version,
    )
