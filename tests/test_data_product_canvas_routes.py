"""HTTP route tests for the visual data-product canvas editor.

Covers the five thin adapters in
``pointlessql.api.data_products_routes.canvas`` end-to-end against a
real ``app.state.session_factory`` and a stubbed soyuz client.  The
materialise route shares its UC-hitting code-path with the executor;
those are mocked the same way the executor's unit tests already do.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import MagicMock

import deltalake
import httpx
import pandas as pd
import pytest
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.column_info import ColumnInfo
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct
from pointlessql.services.dp_canvas import CanvasDoc
from tests.dp_canvas._helpers import edge, linear_doc, node

_EXECUTOR_MOD = "pointlessql.services.dp_canvas._executor"
_PREVIEW_MOD = "pointlessql.services.dp_canvas._preview"


def _seed_dp(
    *,
    schema_name: str = "canvas_routes",
    catalog: str = "main",
    steward_user_id: int | None = None,
) -> int:
    """Insert one DataProduct row and return its id."""
    now = datetime.datetime.now(datetime.UTC)
    factory = app.state.session_factory
    with factory.begin() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema_name,
            description="",
            version="1.0.0",
            sla_minutes=60,
            steward_user_id=steward_user_id,
            contract_yaml_hash=f"hash_{schema_name}",
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.flush()
        return dp.id


def _doc_dict(doc: CanvasDoc) -> dict[str, Any]:
    """Convert a CanvasDoc to a JSON-roundtripped dict for HTTP bodies."""
    return doc.model_dump(mode="json")


def _bare_doc() -> CanvasDoc:
    return linear_doc("main.canvas_routes.src", "main.canvas_routes.tgt")


# ---------------------------------------------------------------------------
# 148.1 — save + load + versions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_canvas_empty_returns_null(admin_client: httpx.AsyncClient) -> None:
    dp_id = _seed_dp()
    res = await admin_client.get(f"/api/dp/{dp_id}/canvas")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"document": None, "version": None, "created_at": None}


@pytest.mark.asyncio
async def test_save_canvas_creates_v1(admin_client: httpx.AsyncClient) -> None:
    dp_id = _seed_dp()
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={"document": _doc_dict(_bare_doc())},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == 1
    assert "created_at" in body


@pytest.mark.asyncio
async def test_save_then_save_again_increments_version(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp()
    payload = {"document": _doc_dict(_bare_doc())}
    r1 = await admin_client.post(f"/api/dp/{dp_id}/canvas", json=payload)
    r2 = await admin_client.post(f"/api/dp/{dp_id}/canvas", json=payload)
    assert (r1.json()["version"], r2.json()["version"]) == (1, 2)


@pytest.mark.asyncio
async def test_get_canvas_after_save_returns_doc(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp()
    await admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={"document": _doc_dict(_bare_doc())},
    )
    res = await admin_client.get(f"/api/dp/{dp_id}/canvas")
    body = res.json()
    assert body["version"] == 1
    assert body["document"] is not None
    assert len(body["document"]["nodes"]) == 2


@pytest.mark.asyncio
async def test_save_canvas_non_steward_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp(steward_user_id=999_999)
    res = await non_admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={"document": _doc_dict(_bare_doc())},
    )
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_get_canvas_non_steward_allowed(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Read access is open to any authenticated user (write is steward/admin)."""
    dp_id = _seed_dp(steward_user_id=999_999)
    res = await non_admin_client.get(f"/api/dp/{dp_id}/canvas")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_get_canvas_404_for_unknown_dp(
    admin_client: httpx.AsyncClient,
) -> None:
    res = await admin_client.get("/api/dp/999999/canvas")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_list_versions_returns_newest_first(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp()
    payload = {"document": _doc_dict(_bare_doc())}
    await admin_client.post(f"/api/dp/{dp_id}/canvas", json=payload)
    await admin_client.post(f"/api/dp/{dp_id}/canvas", json=payload)
    await admin_client.post(f"/api/dp/{dp_id}/canvas", json=payload)
    res = await admin_client.get(f"/api/dp/{dp_id}/canvas/versions")
    assert res.status_code == 200
    versions = res.json()["versions"]
    assert [v["version"] for v in versions] == [3, 2, 1]


@pytest.mark.asyncio
async def test_save_optimistic_concurrency_conflict(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp()
    payload = {"document": _doc_dict(_bare_doc())}
    await admin_client.post(f"/api/dp/{dp_id}/canvas", json=payload)
    # Caller assumes the canvas is still at v0 but the server is at v1.
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={"document": _doc_dict(_bare_doc()), "expected_base_version": 0},
    )
    assert res.status_code == 422, res.text
    assert "conflict" in res.text.lower()


# ---------------------------------------------------------------------------
# 148.2 — round-trip + larger doc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roundtrip_complex_doc(admin_client: httpx.AsyncClient) -> None:
    """A doc using every block type round-trips losslessly through save+load."""
    dp_id = _seed_dp(schema_name="canvas_complex")
    doc = CanvasDoc(
        nodes=[
            node("inp_a", "InputPort", {"table_fqn": "main.complex.a"}),
            node("inp_b", "InputPort", {"table_fqn": "main.complex.b"}),
            node("flt", "Filter", {"predicate": "amount > 0"}),
            node("prj", "Project", {"columns": ["id", "amount"]}),
            node("jn", "Join", {"how": "left", "keys": ["id"]}),
            node(
                "gb",
                "GroupBy",
                {
                    "keys": ["id"],
                    "aggregations": [
                        {"column": "amount", "fn": "sum", "alias": "total"}
                    ],
                },
            ),
            node("lim", "Limit", {"n": 10}),
            node("sql", "SQL", {"query": "SELECT * FROM {{in}}"}),
            node(
                "out",
                "OutputPort",
                {
                    "port_name": "primary",
                    "materialized_table": "main.complex.tgt",
                    "mode": "overwrite",
                },
            ),
        ],
        edges=[
            edge("e1", "inp_a", "out", "flt", "in"),
            edge("e2", "flt", "out", "prj", "in"),
            edge("e3", "prj", "out", "jn", "left"),
            edge("e4", "inp_b", "out", "jn", "right"),
            edge("e5", "jn", "out", "gb", "in"),
            edge("e6", "gb", "out", "lim", "in"),
            edge("e7", "lim", "out", "sql", "in"),
            edge("e8", "sql", "out", "out", "in"),
        ],
    )

    save_res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={"document": _doc_dict(doc)},
    )
    assert save_res.status_code == 200

    load_res = await admin_client.get(f"/api/dp/{dp_id}/canvas")
    body = load_res.json()
    roundtripped = CanvasDoc.model_validate(body["document"])
    assert roundtripped == doc


