"""Verify CanvasDoc.metadata round-trips through the storage layer.

Sticky-note annotations ride along in ``metadata.annotations`` so
they're persisted across save / load, but they MUST stay out of the
compile graph (no node, no edge, no validation envelope).
"""

from __future__ import annotations

import json

from pointlessql.services.dp_canvas._types import CanvasDoc, CanvasNode


def test_metadata_roundtrip_through_model_json() -> None:
    notes = [
        {"id": "n1", "x": 10, "y": 20, "width": 220, "height": 120, "content": "dedupe upstream"},
        {"id": "n2", "x": 80, "y": 200, "width": 160, "height": 80, "content": ""},
    ]
    doc = CanvasDoc(
        nodes=[CanvasNode(id="inp", block_type="InputPort", config={"table_fqn": "main.t"})],
        edges=[],
        metadata={"annotations": notes},
    )
    raw = doc.model_dump_json()
    back = CanvasDoc.model_validate_json(raw)
    assert back.metadata == {"annotations": notes}


def test_metadata_default_empty_dict() -> None:
    doc = CanvasDoc.model_validate_json(json.dumps({"nodes": [], "edges": []}))
    assert doc.metadata == {}


def test_annotations_dont_leak_into_nodes_or_edges() -> None:
    doc = CanvasDoc(
        nodes=[CanvasNode(id="inp", block_type="InputPort", config={"table_fqn": "t"})],
        edges=[],
        metadata={"annotations": [{"id": "a", "x": 1, "y": 1, "content": "hi"}]},
    )
    assert len(doc.nodes) == 1
    assert len(doc.edges) == 0
    assert doc.nodes[0].id == "inp"
