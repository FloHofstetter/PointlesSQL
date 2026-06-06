"""HTTP routes for the DataFrame Studio — sink-free visual query builder.

Three read-only adapters over the shared canvas machinery, all consuming
the document verbatim from the request body (no persistence, no version
ledger):

* ``POST /api/dataframe-studio/compile``  — compile the slice ending at a
  terminal node to a governed ``SELECT`` + its column schema.
* ``POST /api/dataframe-studio/preview``  — run that slice on DuckDB and
  return the first rows (reuses ``preview_until``).
* ``POST /api/dataframe-studio/validate`` — schema-flow badges + edge
  colours, plus the disallowed-block guard.

The Studio reuses the data-product canvas helpers (soyuz client, schema
seeding) and the shared ``canvas_df`` compiler; it rejects sink
(``OutputPort`` / ``FileOutput``) and ``DataProduct`` blocks.  Persistence
is handled client-side by emitting the SQL into a notebook cell, so there
is no Studio graph table.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from pointlessql.api.data_products_routes.canvas._helpers import (
    raw_soyuz_client,
    seed_schemas_for_doc,
)
from pointlessql.api.dependencies import require_user
from pointlessql.services.canvas_df import (
    CanvasDoc,
    ColumnSpec,
    CompileError,
    PinSchema,
    validate_schema_flow,
)
from pointlessql.services.canvas_df._edge_types import categorize_pin_schema
from pointlessql.services.dataframe_studio import (
    compile_studio_select,
    disallowed_block_errors,
)
from pointlessql.services.dp_canvas._preview import preview_until

router = APIRouter(prefix="/api/dataframe-studio", tags=["dataframe-studio"])


class StudioCompileRequest(BaseModel):
    """Body for ``POST /api/dataframe-studio/compile``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc
    terminal_node_id: str


class StudioCompileResponse(BaseModel):
    """Response for ``POST /api/dataframe-studio/compile``."""

    sql: str = ""
    columns: list[ColumnSpec] = Field(default_factory=lambda: [])
    referenced_tables: list[str] = Field(default_factory=lambda: [])
    errors: list[CompileError] = Field(default_factory=lambda: [])


class StudioPreviewRequest(BaseModel):
    """Body for ``POST /api/dataframe-studio/preview``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc
    terminal_node_id: str
    limit: int = 100


class StudioPreviewResponse(BaseModel):
    """Response for ``POST /api/dataframe-studio/preview``."""

    columns: list[str] = Field(default_factory=lambda: [])
    rows: list[list[object]] = Field(default_factory=lambda: [])
    truncated: bool = False
    row_count: int = 0
    sql: str = ""
    errors: list[CompileError] = Field(default_factory=lambda: [])


class StudioValidateRequest(BaseModel):
    """Body for ``POST /api/dataframe-studio/validate``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc


class StudioValidateResponse(BaseModel):
    """Response for ``POST /api/dataframe-studio/validate``."""

    pin_schemas: dict[str, PinSchema] = Field(default_factory=lambda: {})
    edge_categories: dict[str, str] = Field(default_factory=lambda: {})
    errors: list[CompileError] = Field(default_factory=lambda: [])


@router.post("/compile", response_model=StudioCompileResponse)
def compile_studio(body: StudioCompileRequest, request: Request) -> StudioCompileResponse:
    """Compile the slice ending at *terminal_node_id* to a governed SELECT."""
    require_user(request)
    client = raw_soyuz_client(request)
    seeds, seed_errors = seed_schemas_for_doc(body.document, client)
    result, errors = compile_studio_select(
        body.document,
        terminal_node_id=body.terminal_node_id,
        upstream_schemas=seeds,
    )
    if result is None:
        return StudioCompileResponse(errors=[*seed_errors, *errors])
    return StudioCompileResponse(
        sql=result.sql,
        columns=list(result.output_schema.columns),
        referenced_tables=list(result.referenced_tables),
        errors=list(seed_errors),
    )


@router.post("/preview", response_model=StudioPreviewResponse)
def preview_studio(body: StudioPreviewRequest, request: Request) -> StudioPreviewResponse:
    """Run the slice ending at *terminal_node_id* and return preview rows."""
    require_user(request)
    blocked = disallowed_block_errors(body.document)
    if blocked:
        return StudioPreviewResponse(errors=blocked)
    client = raw_soyuz_client(request)
    seeds, seed_errors = seed_schemas_for_doc(body.document, client)
    result = preview_until(
        body.document,
        upto_node_id=body.terminal_node_id,
        limit=body.limit,
        soyuz_client=client,
        upstream_seeds=seeds,
        cache_dp_id=None,
    )
    return StudioPreviewResponse(
        columns=list(result.columns),
        rows=[list(row) for row in result.rows],
        truncated=result.truncated,
        row_count=result.row_count,
        sql=result.sql,
        errors=[*seed_errors, *result.errors],
    )


@router.post("/validate", response_model=StudioValidateResponse)
def validate_studio(body: StudioValidateRequest, request: Request) -> StudioValidateResponse:
    """Schema-flow badges + edge colours, plus the disallowed-block guard."""
    require_user(request)
    blocked = disallowed_block_errors(body.document)
    client = raw_soyuz_client(request)
    seeds, seed_errors = seed_schemas_for_doc(body.document, client)
    pin_schemas, flow_errors = validate_schema_flow(body.document, seed_schemas=seeds)
    wire_schemas = {
        f"{node_id}:{pin}": schema for (node_id, pin), schema in pin_schemas.items()
    }
    edge_categories: dict[str, str] = {}
    for edge in body.document.edges:
        source_schema = pin_schemas.get((edge.source_node_id, edge.source_pin))
        key = (
            f"{edge.source_node_id}:{edge.source_pin}->"
            f"{edge.target_node_id}:{edge.target_pin}"
        )
        edge_categories[key] = categorize_pin_schema(source_schema)
    return StudioValidateResponse(
        pin_schemas=wire_schemas,
        edge_categories=edge_categories,
        errors=[*blocked, *seed_errors, *flow_errors],
    )


__all__ = [
    "StudioCompileRequest",
    "StudioCompileResponse",
    "StudioPreviewRequest",
    "StudioPreviewResponse",
    "StudioValidateRequest",
    "StudioValidateResponse",
    "router",
]
