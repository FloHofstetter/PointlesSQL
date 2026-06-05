"""Behaviour tests that pin down ``pql.aggregate`` against mutation.

These tests target the observable contract of the three building
blocks in :mod:`pointlessql.pql._aggregate`:

* ``aggregate_table`` — the end-to-end primitive.  Driven here with a
  fake engine and stubbed catalog hops so the return dict, the audit
  ``params`` / ``extra_params`` payloads, and the recorder's pending
  lineage/column edges are all asserted exactly.
* ``_build_aggregate_frame`` — the groupby + deterministic
  ``_lineage_row_id`` stamper, asserted for exact output schema,
  aggregation values, fan-in mapping, and the no-lineage branch.
* ``_build_aggregate_column_edges`` — the column-lineage translator,
  asserted field-by-field across every branch (identity, aggregate,
  derived, unknown-origin, missing-derivation-reference, synth row id).

The aim is exact-value coverage: every emitted column, every recorder
field, every edge attribute is checked, so a flipped constant,
dropped keyword, or swapped column surfaces as a test failure.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from pointlessql.pql import _aggregate as agg
from pointlessql.services.agent_runs.operations._common import OperationRecorder

if TYPE_CHECKING:
    from collections.abc import Iterator

_LRID = "_lineage_row_id"


# --------------------------------------------------------------------------
# Validation: exact error-message text (pins the message-string mutants)
# --------------------------------------------------------------------------


def _validation_call(**over: object) -> object:
    kwargs: dict[str, object] = {
        "client": object(),
        "engine": object(),
        "source_df": pd.DataFrame({"k": [1], "amount": [10]}),
        "target": "c.s.t",
        "group_by": ["k"],
        "aggs": {"total": ("amount", "sum")},
        "source_table_fqn": "c.s.src",
        "unreachable_msg": "down",
    }
    kwargs.update(over)
    return agg.aggregate_table(**kwargs)  # type: ignore[arg-type]


def test_empty_group_by_exact_message() -> None:
    from pointlessql.exceptions import ValidationError

    with pytest.raises(ValidationError) as ei:
        _validation_call(group_by=[])
    assert str(ei.value) == "aggregate requires at least one column in 'group_by'"


def test_missing_source_table_fqn_exact_message() -> None:
    from pointlessql.exceptions import ValidationError

    with pytest.raises(ValidationError) as ei:
        _validation_call(source_table_fqn="")
    assert str(ei.value) == (
        "aggregate requires source_table_fqn — without a declared source, "
        "fan-in lineage cannot be recorded"
    )


def test_empty_aggs_exact_message() -> None:
    from pointlessql.exceptions import ValidationError

    with pytest.raises(ValidationError) as ei:
        _validation_call(aggs={})
    assert str(ei.value) == "aggregate requires at least one entry in 'aggs'"


def test_non_dataframe_message_names_real_type() -> None:
    """The error must name the *actual* bad type, not a hard-coded one."""
    from pointlessql.exceptions import ValidationError

    with pytest.raises(ValidationError) as ei:
        _validation_call(source_df=42)
    assert str(ei.value) == "aggregate source must be a pandas DataFrame, got int"


def test_missing_group_by_column_message_lists_columns() -> None:
    from pointlessql.exceptions import ValidationError

    with pytest.raises(ValidationError) as ei:
        _validation_call(source_df=pd.DataFrame({"other": [1], "amount": [2]}))
    assert str(ei.value) == (
        "aggregate group_by columns ['k'] not present on source frame (['other', 'amount'])"
    )


# --------------------------------------------------------------------------
# End-to-end ``aggregate_table`` harness
# --------------------------------------------------------------------------


class _FakeEngine:
    """Records ``write`` args and returns deterministic ``columns_info``."""

    def __init__(self) -> None:
        self.write_calls: list[tuple[Any, str, str]] = []
        self.columns_calls: list[Any] = []

    def write(self, frame: Any, location: str, mode: str) -> None:
        self.write_calls.append((frame, location, mode))

    def columns_info(self, frame: Any) -> list[tuple[str, str, str, bool]]:
        self.columns_calls.append(frame)
        return [(str(c), "STRING", "string", True) for c in frame.columns]


class _Captured:
    """Bag holding everything observed across one ``aggregate_table`` call."""

    def __init__(self) -> None:
        self.recorder = OperationRecorder()
        self.op_params: dict[str, Any] | None = None
        self.op_name: Any = None
        self.op_target: str | None = None
        self.create_bodies: list[Any] = []
        self.get_calls: list[str] = []


def _drive(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_df: pd.DataFrame,
    table_exists: bool,
    agent_run_id: str | None = "run-1",
    mode: str | None = "overwrite",
    group_by: list[str] | None = None,
    aggs: dict[str, agg.AggSpec] | None = None,
    source_table_fqn: str = "main.silver.src",
    target: str = "main.gold.t",
    derivations: Any = None,
) -> tuple[dict[str, Any], _Captured, _FakeEngine]:
    """Run ``aggregate_table`` with the catalog + audit hops stubbed.

    Patches the module-level catalog client functions, the audit
    ``operation_context`` (so a real recorder is captured without a
    DB), and ``get_session_factory``.  Returns the primitive's result
    dict, the captured side effects, and the fake engine.
    """
    cap = _Captured()
    engine = _FakeEngine()

    # ---- stub catalog get/create -------------------------------------
    class _FakeGet:
        @staticmethod
        def sync(*, client: Any, full_name: str) -> Any:
            cap.get_calls.append(full_name)
            if table_exists:
                info = agg.TableInfo()
                info.storage_location = "file:///tmp/existing-loc"
                return info
            return None

    class _FakeCreate:
        @staticmethod
        def sync(*, client: Any, body: Any) -> Any:
            cap.create_bodies.append(body)
            return body

    monkeypatch.setattr(agg, "_get_table", _FakeGet)
    monkeypatch.setattr(agg, "_create_table", _FakeCreate)

    # ---- derive a location when the table is "new" -------------------
    monkeypatch.setattr(agg, "derive_storage_location", lambda *a, **k: "file:///tmp/new-loc")

    # ---- capture the audit recorder without touching a DB ------------
    @contextlib.contextmanager
    def _fake_ctx(
        factory: Any,
        *,
        agent_run_id: Any,
        op_name: Any,
        params: dict[str, Any],
        target_table: str | None = None,
    ) -> Iterator[OperationRecorder]:
        cap.op_params = params
        cap.op_name = op_name
        cap.op_target = target_table
        yield cap.recorder

    monkeypatch.setattr(agg, "operation_context", _fake_ctx)
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: object(), raising=False)

    call_kwargs: dict[str, Any] = {
        "client": object(),
        "engine": engine,
        "source_df": source_df,
        "target": target,
        "group_by": group_by or ["k"],
        "aggs": aggs or {"total": ("amount", "sum")},
        "source_table_fqn": source_table_fqn,
        "unreachable_msg": "catalog down",
        "derivations": derivations,
        "agent_run_id": agent_run_id,
    }
    # ``mode=None`` means "omit the kwarg" so the signature default applies.
    if mode is not None:
        call_kwargs["mode"] = mode

    result = agg.aggregate_table(**call_kwargs)  # type: ignore[arg-type]
    return result, cap, engine


def test_end_to_end_new_table_with_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full new-table path: return dict, params, recorder, create body."""
    df = pd.DataFrame(
        {
            "k": ["a", "a", "b"],
            "amount": [10, 5, 7],
            _LRID: ["s1", "s2", "s3"],
        }
    )
    result, cap, engine = _drive(monkeypatch, source_df=df, table_exists=False, mode="append")

    # --- return dict: exact keys and values (kills return-dict mutants).
    assert result == {
        "target": "main.gold.t",
        "rows_written": 2,  # two groups: a, b
        "groups": 2,
        "edges_emitted": 3,  # s1,s2 (group a) + s3 (group b)
    }

    # --- engine.write got the grouped frame, derived location, mode.
    assert len(engine.write_calls) == 1
    written, location, mode = engine.write_calls[0]
    assert location == "file:///tmp/new-loc"
    assert mode == "append"
    assert sorted(written["k"]) == ["a", "b"]
    assert dict(zip(written["k"], written["total"], strict=True)) == {
        "a": 15,
        "b": 7,
    }
    assert _LRID in written.columns

    # --- new table → a CreateTable body was sent with the right names.
    assert len(cap.create_bodies) == 1
    body = cap.create_bodies[0]
    assert body.catalog_name == "main"
    assert body.schema_name == "gold"
    assert body.name == "t"
    assert body.table_type == "MANAGED"
    assert body.data_source_format == "DELTA"
    assert body.storage_location == "file:///tmp/new-loc"

    # --- audit params block (kills the params-dict key/value mutants).
    assert cap.op_target == "main.gold.t"
    assert cap.op_params == {
        "target": "main.gold.t",
        "group_by": ["k"],
        "aggs": {"total": ["amount", "sum"]},
        "mode": "append",
    }

    # --- recorder side effects.
    rec = cap.recorder
    assert rec.rows_affected == 2
    assert rec.extra_params["source_table_fqn"] == "main.silver.src"
    assert rec.extra_params["groups"] == 2
    assert rec.extra_params["edges_emitted"] == 3

    # pending lineage edges: 3 source rows, target ids replicated.
    edges = rec.pending_lineage_edges
    assert edges is not None
    assert edges["source_table"] == "main.silver.src"
    assert sorted(edges["source_row_ids"]) == ["s1", "s2", "s3"]
    assert len(edges["target_row_ids"]) == 3
    # group "a" fans two source rows into one target id.
    pairs = dict(zip(edges["source_row_ids"], edges["target_row_ids"], strict=True))
    assert pairs["s1"] == pairs["s2"]
    assert pairs["s1"] != pairs["s3"]

    # pending column edges were computed and stamped.
    assert rec.pending_column_edges is not None
    kinds = {e.target_column: e.transform_kind for e in rec.pending_column_edges}
    assert kinds["k"] == "identity"
    assert kinds["total"] == "aggregate"
    assert kinds[_LRID] == "derived"


