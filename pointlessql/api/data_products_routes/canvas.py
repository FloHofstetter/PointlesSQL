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
from pointlessql.models import DataProduct, DataProductCanvasGraph, DataProductOutputPort
from pointlessql.services.dp_canvas import (
    CanvasDoc,
    ColumnSpec,
    CompileError,
    MultiExecuteResult,
    PinSchema,
    execute_canvas,
    load_latest_graph,
    save_graph,
    validate_schema_flow,
)
from pointlessql.services.dp_canvas._diff import CanvasDiff, diff_docs
from pointlessql.services.dp_canvas._edge_types import categorize_pin_schema
from pointlessql.services.dp_canvas._pinning import (
    pin_version as _pin_canvas_version,
)
from pointlessql.services.dp_canvas._pinning import (
    unpin_version as _unpin_canvas_version,
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


def _resolve_dp_refs(request: Request, doc: CanvasDoc) -> CanvasDoc:
    """Walk every ``DataProduct`` block and fill ``materialized_table``.

    The editor stores ``dp_id`` + ``port_name`` on the block; the
    compiler reads the resolved 3-part FQN.  Doing the lookup here on
    save (and re-doing it on validate / materialise) means the
    compile path stays pure and a rename of the upstream port can be
    surfaced at edit-time without rewriting saved docs.
    """
    factory = request.app.state.session_factory
    needs = [
        (n, int(n.config.get("dp_id", 0) or 0), str(n.config.get("port_name") or "").strip())
        for n in doc.nodes
        if n.block_type == "DataProduct"
    ]
    if not needs:
        return doc
    targets: dict[tuple[int, str], str] = {}
    with factory() as session:
        for _node, dp_id, port_name in needs:
            if dp_id <= 0 or not port_name:
                continue
            key = (dp_id, port_name)
            if key in targets:
                continue
            row = session.execute(
                select(DataProductOutputPort).where(
                    DataProductOutputPort.data_product_id == dp_id,
                    DataProductOutputPort.name == port_name,
                )
            ).scalar_one_or_none()
            if row is None or not row.location:
                continue
            targets[key] = row.location
    updated_nodes = []
    for node in doc.nodes:
        if node.block_type != "DataProduct":
            updated_nodes.append(node)
            continue
        dp_id = int(node.config.get("dp_id", 0) or 0)
        port_name = str(node.config.get("port_name") or "").strip()
        resolved = targets.get((dp_id, port_name))
        if resolved:
            new_cfg = {**node.config, "materialized_table": resolved}
            updated_nodes.append(node.model_copy(update={"config": new_cfg}))
        else:
            updated_nodes.append(node)
    return doc.model_copy(update={"nodes": updated_nodes})


def _seed_schemas_for_doc(
    doc: CanvasDoc, client: SoyuzClient
) -> tuple[dict[str, PinSchema], list[CompileError]]:
    """Resolve every InputPort + DataProduct source FQN to a ``PinSchema`` via soyuz.

    Returns a ``(seeds, errors)`` tuple; errors carry ``bad_config`` kind
    so the editor surfaces them on the offending node.
    """
    seeds: dict[str, PinSchema] = {}
    errors: list[CompileError] = []
    for node in doc.nodes:
        if node.block_type == "InputPort":
            fqn_key = "table_fqn"
        elif node.block_type == "DataProduct":
            fqn_key = "materialized_table"
        else:
            continue
        fqn = str(node.config.get(fqn_key) or "").strip()
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
    is_production: bool = False


class CanvasVersionsResponse(BaseModel):
    """Response for ``GET /api/dp/{dp_id}/canvas/versions``."""

    versions: list[CanvasVersionEntry]
    pinned_version: int | None = None


class CanvasValidateRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas/validate``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc


class CanvasValidateResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas/validate``.

    ``pin_schemas`` is keyed as ``f"{node_id}:{pin_name}"`` because JSON
    cannot represent tuple keys.  ``edge_categories`` maps an edge id
    (``"{source_node_id}:{source_pin}->{target_node_id}:{target_pin}"``)
    to a dominant data-type bucket (``numeric``, ``text``, ``temporal``,
    ``boolean``, ``complex``, ``mixed``) so the editor can colour each
    connection by what flows through it.
    """

    pin_schemas: dict[str, PinSchema]
    errors: list[CompileError]
    edge_categories: dict[str, str] = Field(default_factory=dict)


class CanvasLoadVersionResponse(BaseModel):
    """Response for ``GET /api/dp/{dp_id}/canvas/versions/{version}``."""

    document: CanvasDoc
    version: int
    created_at: datetime.datetime


class CanvasDiffResponse(BaseModel):
    """Response for ``GET /api/dp/{dp_id}/canvas/diff``."""

    from_version: int
    to_version: int
    diff: CanvasDiff


class CanvasGhostDiffRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas/ghost-diff``."""

    model_config = ConfigDict(extra="forbid")

    proposed_document: CanvasDoc


class CanvasGhostDiffResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas/ghost-diff``.

    Diffs an agent- (or user-) proposed canvas against the currently saved
    one and validates the proposal in the same pass, so a read-only editor
    overlay can paint added / removed / modified nodes and edges, badge the
    proposal's schema errors, and colour its wires — all before anyone
    commits the change.  ``pin_schemas`` / ``edge_categories`` follow the
    same shape as the validate endpoint.
    """

    diff: CanvasDiff
    pin_schemas: dict[str, PinSchema]
    errors: list[CompileError]
    edge_categories: dict[str, str] = Field(default_factory=dict)


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
    row_count: int
    sql: str
    errors: list[CompileError]
    cache_hit: bool = False


class CanvasMaterializeRequest(BaseModel):
    """Body for ``POST /api/dp/{dp_id}/canvas/materialize``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc | None = None
    expected_base_version: int | None = None


class CanvasMaterializeSink(BaseModel):
    """One materialised sink's outcome in a materialize response."""

    port_name: str
    target_fqn: str
    rows_written: int
    output_port_id: int | None
    status: str
    error: str | None = None


class CanvasMaterializeResponse(BaseModel):
    """Response for ``POST /api/dp/{dp_id}/canvas/materialize``.

    A canvas may publish several output ports; ``sinks`` carries one entry
    per ``OutputPort`` block.  Materialisation is best-effort per sink, so
    a partial run returns HTTP 200 with a mix of ``ok`` / ``failed``
    statuses rather than a top-level error.
    """

    sinks: list[CanvasMaterializeSink]
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
    resolved_doc = _resolve_dp_refs(request, body.document)
    new_version = save_graph(
        factory,
        data_product_id=dp_id,
        doc=resolved_doc,
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
            is_production=bool(r.is_production),
        )
        for r in rows
    ]
    pinned = next((e.version for e in entries if e.is_production), None)
    return CanvasVersionsResponse(versions=entries, pinned_version=pinned)


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
    resolved_doc = _resolve_dp_refs(request, body.document)
    seeds, seed_errors = _seed_schemas_for_doc(resolved_doc, client)
    pin_schemas, flow_errors = validate_schema_flow(resolved_doc, seed_schemas=seeds)
    wire_schemas = {
        f"{node_id}:{pin}": schema for (node_id, pin), schema in pin_schemas.items()
    }
    edge_categories: dict[str, str] = {}
    for edge in resolved_doc.edges:
        source_schema = pin_schemas.get((edge.source_node_id, edge.source_pin))
        key = (
            f"{edge.source_node_id}:{edge.source_pin}->"
            f"{edge.target_node_id}:{edge.target_pin}"
        )
        edge_categories[key] = categorize_pin_schema(source_schema)
    return CanvasValidateResponse(
        pin_schemas=wire_schemas,
        errors=[*seed_errors, *flow_errors],
        edge_categories=edge_categories,
    )


