"""HTTP routes for the visual data-product canvas editor.

Five thin adapters over the ``pointlessql.services.dp_canvas`` surface:

* ``GET    /api/dp/{dp_id}/canvas``             — load latest saved doc.
* ``POST   /api/dp/{dp_id}/canvas``             — save next version.
* ``GET    /api/dp/{dp_id}/canvas/versions``    — newest-first version list.
* ``POST   /api/dp/{dp_id}/canvas/validate``    — schema-flow check
  (resolves each ``InputPort.table_fqn`` against soyuz to seed the upstream
  schemas, then forward-propagates pin schemas through the DAG).
* ``POST   /api/dp/{dp_id}/canvas/materialize`` — compile + execute the
  canvas; writes the target Delta location and upserts the output port.

Path scheme uses the integer ``data_products.id`` rather than
``{catalog}/{schema}`` because the canvas storage layer keys on that
id; the visual editor is reached via the standalone editor page rather
than the existing tab strip, so the URL shape never collides with the
canonical DP browsing URLs.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from soyuz_catalog_client import Client as SoyuzClient
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_uc_client,
    get_user,
    require_user,
)
from pointlessql.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models import DataProduct, DataProductCanvasGraph
from pointlessql.services.dp_canvas import (
    CanvasDoc,
    ColumnSpec,
    CompileError,
    ExecuteResult,
    PinSchema,
    execute_canvas,
    load_latest_graph,
    save_graph,
    validate_schema_flow,
)
from pointlessql.services.dp_canvas._preview import PreviewResult, preview_until

router = APIRouter(prefix="/api/dp", tags=["data-products-canvas"])


def _load_dp(request: Request, dp_id: int) -> DataProduct:
    """Resolve *dp_id* in the active workspace; raise 404 otherwise."""
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(DataProduct, dp_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError(f"data product id={dp_id} not found")
        session.expunge(row)
        return row


def _require_dp_write(user: Any, row: DataProduct) -> None:
    """Raise :class:`AuthorizationError` unless the caller may edit *row*."""
    is_steward = row.steward_user_id is not None and row.steward_user_id == user["id"]
    is_admin = bool(user.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="canvas-write",
            securable_type="data_product",
            full_name=f"{row.catalog_name}.{row.schema_name}",
        )


def _raw_soyuz_client(request: Request) -> SoyuzClient:
    """Return the per-request raw ``soyuz_catalog_client.Client``.

    The visual canvas executor + validator both consume the generated
    client directly because they make sync calls inside DuckDB
    materialise loops where the async facade would force an event-loop
    hop on every base-table lookup.
    """
    uc = get_uc_client(request)
    return uc._client  # pyright: ignore[reportPrivateUsage]


def _table_info_to_pin_schema(info: TableInfo) -> PinSchema:
    """Project a soyuz ``TableInfo`` onto the canvas's ``PinSchema``."""
    raw_columns = info.columns if not isinstance(info.columns, Unset) else None
    specs: list[ColumnSpec] = []
    for col in raw_columns or []:
        name = col.name if not isinstance(col.name, Unset) else None
        if not name:
            continue
        type_text = col.type_text if not isinstance(col.type_text, Unset) else None
        if not type_text:
            type_name = col.type_name if not isinstance(col.type_name, Unset) else None
            type_text = type_name or "VARCHAR"
        nullable_raw = col.nullable if not isinstance(col.nullable, Unset) else None
        nullable = True if nullable_raw is None else bool(nullable_raw)
        specs.append(
            ColumnSpec(name=str(name), duckdb_type=str(type_text), nullable=nullable)
        )
    return PinSchema(kind="table", columns=specs, unknown=False)


def _seed_schemas_for_doc(
    doc: CanvasDoc, client: SoyuzClient
) -> tuple[dict[str, PinSchema], list[CompileError]]:
    """Resolve every ``InputPort.table_fqn`` to a ``PinSchema`` via soyuz.

    Returns a ``(seeds, errors)`` tuple; errors carry ``bad_config`` kind
    so the editor surfaces them on the offending node.
    """
    seeds: dict[str, PinSchema] = {}
    errors: list[CompileError] = []
    for node in doc.nodes:
        if node.block_type != "InputPort":
            continue
        fqn = str(node.config.get("table_fqn") or "").strip()
        if not fqn:
            continue
        try:
            response = _get_table.sync(client=client, full_name=fqn)
        except httpx.ConnectError:
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node.id,
                    pin="out",
                    message=f"soyuz-catalog unreachable while resolving {fqn!r}",
                )
            )
            continue
        except UnexpectedStatus as exc:
            if exc.status_code == 404:
                errors.append(
                    CompileError(
                        kind="bad_config",
                        node_id=node.id,
                        pin="out",
                        message=f"table {fqn!r} not registered in UC",
                    )
                )
                continue
            raise
        if not isinstance(response, TableInfo):
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node.id,
                    pin="out",
                    message=f"table {fqn!r} not registered in UC",
                )
            )
            continue
        seeds[node.id] = _table_info_to_pin_schema(response)
    return seeds, errors


class CanvasSaveRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc
    expected_base_version: int | None = Field(
        default=None,
        description=(
            "When set, the save returns 422 if the latest stored version "
            "differs — optimistic-concurrency guard for autosave races."
        ),
    )


class CanvasSaveResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas``."""

    version: int
    created_at: datetime.datetime


class CanvasLoadResponse(BaseModel):
    """Response for ``GET /api/dp/{dp_id}/canvas``."""

    document: CanvasDoc | None
    version: int | None
    created_at: datetime.datetime | None


class CanvasVersionEntry(BaseModel):
    """One row in the version list."""

    version: int
    created_at: datetime.datetime
    author_user_id: int | None


class CanvasVersionsResponse(BaseModel):
    """Response for ``GET /api/dp/{dp_id}/canvas/versions``."""

    versions: list[CanvasVersionEntry]


class CanvasValidateRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas/validate``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc


class CanvasValidateResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas/validate``.

    ``pin_schemas`` is keyed as ``f"{node_id}:{pin_name}"`` because JSON
    cannot represent tuple keys.
    """

    pin_schemas: dict[str, PinSchema]
    errors: list[CompileError]


class CanvasPreviewRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas/preview``.

    POST (not GET) so the editor can send the in-memory dirty document
    without the URL-encoding pain of cramming JSON into a query string.
    """

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc
    upto_node_id: str = Field(min_length=1, max_length=64)
    limit: int = Field(default=100, ge=1, le=1000)


class CanvasPreviewResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas/preview``."""

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    sql: str
    errors: list[CompileError]


class CanvasMaterializeRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas/materialize``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc | None = None
    expected_base_version: int | None = None


class CanvasMaterializeResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas/materialize``."""

    rows_written: int
    target_fqn: str
    output_port_id: int | None
    graph_version: int


@router.get("/{dp_id}/canvas", response_model=CanvasLoadResponse)
def get_canvas(dp_id: int, request: Request) -> CanvasLoadResponse:
    """Return the most recent saved canvas document for *dp_id*."""
    require_user(request)
    _load_dp(request, dp_id)
    factory = request.app.state.session_factory
    result = load_latest_graph(factory, data_product_id=dp_id)
    if result is None:
        return CanvasLoadResponse(document=None, version=None, created_at=None)
    doc, version = result
    with factory() as session:
        row = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version == version,
            )
        ).scalar_one()
        created_at = row.created_at
    return CanvasLoadResponse(document=doc, version=version, created_at=created_at)


@router.post("/{dp_id}/canvas", response_model=CanvasSaveResponse)
def save_canvas(
    dp_id: int, body: CanvasSaveRequest, request: Request
) -> CanvasSaveResponse:
    """Persist *body.document* as the next version for *dp_id*."""
    require_user(request)
    user = get_user(request)
    row = _load_dp(request, dp_id)
    _require_dp_write(user, row)
    factory = request.app.state.session_factory

    if body.expected_base_version is not None:
        existing = load_latest_graph(factory, data_product_id=dp_id)
        existing_version = existing[1] if existing else 0
        if existing_version != body.expected_base_version:
            raise ValidationError(
                f"canvas save conflict: caller expected v{body.expected_base_version} "
                f"but latest is v{existing_version}"
            )

    actor_id = int(user["id"]) if user["id"] > 0 else None
    new_version = save_graph(
        factory,
        data_product_id=dp_id,
        doc=body.document,
        author_user_id=actor_id,
    )
    with factory() as session:
        saved = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version == new_version,
            )
        ).scalar_one()
        created_at = saved.created_at
    return CanvasSaveResponse(version=new_version, created_at=created_at)


@router.get("/{dp_id}/canvas/versions", response_model=CanvasVersionsResponse)
def list_canvas_versions(dp_id: int, request: Request) -> CanvasVersionsResponse:
    """List saved canvas versions for *dp_id* newest-first."""
    require_user(request)
    _load_dp(request, dp_id)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(DataProductCanvasGraph)
                .where(DataProductCanvasGraph.data_product_id == dp_id)
                .order_by(DataProductCanvasGraph.version.desc())
            )
            .scalars()
            .all()
        )
    entries = [
        CanvasVersionEntry(
            version=r.version,
            created_at=r.created_at,
            author_user_id=r.author_user_id,
        )
        for r in rows
    ]
    return CanvasVersionsResponse(versions=entries)


@router.post("/{dp_id}/canvas/validate", response_model=CanvasValidateResponse)
def validate_canvas(
    dp_id: int, body: CanvasValidateRequest, request: Request
) -> CanvasValidateResponse:
    """Run schema-flow validation against *body.document*.

    Looks up each ``InputPort`` block's ``table_fqn`` in UC so the
    propagation has real upstream schemas to chain against.
    """
    require_user(request)
    _load_dp(request, dp_id)
    client = _raw_soyuz_client(request)
    seeds, seed_errors = _seed_schemas_for_doc(body.document, client)
    pin_schemas, flow_errors = validate_schema_flow(body.document, seed_schemas=seeds)
    wire_schemas = {
        f"{node_id}:{pin}": schema for (node_id, pin), schema in pin_schemas.items()
    }
    return CanvasValidateResponse(
        pin_schemas=wire_schemas,
        errors=[*seed_errors, *flow_errors],
    )


@router.post("/{dp_id}/canvas/preview", response_model=CanvasPreviewResponse)
def preview_canvas(
    dp_id: int, body: CanvasPreviewRequest, request: Request
) -> CanvasPreviewResponse:
    """Compile the canvas slice ending at *upto_node_id* and return preview rows.

    Read-only: the request is rejected for ``OutputPort`` nodes (use
    materialise for that path), no Delta write happens, and the graph
    version is *not* bumped — the document is consumed verbatim from
    the request body so the editor can preview dirty unsaved state.
    """
    require_user(request)
    _load_dp(request, dp_id)
    client = _raw_soyuz_client(request)
    seeds, _seed_errors = _seed_schemas_for_doc(body.document, client)
    result: PreviewResult = preview_until(
        body.document,
        upto_node_id=body.upto_node_id,
        limit=body.limit,
        soyuz_client=client,
        upstream_seeds=seeds,
    )
    return CanvasPreviewResponse(
        columns=list(result.columns),
        rows=[list(row) for row in result.rows],
        truncated=result.truncated,
        sql=result.sql,
        errors=list(result.errors),
    )


@router.post(
    "/{dp_id}/canvas/materialize", response_model=CanvasMaterializeResponse
)
def materialize_canvas(
    dp_id: int, body: CanvasMaterializeRequest, request: Request
) -> CanvasMaterializeResponse:
    """Compile + execute the canvas; write Delta + upsert the output port."""
    require_user(request)
    user = get_user(request)
    row = _load_dp(request, dp_id)
    _require_dp_write(user, row)
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
        save_graph(
            factory,
            data_product_id=dp_id,
            doc=body.document,
            author_user_id=actor_id,
        )
        doc = body.document
    else:
        loaded = load_latest_graph(factory, data_product_id=dp_id)
        if loaded is None:
            raise ValidationError(
                f"data product {dp_id} has no saved canvas to materialise"
            )
        doc = loaded[0]

    client = _raw_soyuz_client(request)
    result: ExecuteResult = execute_canvas(
        factory,
        doc=doc,
        data_product_id=dp_id,
        soyuz_client=client,
        actor_user_id=actor_id,
    )
    return CanvasMaterializeResponse(
        rows_written=result.rows_written,
        target_fqn=result.target_fqn,
        output_port_id=result.output_port_id,
        graph_version=result.graph_version,
    )


__all__ = [
    "CanvasLoadResponse",
    "CanvasMaterializeRequest",
    "CanvasMaterializeResponse",
    "CanvasPreviewRequest",
    "CanvasPreviewResponse",
    "CanvasSaveRequest",
    "CanvasSaveResponse",
    "CanvasValidateRequest",
    "CanvasValidateResponse",
    "CanvasVersionEntry",
    "CanvasVersionsResponse",
    "router",
]