def test_end_to_end_existing_table_uses_registered_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing table: registered location used, no CreateTable sent."""
    df = pd.DataFrame({"k": ["a", "b"], "amount": [1, 2]})
    result, cap, engine = _drive(monkeypatch, source_df=df, table_exists=True, mode="overwrite")

    assert result["rows_written"] == 2
    assert result["groups"] == 2
    # No lineage column → zero edges, no pending lineage block.
    assert result["edges_emitted"] == 0
    assert cap.recorder.pending_lineage_edges is None

    # Existing table → registered storage location, no create call.
    assert engine.write_calls[0][1] == "file:///tmp/existing-loc"
    assert cap.create_bodies == []
    assert cap.op_params is not None
    assert cap.op_params["mode"] == "overwrite"


def test_mode_defaults_to_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting ``mode`` must default to ``"overwrite"`` everywhere it flows."""
    df = pd.DataFrame({"k": ["a", "b"], "amount": [1, 2]})
    # mode=None tells the harness to omit the kwarg entirely, so the
    # signature default is what flows to the engine and audit params.
    _result, cap, engine = _drive(monkeypatch, source_df=df, table_exists=True, mode=None)
    assert engine.write_calls[0][2] == "overwrite"
    assert cap.op_params is not None
    assert cap.op_params["mode"] == "overwrite"


