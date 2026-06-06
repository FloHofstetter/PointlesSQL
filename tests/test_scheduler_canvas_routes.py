"""Tests for the scheduler task-chain canvas service + read routes.

Covers the ``JobTask`` ⇄ ``CanvasDoc`` bridge
(:mod:`pointlessql.services.scheduler._canvas`): building a doc from live
task rows, the side-effect-free validate checks, the per-node run-status
overlay, and the registry-fed kind palette.  Pure service-level tests
driven through an in-memory session factory — no live stack.
"""

from __future__ import annotations

import datetime
import itertools
import json
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.models import (
    Base,
    Job,
    JobRun,
    JobTask,
    TaskRun,
    User,
)
from pointlessql.services.scheduler import build_default_registry
from pointlessql.services.scheduler._canvas import (
    build_job_dag_doc,
    build_run_status,
    node_id_for_task,
    task_id_from_node_id,
    validate_job_dag_doc,
)

_SEED_COUNTER = itertools.count()


@pytest.fixture
def canvas_factory() -> Any:
    """In-memory session factory seeded with one runner user."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="runner@test.com",
                display_name="Runner",
                password_hash="x",
                is_admin=False,
                created_at=datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_job_with_tasks(
    factory: Any, tasks_spec: list[dict[str, Any]]
) -> tuple[int, dict[str, int]]:
    """Create a job + ``JobTask`` rows; resolve ``depends_on`` names to ids.

    Returns ``(job_id, {task_name: task_id})``.
    """
    now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    with factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        job = Job(
            name=f"dag-{next(_SEED_COUNTER)}",
            cron_expr="* * * * *",
            run_as_user_id=user.id,
            kind="python",
            config="{}",
            is_paused=False,
            max_parallel_runs=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        name_to_id: dict[str, int] = {}
        for spec in tasks_spec:
            jt = JobTask(
                job_id=job.id,
                name=spec["name"],
                order=0,
                kind=spec.get("kind", "python"),
                config=json.dumps(spec.get("config") or {}),
                depends_on="[]",
                max_retries=int(spec.get("max_retries", 0)),
                retry_backoff_seconds=int(spec.get("retry_backoff_seconds", 0)),
            )
            session.add(jt)
            session.flush()
            name_to_id[spec["name"]] = jt.id
        for spec in tasks_spec:
            deps = [name_to_id[n] for n in spec.get("depends_on") or []]
            row = session.get(JobTask, name_to_id[spec["name"]])
            assert row is not None
            row.depends_on = json.dumps(deps)
        session.commit()
        return job.id, name_to_id


# --- node-id helpers -------------------------------------------------------


def test_node_id_round_trip() -> None:
    assert node_id_for_task(7) == "task-7"
    assert task_id_from_node_id("task-7") == 7


def test_task_id_from_new_node_id_is_none() -> None:
    assert task_id_from_node_id("n-abc123") is None
    assert task_id_from_node_id("task-nope") is None


# --- build_job_dag_doc -----------------------------------------------------


def test_build_doc_empty_job(canvas_factory: Any) -> None:
    job_id, _ = _seed_job_with_tasks(canvas_factory, [])
    doc = build_job_dag_doc(canvas_factory, job_id=job_id)
    assert doc.nodes == []
    assert doc.edges == []


def test_build_doc_nodes_and_edges(canvas_factory: Any) -> None:
    job_id, ids = _seed_job_with_tasks(
        canvas_factory,
        [
            {"name": "extract", "kind": "python", "config": {"foo": 1}},
            {"name": "load", "kind": "pg_sync", "depends_on": ["extract"]},
        ],
    )
    doc = build_job_dag_doc(canvas_factory, job_id=job_id)
    by_id = {n.id: n for n in doc.nodes}
    extract = by_id[node_id_for_task(ids["extract"])]
    load = by_id[node_id_for_task(ids["load"])]
    assert extract.block_type == "python"
    assert extract.config["name"] == "extract"
    assert extract.config["params"] == {"foo": 1}
    assert load.block_type == "pg_sync"
    # one edge extract -> load (B depends on A: source=dep, target=task)
    assert len(doc.edges) == 1
    edge = doc.edges[0]
    assert edge.source_node_id == node_id_for_task(ids["extract"])
    assert edge.target_node_id == node_id_for_task(ids["load"])
    assert edge.source_pin == "out"
    assert edge.target_pin == "deps"


# --- validate_job_dag_doc --------------------------------------------------


def _kinds() -> set[str]:
    return set(build_default_registry().kinds())


def test_validate_clean_doc(canvas_factory: Any) -> None:
    job_id, _ = _seed_job_with_tasks(
        canvas_factory,
        [
            {"name": "a", "kind": "python"},
            {"name": "b", "kind": "python", "depends_on": ["a"]},
        ],
    )
    doc = build_job_dag_doc(canvas_factory, job_id=job_id)
    assert validate_job_dag_doc(doc, known_kinds=_kinds()) == []


def test_validate_unknown_kind(canvas_factory: Any) -> None:
    job_id, _ = _seed_job_with_tasks(
        canvas_factory, [{"name": "a", "kind": "python"}]
    )
    doc = build_job_dag_doc(canvas_factory, job_id=job_id)
    doc.nodes[0].block_type = "not_a_real_kind"
    issues = validate_job_dag_doc(doc, known_kinds=_kinds())
    assert any("unknown kind" in i for i in issues)


def test_validate_missing_name() -> None:
    from pointlessql.services.canvas_core import CanvasDoc, CanvasNode

    doc = CanvasDoc(
        nodes=[CanvasNode(id="task-1", block_type="python", config={"name": ""})],
        edges=[],
    )
    issues = validate_job_dag_doc(doc, known_kinds=_kinds())
    assert any("name is required" in i for i in issues)


def test_validate_duplicate_name() -> None:
    from pointlessql.services.canvas_core import CanvasDoc, CanvasNode

    doc = CanvasDoc(
        nodes=[
            CanvasNode(id="task-1", block_type="python", config={"name": "dup"}),
            CanvasNode(id="task-2", block_type="python", config={"name": "dup"}),
        ],
        edges=[],
    )
    issues = validate_job_dag_doc(doc, known_kinds=_kinds())
    assert any("duplicate task name" in i for i in issues)


def test_validate_cycle() -> None:
    from pointlessql.services.canvas_core import CanvasDoc, CanvasEdge, CanvasNode

    doc = CanvasDoc(
        nodes=[
            CanvasNode(id="task-1", block_type="python", config={"name": "a"}),
            CanvasNode(id="task-2", block_type="python", config={"name": "b"}),
        ],
        edges=[
            CanvasEdge(
                id="e1",
                source_node_id="task-1",
                source_pin="out",
                target_node_id="task-2",
                target_pin="deps",
            ),
            CanvasEdge(
                id="e2",
                source_node_id="task-2",
                source_pin="out",
                target_node_id="task-1",
                target_pin="deps",
            ),
        ],
    )
    issues = validate_job_dag_doc(doc, known_kinds=_kinds())
    assert any("cycle" in i.lower() for i in issues)


# --- build_run_status ------------------------------------------------------


def test_run_status_overlay(canvas_factory: Any) -> None:
    job_id, ids = _seed_job_with_tasks(
        canvas_factory,
        [
            {"name": "a", "kind": "python"},
            {"name": "b", "kind": "python", "depends_on": ["a"]},
        ],
    )
    now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    with canvas_factory() as session:
        run = JobRun(
            job_id=job_id, started_at=now, status="running", trigger="manual"
        )
        session.add(run)
        session.flush()
        session.add(
            TaskRun(
                job_run_id=run.id,
                task_id=ids["a"],
                status="succeeded",
                started_at=now,
            )
        )
        session.add(
            TaskRun(
                job_run_id=run.id,
                task_id=ids["b"],
                status="running",
                started_at=now,
            )
        )
        session.commit()
        run_id = run.id

    statuses = build_run_status(canvas_factory, job_id=job_id, run_id=run_id)
    assert statuses[node_id_for_task(ids["a"])] == "succeeded"
    assert statuses[node_id_for_task(ids["b"])] == "running"


def test_run_status_cross_job_is_empty(canvas_factory: Any) -> None:
    job_a, _ = _seed_job_with_tasks(canvas_factory, [{"name": "a"}])
    job_b, ids_b = _seed_job_with_tasks(canvas_factory, [{"name": "b"}])
    now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    with canvas_factory() as session:
        run = JobRun(
            job_id=job_b, started_at=now, status="running", trigger="manual"
        )
        session.add(run)
        session.flush()
        run_id = run.id
        session.commit()
    # Asking for job_a's view of a run that belongs to job_b returns nothing.
    assert build_run_status(canvas_factory, job_id=job_a, run_id=run_id) == {}


# --- registry palette ------------------------------------------------------


def test_registry_kinds_nonempty() -> None:
    kinds = build_default_registry().kinds()
    assert "python" in kinds
    assert "papermill" in kinds
    assert len(kinds) == len(set(kinds))
