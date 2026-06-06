# pyright: reportUnusedFunction=false
"""DAG primitives: cycle detection + topological order.

Pure graph algorithms operating on
:class:`~pointlessql.models.JobTask` rows.  No DB access, no HTTP,
no async — testable end-to-end without fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from pointlessql.exceptions import ValidationError
from pointlessql.models import JobTask
from pointlessql.services.canvas_core import (
    CanvasEdge,
    CanvasNode,
    CompileError,
    topo_sort,
)


def _parse_depends_on(raw: str) -> list[int]:
    """Deserialize a ``job_tasks.depends_on`` string into a list of ids."""
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValidationError(f"task depends_on is not valid JSON: {raw!r}") from exc
    if not isinstance(value, list):
        raise ValidationError("task depends_on must be a JSON array")
    typed: list[int] = []
    for item in value:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, int):
            raise ValidationError("task depends_on entries must be integers")
        typed.append(item)
    return typed


def validate_dag(tasks: Iterable[JobTask]) -> None:
    """Ensure the task graph is a DAG.

    Iterative three-color DFS: nodes start WHITE. When we descend into
    a node we mark it GRAY; when we come back up we mark it BLACK. A
    back-edge onto a GRAY node means we've looped back into the
    current recursion stack — that is a cycle. BLACK nodes are fully
    explored and safe to cross repeatedly. Also checks every
    ``depends_on`` target actually exists within the same job.

    Args:
        tasks: All :class:`JobTask` rows that form the candidate DAG.

    Raises:
        ValidationError: When any cycle is detected or a dependency
            points to an id outside the supplied set.
    """
    task_list = list(tasks)
    by_id: dict[int, JobTask] = {t.id: t for t in task_list}

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {t.id: WHITE for t in task_list}

    # Pre-resolve every task's dependency list once so the walk below
    # is a pure graph traversal with no further JSON parsing.
    deps_of: dict[int, list[int]] = {}
    for t in task_list:
        parsed = _parse_depends_on(t.depends_on)
        for dep_id in parsed:
            if dep_id not in by_id:
                raise ValidationError(f"task {t.id} depends on unknown task id {dep_id}")
        deps_of[t.id] = parsed

    for root in task_list:
        if color[root.id] != WHITE:
            continue
        # Stack frames: (task_id, remaining-deps-to-visit). Fresh
        # frames push a copy of ``deps_of[node]`` so we can pop from
        # it without mutating the shared map.
        path: list[int] = [root.id]
        stack: list[tuple[int, list[int]]] = [(root.id, list(deps_of[root.id]))]
        color[root.id] = GRAY
        while stack:
            node_id, remaining = stack[-1]
            if not remaining:
                color[node_id] = BLACK
                path.pop()
                stack.pop()
                continue
            next_dep = remaining.pop(0)
            state = color[next_dep]
            if state == GRAY:
                cycle = path[path.index(next_dep) :] + [next_dep]
                raise ValidationError(f"cycle detected in task graph: {cycle}")
            if state == BLACK:
                continue
            color[next_dep] = GRAY
            path.append(next_dep)
            stack.append((next_dep, list(deps_of[next_dep])))


def _topological_order(tasks: list[JobTask]) -> list[JobTask]:
    """Return *tasks* in a deterministic topological order.

    Delegates the Kahn's-algorithm walk to the shared
    :func:`pointlessql.services.canvas_core.topo_sort` so the whole
    codebase carries one graph ordering, then maps the ordered canvas
    nodes back to their :class:`JobTask` rows.  Node ids are the tasks'
    integer primary keys stringified; the sort is told to break ties
    numerically (``sort_key=int``) so ``"10"`` orders after ``"2"`` — the
    stable per-round ordering callers rely on, identical to the bespoke
    integer-sorted Kahn walk this used to carry.

    Args:
        tasks: All :class:`JobTask` rows for one job.

    Returns:
        The same rows, re-ordered so every task appears after its
        dependencies.

    Raises:
        ValidationError: When the graph contains a cycle (should have
            been caught at DAG-validation time, but we guard here too).
    """
    by_id: dict[int, JobTask] = {t.id: t for t in tasks}
    nodes = [CanvasNode(id=str(t.id), block_type="task") for t in tasks]
    edges: list[CanvasEdge] = []
    for t in tasks:
        for dep_id in _parse_depends_on(t.depends_on):
            edges.append(
                CanvasEdge(
                    id=f"{dep_id}->{t.id}",
                    source_node_id=str(dep_id),
                    source_pin="out",
                    target_node_id=str(t.id),
                    target_pin="deps",
                )
            )
    errors: list[CompileError] = []
    ordered = topo_sort(nodes, edges, errors, sort_key=int)
    if ordered is None:
        raise ValidationError("cycle detected in task graph during toposort")
    return [by_id[int(n.id)] for n in ordered]
