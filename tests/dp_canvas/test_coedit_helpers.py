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
    result = persist_canvas_ydoc(
        factory, data_product_id=dp_id, doc=doc, author_user_id=None
    )
    assert result == v1


def test_persist_canvas_ydoc_bumps_version_on_change() -> None:
    pytest.importorskip("pycrdt")
    import pycrdt

    dp_id = _seed_dp("coedit_bump")
    factory = app.state.session_factory
    doc = get_or_init_canvas_ydoc(factory, data_product_id=dp_id)
    new_payload = CanvasDoc(
        nodes=[CanvasNode(id="inp2", block_type="InputPort", config={"table_fqn": "x.y.z"})],
        edges=[],
    ).model_dump_json()
    canvas_map = doc.get("canvas", type=pycrdt.Map)
    canvas_map["json"] = new_payload
    v = persist_canvas_ydoc(
        factory, data_product_id=dp_id, doc=doc, author_user_id=None
    )
    assert v is not None
    assert v >= 1
