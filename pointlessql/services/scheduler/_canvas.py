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
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import select

from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models import Job, JobRun, JobTask, TaskRun
from pointlessql.services.canvas_core import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
    topo_sort,
    validate_envelope,
)
from pointlessql.services.scheduler.dag import validate_dag

# Run states that pin a task in place — a task with a TaskRun in one of
# these states cannot be deleted from under the live loop.
_LIVE_RUN_STATUSES = ("running", "pending")

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


class JobDagSaveSummary(BaseModel):
    """Outcome of a task-chain diff-save."""

    created: int
    updated: int
    deleted: int
    # client-minted node id → its persisted ``task-{pk}`` id, so the editor
    # can rewrite the optimistic nodes it drew before the save returned.
    id_remap: dict[str, str]


def _tasks_with_live_runs(
    session: Any, job_id: int, task_ids: list[int]
) -> list[int]:
    """Return the subset of *task_ids* pinned by an in-flight run.

    A task is pinned when it has a ``TaskRun`` whose parent ``JobRun`` is
    still ``running`` and the task itself is ``pending`` or ``running`` —
    deleting it would desync the live loop mid-execution.
    """
    if not task_ids:
        return []
    live_run_ids = list(
        session.scalars(
            select(JobRun.id).where(
                JobRun.job_id == job_id, JobRun.status == "running"
            )
        )
    )
    if not live_run_ids:
        return []
    rows = session.scalars(
        select(TaskRun.task_id).where(
            TaskRun.job_run_id.in_(live_run_ids),
            TaskRun.task_id.in_(task_ids),
            TaskRun.status.in_(_LIVE_RUN_STATUSES),
        )
    )
    return sorted({int(tid) for tid in rows})


def _node_fields(node: CanvasNode) -> tuple[str, str, str, int, int]:
    """Extract the JobTask columns carried in a canvas node's config."""
    cfg = node.config or {}
    name = str(cfg.get("name", "")).strip()
    raw_params = cfg.get("params")
    params = cast("dict[str, Any]", raw_params if isinstance(raw_params, dict) else {})
    max_retries = int(cfg.get("max_retries") or 0)
    backoff = int(cfg.get("retry_backoff_seconds") or 0)
    return name, str(node.block_type), json.dumps(params), max_retries, backoff


def apply_job_dag_doc(
    factory: Any,
    *,
    job_id: int,
    doc: CanvasDoc,
    known_kinds: set[str] | None = None,
) -> JobDagSaveSummary:
    """Diff *doc* against a job's ``JobTask`` rows and apply the delta.

    A node whose id is ``task-{pk}`` updates that task; any other id (an
    editor-minted new node) creates one.  Tasks absent from the doc are
    deleted — unless pinned by an in-flight run.  ``depends_on`` is recomputed
    from the edges (``B depends on A`` for an ``A → B`` edge).  The whole
    delta runs in one transaction and is gated by ``validate_dag`` *before*
    commit, so a cyclic edit rolls back and never reaches the live loop.

    Args:
        factory: Session factory for the own-metadata DB.
        job_id: The job whose task graph to overwrite.
        doc: The edited canvas document.
        known_kinds: Runnable kinds for the pre-flight check; when given an
            unknown ``block_type`` is rejected before any write.

    Returns:
        A :class:`JobDagSaveSummary` with create/update/delete counts and the
        new-node id remap.

    Raises:
        ResourceNotFoundError: When *job_id* does not exist.
        ValidationError: On a pre-flight shape/kind/name failure, an attempt
            to delete a task with a live run, or a cyclic resulting graph.
    """
    issues = validate_job_dag_doc(doc, known_kinds=known_kinds)
    if issues:
        raise ValidationError("; ".join(issues))

    created = updated = deleted = 0
    id_remap: dict[str, str] = {}

    with factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise ResourceNotFoundError(f"Job {job_id} not found")
        existing = {
            t.id: t
            for t in session.scalars(
                select(JobTask).where(JobTask.job_id == job_id)
            )
        }

        node_to_task: dict[str, JobTask] = {}
        seen_ids: set[int] = set()
        for order, node in enumerate(doc.nodes):
            name, kind, params_json, max_retries, backoff = _node_fields(node)
            tid = task_id_from_node_id(node.id)
            if tid is not None and tid in existing:
                task = existing[tid]
                task.name = name
                task.kind = kind
                task.config = params_json
                task.max_retries = max_retries
                task.retry_backoff_seconds = backoff
                task.order = order
                seen_ids.add(tid)
                updated += 1
            else:
                task = JobTask(
                    workspace_id=job.workspace_id or 1,
                    job_id=job_id,
                    name=name,
                    order=order,
                    kind=kind,
                    config=params_json,
                    depends_on="[]",
                    max_retries=max_retries,
                    retry_backoff_seconds=backoff,
                )
                session.add(task)
                session.flush()
                id_remap[node.id] = node_id_for_task(task.id)
                created += 1
            node_to_task[node.id] = task

        # Delete tasks the doc dropped — guarded against in-flight runs.
        to_delete = [t for tid, t in existing.items() if tid not in seen_ids]
        pinned = _tasks_with_live_runs(
            session, job_id, [t.id for t in to_delete]
        )
        if pinned:
            names = sorted(
                existing[tid].name for tid in pinned if tid in existing
            )
            raise ValidationError(
                f"cannot delete task(s) with an in-flight run: {names}"
            )
        for task in to_delete:
            session.delete(task)
            deleted += 1

        # Recompute depends_on from the edges (A → B ⇒ B depends on A).
        deps_by_task: dict[int, list[int]] = {
            t.id: [] for t in node_to_task.values()
        }
        for edge in doc.edges:
            src = node_to_task.get(edge.source_node_id)
            tgt = node_to_task.get(edge.target_node_id)
            if src is None or tgt is None:
                continue
            bucket = deps_by_task.setdefault(tgt.id, [])
            if src.id not in bucket:
                bucket.append(src.id)
        for task in node_to_task.values():
            task.depends_on = json.dumps(deps_by_task.get(task.id, []))

        session.flush()
        remaining = list(
            session.scalars(select(JobTask).where(JobTask.job_id == job_id))
        )
        # Final gate on the persisted rows — rolls back the whole save on a
        # cycle (the context manager exits without commit on the raise).
        validate_dag(remaining)
        session.commit()

    return JobDagSaveSummary(
        created=created, updated=updated, deleted=deleted, id_remap=id_remap
    )