def test_interactive_path_skips_audit_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``agent_run_id=None`` writes but records nothing on the recorder."""
    df = pd.DataFrame({"k": ["a", "a", "b"], "amount": [1, 2, 3], _LRID: ["s1", "s2", "s3"]})
    result, cap, engine = _drive(monkeypatch, source_df=df, table_exists=True, agent_run_id=None)

    assert result["edges_emitted"] == 3  # still computed for the return dict
    assert len(engine.write_calls) == 1
    # The ``agent_run_id is not None`` guard kept the recorder untouched.
    assert cap.recorder.rows_affected is None
    assert cap.recorder.pending_lineage_edges is None
    assert cap.recorder.pending_column_edges is None
    assert cap.recorder.extra_params == {}


# --------------------------------------------------------------------------
# ``_build_aggregate_frame`` — exact schema + values
# --------------------------------------------------------------------------


def test_frame_output_schema_and_values_with_lineage() -> None:
    df = pd.DataFrame(
        {
            "k": ["a", "a", "b"],
            "amount": [3, 5, 7],
            _LRID: ["s1", "s2", "s3"],
        }
    )
    grouped, per_group = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )

    # Group-by column survives as a real column (kills as_index toggles
    # and the missing-``on``/merge mutants that drop the key).
    assert "k" in grouped.columns
    assert "total" in grouped.columns
    # Internal helper column must not leak into the output frame.
    assert "_pql_source_ids" not in grouped.columns
    assert dict(zip(grouped["k"], grouped["total"], strict=True)) == {"a": 8, "b": 7}

    # Deterministic, unique, well-formed lineage ids.
    ids = list(grouped[_LRID])
    assert all(isinstance(v, str) and len(v) == 64 for v in ids)
    assert len(set(ids)) == 2

    # Fan-in: group "a" carries both source rows in order, "b" one.
    by_group = {tuple(sorted(sids)): tid for tid, sids in per_group}
    assert ("s1", "s2") in by_group
    assert ("s3",) in by_group


def test_frame_no_lineage_branch_stamps_real_ids() -> None:
    """No ``_lineage_row_id`` source column still mints valid ids."""
    df = pd.DataFrame({"k": ["a", "a", "b"], "amount": [1, 2, 3]})
    grouped, per_group = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    ids = list(grouped[_LRID])
    # tid must be a real digest, not None (kills tid=None / append(None)).
    assert all(isinstance(v, str) and len(v) == 64 for v in ids)
    assert all(sids == [] for _tid, sids in per_group)
    # The (target_id, []) tuple must reuse the same id that was stamped.
    assert sorted(tid for tid, _ in per_group) == sorted(ids)


def test_frame_target_ids_track_group_keys() -> None:
    """Distinct group keys → distinct ids; same keys → same ids."""
    df = pd.DataFrame({"k": ["a", "b"], "amount": [1, 2]})
    g1, _ = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    g2, _ = agg._build_aggregate_frame(
        source_df=df.copy(), target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    a_id = g1.loc[g1["k"] == "a", _LRID].iloc[0]
    b_id = g1.loc[g1["k"] == "b", _LRID].iloc[0]
    assert a_id != b_id
    # Determinism across re-runs.
    assert g1.set_index("k")[_LRID].to_dict() == g2.set_index("k")[_LRID].to_dict()


# --------------------------------------------------------------------------
# ``_build_aggregate_column_edges`` — every field, every branch
# --------------------------------------------------------------------------


def _by_target(edges: list[Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for e in edges:
        out.setdefault(e.target_column, []).append(e)
    return out


def test_edges_identity_full_fields() -> None:
    src = pd.DataFrame({"k": [1], "amount": [2]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["k"],
        aggs={"total": ("amount", "sum")},
        derivations=None,
    )
    by = _by_target(edges)

    # group-by identity edge: every field exact.
    (ident,) = by["k"]
    assert ident.source_table == "main.silver.src"
    assert ident.source_column == "k"
    assert ident.target_table == "main.gold.t"
    assert ident.target_column == "k"
    assert ident.transform_kind == "identity"
    assert ident.transform_detail is None

    # aggregate edge: every field exact.
    (out,) = by["total"]
    assert out.source_table == "main.silver.src"
    assert out.source_column == "amount"
    assert out.target_table == "main.gold.t"
    assert out.target_column == "total"
    assert out.transform_kind == "aggregate"
    assert out.transform_detail == "sum"


def test_edges_group_by_missing_unknown_origin() -> None:
    src = pd.DataFrame({"amount": [2]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["missing"],
        aggs={"total": ("amount", "sum")},
        derivations=None,
    )
    (e,) = _by_target(edges)["missing"]
    assert e.source_table is None
    assert e.source_column is None
    assert e.target_table == "main.gold.t"
    assert e.target_column == "missing"
    assert e.transform_kind == "unknown_origin"
    assert e.transform_detail is None


def test_edges_aggregate_on_missing_column_unknown_origin() -> None:
    src = pd.DataFrame({"k": [1]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["k"],
        aggs={"total": ("nope", "mean")},
        derivations=None,
    )
    (e,) = _by_target(edges)["total"]
    assert e.source_table is None
    assert e.source_column is None
    assert e.target_table == "main.gold.t"
    assert e.target_column == "total"
    assert e.transform_kind == "unknown_origin"
    # detail names the failed aggregation + missing column.
    assert e.transform_detail == "aggregate mean on missing column 'nope'"


def test_edges_group_by_derivation_present() -> None:
    src = pd.DataFrame({"raw": [1], "amount": [2]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["day"],
        aggs={"total": ("amount", "sum")},
        derivations={"day": ["raw"]},
    )
    (e,) = _by_target(edges)["day"]
    assert e.source_table == "main.silver.src"
    assert e.source_column == "raw"
    assert e.target_table == "main.gold.t"
    assert e.target_column == "day"
    assert e.transform_kind == "derived"
    assert e.transform_detail is None


def test_edges_group_by_derivation_references_missing() -> None:
    """group-by derivation pointing at an absent column → unknown_origin."""
    src = pd.DataFrame({"amount": [2]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["day"],
        aggs={"total": ("amount", "sum")},
        derivations={"day": ["ghost"]},
    )
    (e,) = _by_target(edges)["day"]
    assert e.source_table is None
    assert e.source_column is None
    assert e.target_table == "main.gold.t"
    assert e.target_column == "day"
    assert e.transform_kind == "unknown_origin"
    assert e.transform_detail == "derivation references 'ghost' which is not on source"


def test_edges_agg_derivation_present_chain() -> None:
    src = pd.DataFrame({"day": ["d"], "qty": [1], "unit_price": [2.0], "rev": [2.0]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["day"],
        aggs={"revenue": ("rev", "sum")},
        derivations={"rev": ["qty", "unit_price"]},
    )
    rev = _by_target(edges)["revenue"]
    assert {e.source_column for e in rev} == {"qty", "unit_price"}
    for e in rev:
        assert e.source_table == "main.silver.src"
        assert e.target_table == "main.gold.t"
        assert e.target_column == "revenue"
        assert e.transform_kind == "derived"
        # chain detail references the intermediate column + agg label.
        assert e.transform_detail == "via 'rev' → sum('rev')"


def test_edges_agg_derivation_references_missing() -> None:
    """aggregate derivation pointing at an absent column → unknown_origin."""
    src = pd.DataFrame({"day": ["d"], "rev": [2.0]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["day"],
        aggs={"revenue": ("rev", "sum")},
        derivations={"rev": ["ghost"]},
    )
    (e,) = _by_target(edges)["revenue"]
    assert e.source_table is None
    assert e.source_column is None
    assert e.target_table == "main.gold.t"
    assert e.target_column == "revenue"
    assert e.transform_kind == "unknown_origin"
    assert e.transform_detail == "derivation references 'ghost' which is not on source"


def test_edges_synth_lineage_row_id_full_fields() -> None:
    src = pd.DataFrame({"k": [1], "amount": [2], _LRID: ["s1"]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["k"],
        aggs={"total": ("amount", "sum")},
        derivations=None,
    )
    (e,) = _by_target(edges)[_LRID]
    assert e.source_table == "main.silver.src"
    assert e.source_column == _LRID
    assert e.target_table == "main.gold.t"
    assert e.target_column == _LRID
    assert e.transform_kind == "derived"
    assert e.transform_detail == "synth_target_row_id"


def test_edges_no_lineage_column_no_synth_edge() -> None:
    src = pd.DataFrame({"k": [1], "amount": [2]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["k"],
        aggs={"total": ("amount", "sum")},
        derivations=None,
    )
    assert all(e.target_column != _LRID for e in edges)


def test_agg_derivation_chain_uses_agg_label_not_constant() -> None:
    """The chain detail interpolates the *real* agg label (max, not sum)."""
    src = pd.DataFrame({"day": ["d"], "qty": [1], "rev": [2.0]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["day"],
        aggs={"peak": ("rev", "max")},
        derivations={"rev": ["qty"]},
    )
    (e,) = _by_target(edges)["peak"]
    assert e.transform_detail == "via 'rev' → max('rev')"


# --------------------------------------------------------------------------
# ``_build_aggregate_column_edges`` — loop-control (continue, not break)
# --------------------------------------------------------------------------


def test_group_by_derivation_does_not_short_circuit_remaining_keys() -> None:
    """A derived group-by key must not stop later group-by keys being emitted.

    The per-key loop ``continue``s after handling a derivation; a
    ``break`` here would silently drop every group-by column after the
    first derived one.
    """
    src = pd.DataFrame({"raw": [1], "plain": [2], "amount": [3]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        # first key is a derivation (hits the ``continue``); second key
        # must still produce its own identity edge afterwards.
        group_by=["day", "plain"],
        aggs={"total": ("amount", "sum")},
        derivations={"day": ["raw"]},
    )
    by = _by_target(edges)
    # both the derived key and the trailing identity key are present.
    assert "day" in by
    (plain,) = by["plain"]
    assert plain.target_column == "plain"
    assert plain.transform_kind == "identity"


def test_agg_derivation_does_not_short_circuit_remaining_aggs() -> None:
    """A derived agg output must not stop later agg outputs being emitted.

    The aggregation loop ``continue``s after handling a derivation; a
    ``break`` would drop every aggregation declared after the first
    derived one.
    """
    src = pd.DataFrame({"k": ["a"], "rev": [2.0], "amount": [3]})
    edges = agg._build_aggregate_column_edges(
        source_df=src,
        source_table_fqn="main.silver.src",
        target="main.gold.t",
        group_by=["k"],
        # first agg is a derivation (hits the ``continue``); the second
        # plain aggregate must still be emitted afterwards.
        aggs={"revenue": ("rev", "sum"), "total": ("amount", "sum")},
        derivations={"rev": ["amount"]},
    )
    by = _by_target(edges)
    assert "revenue" in by
    (total,) = by["total"]
    assert total.target_column == "total"
    assert total.transform_kind == "aggregate"
    assert total.transform_detail == "sum"


# --------------------------------------------------------------------------
# ``_build_aggregate_frame`` — grouped row order is insertion order
# --------------------------------------------------------------------------


def test_frame_preserves_insertion_order_not_sorted() -> None:
    """Grouped rows follow first-appearance order (``sort=False``), not key sort.

    ``b`` appears before ``a`` in the source, so the output frame must
    list ``b`` first; a ``sort=True`` flip would re-order it to ``a, b``.
    """
    df = pd.DataFrame({"k": ["b", "b", "a"], "amount": [1, 2, 3], _LRID: ["s1", "s2", "s3"]})
    grouped, per_group = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    assert list(grouped["k"]) == ["b", "a"]
    # source-id grouping order tracks the same (left-merge) row order.
    assert [tuple(sorted(s)) for _tid, s in per_group] == [("s1", "s2"), ("s3",)]


def test_frame_no_lineage_preserves_insertion_order() -> None:
    """The no-lineage branch also keeps first-appearance group order."""
    df = pd.DataFrame({"k": ["b", "b", "a"], "amount": [1, 2, 3]})
    grouped, _ = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    assert list(grouped["k"]) == ["b", "a"]


# --------------------------------------------------------------------------
# ``_resolve_or_plan_target`` — direct unit coverage
# --------------------------------------------------------------------------


def _patch_resolve(
    monkeypatch: pytest.MonkeyPatch,
    *,
    get_returns: Any = None,
    get_raises: BaseException | None = None,
) -> list[Any]:
    """Stub ``_get_table`` + ``derive_storage_location`` for resolve tests.

    Returns the list that records the positional args every
    ``derive_storage_location`` call received.
    """
    derive_args: list[Any] = []

    class _FakeGet:
        @staticmethod
        def sync(*, client: Any, full_name: str) -> Any:
            if get_raises is not None:
                raise get_raises
            return get_returns

    def _derive(*args: Any, **kwargs: Any) -> str:
        derive_args.append((args, kwargs))
        return "file:///tmp/derived"

    monkeypatch.setattr(agg, "_get_table", _FakeGet)
    monkeypatch.setattr(agg, "derive_storage_location", _derive)
    return derive_args


def test_resolve_existing_requires_real_storage_location() -> None:
    """An empty ``storage_location`` must NOT count the table as existing.

    The guard is ``not isinstance(loc, Unset) and loc`` — an ``or``
    flip would treat an empty-string location as a live table.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        derive_args = _patch_resolve(monkeypatch, get_returns=_table_info_with_loc(""))
        location, table_exists = agg._resolve_or_plan_target(
            client=object(), target="c.s.t", unreachable_msg="down"
        )
        # empty loc → falls through to derive, table treated as new.
        assert table_exists is False
        assert location == "file:///tmp/derived"
        assert len(derive_args) == 1
    finally:
        monkeypatch.undo()