# ---------------------------------------------------------------------------
# 148.3 — validate
# ---------------------------------------------------------------------------


def _stub_uc_client(monkeypatch, *, columns_by_fqn: dict[str, list[ColumnInfo]]):
    """Swap ``app.state.uc_client._client`` for a stub whose ``_get_table.sync``
    returns the supplied columns per FQN.
    """
    import pointlessql.api.data_products_routes.canvas as canvas_module

    fake_get_table = MagicMock()

    def _table_sync(*, client: Any, full_name: str) -> Any:
        if full_name in columns_by_fqn:
            return TableInfo(name=full_name.split(".")[-1], columns=columns_by_fqn[full_name])
        raise UnexpectedStatus(404, b"Not Found")

    fake_get_table.sync.side_effect = _table_sync
    monkeypatch.setattr(canvas_module, "_get_table", fake_get_table)


@pytest.mark.asyncio
async def test_validate_valid_doc_zero_errors(
    admin_client: httpx.AsyncClient, monkeypatch
) -> None:
    dp_id = _seed_dp(schema_name="canvas_valid")
    _stub_uc_client(
        monkeypatch,
        columns_by_fqn={
            "main.canvas_valid.src": [
                ColumnInfo(name="id", type_text="BIGINT", nullable=False),
                ColumnInfo(name="amount", type_text="DOUBLE", nullable=True),
            ],
        },
    )
    doc = linear_doc(
        "main.canvas_valid.src", "main.canvas_valid.tgt", predicate="amount > 0"
    )
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/validate",
        json={"document": _doc_dict(doc)},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["errors"] == []
    assert "inp:out" in body["pin_schemas"]


@pytest.mark.asyncio
async def test_validate_unknown_input_table_emits_bad_config(
    admin_client: httpx.AsyncClient, monkeypatch
) -> None:
    dp_id = _seed_dp(schema_name="canvas_404src")
    _stub_uc_client(monkeypatch, columns_by_fqn={})
    doc = linear_doc("main.canvas_404src.src", "main.canvas_404src.tgt")
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/validate",
        json={"document": _doc_dict(doc)},
    )
    assert res.status_code == 200, res.text
    errors = res.json()["errors"]
    assert any(e["kind"] == "bad_config" for e in errors)


