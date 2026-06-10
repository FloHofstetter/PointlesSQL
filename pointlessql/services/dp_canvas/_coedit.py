"""Per-canvas in-memory Y.Doc state used by the co-edit WS hub.

Wraps :mod:`pycrdt` so the hub's WebSocket endpoint can stay tiny:
the service owns ``get_or_init_canvas_ydoc`` (seed from the saved
canvas if any) and ``persist_canvas_ydoc`` (mirror the live Y.Doc
back into the ``data_product_canvas_graph`` table by minting a new
version row through the existing :func:`save_graph`).

Y.Doc shape (granular v2):

* ``canvas`` (Y.Map) — root metadata, currently just
  ``{"schema_version": "v2"}``.  The earlier v1 layout stored the
  whole serialised CanvasDoc as a single ``"json"`` slot inside this
  map; v2 reads + transparently migrates that legacy slot on first
  load so existing in-flight co-edit sessions don't break.
* ``nodes_order`` (Y.Array of str) — stable ordering of node ids.
* ``nodes_map`` (Y.Map) — ``{node_id: Y.Map({block_type, config_json,
  position_json})}``.  Per-block storage so two users editing two
  different nodes' configs never write to the same Y.Map key + never
  conflict.  Config + position are JSON-encoded strings rather than
  nested Y.Maps because the in-process editor still works against the
  full :class:`CanvasDoc` Pydantic round-trip and granular per-key
  config sync is out of scope for v1.
* ``edges_order`` (Y.Array of str) + ``edges_map`` (Y.Map) — mirror
  shape for edges.

Why granular: under v1 ("single JSON slot") two users editing
unrelated nodes in the same canvas would race on the slot's last-
writer-wins update.  Granular per-block storage makes those edits
non-conflicting at the Y.js layer.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pointlessql.services.dp_canvas._storage import load_latest_graph, save_graph
from pointlessql.services.dp_canvas._types import CanvasDoc, CanvasEdge, CanvasNode

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

try:  # pragma: no cover — exercised only when pycrdt is installed (already a project dep)
    import pycrdt
except ImportError:  # pragma: no cover
    pycrdt = None  # type: ignore[assignment]


_SCHEMA_VERSION = "v2"


def _seed_granular_from_canvas(doc: Any, canvas_doc: CanvasDoc) -> None:
    """Populate the granular Y.Maps from a `CanvasDoc`.  Idempotent."""
    assert pycrdt is not None  # noqa: S101 — module-level None guard runs at import
    nodes_order = doc.get("nodes_order", type=pycrdt.Array)
    nodes_map = doc.get("nodes_map", type=pycrdt.Map)
    edges_order = doc.get("edges_order", type=pycrdt.Array)
    edges_map = doc.get("edges_map", type=pycrdt.Map)
    # Reset to canonical state.
    while len(nodes_order) > 0:
        del nodes_order[0]
    for k in list(nodes_map.keys()):
        del nodes_map[k]
    while len(edges_order) > 0:
        del edges_order[0]
    for k in list(edges_map.keys()):
        del edges_map[k]
    for node in canvas_doc.nodes:
        node_record = pycrdt.Map()
        nodes_map[node.id] = node_record
        nodes_map[node.id]["block_type"] = node.block_type
        nodes_map[node.id]["config_json"] = json.dumps(node.config, default=str)
        nodes_map[node.id]["position_json"] = json.dumps(node.position or {}, default=str)
        nodes_order.append(node.id)
    for edge in canvas_doc.edges:
        edge_record = pycrdt.Map()
        edges_map[edge.id] = edge_record
        edges_map[edge.id]["source_node_id"] = edge.source_node_id
        edges_map[edge.id]["source_pin"] = edge.source_pin
        edges_map[edge.id]["target_node_id"] = edge.target_node_id
        edges_map[edge.id]["target_pin"] = edge.target_pin
        edges_order.append(edge.id)


def _read_granular(doc: Any) -> CanvasDoc | None:
    """Reconstruct a `CanvasDoc` from the granular Y.Maps.

    Returns ``None`` only when the granular schema marker is absent
    AND the maps are empty — that lets the caller treat "untouched
    doc" differently from "intentionally empty canvas".
    """
    assert pycrdt is not None  # noqa: S101 — module-level None guard runs at import
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    schema_version = canvas_map.get("schema_version")
    nodes_order = doc.get("nodes_order", type=pycrdt.Array)
    nodes_map = doc.get("nodes_map", type=pycrdt.Map)
    edges_order = doc.get("edges_order", type=pycrdt.Array)
    edges_map = doc.get("edges_map", type=pycrdt.Map)
    if schema_version != _SCHEMA_VERSION and len(nodes_order) == 0 and len(nodes_map) == 0:
        return None
    nodes: list[CanvasNode] = []
    for node_id in nodes_order:
        node_id_str = str(node_id)
        record = nodes_map.get(node_id_str)
        if record is None:
            continue
        block_type = str(record.get("block_type") or "")
        if not block_type:
            continue
        try:
            config = json.loads(str(record.get("config_json") or "{}"))
        except ValueError, json.JSONDecodeError:
            config = {}
        position_raw = record.get("position_json")
        position: dict[str, Any] | None = None
        if position_raw:
            try:
                parsed = json.loads(str(position_raw))
                if isinstance(parsed, dict) and parsed:
                    position = parsed
            except ValueError, json.JSONDecodeError:
                position = None
        nodes.append(
            CanvasNode(
                id=node_id_str,
                block_type=block_type,
                config=config,
                position=position,
            )
        )
    edges: list[CanvasEdge] = []
    for edge_id in edges_order:
        edge_id_str = str(edge_id)
        record = edges_map.get(edge_id_str)
        if record is None:
            continue
        edges.append(
            CanvasEdge(
                id=edge_id_str,
                source_node_id=str(record.get("source_node_id") or ""),
                source_pin=str(record.get("source_pin") or ""),
                target_node_id=str(record.get("target_node_id") or ""),
                target_pin=str(record.get("target_pin") or ""),
            )
        )
    return CanvasDoc(nodes=nodes, edges=edges)


def _read_legacy_json_slot(doc: Any) -> CanvasDoc | None:
    """Fall back to the v1 ``canvas/json`` slot for in-flight migrations."""
    assert pycrdt is not None  # noqa: S101 — module-level None guard runs at import
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    payload = canvas_map.get("json")
    if not isinstance(payload, str) or not payload.strip():
        return None
    try:
        return CanvasDoc.model_validate_json(payload)
    except ValueError, json.JSONDecodeError:
        return None


def get_or_init_canvas_ydoc(factory: sessionmaker[Session], *, data_product_id: int) -> Any:
    """Return a fresh :class:`pycrdt.Doc` seeded from the latest saved canvas.

    Always populates the granular ``nodes_*`` / ``edges_*`` maps so
    new co-edit sessions start on the v2 shape.  Legacy v1 payloads
    are migrated on read by :func:`extract_canvas_doc` so a hub
    spun up from a fresh v1-only Y.Doc is still parseable.
    """
    if pycrdt is None:  # pragma: no cover
        raise RuntimeError("pycrdt is required for canvas co-edit; pip install pycrdt")
    doc = pycrdt.Doc()
    latest = load_latest_graph(factory, data_product_id=data_product_id)
    seed_doc = latest[0] if latest is not None else CanvasDoc(nodes=[], edges=[])
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    canvas_map["schema_version"] = _SCHEMA_VERSION
    _seed_granular_from_canvas(doc, seed_doc)
    return doc


def extract_canvas_doc(doc: Any) -> CanvasDoc | None:
    """Pull the :class:`CanvasDoc` out of a live Y.Doc — ``None`` on parse error.

    Prefers the granular v2 maps; falls back to the legacy v1 single-
    slot JSON payload when the granular shape is empty, which covers
    co-edit sessions started from a hub that hasn't migrated yet.
    """
    if pycrdt is None:  # pragma: no cover
        return None
    granular = _read_granular(doc)
    if granular is not None:
        return granular
    legacy = _read_legacy_json_slot(doc)
    if legacy is not None:
        # Auto-migrate: seed the granular maps from the v1 payload so the
        # next read takes the fast path.
        _seed_granular_from_canvas(doc, legacy)
        assert pycrdt is not None  # noqa: S101
        canvas_map = doc.get("canvas", type=pycrdt.Map)
        if "json" in canvas_map:
            del canvas_map["json"]
        canvas_map["schema_version"] = _SCHEMA_VERSION
        return legacy
    return None


def persist_canvas_ydoc(
    factory: sessionmaker[Session],
    *,
    data_product_id: int,
    doc: Any,
    author_user_id: int | None,
) -> int | None:
    """Persist the live Y.Doc into a fresh ``data_product_canvas_graph`` row.

    Returns the new ``version`` integer or ``None`` if the Y.Doc
    payload cannot be parsed as a :class:`CanvasDoc`.
    """
    canvas_doc = extract_canvas_doc(doc)
    if canvas_doc is None:
        return None
    latest = load_latest_graph(factory, data_product_id=data_product_id)
    if latest is not None and latest[0] == canvas_doc:
        # No structural change — skip the version bump so an idle hub
        # doesn't append a flood of identical rows over time.
        return latest[1]
    return save_graph(
        factory,
        data_product_id=data_product_id,
        doc=canvas_doc,
        author_user_id=author_user_id,
    )


__all__ = [
    "extract_canvas_doc",
    "get_or_init_canvas_ydoc",
    "persist_canvas_ydoc",
]