def test_resolve_existing_with_real_location_skips_derive() -> None:
    """A real ``storage_location`` marks the table existing and skips derive."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        derive_args = _patch_resolve(
            monkeypatch, get_returns=_table_info_with_loc("file:///tmp/real")
        )
        location, table_exists = agg._resolve_or_plan_target(
            client=object(), target="c.s.t", unreachable_msg="down"
        )
        assert table_exists is True
        assert location == "file:///tmp/real"
        assert derive_args == []
    finally:
        monkeypatch.undo()


def test_resolve_404_is_swallowed_other_status_reraises() -> None:
    """A 404 from get-table means 'not found' (derive); other codes re-raise."""
    from soyuz_catalog_client.errors import UnexpectedStatus

    # 404 → swallowed, table treated as new.
    monkeypatch = pytest.MonkeyPatch()
    try:
        derive_args = _patch_resolve(
            monkeypatch,
            get_raises=UnexpectedStatus(404, b"missing"),
        )
        location, table_exists = agg._resolve_or_plan_target(
            client=object(), target="c.s.t", unreachable_msg="down"
        )
        assert table_exists is False
        assert location == "file:///tmp/derived"
        assert len(derive_args) == 1
    finally:
        monkeypatch.undo()

    # 500 → must propagate (the != 404 guard re-raises non-404).
    monkeypatch2 = pytest.MonkeyPatch()
    try:
        _patch_resolve(monkeypatch2, get_raises=UnexpectedStatus(500, b"boom"))
        with pytest.raises(UnexpectedStatus):
            agg._resolve_or_plan_target(client=object(), target="c.s.t", unreachable_msg="down")
    finally:
        monkeypatch2.undo()


def test_resolve_derive_gets_exact_parsed_name_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``derive_storage_location`` receives ``(client, catalog, schema, table)``.

    Pins every positional argument so a dropped or None-substituted
    argument to the derive call is observable.
    """
    sentinel_client = object()
    derive_args = _patch_resolve(monkeypatch, get_returns=None)
    agg._resolve_or_plan_target(
        client=sentinel_client, target="cat.sch.tbl", unreachable_msg="down"
    )
    assert len(derive_args) == 1
    args, kwargs = derive_args[0]
    assert kwargs == {}
    assert args == (sentinel_client, "cat", "sch", "tbl")