@pytest.mark.asyncio
async def test_validate_404_unknown_dp(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post(
        "/api/dp/999999/canvas/validate",
        json={"document": _doc_dict(_bare_doc())},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 148.5 — materialize
# ---------------------------------------------------------------------------


def _install_executor_patches(
    monkeypatch, *, source_paths: dict[str, str], target_schema_root: str
):
    """Patch the executor module's soyuz handles (same as test_executor)."""
    get_table = MagicMock()
    get_schema = MagicMock()
    create_table = MagicMock()

    def _table_sync(*, client: Any, full_name: str) -> Any:
        if full_name in source_paths:
            return TableInfo(
                name=full_name.split(".")[-1],
                storage_location=source_paths[full_name],
            )
        raise UnexpectedStatus(404, b"Not Found")

    def _schema_sync(*, client: Any, full_name: str) -> Any:
        return SchemaInfo(storage_root=target_schema_root)

    get_table.sync.side_effect = _table_sync
    get_schema.sync.side_effect = _schema_sync
    create_table.sync.return_value = TableInfo(name="created")

    monkeypatch.setattr(f"{_EXECUTOR_MOD}._get_table", get_table)
    monkeypatch.setattr(f"{_EXECUTOR_MOD}._get_schema", get_schema)
    monkeypatch.setattr(f"{_EXECUTOR_MOD}._create_table", create_table)


@pytest.mark.asyncio
async def test_materialize_writes_rows_and_registers_port(
    admin_client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    dp_id = _seed_dp(schema_name="mat_simple")
    src_path = str(tmp_path / "src_mat")
    deltalake.write_deltalake(
        src_path,
        pd.DataFrame({"id": [1, 2, 3], "amt": [10, 20, 30]}),
        mode="overwrite",
    )
    target_root = str(tmp_path / "mat_root")
    _install_executor_patches(
        monkeypatch,
        source_paths={"main.mat_simple.src": src_path},
        target_schema_root=target_root,
    )

    doc = linear_doc(
        "main.mat_simple.src",
        "main.mat_simple.tgt",
        predicate="amt > 10",
        port_name="primary",
    )
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/materialize",
        json={"document": _doc_dict(doc)},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rows_written"] == 2
    assert body["target_fqn"] == "main.mat_simple.tgt"
    assert body["graph_version"] >= 1

    # Output port row exists on the DP.
    factory = app.state.session_factory
    with factory() as session:
        from pointlessql.models import DataProductOutputPort

        port = session.execute(
            select(DataProductOutputPort).where(
                DataProductOutputPort.data_product_id == dp_id,
                DataProductOutputPort.name == "primary",
            )
        ).scalar_one()
    assert port.location == "main.mat_simple.tgt"


@pytest.mark.asyncio
async def test_materialize_compile_failure_returns_422(
    admin_client: httpx.AsyncClient,
) -> None:
    """Doc without an OutputPort fails compile → ValidationError → 422."""
    dp_id = _seed_dp(schema_name="mat_noout")
    doc = CanvasDoc(
        nodes=[node("inp", "InputPort", {"table_fqn": "main.mat_noout.src"})],
        edges=[],
    )
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/materialize",
        json={"document": _doc_dict(doc)},
    )
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_materialize_404_unknown_dp(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post(
        "/api/dp/999999/canvas/materialize",
        json={"document": _doc_dict(_bare_doc())},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 149.1 — per-node preview
# ---------------------------------------------------------------------------


def _install_preview_patches(
    monkeypatch,
    *,
    source_paths_to_columns: dict[str, tuple[str, list[ColumnInfo]]],
):
    """Patch both seeding (canvas route) and storage-resolve (preview helper).

    ``source_paths_to_columns`` maps each FQN to ``(delta_path, columns)``.
    The seed-side returns ``ColumnInfo`` lists so the editor's schema-flow
    has real types; the preview-side returns ``storage_location`` so
    DuckDB can attach a Delta view.
    """
    import pointlessql.api.data_products_routes.canvas as canvas_module

    seed_table = MagicMock()
    preview_table = MagicMock()

    def _seed_sync(*, client: Any, full_name: str) -> Any:
        if full_name in source_paths_to_columns:
            _, columns = source_paths_to_columns[full_name]
            return TableInfo(name=full_name.split(".")[-1], columns=columns)
        raise UnexpectedStatus(404, b"Not Found")

    def _preview_sync(*, client: Any, full_name: str) -> Any:
        if full_name in source_paths_to_columns:
            location, _ = source_paths_to_columns[full_name]
            return TableInfo(
                name=full_name.split(".")[-1], storage_location=location
            )
        raise UnexpectedStatus(404, b"Not Found")

    seed_table.sync.side_effect = _seed_sync
    preview_table.sync.side_effect = _preview_sync
    monkeypatch.setattr(canvas_module, "_get_table", seed_table)
    monkeypatch.setattr(f"{_PREVIEW_MOD}._get_table", preview_table)


@pytest.mark.asyncio
async def test_preview_input_port_returns_rows(
    admin_client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    dp_id = _seed_dp(schema_name="prev_inp")
    src_path = str(tmp_path / "prev_inp_src")
    deltalake.write_deltalake(
        src_path,
        pd.DataFrame({"id": [1, 2, 3], "amt": [10, 20, 30]}),
        mode="overwrite",
    )
    _install_preview_patches(
        monkeypatch,
        source_paths_to_columns={
            "main.prev_inp.src": (
                src_path,
                [
                    ColumnInfo(name="id", type_text="BIGINT", nullable=False),
                    ColumnInfo(name="amt", type_text="BIGINT", nullable=True),
                ],
            ),
        },
    )
    doc = linear_doc("main.prev_inp.src", "main.prev_inp.tgt")
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/preview",
        json={
            "document": _doc_dict(doc),
            "upto_node_id": "inp",
            "limit": 10,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["errors"] == []
    assert sorted(body["columns"]) == ["amt", "id"]
    assert len(body["rows"]) == 3
    assert body["truncated"] is False


@pytest.mark.asyncio
async def test_preview_filter_applies_predicate(
    admin_client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    dp_id = _seed_dp(schema_name="prev_flt")
    src_path = str(tmp_path / "prev_flt_src")
    deltalake.write_deltalake(
        src_path,
        pd.DataFrame({"id": [1, 2, 3, 4], "amt": [5, 15, 25, 35]}),
        mode="overwrite",
    )
    _install_preview_patches(
        monkeypatch,
        source_paths_to_columns={
            "main.prev_flt.src": (
                src_path,
                [
                    ColumnInfo(name="id", type_text="BIGINT", nullable=False),
                    ColumnInfo(name="amt", type_text="BIGINT", nullable=True),
                ],
            ),
        },
    )
    doc = linear_doc(
        "main.prev_flt.src", "main.prev_flt.tgt", predicate="amt > 10"
    )
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/preview",
        json={
            "document": _doc_dict(doc),
            "upto_node_id": "flt",
            "limit": 100,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["errors"] == []
    assert len(body["rows"]) == 3


@pytest.mark.asyncio
async def test_preview_limit_truncates(
    admin_client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    dp_id = _seed_dp(schema_name="prev_lim")
    src_path = str(tmp_path / "prev_lim_src")
    deltalake.write_deltalake(
        src_path,
        pd.DataFrame({"id": list(range(10))}),
        mode="overwrite",
    )
    _install_preview_patches(
        monkeypatch,
        source_paths_to_columns={
            "main.prev_lim.src": (
                src_path,
                [ColumnInfo(name="id", type_text="BIGINT", nullable=False)],
            ),
        },
    )
    doc = linear_doc("main.prev_lim.src", "main.prev_lim.tgt")
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/preview",
        json={
            "document": _doc_dict(doc),
            "upto_node_id": "inp",
            "limit": 4,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["rows"]) == 4
    assert body["truncated"] is True


@pytest.mark.asyncio
async def test_preview_unknown_node_returns_404(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp(schema_name="prev_404")
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/preview",
        json={
            "document": _doc_dict(_bare_doc()),
            "upto_node_id": "does_not_exist",
            "limit": 10,
        },
    )
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_diff_two_versions_surfaces_modified_node(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp(schema_name="diffroute")
    await admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={
            "document": _doc_dict(
                linear_doc(
                    "main.diffroute.src", "main.diffroute.tgt", predicate="x > 0"
                )
            )
        },
    )
    await admin_client.post(
        f"/api/dp/{dp_id}/canvas",
        json={
            "document": _doc_dict(
                linear_doc(
                    "main.diffroute.src", "main.diffroute.tgt", predicate="x > 99"
                )
            )
        },
    )
    res = await admin_client.get(
        f"/api/dp/{dp_id}/canvas/diff?from_version=1&to_version=2"
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["from_version"] == 1
    assert body["to_version"] == 2
    modified = body["diff"]["modified_nodes"]
    assert any(n["id"] == "flt" for n in modified)


@pytest.mark.asyncio
async def test_load_specific_version_returns_doc(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp(schema_name="vload")
    # Save v1 + v2.
    for predicate in ("amt > 1", "amt > 100"):
        await admin_client.post(
            f"/api/dp/{dp_id}/canvas",
            json={
                "document": _doc_dict(
                    linear_doc("main.vload.src", "main.vload.tgt", predicate=predicate)
                )
            },
        )
    res = await admin_client.get(f"/api/dp/{dp_id}/canvas/versions/1")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == 1
    flt = next(n for n in body["document"]["nodes"] if n["block_type"] == "Filter")
    assert flt["config"]["predicate"] == "amt > 1"


@pytest.mark.asyncio
async def test_load_unknown_version_404(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp(schema_name="vmiss")
    res = await admin_client.get(f"/api/dp/{dp_id}/canvas/versions/999")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_preview_output_port_rejected(
    admin_client: httpx.AsyncClient,
) -> None:
    dp_id = _seed_dp(schema_name="prev_outport")
    res = await admin_client.post(
        f"/api/dp/{dp_id}/canvas/preview",
        json={
            "document": _doc_dict(_bare_doc()),
            "upto_node_id": "out",
            "limit": 10,
        },
    )
    assert res.status_code == 422, res.text
