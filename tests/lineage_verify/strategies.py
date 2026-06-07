"""Hypothesis strategies for valid lineage-bearing PQL pipelines.

Generates small *valid* DataFrames (a schema of safe business columns plus a
unique ``_lineage_row_id`` per row) so the harness can run them through real
PQL primitives and assert the recorded lineage satisfies every invariant.
Business-column identifiers start with a letter, so they can never collide
with the underscore-prefixed audit/lineage columns; values stay ASCII-
printable here (Unicode / NULL-key edge cases live in the golden corpus).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from hypothesis import strategies as st

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN

_COLUMN_TYPES = ("int", "float", "str")
_identifiers = st.from_regex(r"[a-z][a-z0-9_]{0,11}", fullmatch=True)
_printable = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    max_size=12,
)


@dataclass(frozen=True)
class WritePipeline:
    """A single lineage-bearing ``write_table`` op to verify."""

    frame: pd.DataFrame
    source_fqn: str
    table_name: str


@dataclass(frozen=True)
class SqlPipeline:
    """A bronze -> SELECT(subset) -> silver-write pipeline to verify.

    The SELECT deliberately omits ``_lineage_row_id`` from its projection
    (the 15.8 shape); auto-projection should carry it forward so the silver
    write still records row-edges.
    """

    bronze_frame: pd.DataFrame
    select_columns: list[str]
    table_name: str


def _column_values(draw: Any, kind: str, n: int) -> list[Any]:
    if kind == "int":
        return draw(st.lists(st.integers(-1_000_000, 1_000_000), min_size=n, max_size=n))
    if kind == "float":
        return draw(
            st.lists(
                st.floats(allow_nan=False, allow_infinity=False),
                min_size=n,
                max_size=n,
            )
        )
    return draw(st.lists(_printable, min_size=n, max_size=n))


@st.composite
def _schemas(draw: Any) -> list[tuple[str, str]]:
    names = draw(st.lists(_identifiers, min_size=1, max_size=4, unique=True))
    return [(name, draw(st.sampled_from(_COLUMN_TYPES))) for name in names]


@st.composite
def write_pipelines(draw: Any) -> WritePipeline:
    """Draw a valid lineage-bearing frame + source/target labels for write_table."""
    schema = draw(_schemas())
    n = draw(st.integers(min_value=1, max_value=12))
    data: dict[str, list[Any]] = {name: _column_values(draw, kind, n) for name, kind in schema}
    data[LINEAGE_ROW_ID_COLUMN] = [f"row-{i}" for i in range(n)]
    frame = pd.DataFrame(data)
    return WritePipeline(
        frame=frame,
        source_fqn=f"lv.bronze.{draw(_identifiers)}",
        table_name=draw(_identifiers),
    )


@dataclass(frozen=True)
class UpdatePipeline:
    """An in-place UPDATE op (value-changes only) to verify."""

    base_frame: pd.DataFrame
    set_clause: dict[str, str]
    table_name: str


@st.composite
def update_pipelines(draw: Any) -> UpdatePipeline:
    """Draw a numeric frame + a SET expression that changes every row."""
    n = draw(st.integers(min_value=1, max_value=8))
    values = draw(st.lists(st.integers(0, 1_000_000), min_size=n, max_size=n))
    base = pd.DataFrame({"v": values, LINEAGE_ROW_ID_COLUMN: [f"row-{i}" for i in range(n)]})
    return UpdatePipeline(base_frame=base, set_clause={"v": "v + 1"}, table_name=draw(_identifiers))


@dataclass(frozen=True)
class AggregatePipeline:
    """A group-aggregate (fan-in) op to verify."""

    source_frame: pd.DataFrame
    group_by: list[str]
    aggs: dict[str, tuple[str, str]]
    table_name: str


@st.composite
def aggregate_pipelines(draw: Any) -> AggregatePipeline:
    """Draw a source whose low-cardinality group key fans many rows into few groups."""
    n = draw(st.integers(min_value=2, max_value=12))
    n_groups = draw(st.integers(min_value=1, max_value=max(1, n // 2)))
    groups = [f"g{draw(st.integers(0, n_groups - 1))}" for _ in range(n)]
    values = draw(st.lists(st.integers(0, 1_000_000), min_size=n, max_size=n))
    source = pd.DataFrame(
        {"g": groups, "v": values, LINEAGE_ROW_ID_COLUMN: [f"row-{i}" for i in range(n)]}
    )
    return AggregatePipeline(
        source_frame=source,
        group_by=["g"],
        aggs={"total": ("v", "sum")},
        table_name=draw(_identifiers),
    )


@dataclass(frozen=True)
class MergePipeline:
    """A bootstrap-then-upsert merge to verify, optionally with rejects."""

    base_frame: pd.DataFrame
    merge_frame: pd.DataFrame
    on: list[str]
    table_name: str


@st.composite
def merge_pipelines(draw: Any) -> MergePipeline:
    """Draw a clean base + an all-matched upsert source, optionally with rejects.

    Every merge row reuses a base key (so the post-merge table is exactly the
    merge's outputs) with a bumped value (a guaranteed value-change); optional
    null-key and duplicate-key rows exercise the reject ledger.
    """
    n = draw(st.integers(min_value=2, max_value=8))
    keys = [f"key-{i}" for i in range(n)]
    values = draw(st.lists(st.integers(0, 1_000_000), min_size=n, max_size=n))
    base = pd.DataFrame(
        {"k": keys, "v": values, LINEAGE_ROW_ID_COLUMN: [f"row-{i}" for i in range(n)]}
    )

    cols_k: list[Any] = list(keys)
    cols_v: list[int] = [v + 1 for v in values]
    cols_id: list[str] = [f"row-{i}" for i in range(n)]
    if draw(st.booleans()):  # null-key reject
        cols_k.append(None)
        cols_v.append(0)
        cols_id.append("reject-null")
    if draw(st.booleans()):  # duplicate-key reject
        cols_k.append(keys[0])
        cols_v.append(-1)
        cols_id.append("reject-dup")
    merge = pd.DataFrame({"k": cols_k, "v": cols_v, LINEAGE_ROW_ID_COLUMN: cols_id})

    return MergePipeline(
        base_frame=base, merge_frame=merge, on=["k"], table_name=draw(_identifiers)
    )


@st.composite
def sql_pipelines(draw: Any) -> SqlPipeline:
    """Draw a bronze frame + a non-empty business-column projection subset."""
    base = draw(write_pipelines())
    business = [c for c in base.frame.columns if c != LINEAGE_ROW_ID_COLUMN]
    select_columns = draw(
        st.lists(st.sampled_from(business), min_size=1, max_size=len(business), unique=True)
    )
    return SqlPipeline(
        bronze_frame=base.frame,
        select_columns=select_columns,
        table_name=base.table_name,
    )
