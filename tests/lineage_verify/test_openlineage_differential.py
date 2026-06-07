"""Differential: emitted OpenLineage facets match the local lineage tables.

The post-commit hook serialises the same recorded lineage twice — once into
the four lineage tables, once into the OpenLineage event POSTed to soyuz.
These tests intercept the event and assert the two serialisers agree, so the
exported graph can never drift from the internal source of truth.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given

from tests.lineage_verify._harness import (
    capture_openlineage,
    run_merge_op,
    run_write_op,
)
from tests.lineage_verify.strategies import (
    MergePipeline,
    WritePipeline,
    merge_pipelines,
    write_pipelines,
)


def _facet(dataset: Any, name: str) -> dict[str, Any] | None:
    """Return one named facet off an OpenLineage output dataset, if present."""
    facets = dataset["facets"] if "facets" in dataset else None
    if not isinstance(facets, dict):
        return None
    facet = facets.get(name)
    return facet if isinstance(facet, dict) else None


def _columnlineage_triples(event: Any) -> set[tuple[str, str, str]]:
    """Collect ``(source_table, source_column, target_column)`` from the event."""
    triples: set[tuple[str, str, str]] = set()
    for dataset in event.outputs or []:
        facet = _facet(dataset, "columnLineage")
        if facet is None:
            continue
        for target_column, spec in facet.get("fields", {}).items():
            for field in spec.get("inputFields", []):
                triples.add((field["name"], field["field"], target_column))
    return triples


def _valuechange_tuples(event: Any) -> set[tuple[str, str, str | None, str | None]]:
    """Collect ``(row_id, column, old, new)`` from the event's valueChange facet."""
    tuples: set[tuple[str, str, str | None, str | None]] = set()
    for dataset in event.outputs or []:
        facet = _facet(dataset, "valueChange")
        if facet is None:
            continue
        for change in facet.get("changes", []):
            tuples.add(
                (change["rowId"], change["column"], change.get("oldValue"), change.get("newValue"))
            )
    return tuples


@pytest.mark.lineage_verify
@given(pipeline=write_pipelines())
def test_columnlineage_facet_matches_lineage_tables(pipeline: WritePipeline) -> None:
    """Every emitted columnLineage edge is a recorded column-map row, and back.

    The OpenLineage facet drops edges with no known source column; the
    remaining triples must exactly match the source-bearing column-map rows.
    """
    with capture_openlineage() as events:
        facts = run_write_op(
            frame=pipeline.frame,
            source_fqn=pipeline.source_fqn,
            table_name=pipeline.table_name,
        )
    assert events, "the write should have emitted an OpenLineage event"
    emitted = _columnlineage_triples(events[-1])
    recorded = {
        (c.source_table, c.source_column, c.target_column)
        for c in facts.column_map
        if c.source_table and c.source_column
    }
    assert emitted == recorded


@pytest.mark.lineage_verify
@given(pipeline=merge_pipelines())
def test_valuechange_facet_matches_lineage_tables(pipeline: MergePipeline) -> None:
    """Every emitted valueChange equals a recorded value-change row, and back."""
    with capture_openlineage() as events:
        facts = run_merge_op(
            base_frame=pipeline.base_frame,
            merge_frame=pipeline.merge_frame,
            on=pipeline.on,
            table_name=pipeline.table_name,
        )
    merge_events = [e for e in events if _valuechange_tuples(e)]
    assert merge_events, "the merge should have emitted value-changes"
    emitted = _valuechange_tuples(merge_events[-1])
    recorded = {
        (v.target_row_id, v.target_column, v.old_value, v.new_value) for v in facts.value_changes
    }
    assert emitted == recorded