def test_resolve_connect_error_carries_unreachable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connect error surfaces as ``CatalogUnavailableError(unreachable_msg)``."""
    import httpx

    from pointlessql.exceptions import CatalogUnavailableError

    _patch_resolve(monkeypatch, get_raises=httpx.ConnectError("no route"))
    with pytest.raises(CatalogUnavailableError) as ei:
        agg._resolve_or_plan_target(
            client=object(), target="c.s.t", unreachable_msg="catalog is down"
        )
    assert str(ei.value) == "catalog is down"


def _table_info_with_loc(loc: str) -> Any:
    info = agg.TableInfo()
    info.storage_location = loc
    return info


# --------------------------------------------------------------------------
# ``aggregate_table`` — argument-forwarding + recorder side effects
# --------------------------------------------------------------------------


def _drive_capture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_df: pd.DataFrame,
    table_exists: bool,
    agent_run_id: str | None = "run-1",
    derivations: Any = None,
    write_raises: BaseException | None = None,
    create_raises: BaseException | None = None,
    sha_raises: BaseException | None = None,
) -> dict[str, Any]:
    """Run ``aggregate_table`` capturing forwarded args + recorder fields.

    Unlike ``_drive`` this records the exact ``client`` objects handed
    to the catalog hops, the ``operation_context`` positional/keyword
    args, and stubs ``safe_delta_version`` so its argument and result
    are observable.  Returns a bag of everything captured.
    """
    from pointlessql.types import OpName

    bag: dict[str, Any] = {
        "recorder": OperationRecorder(),
        "get_clients": [],
        "get_full_names": [],
        "create_clients": [],
        "create_bodies": [],
        "ctx_factory": "unset",
        "ctx_agent_run_id": "unset",
        "ctx_op_name": "unset",
        "delta_version_calls": [],
        "real_client": object(),
    }
    engine = _FakeEngine()
    orig_write = engine.write

    def _write(frame: Any, location: str, mode: str) -> None:
        if write_raises is not None:
            raise write_raises
        orig_write(frame, location, mode)

    engine.write = _write  # type: ignore[method-assign]

    class _FakeGet:
        @staticmethod
        def sync(*, client: Any, full_name: str) -> Any:
            bag["get_clients"].append(client)
            bag["get_full_names"].append(full_name)
            if table_exists:
                info = agg.TableInfo()
                info.storage_location = "file:///tmp/existing-loc"
                return info
            return None

    class _FakeCreate:
        @staticmethod
        def sync(*, client: Any, body: Any) -> Any:
            bag["create_clients"].append(client)
            bag["create_bodies"].append(body)
            if create_raises is not None:
                raise create_raises
            return body

    monkeypatch.setattr(agg, "_get_table", _FakeGet)
    monkeypatch.setattr(agg, "_create_table", _FakeCreate)
    monkeypatch.setattr(agg, "derive_storage_location", lambda *a, **k: "file:///tmp/new-loc")

    def _safe_ver(location: Any) -> Any:
        bag["delta_version_calls"].append(location)
        # distinct, non-None sentinels keyed on the argument so both the
        # call and its argument are observable.
        return f"ver::{location}"

    monkeypatch.setattr(agg, "safe_delta_version", _safe_ver)

    if sha_raises is not None:

        def _sha(_frame: Any) -> str:
            raise sha_raises

        monkeypatch.setattr(agg, "arrow_ipc_sha256", _sha)

    @contextlib.contextmanager
    def _fake_ctx(
        factory: Any,
        *,
        agent_run_id: Any,
        op_name: Any,
        params: dict[str, Any],
        target_table: str | None = None,
    ) -> Iterator[OperationRecorder]:
        bag["ctx_factory"] = factory
        bag["ctx_agent_run_id"] = agent_run_id
        bag["ctx_op_name"] = op_name
        yield bag["recorder"]

    monkeypatch.setattr(agg, "operation_context", _fake_ctx)
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: object(), raising=False)

    bag["result"] = agg.aggregate_table(
        client=bag["real_client"],
        engine=engine,
        source_df=source_df,
        target="main.gold.t",
        group_by=["k"],
        aggs={"total": ("amount", "sum")},
        source_table_fqn="main.silver.src",
        unreachable_msg="catalog down",
        derivations=derivations,
        agent_run_id=agent_run_id,
    )
    bag["expected_op_name"] = OpName.AGGREGATE
    return bag


def test_catalog_hops_receive_real_client_and_target() -> None:
    """The configured client + target flow into get/create unchanged.

    Pins ``client=`` on both ``_get_table`` and ``_create_table`` and
    ``full_name=`` on the get, so a None-substituted client or target
    is caught.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1], _LRID: ["s1"]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=False)
    finally:
        monkeypatch.undo()
    assert bag["get_clients"] == [bag["real_client"]]
    assert bag["get_full_names"] == ["main.gold.t"]
    assert bag["create_clients"] == [bag["real_client"]]


