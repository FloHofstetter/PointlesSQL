"""Topological-sort parity tests for the shared canvas-core kernel.

Two contracts are pinned here:

* :func:`pointlessql.services.canvas_core.topo_sort` breaks ready-set ties
  lexically by default (the dataframe compiler relies on this for stable
  CTE names) and numerically when handed ``sort_key=int``.
* The scheduler's :func:`_topological_order`, now delegating to the shared
  kernel, still orders tasks by **numeric** id within a round — ``"10"``
  after ``"2"``, never before it.  A regression here would silently
  reorder task execution, so this is the single highest-risk unit in the
  canvas-core extraction.
"""

from __future__ import annotations

import json

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.models import JobTask
from pointlessql.services.canvas_core import (
    CanvasEdge,
    CanvasNode,
    CompileError,
    topo_sort,
)
from pointlessql.services.scheduler.dag import _topological_order


def _nodes(*ids: str) -> list[CanvasNode]:
    return [CanvasNode(id=i, block_type="task") for i in ids]


def _edge(src: str, dst: str) -> CanvasEdge:
    return CanvasEdge(
        id=f"{src}->{dst}",
        source_node_id=src,
        source_pin="out",
        target_node_id=dst,
        target_pin="in",
    )


def _task(task_id: int, deps: list[int]) -> JobTask:
    return JobTask(
        id=task_id,
        job_id=1,
        name=f"t{task_id}",
        order=0,
        kind="fake",
        config="{}",
        depends_on=json.dumps(deps),
        max_retries=0,
        retry_backoff_seconds=0,
    )


class TestKernelTopoSort:
    def test_default_sort_key_is_lexical(self) -> None:
        # Three independent nodes; default tie-break is string order.
        errors: list[CompileError] = []
        ordered = topo_sort(_nodes("2", "10", "1"), [], errors)
        assert ordered is not None
        assert [n.id for n in ordered] == ["1", "10", "2"]
        assert errors == []

    def test_int_sort_key_is_numeric(self) -> None:
        errors: list[CompileError] = []
        ordered = topo_sort(_nodes("2", "10", "1"), [], errors, sort_key=int)
        assert ordered is not None
        assert [n.id for n in ordered] == ["1", "2", "10"]

    def test_dependency_order_respected_with_numeric_ties(self) -> None:
        # 2 and 10 are roots; 3 depends on both. Numeric ties → 2 before 10.
        errors: list[CompileError] = []
        ordered = topo_sort(
            _nodes("3", "2", "10"),
            [_edge("2", "3"), _edge("10", "3")],
            errors,
            sort_key=int,
        )
        assert ordered is not None
        assert [n.id for n in ordered] == ["2", "10", "3"]

    def test_cycle_returns_none_and_appends_error(self) -> None:
        errors: list[CompileError] = []
        ordered = topo_sort(
            _nodes("1", "2"),
            [_edge("1", "2"), _edge("2", "1")],
            errors,
        )
        assert ordered is None
        assert len(errors) == 1
        assert errors[0].kind == "cycle"


class TestSchedulerTopologicalOrder:
    def test_independent_tasks_order_numerically(self) -> None:
        # The regression guard: ids 1, 2, 10 with no deps must come back
        # 1, 2, 10 — not the lexical 1, 10, 2.
        tasks = [_task(2, []), _task(10, []), _task(1, [])]
        ordered = _topological_order(tasks)
        assert [t.id for t in ordered] == [1, 2, 10]

    def test_ready_round_breaks_ties_numerically(self) -> None:
        # 2 and 10 are roots, 3 depends on both.
        tasks = [_task(3, [2, 10]), _task(2, []), _task(10, [])]
        ordered = _topological_order(tasks)
        assert [t.id for t in ordered] == [2, 10, 3]

    def test_diamond_orders_dependencies_first(self) -> None:
        # 1 → 2,3 → 4
        tasks = [
            _task(1, []),
            _task(2, [1]),
            _task(3, [1]),
            _task(4, [2, 3]),
        ]
        ordered = [t.id for t in _topological_order(tasks)]
        assert ordered[0] == 1
        assert ordered[-1] == 4
        assert set(ordered[1:3]) == {2, 3}
        assert ordered[1] < ordered[2]  # numeric tie-break: 2 before 3

    def test_cycle_raises_validation_error(self) -> None:
        tasks = [_task(1, [2]), _task(2, [1])]
        with pytest.raises(ValidationError, match="cycle"):
            _topological_order(tasks)
