"""Unit tests for the co-edit service helpers in dp_canvas/_coedit.py.

The WebSocket endpoint is excercised by manual browser replay; the
service helpers are pure-Python and trivially testable in isolation.
"""

from __future__ import annotations

import datetime

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct
from pointlessql.services.dp_canvas import CanvasDoc, CanvasNode, save_graph
from pointlessql.services.dp_canvas._coedit import (
    extract_canvas_doc,
    get_or_init_canvas_ydoc,
    persist_canvas_ydoc,
)


def _seed_dp(schema_name: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    factory = app.state.session_factory
    with factory.begin() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="main",
            schema_name=schema_name,
            description="",
            version="1.0.0",
            sla_minutes=60,
            steward_user_id=None,
            contract_yaml_hash=f"h_{schema_name}",
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.flush()
        return dp.id


def test_get_or_init_ydoc_returns_empty_canvas_when_no_saved_graph() -> None:
    pytest.importorskip("pycrdt")
    dp_id = _seed_dp("coedit_empty")
    factory = app.state.session_factory
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    canvas = extract_canvas_doc(doc)
    assert canvas is not None
    assert canvas.nodes == []
    assert canvas.edges == []


def test_get_or_init_ydoc_seeds_from_latest_saved_graph() -> None:
    pytest.importorskip("pycrdt")
    dp_id = _seed_dp("coedit_seeded")
    factory = app.state.session_factory
    seed = CanvasDoc(
        nodes=[CanvasNode(id="inp", block_type="InputPort", config={"table_fqn": "a.b.c"})],
        edges=[],
    )
    save_graph(factory, data_product_id=dp_id, doc=seed, author_user_id=None)
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    canvas = extract_canvas_doc(doc)
    assert canvas is not None
    assert canvas.nodes[0].id == "inp"


def test_persist_canvas_ydoc_skips_when_no_change() -> None:
    pytest.importorskip("pycrdt")
    dp_id = _seed_dp("coedit_skip")
    factory = app.state.session_factory
    seed = CanvasDoc(
        nodes=[CanvasNode(id="inp", block_type="InputPort", config={"table_fqn": "a.b.c"})],
        edges=[],
    )
    v1 = save_graph(factory, data_product_id=dp_id, doc=seed, author_user_id=None)
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    # No changes between fetched seed and current state → persist returns same version.
    result = persist_canvas_ydoc(factory, data_product_id=dp_id, doc=doc, author_user_id=None)
    assert result == v1


def test_persist_canvas_ydoc_bumps_version_on_change() -> None:
    pytest.importorskip("pycrdt")
    import pycrdt

    dp_id = _seed_dp("coedit_bump")
    factory = app.state.session_factory
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    # Push a new node via the granular maps (mirrors what the frontend
    # client does post Phase 160).
    nodes_map = doc.get("nodes_map", type=pycrdt.Map)
    nodes_order = doc.get("nodes_order", type=pycrdt.Array)
    rec = pycrdt.Map()
    nodes_map["inp2"] = rec
    nodes_map["inp2"]["block_type"] = "InputPort"
    nodes_map["inp2"]["config_json"] = '{"table_fqn": "x.y.z"}'
    nodes_map["inp2"]["position_json"] = "{}"
    nodes_order.append("inp2")
    v = persist_canvas_ydoc(factory, data_product_id=dp_id, doc=doc, author_user_id=None)
    assert v is not None
    assert v >= 1


# ---------------------------------------------------------------------------
# Phase 160 — granular per-block Y.Doc sync
# ---------------------------------------------------------------------------


def test_get_or_init_creates_granular_maps() -> None:
    pytest.importorskip("pycrdt")
    import pycrdt

    dp_id = _seed_dp("coedit_granular_init")
    factory = app.state.session_factory
    seed = CanvasDoc(
        nodes=[CanvasNode(id="n1", block_type="InputPort", config={"table_fqn": "a.b.c"})],
        edges=[],
    )
    save_graph(factory, data_product_id=dp_id, doc=seed, author_user_id=None)
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    nodes_order = doc.get("nodes_order", type=pycrdt.Array)
    nodes_map = doc.get("nodes_map", type=pycrdt.Map)
    assert canvas_map["schema_version"] == "v2"
    assert len(nodes_order) == 1
    assert "n1" in nodes_map


def test_persist_reads_from_granular_maps() -> None:
    pytest.importorskip("pycrdt")
    import pycrdt

    dp_id = _seed_dp("coedit_read_granular")
    factory = app.state.session_factory
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    nodes_map = doc.get("nodes_map", type=pycrdt.Map)
    nodes_order = doc.get("nodes_order", type=pycrdt.Array)
    rec = pycrdt.Map()
    nodes_map["filt"] = rec
    nodes_map["filt"]["block_type"] = "Filter"
    nodes_map["filt"]["config_json"] = '{"predicate": "amt > 10"}'
    nodes_map["filt"]["position_json"] = "{}"
    nodes_order.append("filt")
    v = persist_canvas_ydoc(factory, data_product_id=dp_id, doc=doc, author_user_id=None)
    assert v == 1
    canvas = extract_canvas_doc(doc)
    assert canvas is not None
    assert canvas.nodes[0].block_type == "Filter"
    assert canvas.nodes[0].config["predicate"] == "amt > 10"


def test_extract_falls_back_to_legacy_json_slot() -> None:
    pytest.importorskip("pycrdt")
    import pycrdt

    dp_id = _seed_dp("coedit_legacy_fallback")
    factory = app.state.session_factory
    # Skip get_or_init so we manufacture a pure-v1 Y.Doc (legacy slot only).
    doc = pycrdt.Doc()
    legacy_payload = CanvasDoc(
        nodes=[CanvasNode(id="legacy", block_type="InputPort", config={"table_fqn": "x.y.z"})],
        edges=[],
    ).model_dump_json()
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    canvas_map["json"] = legacy_payload
    extracted = extract_canvas_doc(doc)
    assert extracted is not None
    assert extracted.nodes[0].id == "legacy"
    # First extract should auto-migrate: granular maps now populated,
    # legacy slot cleared.
    nodes_order = doc.get("nodes_order", type=pycrdt.Array)
    assert len(nodes_order) == 1
    assert "json" not in canvas_map
    # Persist round-trip still works.
    v = persist_canvas_ydoc(factory, data_product_id=dp_id, doc=doc, author_user_id=None)
    assert v is not None and v >= 1


def test_concurrent_node_edits_do_not_conflict() -> None:
    """Two simulated peers add different nodes; both survive."""
    pytest.importorskip("pycrdt")
    import pycrdt

    dp_id = _seed_dp("coedit_concurrent")
    factory = app.state.session_factory
    # Peer A: starts the doc, adds a node.
    doc_a = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    nodes_map_a = doc_a.get("nodes_map", type=pycrdt.Map)
    nodes_order_a = doc_a.get("nodes_order", type=pycrdt.Array)
    rec_a = pycrdt.Map()
    nodes_map_a["a"] = rec_a
    nodes_map_a["a"]["block_type"] = "InputPort"
    nodes_map_a["a"]["config_json"] = "{}"
    nodes_map_a["a"]["position_json"] = "{}"
    nodes_order_a.append("a")
    state_a = doc_a.get_update()
    # Peer B: clones the doc from A's update, adds a different node.
    doc_b = pycrdt.Doc()
    doc_b.apply_update(state_a)
    nodes_map_b = doc_b.get("nodes_map", type=pycrdt.Map)
    nodes_order_b = doc_b.get("nodes_order", type=pycrdt.Array)
    rec_b = pycrdt.Map()
    nodes_map_b["b"] = rec_b
    nodes_map_b["b"]["block_type"] = "Filter"
    nodes_map_b["b"]["config_json"] = '{"predicate": "1=1"}'
    nodes_map_b["b"]["position_json"] = "{}"
    nodes_order_b.append("b")
    # Merge B's update back into A.
    doc_a.apply_update(doc_b.get_update())
    canvas = extract_canvas_doc(doc_a)
    assert canvas is not None
    ids = {n.id for n in canvas.nodes}
    assert ids == {"a", "b"}