def test_operation_context_receives_factory_run_id_and_op_name() -> None:
    """factory, agent_run_id and op_name are forwarded into the audit context."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=True)
    finally:
        monkeypatch.undo()
    # factory is the session factory (not None) because agent_run_id is set.
    assert bag["ctx_factory"] is not None
    assert bag["ctx_agent_run_id"] == "run-1"
    assert bag["ctx_op_name"] == bag["expected_op_name"]


def test_factory_is_none_when_no_agent_run() -> None:
    """Interactive runs pass a ``None`` factory to the audit context."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=True, agent_run_id=None)
    finally:
        monkeypatch.undo()
    assert bag["ctx_factory"] is None
    assert bag["ctx_agent_run_id"] is None


def test_delta_versions_capture_location_for_existing_table() -> None:
    """before+after delta versions are read against the *write* location.

    Pins both ``safe_delta_version`` calls (argument == location, result
    stored on the recorder) so a None argument or a ``= None`` overwrite
    is observable.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=True)
    finally:
        monkeypatch.undo()
    rec = bag["recorder"]
    loc = "file:///tmp/existing-loc"
    # before (table exists) and after both read the same location.
    assert rec.delta_version_before == f"ver::{loc}"
    assert rec.delta_version_after == f"ver::{loc}"
    assert bag["delta_version_calls"] == [loc, loc]


def test_delta_version_after_set_only_for_agent_runs() -> None:
    """The post-write version is recorded only when an agent run is active."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=True, agent_run_id=None)
    finally:
        monkeypatch.undo()
    # No agent run → no version probe at all, recorder stays clean.
    assert bag["recorder"].delta_version_after is None
    assert bag["delta_version_calls"] == []


