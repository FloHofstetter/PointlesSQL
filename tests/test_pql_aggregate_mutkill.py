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