@router.post("/{dp_id}/canvas/versions/{version}/pin", status_code=204)
def pin_canvas_version(dp_id: int, version: int, request: Request) -> None:
    """Mark *version* of canvas *dp_id* as the production revision."""
    require_user(request)
    user = get_user(request)
    dp = _load_dp(request, dp_id)
    _require_dp_write(user, dp)
    factory = request.app.state.session_factory
    client_ip = request.client.host if request.client else None
    _pin_canvas_version(
        factory,
        dp_id=dp_id,
        version=version,
        actor_user_id=int(user["id"]),
        actor_user_email=str(user.get("email") or ""),
        workspace_id=current_workspace_id(request),
        client_ip=client_ip,
    )


@router.post("/{dp_id}/canvas/versions/{version}/unpin", status_code=204)
def unpin_canvas_version(dp_id: int, version: int, request: Request) -> None:
    """Clear the production-pin from *version* of canvas *dp_id*."""
    require_user(request)
    user = get_user(request)
    dp = _load_dp(request, dp_id)
    _require_dp_write(user, dp)
    factory = request.app.state.session_factory
    client_ip = request.client.host if request.client else None
    _unpin_canvas_version(
        factory,
        dp_id=dp_id,
        version=version,
        actor_user_id=int(user["id"]),
        actor_user_email=str(user.get("email") or ""),
        workspace_id=current_workspace_id(request),
        client_ip=client_ip,
    )


class DataProductPickerEntry(BaseModel):
    """One row in the DP-picker dropdown the DP compound block uses."""

    model_config = ConfigDict(protected_namespaces=(), populate_by_name=True)

    dp_id: int
    catalog: str
    schema_name: str = Field(serialization_alias="schema")
    ref: str
    output_ports: list[dict[str, Any]]


class DataProductPickerResponse(BaseModel):
    """Response for ``GET /api/dp/_picker``."""

    data_products: list[DataProductPickerEntry]


