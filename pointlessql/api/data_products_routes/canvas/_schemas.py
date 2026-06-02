"""Request / response models for the visual data-product canvas routes.

Kept in one module so the canvas endpoints — split by concern across the
sibling handler modules — share a single, scannable definition of their
HTTP contract.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pointlessql.services.dp_canvas import CanvasDoc, CompileError, PinSchema
from pointlessql.services.dp_canvas._diff import CanvasDiff


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
