"""Unit tests for the ``pql.aggregate`` primitive's pure helpers.

The catalog/engine write path needs a live client, but the interesting
logic is pure: input validation (fail-fast), the groupby frame builder
that stamps deterministic ``_lineage_row_id``s and collects fan-in source
ids, and the column-edge translator that turns group-by / aggs /
derivations into lineage edges. Those are covered directly here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.pql import _aggregate as agg

_LRID = "_lineage_row_id"


# --- _agg_repr ------------------------------------------------------------


def test_agg_repr_string_passthrough() -> None:
    assert agg._agg_repr("sum") == "sum"


def test_agg_repr_callable_is_placeholder() -> None:
    assert agg._agg_repr(lambda s: s) == "<callable>"


# --- aggregate_table fail-fast validation --------------------------------


def _call(**over: object) -> object:
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


def test_empty_group_by_raises() -> None:
    with pytest.raises(ValidationError, match="group_by"):
        _call(group_by=[])


def test_empty_source_table_fqn_raises() -> None:
    with pytest.raises(ValidationError, match="source_table_fqn"):
        _call(source_table_fqn="")


def test_empty_aggs_raises() -> None:
    with pytest.raises(ValidationError, match="aggs"):
        _call(aggs={})


def test_non_dataframe_source_raises() -> None:
    with pytest.raises(ValidationError, match="DataFrame"):
        _call(source_df=object())


def test_missing_group_by_column_raises() -> None:
    with pytest.raises(ValidationError, match="not present"):
        _call(source_df=pd.DataFrame({"other": [1], "amount": [2]}))


# --- _build_aggregate_frame ----------------------------------------------


def test_build_frame_aggregates_and_stamps_lineage_id() -> None:
    df = pd.DataFrame({"k": ["a", "a", "b"], "amount": [1, 2, 3]})
    grouped, per_group = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    assert _LRID in grouped.columns
    rows = dict(zip(grouped["k"], grouped["total"], strict=True))
    assert rows == {"a": 3, "b": 3}
    # No source lineage column → empty source-id lists.
    assert all(sids == [] for _tid, sids in per_group)


def test_build_frame_collects_source_ids_when_lineage_present() -> None:
    df = pd.DataFrame({"k": ["a", "a", "b"], "amount": [1, 2, 3], _LRID: ["s1", "s2", "s3"]})
    grouped, per_group = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    by_group = {tid: sids for tid, sids in per_group}
    # Group "a" fans in two source rows, group "b" one.
    sizes = sorted(len(v) for v in by_group.values())
    assert sizes == [1, 2]
    assert grouped[_LRID].is_unique


def test_build_frame_target_ids_are_deterministic() -> None:
    df = pd.DataFrame({"k": ["a", "b"], "amount": [1, 2]})
    g1, _ = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    g2, _ = agg._build_aggregate_frame(
        source_df=df, target="c.s.t", group_by=["k"], aggs={"total": ("amount", "sum")}
    )
    assert list(g1[_LRID]) == list(g2[_LRID])


# --- _build_aggregate_column_edges ---------------------------------------


def _edges(**over: object) -> list:
    kwargs: dict[str, object] = {
        "source_df": pd.DataFrame({"k": [1], "amount": [2]}),
        "source_table_fqn": "c.s.src",
        "target": "c.s.t",
        "group_by": ["k"],
        "aggs": {"total": ("amount", "sum")},
        "derivations": None,
    }
    kwargs.update(over)
    return agg._build_aggregate_column_edges(**kwargs)  # type: ignore[arg-type]


def test_group_by_present_yields_identity_edge() -> None:
    edges = _edges()
    identity = [e for e in edges if e.target_column == "k"]
    assert identity and identity[0].transform_kind == "identity"


def test_group_by_missing_yields_unknown_origin() -> None:
    edges = _edges(
        source_df=pd.DataFrame({"amount": [2]}),
        group_by=["missing"],
        aggs={"total": ("amount", "sum")},
    )
    miss = [e for e in edges if e.target_column == "missing"]
    assert miss and miss[0].transform_kind == "unknown_origin"


def test_aggregate_output_edge_carries_agg_label() -> None:
    edges = _edges()
    out = [e for e in edges if e.target_column == "total"]
    assert out and out[0].transform_kind == "aggregate"
    assert out[0].transform_detail == "sum"


def test_aggregate_on_missing_source_is_unknown_origin() -> None:
    edges = _edges(source_df=pd.DataFrame({"k": [1]}), aggs={"total": ("nope", "sum")})
    out = [e for e in edges if e.target_column == "total"]
    assert out and out[0].transform_kind == "unknown_origin"


def test_derivation_on_group_by_yields_derived_edge() -> None:
    edges = _edges(
        source_df=pd.DataFrame({"raw": [1], "amount": [2]}),
        group_by=["day"],
        derivations={"day": ["raw"]},
    )
    day = [e for e in edges if e.target_column == "day"]
    assert day and day[0].transform_kind == "derived"
    assert day[0].source_column == "raw"


def test_lineage_row_id_present_adds_derived_edge() -> None:
    edges = _edges(source_df=pd.DataFrame({"k": [1], "amount": [2], _LRID: ["s1"]}))
    lrid = [e for e in edges if e.target_column == _LRID]
    assert lrid and lrid[0].transform_detail == "synth_target_row_id"
