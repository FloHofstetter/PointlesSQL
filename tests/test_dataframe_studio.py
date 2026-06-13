"""Tests for the DataFrame Studio consumer logic.

The Studio is deliberately thin — its only unique behaviour is the
disallowed-block guard (no sinks, no DataProduct drill-in) wrapped around
the shared ``compile_to_select``.  The run / schema-flow paths it exposes
over HTTP are the already-tested ``preview_until`` / ``validate_schema_flow``
machinery, so these tests pin the guard + the compile wrapper.

Importing ``dp_canvas`` registers the source blocks (InputPort, …) into the
shared registry so the slices below resolve.
"""

from __future__ import annotations

import pointlessql.services.dp_canvas as _dp_canvas  # noqa: F401  (registers source blocks)
from pointlessql.services.canvas_df import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    ColumnSpec,
    PinSchema,
)
from pointlessql.services.dataframe_studio import (
    DISALLOWED_BLOCKS,
    compile_studio_select,
    disallowed_block_errors,
)


def _seed(node_id: str) -> dict[str, PinSchema]:
    return {
        node_id: PinSchema(
            kind="table",
            columns=[ColumnSpec(name="amount", duckdb_type="INT", nullable=True)],
        )
    }


def _src_filter_doc() -> CanvasDoc:
    return CanvasDoc(
        nodes=[
            CanvasNode(id="src", block_type="InputPort", config={"table_fqn": "main.s.orders"}),
            CanvasNode(id="flt", block_type="Filter", config={"predicate": "amount > 0"}),
        ],
        edges=[
            CanvasEdge(
                id="e1",
                source_node_id="src",
                source_pin="out",
                target_node_id="flt",
                target_pin="in",
            )
        ],
    )


def test_disallowed_blocks_constant() -> None:
    assert DISALLOWED_BLOCKS == frozenset({"OutputPort", "FileOutput", "DataProduct"})


def test_disallowed_block_errors_flags_each_sink() -> None:
    doc = CanvasDoc(
        nodes=[
            CanvasNode(id="src", block_type="InputPort", config={"table_fqn": "main.s.o"}),
            CanvasNode(id="out", block_type="OutputPort", config={}),
            CanvasNode(id="f", block_type="FileOutput", config={}),
        ],
        edges=[],
    )
    errors = disallowed_block_errors(doc)
    flagged = {e.node_id for e in errors}
    assert flagged == {"out", "f"}
    assert all(e.kind == "bad_config" for e in errors)


def test_disallowed_block_errors_clean_doc() -> None:
    assert disallowed_block_errors(_src_filter_doc()) == []


def test_compile_studio_select_ok() -> None:
    doc = _src_filter_doc()
    result, errors = compile_studio_select(
        doc, terminal_node_id="flt", upstream_schemas=_seed("src")
    )
    assert errors == []
    assert result is not None
    assert result.sql.strip().endswith("SELECT * FROM n1_filter")
    assert "LIMIT" not in result.sql
    assert [c.name for c in result.output_schema.columns] == ["amount"]


def test_compile_studio_select_rejects_sink() -> None:
    doc = _src_filter_doc()
    doc.nodes.append(
        CanvasNode(id="out", block_type="OutputPort", config={"materialized_table": "a.b.c"})
    )
    doc.edges.append(
        CanvasEdge(
            id="e2",
            source_node_id="flt",
            source_pin="out",
            target_node_id="out",
            target_pin="in",
        )
    )
    result, errors = compile_studio_select(
        doc, terminal_node_id="flt", upstream_schemas=_seed("src")
    )
    assert result is None
    assert any(e.node_id == "out" and "not available" in e.message for e in errors)


def test_seed_schemas_skips_malformed_fqn_without_soyuz(monkeypatch) -> None:
    """A malformed input-port FQN must not be sent to soyuz.

    soyuz answers a bad ``full_name`` with a non-404 error the lookup
    re-raises, which 500'd the compile / preview / validate call. The seed
    pass now skips such names so the block compiler reports the same
    ``bad_config`` the editor already shows on the node.
    """
    from pointlessql.api.data_products_routes.canvas import _helpers

    def _boom(client: object, fqn: str) -> object:
        raise AssertionError(f"soyuz must not be queried for malformed FQN {fqn!r}")

    monkeypatch.setattr(_helpers, "fetch_table_info", _boom)
    for bad in ("demo", "demo.sales", "demo.", ".s.t", "a.b.c.d"):
        doc = CanvasDoc(
            nodes=[CanvasNode(id="src", block_type="InputPort", config={"table_fqn": bad})],
            edges=[],
        )
        seeds, errors = _helpers.seed_schemas_for_doc(doc, client=object())  # type: ignore[arg-type]
        assert seeds == {}, bad
        assert errors == [], bad


def test_seed_schemas_queries_soyuz_for_valid_fqn(monkeypatch) -> None:
    """A well-formed three-part FQN still reaches soyuz."""
    from pointlessql.api.data_products_routes.canvas import _helpers

    calls: list[str] = []

    def _record(client: object, fqn: str) -> None:
        calls.append(fqn)
        return None

    monkeypatch.setattr(_helpers, "fetch_table_info", _record)
    doc = CanvasDoc(
        nodes=[
            CanvasNode(id="src", block_type="InputPort", config={"table_fqn": "demo.sales.orders"})
        ],
        edges=[],
    )
    seeds, errors = _helpers.seed_schemas_for_doc(doc, client=object())  # type: ignore[arg-type]
    assert calls == ["demo.sales.orders"]
    assert seeds == {}
    # fetch returned None → the table-missing path emits a bad_config.
    assert [e.kind for e in errors] == ["bad_config"]
