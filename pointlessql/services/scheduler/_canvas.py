"""JobTask ⇄ CanvasDoc bridge for the visual task-chain editor.

Builds a consumer-agnostic :class:`~pointlessql.services.canvas_core.CanvasDoc`
from the live ``JobTask`` rows of a job, validates an edited doc's shape +
acyclicity without touching the DB, and overlays per-node run status from a
``JobRun``'s ``TaskRun`` rows.  The diff-save half (``apply_job_dag_doc``)
lands with the save route.

The canvas speaks the same ``CanvasDoc`` the data-product and DataFrame
Studio editors do, so the shared Drawflow editor shell drives it unchanged:

* node id    — ``task-{job_task.id}`` for a persisted task; the editor mints
  its own ids for new nodes, which the save path remaps to ``task-{pk}``.
* block_type — the task ``kind`` (a ``JOB_REGISTRY`` executor key); the
  editor's palette is fed from the registry so it never declares a kind the
  scheduler cannot run.
* config     — ``{name, params, max_retries, retry_backoff_seconds}`` where
  ``params`` is the executor's own ``job_tasks.config`` dict.
* edge A→B   — *B depends on A*: a ``out`` source pin into a ``deps`` target
  pin, matching the dependency direction the scheduler's topo-sort and
  ``validate_dag`` already use (source precedes target).

Unlike the data-product canvas there is **no graph store**: a job's tasks
*are* the document, so positions are not persisted — the editor lays the
graph out on load.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import JobRun, JobTask, TaskRun
from pointlessql.services.canvas_core import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
    topo_sort,
    validate_envelope,
)

_NODE_PREFIX = "task-"
SOURCE_PIN = "out"
TARGET_PIN = "deps"


def node_id_for_task(task_id: int) -> str:
    """Return the canvas node id for a persisted task (``task-{pk}``)."""
    return f"{_NODE_PREFIX}{task_id}"


def task_id_from_node_id(node_id: str) -> int | None:
    """Return the task pk encoded in *node_id*, or ``None`` for a new node.

    Editor-minted node ids (a fresh-node UUID, or any id that does not match
    ``task-<int>``) return ``None`` so the save path treats them as creates.
    """
    if not node_id.startswith(_NODE_PREFIX):
        return None
    try:
        return int(node_id[len(_NODE_PREFIX) :])
    except ValueError:
        return None


def _parse_deps(raw: str) -> list[int]:
    """Leniently deserialize a ``job_tasks.depends_on`` string to ids."""
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    typed: list[int] = []
    for item in value:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(item, int):
            typed.append(item)
    return typed


def _task_node(task: JobTask) -> CanvasNode:
    """Map one ``JobTask`` row to a ``CanvasNode``."""
    try:
        params = json.loads(task.config or "{}")
    except json.JSONDecodeError:
        params = {}
    if not isinstance(params, dict):
        params = {}
    return CanvasNode(
        id=node_id_for_task(task.id),
        block_type=str(task.kind),
        config={
            "name": task.name,
            "params": params,
            "max_retries": int(task.max_retries or 0),
            "retry_backoff_seconds": int(task.retry_backoff_seconds or 0),
        },
        position=None,
    )


def build_job_dag_doc(factory: Any, *, job_id: int) -> CanvasDoc:
    """Snapshot a job's ``JobTask`` rows as a ``CanvasDoc``.

    Args:
        factory: Session factory for the own-metadata DB.
        job_id: The job whose task graph to render.

    Returns:
        A ``CanvasDoc`` with one node per task and one edge per
        ``depends_on`` entry (``dep → task``).  Empty when the job has no
        tasks.
    """
    with factory() as session:
        tasks = list(
            session.scalars(select(JobTask).where(JobTask.job_id == job_id))
        )
    nodes = [_task_node(t) for t in tasks]
    edges: list[CanvasEdge] = []
    for t in tasks:
        for dep_id in _parse_deps(t.depends_on):
            edges.append(
                CanvasEdge(
                    id=f"e-{dep_id}->{t.id}",
                    source_node_id=node_id_for_task(dep_id),
                    source_pin=SOURCE_PIN,
                    target_node_id=node_id_for_task(t.id),
                    target_pin=TARGET_PIN,
                )
            )
    return CanvasDoc(nodes=nodes, edges=edges)


def validate_job_dag_doc(
    doc: CanvasDoc, *, known_kinds: set[str] | None = None
) -> list[str]:
    """Run side-effect-free checks on an edited task-chain doc.

    Surfaces the same failure classes the save path would reject — a cyclic
    or structurally invalid graph, an unknown task kind, a missing or
    duplicate task name — as human-readable strings, so the editor can badge
    problems before the user saves.

    Args:
        doc: The edited canvas document.
        known_kinds: The runnable task kinds (``JOB_REGISTRY.kinds()``).  When
            given, any node whose ``block_type`` is not in the set is flagged.

    Returns:
        A list of issue messages; empty when the doc is valid.
    """
    issues: list[str] = []

    envelope_errors: list[CompileError] = []
    validate_envelope(doc, envelope_errors)
    issues.extend(e.message for e in envelope_errors)

    # Only walk the graph once the envelope is structurally sound — topo_sort
    # assumes edges reference existing, non-duplicate nodes.
    if not envelope_errors:
        cycle_errors: list[CompileError] = []
        topo_sort(doc.nodes, doc.edges, cycle_errors)
        issues.extend(e.message for e in cycle_errors)

    seen_names: set[str] = set()
    for node in doc.nodes:
        if known_kinds is not None and node.block_type not in known_kinds:
            issues.append(f"task {node.id!r}: unknown kind {node.block_type!r}")
        name = str((node.config or {}).get("name", "")).strip()
        if not name:
            issues.append(f"task {node.id!r}: name is required")
        elif name in seen_names:
            issues.append(f"duplicate task name: {name!r}")
        else:
            seen_names.add(name)

    return issues


def build_run_status(factory: Any, *, job_id: int, run_id: int) -> dict[str, str]:
    """Map a run's ``TaskRun`` statuses onto canvas node ids.

    Args:
        factory: Session factory for the own-metadata DB.
        job_id: The job the run must belong to (guards cross-job leakage).
        run_id: The ``JobRun`` whose per-task statuses to overlay.

    Returns:
        ``{node_id: status}`` for each task that has a ``TaskRun`` in the
        run (status one of ``pending`` / ``running`` / ``succeeded`` /
        ``failed`` / ``skipped``).  Empty when the run is unknown or belongs
        to another job.
    """
    statuses: dict[str, str] = {}
    with factory() as session:
        run = session.get(JobRun, run_id)
        if run is None or run.job_id != job_id:
            return statuses
        rows = session.scalars(
            select(TaskRun).where(TaskRun.job_run_id == run_id)
        )
        for tr in rows:
            statuses[node_id_for_task(tr.task_id)] = str(tr.status)
    return statuses