@router.get("/_picker", response_model=DataProductPickerResponse)
def list_dp_picker(request: Request) -> DataProductPickerResponse:
    """Return DPs in the active workspace plus their output ports.

    Powers the DataProduct compound-block's config-form dropdown so
    the user can pick which upstream DP + which port to wire in.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        dps = (
            session.execute(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        ports = (
            session.execute(
                select(DataProductOutputPort).where(
                    DataProductOutputPort.data_product_id.in_(
                        [dp.id for dp in dps] or [-1]
                    )
                )
            )
            .scalars()
            .all()
        )
    ports_by_dp: dict[int, list[dict[str, Any]]] = {}
    for port in ports:
        ports_by_dp.setdefault(port.data_product_id, []).append(
            {
                "name": port.name,
                "kind": port.kind,
                "location": port.location,
            }
        )
    return DataProductPickerResponse(
        data_products=[
            DataProductPickerEntry(
                dp_id=dp.id,
                catalog=dp.catalog_name,
                schema_name=dp.schema_name,
                ref=f"{dp.catalog_name}.{dp.schema_name}",
                output_ports=ports_by_dp.get(dp.id, []),
            )
            for dp in dps
        ]
    )


@router.get(
    "/{dp_id}/canvas/versions/{version}", response_model=CanvasLoadVersionResponse
)
def load_canvas_version(
    dp_id: int, version: int, request: Request
) -> CanvasLoadVersionResponse:
    """Return the canvas document for a specific stored version."""
    require_user(request)
    _load_dp(request, dp_id)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version == version,
            )
        ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError(
            f"canvas version v{version} not found on dp {dp_id}"
        )
    return CanvasLoadVersionResponse(
        document=CanvasDoc.model_validate_json(row.document),
        version=row.version,
        created_at=row.created_at,
    )


@router.get("/{dp_id}/canvas/diff", response_model=CanvasDiffResponse)
def diff_canvas_versions(
    dp_id: int,
    request: Request,
    from_version: int,
    to_version: int,
) -> CanvasDiffResponse:
    """Compare two saved canvas versions and return the structural diff."""
    require_user(request)
    _load_dp(request, dp_id)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version.in_([from_version, to_version]),
            )
        ).scalars().all()
    by_version = {r.version: r for r in rows}
    if from_version not in by_version or to_version not in by_version:
        raise ResourceNotFoundError(
            f"canvas version(s) missing on dp {dp_id}: requested "
            f"v{from_version}/v{to_version}, have {sorted(by_version)}"
        )
    before = CanvasDoc.model_validate_json(by_version[from_version].document)
    after = CanvasDoc.model_validate_json(by_version[to_version].document)
    return CanvasDiffResponse(
        from_version=from_version,
        to_version=to_version,
        diff=diff_docs(before, after),
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
    _load_dp(request, dp_id)
    factory = request.app.state.session_factory
    result = load_latest_graph(factory, data_product_id=dp_id)
    current = result[0] if result else CanvasDoc(nodes=[], edges=[])
    proposed = _resolve_dp_refs(request, body.proposed_document)
    client = _raw_soyuz_client(request)
    seeds, seed_errors = _seed_schemas_for_doc(proposed, client)
    pin_schemas, flow_errors = validate_schema_flow(proposed, seed_schemas=seeds)
    wire_schemas = {
        f"{node_id}:{pin}": schema for (node_id, pin), schema in pin_schemas.items()
    }
    edge_categories: dict[str, str] = {}
    for edge in proposed.edges:
        source_schema = pin_schemas.get((edge.source_node_id, edge.source_pin))
        key = (
            f"{edge.source_node_id}:{edge.source_pin}->"
            f"{edge.target_node_id}:{edge.target_pin}"
        )
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
    _load_dp(request, dp_id)
    if bust:
        from pointlessql.services.dp_canvas import _preview_cache

        _preview_cache.clear_for_dp(dp_id)
    client = _raw_soyuz_client(request)
    resolved_doc = _resolve_dp_refs(request, body.document)
    seeds, _seed_errors = _seed_schemas_for_doc(resolved_doc, client)
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
        # execute_canvas stamps the single authoritative graph version
        # after a successful run, so we deliberately do not pre-save the
        # document here: pre-saving double-bumps the version on success
        # and — worse — leaves a bumped version behind on a *failed* run,
        # which desyncs the client and blocks the retry with a phantom
        # version conflict.
        doc = _resolve_dp_refs(request, body.document)
    else:
        loaded = load_latest_graph(factory, data_product_id=dp_id)
        if loaded is None:
            raise ValidationError(
                f"data product {dp_id} has no saved canvas to materialise"
            )
        doc = loaded[0]

    client = _raw_soyuz_client(request)
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


__all__ = [
    "CanvasDiffResponse",
    "CanvasGhostDiffRequest",
    "CanvasGhostDiffResponse",
    "CanvasLoadResponse",
    "CanvasLoadVersionResponse",
    "CanvasMaterializeRequest",
    "CanvasMaterializeResponse",
    "CanvasMaterializeSink",
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
