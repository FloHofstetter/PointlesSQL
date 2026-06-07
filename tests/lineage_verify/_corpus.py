"""Deterministic golden-corpus pipelines + a stable, diffable serialisation.

Hand-curated pipelines that pin edge cases a statistical generator can miss —
Unicode column names, NULL / duplicate merge keys, multi-column group-by.
Each runs real PQL primitives with fixed inputs and table names, so the
synthesised row ids (and therefore the whole snapshot) are reproducible.
``serialize_facts`` sorts every collection so the committed JSON is a
review-friendly diff.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN
from pointlessql.services.lineage.verify import OperationFacts
from tests.lineage_verify._harness import run_aggregate_op, run_merge_op, run_write_op


def _key(row: list[Any]) -> tuple[str, ...]:
    return tuple("" if v is None else str(v) for v in row)


def serialize_facts(facts: OperationFacts) -> dict[str, Any]:
    """Return a deterministic, JSON-serialisable snapshot of recorded lineage."""
    return {
        "target_table": facts.target_table,
        "aggregate": facts.aggregate,
        "source_row_ids": sorted(facts.source_row_ids),
        "output_columns": sorted(facts.output_columns),
        "output_row_ids": sorted(facts.target_row_ids),
        "edges": sorted(([e.source_row_id, e.target_row_id] for e in facts.edges), key=_key),
        "rejects": sorted(([r.source_row_id, r.reason] for r in facts.rejects), key=_key),
        "column_map": sorted(
            (
                [
                    c.source_table,
                    c.source_column,
                    c.target_column,
                    c.transform_kind,
                    c.transform_detail,
                ]
                for c in facts.column_map
            ),
            key=_key,
        ),
        "value_changes": sorted(
            (
                [v.target_row_id, v.target_column, v.old_value, v.new_value]
                for v in facts.value_changes
            ),
            key=_key,
        ),
    }


def _unicode_columns() -> OperationFacts:
    frame = pd.DataFrame(
        {
            "café": [1, 2],
            "naïve_x": ["α", "β"],
            "日本語": [10, 20],
            LINEAGE_ROW_ID_COLUMN: ["bronze-1", "bronze-2"],
        }
    )
    return run_write_op(frame=frame, source_fqn="lv.bronze.unicode_src", table_name="unicode_cols")


def _merge_rejects() -> OperationFacts:
    base = pd.DataFrame(
        {"k": ["a", "b", "c"], "v": [1, 2, 3], LINEAGE_ROW_ID_COLUMN: ["r1", "r2", "r3"]}
    )
    merge = pd.DataFrame(
        {
            "k": ["a", "b", "c", None, "a"],
            "v": [10, 20, 30, 0, 99],
            LINEAGE_ROW_ID_COLUMN: ["r1", "r2", "r3", "reject-null", "reject-dup"],
        }
    )
    return run_merge_op(base_frame=base, merge_frame=merge, on=["k"], table_name="merge_rejects")


def _multicol_aggregate() -> OperationFacts:
    source = pd.DataFrame(
        {
            "region": ["us", "us", "eu", "eu"],
            "tier": ["a", "a", "a", "b"],
            "v": [1, 2, 3, 4],
            LINEAGE_ROW_ID_COLUMN: ["s1", "s2", "s3", "s4"],
        }
    )
    return run_aggregate_op(
        source_frame=source,
        group_by=["region", "tier"],
        aggs={"total": ("v", "sum")},
        table_name="multicol_agg",
    )


CORPUS: dict[str, Any] = {
    "unicode_columns": _unicode_columns,
    "merge_rejects": _merge_rejects,
    "multicol_aggregate": _multicol_aggregate,
}