def test_input_sha_is_recorded_from_grouped_frame() -> None:
    """The recorder's input SHA is the real digest, not a cleared ``None``."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=True)
    finally:
        monkeypatch.undo()
    sha = bag["recorder"].input_sha
    assert isinstance(sha, str)
    assert len(sha) == 64


def test_input_sha_cleared_to_none_on_type_error() -> None:
    """A hashing ``TypeError`` clears the SHA to ``None`` (not an empty string)."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(
            monkeypatch, source_df=df, table_exists=True, sha_raises=TypeError("nope")
        )
    finally:
        monkeypatch.undo()
    assert bag["recorder"].input_sha is None


def test_create_table_body_carries_real_columns() -> None:
    """A new table's CreateTable body carries engine-derived columns, not None."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        bag = _drive_capture(monkeypatch, source_df=df, table_exists=False)
    finally:
        monkeypatch.undo()
    (body,) = bag["create_bodies"]
    assert body.columns is not None
    # k, total, _lineage_row_id → three columns derived from the frame.
    assert len(list(body.columns)) == 3


def test_column_edges_forward_source_target_and_derivations() -> None:
    """source_table_fqn, target, and derivations flow into the column edges.

    A None-substituted ``source_table_fqn``/``target`` or a dropped
    ``derivations`` would change the recorded column edges.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        # 'day' is a group-by derived from 'raw' — only honoured if the
        # derivations mapping is actually forwarded to the edge builder.
        df = pd.DataFrame({"k": ["a"], "raw": [1], "amount": [2], _LRID: ["s1"]})
        # derivation keyed on the agg *source* column ('amount'), so the
        # 'total' output becomes a derived edge from 'raw'.
        bag = _drive_capture(
            monkeypatch,
            source_df=df,
            table_exists=True,
            derivations={"amount": ["raw"]},
        )
    finally:
        monkeypatch.undo()
    edges = bag["recorder"].pending_column_edges
    assert edges is not None
    by = {e.target_column: e for e in edges if e.transform_kind != "unknown_origin"}
    # identity edge for the group-by key carries the real source table+target.
    ident = by["k"]
    assert ident.source_table == "main.silver.src"
    assert ident.target_table == "main.gold.t"
    # derivation forwarded → 'total' becomes a derived edge from 'raw'.
    derived = [e for e in edges if e.target_column == "total"]
    assert any(e.transform_kind == "derived" and e.source_column == "raw" for e in derived)


def test_write_connect_error_raises_unreachable_message() -> None:
    """A connect error during the write surfaces the unreachable message."""
    import httpx

    from pointlessql.exceptions import CatalogUnavailableError

    monkeypatch = pytest.MonkeyPatch()
    try:
        df = pd.DataFrame({"k": ["a"], "amount": [1]})
        with pytest.raises(CatalogUnavailableError) as ei:
            _drive_capture(
                monkeypatch,
                source_df=df,
                table_exists=True,
                write_raises=httpx.ConnectError("no route"),
            )
        assert str(ei.value) == "catalog down"
    finally:
        monkeypatch.undo()
