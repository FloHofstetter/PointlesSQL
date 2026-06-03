"""Per-node preview: compile a canvas truncated at a chosen node, run on DuckDB.

The editor's "preview rows on this node" gesture compiles the upstream
slice of the canvas DAG up to (and including) the chosen node, executes
it through the same DuckDB + Delta plumbing the executor uses, and
returns the first *limit* rows as plain JSON.  Crucially: no Delta
write happens — the preview path is read-only, leaves UC untouched,
and never bumps the canvas-graph version.

Implementation pattern: keep the compiler honest about needing exactly
one OutputPort, but inject a *synthetic* sink wired to the target
node's primary output pin so the existing compile + topo machinery
keeps working without a special "preview mode" branch.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field
from soyuz_catalog_client import Client

from pointlessql.exceptions import (
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.pql.engine import register_delta_view
from pointlessql.pql.sql_parser._prepare import prepare_sql
from pointlessql.services.dp_canvas._blocks import BLOCK_REGISTRY
from pointlessql.services.dp_canvas._compiler import compile_canvas, render_sql
from pointlessql.services.dp_canvas._file_sandbox import rewrite_file_sentinels
from pointlessql.services.dp_canvas._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
    PinSchema,
)
from pointlessql.services.dp_canvas._uc_lookup import resolve_storage_location

if TYPE_CHECKING:
    pass


_PREVIEW_SINK_ID = "__preview_sink__"
_PREVIEW_SINK_PORT = "preview"
_PREVIEW_SINK_TABLE = "preview.preview.preview"
_MAX_PREVIEW_LIMIT = 1000


class PreviewResult(BaseModel):
    """Envelope returned by :func:`preview_until`.

    Attributes:
        columns: Ordered column names from the DuckDB result, or empty
            list when ``errors`` is non-empty.
        rows: Each row as a list of JSON-coerced cell values (datetimes
            stringified, decimals as strings to preserve precision).
        truncated: ``True`` when DuckDB returned exactly *limit* rows —
            the caller cannot tell whether more rows exist without
            re-running with a higher limit, so the editor shows a
            "showing first N" badge instead of a row count.
        row_count: Number of rows returned in *rows*.  When
            ``truncated`` is True this is also the cap (``= limit``);
            when False it is the actual scan size.
        sql: The rendered DuckDB query.  Useful for the "show me what
            this preview ran" debug surface.
        errors: Compile errors when the truncated slice failed to
            compile.  Mirrors the validate endpoint's shape so the
            editor can reuse the same renderer.
        cache_hit: ``True`` when this envelope was served from the
            in-memory preview cache rather than re-executing the
            DuckDB query.  The editor surfaces a "cached" badge in
            the preview-modal footer so the user can tell a cheap
            re-render from a fresh scan.
    """

    model_config = ConfigDict(frozen=True)

    columns: list[str] = Field(default_factory=lambda: [])
    rows: list[list[Any]] = Field(default_factory=lambda: [])
    truncated: bool = False
    row_count: int = 0
    sql: str = ""
    errors: list[CompileError] = Field(default_factory=lambda: [])
    cache_hit: bool = False


def _collect_ancestors(doc: CanvasDoc, upto_node_id: str) -> set[str]:
    """Return the set of node ids that flow into *upto_node_id* (inclusive)."""
    incoming: dict[str, list[str]] = {}
    for edge in doc.edges:
        incoming.setdefault(edge.target_node_id, []).append(edge.source_node_id)
    keep: set[str] = {upto_node_id}
    queue: deque[str] = deque([upto_node_id])
    while queue:
        current = queue.popleft()
        for upstream in incoming.get(current, []):
            if upstream in keep:
                continue
            keep.add(upstream)
            queue.append(upstream)
    return keep


def _primary_output_pin(node: CanvasNode) -> str | None:
    """Return the canonical output pin name to feed the synthetic sink."""
    spec = BLOCK_REGISTRY.get(node.block_type)
    if spec is None or not spec.output_pins:
        return None
    return spec.output_pins[0][0]


def _build_preview_doc(
    doc: CanvasDoc, upto_node: CanvasNode, pin_name: str
) -> CanvasDoc:
    """Return a new doc keeping only upstream-of-*upto_node* plus a synthetic sink."""
    keep = _collect_ancestors(doc, upto_node.id)
    kept_nodes = [n for n in doc.nodes if n.id in keep]
    kept_edges = [
        e for e in doc.edges if e.source_node_id in keep and e.target_node_id in keep
    ]
    sink = CanvasNode(
        id=_PREVIEW_SINK_ID,
        block_type="OutputPort",
        config={
            "port_name": _PREVIEW_SINK_PORT,
            "materialized_table": _PREVIEW_SINK_TABLE,
            "mode": "overwrite",
        },
        position=None,
    )
    sink_edge = CanvasEdge(
        id=f"__preview_edge_{upto_node.id}__",
        source_node_id=upto_node.id,
        source_pin=pin_name,
        target_node_id=_PREVIEW_SINK_ID,
        target_pin="in",
    )
    return CanvasDoc(
        nodes=[*kept_nodes, sink],
        edges=[*kept_edges, sink_edge],
    )


def _coerce_cell(value: Any) -> Any:
    """JSON-safe coercion of one DuckDB cell value."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def preview_until(
    doc: CanvasDoc,
    *,
    upto_node_id: str,
    limit: int,
    soyuz_client: Client,
    upstream_seeds: dict[str, PinSchema] | None = None,
    cache_dp_id: int | None = None,
) -> PreviewResult:
    """Compile a slice of *doc* ending at *upto_node_id* and return preview rows.

    Args:
        doc: The canvas document the editor currently has open.  The
            caller is responsible for handing in the *current* document
            (not a saved version) so the preview matches the dirty
            edit-state.
        upto_node_id: The node whose primary output pin defines the
            preview's tip.  Must not be an ``OutputPort`` block (use
            materialise for that path).
        limit: Maximum number of rows to fetch.  Clamped to
            :data:`_MAX_PREVIEW_LIMIT` so a runaway query cannot empty
            a multi-million-row Delta scan into one JSON response.
        soyuz_client: Configured raw soyuz ``Client`` for resolving
            referenced base-table FQNs to Delta storage locations.
        upstream_seeds: Optional ``{node_id: PinSchema}`` seeding for
            InputPort blocks; the validate route already builds this
            map and can hand it through so we don't re-query soyuz.
        cache_dp_id: When non-None, look up + memoise the result in
            the in-process preview cache keyed on the canvas upstream
            slice's content hash.  The HTTP route passes the dp id;
            unit tests can omit it for cache-free runs.

    Returns:
        A :class:`PreviewResult` envelope.  ``errors`` is populated
        when the truncated slice fails to compile; ``rows`` is
        populated otherwise.

    Raises:
        ResourceNotFoundError: When *upto_node_id* isn't in the doc.
        ValidationError: When the target node is an ``OutputPort`` (the
            preview path is read-only — use materialise instead).
        CatalogUnavailableError: When soyuz is unreachable while
            resolving a referenced table.
    """
    target = next((n for n in doc.nodes if n.id == upto_node_id), None)
    if target is None:
        raise ResourceNotFoundError(
            f"preview node {upto_node_id!r} not found in canvas"
        )
    if target.block_type == "OutputPort":
        raise ValidationError(
            "preview is read-only; the OutputPort block is materialise-only"
        )
    pin = _primary_output_pin(target)
    if pin is None:
        raise ValidationError(
            f"preview node {upto_node_id!r} has no output pin to preview"
        )

    safe_limit = max(1, min(int(limit or 100), _MAX_PREVIEW_LIMIT))

    if cache_dp_id is not None:
        from pointlessql.services.dp_canvas import _preview_cache

        cached = _preview_cache.lookup(
            dp_id=cache_dp_id,
            doc=doc,
            upto_node_id=upto_node_id,
            limit=safe_limit,
        )
        if cached is not None:
            return cached.model_copy(update={"cache_hit": True})

    preview_doc = _build_preview_doc(doc, target, pin)
    fragment, errors = compile_canvas(preview_doc, upstream_schemas=upstream_seeds)
    if fragment is None or errors:
        return PreviewResult(errors=errors)

    rendered = render_sql(fragment, fragment.sinks[0])
    wrapped_sql = f"SELECT * FROM ({rendered}) AS _preview_inner LIMIT {safe_limit}"

    approved: dict[str, str] = {}
    for fqn in fragment.referenced_tables:
        location = resolve_storage_location(soyuz_client, fqn, required=False)
        if location is None:
            return PreviewResult(
                sql=wrapped_sql,
                errors=[
                    CompileError(
                        kind="bad_config",
                        node_id=None,
                        pin=None,
                        message=(
                            f"preview cannot resolve Delta location for table {fqn!r}"
                        ),
                    )
                ],
            )
        approved[fqn] = location

    try:
        sandboxed_sql = rewrite_file_sentinels(wrapped_sql)
    except ValidationError as exc:
        return PreviewResult(
            sql=wrapped_sql,
            errors=[CompileError(kind="bad_config", node_id=None, pin=None, message=str(exc))],
        )
    prepared = prepare_sql(sandboxed_sql)

    import duckdb

    conn = duckdb.connect()
    try:
        for ref in prepared.refs:
            register_delta_view(conn, ref, approved[ref])
        cursor = conn.execute(prepared.rewritten_sql)
        column_names = [desc[0] for desc in cursor.description or []]
        raw_rows = cursor.fetchall()
    finally:
        conn.close()

    rows = [[_coerce_cell(cell) for cell in row] for row in raw_rows]
    truncated = len(rows) == safe_limit
    result = PreviewResult(
        columns=column_names,
        rows=rows,
        truncated=truncated,
        row_count=len(rows),
        sql=wrapped_sql,
        errors=[],
        cache_hit=False,
    )

    if cache_dp_id is not None:
        from pointlessql.services.dp_canvas import _preview_cache

        _preview_cache.store(
            dp_id=cache_dp_id,
            doc=doc,
            upto_node_id=upto_node_id,
            limit=safe_limit,
            result=result,
        )

    return result


__all__ = ["PreviewResult", "preview_until"]
