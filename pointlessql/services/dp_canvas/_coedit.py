"""Per-canvas in-memory Y.Doc state used by the co-edit WS hub.

Wraps :mod:`pycrdt` so the hub's WebSocket endpoint can stay tiny:
the service owns ``get_or_init_canvas_ydoc`` (seed from the saved
canvas if any) and ``persist_canvas_ydoc`` (mirror the live Y.Map
back into the ``data_product_canvas_graph`` table by minting a new
version row through the existing :func:`save_graph`).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pointlessql.services.dp_canvas._storage import load_latest_graph, save_graph
from pointlessql.services.dp_canvas._types import CanvasDoc

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

try:  # pragma: no cover — exercised only when pycrdt is installed (already a project dep)
    import pycrdt
except ImportError:  # pragma: no cover
    pycrdt = None  # type: ignore[assignment]


def _doc_to_payload(doc: CanvasDoc) -> str:
    return doc.model_dump_json()


def _payload_to_doc(payload: str) -> CanvasDoc:
    return CanvasDoc.model_validate_json(payload)


def get_or_init_canvas_ydoc(
    factory: sessionmaker[Session], *, data_product_id: int
) -> Any:
    """Return a fresh :class:`pycrdt.Doc` seeded from the latest saved canvas.

    The Y.Doc's root ``canvas`` map carries one entry, ``"json"``,
    holding the serialised :class:`CanvasDoc`.  Storing the entire
    payload in a single Y.Text-ish slot keeps the protocol trivial
    for v1 — granular Y.Array of nodes can come in a later wave when
    fine-grained co-edit conflict resolution matters.
    """
    if pycrdt is None:  # pragma: no cover
        raise RuntimeError("pycrdt is required for canvas co-edit; pip install pycrdt")
    doc = pycrdt.Doc()
    latest = load_latest_graph(factory, data_product_id=data_product_id)
    if latest is not None:
        seed_doc = latest[0]
    else:
        seed_doc = CanvasDoc(nodes=[], edges=[])
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    canvas_map["json"] = _doc_to_payload(seed_doc)
    return doc


def extract_canvas_doc(doc: Any) -> CanvasDoc | None:
    """Pull the :class:`CanvasDoc` out of a live Y.Doc — ``None`` on parse error."""
    if pycrdt is None:  # pragma: no cover
        return None
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    payload = canvas_map.get("json")
    if not isinstance(payload, str) or not payload.strip():
        return None
    try:
        return _payload_to_doc(payload)
    except (ValueError, json.JSONDecodeError):
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
