"""Sprint 28.2 — workspace_id on user-owned + scheduler tables.

Asserts:

* Schema sanity (workspace_id on jobs / runs / tasks / dashboards /
  saved_queries / saved_audit_queries / recent_tables / alerts /
  alert_events / notebook_outputs / notebook_cell_runs).
* JobRun creation propagates Job.workspace_id.
* recent_tables.upsert is per-workspace; UNIQUE allows same user
  visiting the same table from two workspaces.
* SavedQuery creation honours workspace_id.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.models import (
    Job,
    JobLog,
    JobRun,
    RecentTable,
    SavedQuery,
    User,
)
from pointlessql.services import recents as recents_service
from pointlessql.services import saved_queries as saved_queries_service
from pointlessql.services.scheduler.runs import _start_run, log_job
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        user = session.query(User).filter(User.email == "test@test.com").one()
        return user.id


@pytest.fixture
def two_workspaces() -> tuple[int, int]:
    a = workspaces_service.create_workspace(_factory(), slug="ws-uo", name="UO A")
    b = workspaces_service.create_workspace(_factory(), slug="ws-uo-b", name="UO B")
    return a.id, b.id


def test_28_2_columns_exist() -> None:
    from sqlalchemy import inspect

    insp = inspect(_factory()().get_bind())
    for table in (
        "jobs",
        "job_runs",
        "job_tasks",
        "task_runs",
        "job_logs",
        "dashboards",
        "saved_queries",
        "saved_audit_queries",
        "recent_tables",
        "alerts",
        "alert_events",
        "notebook_outputs",
        "notebook_cell_runs",
    ):
        cols = {c["name"] for c in insp.get_columns(table)}
        assert "workspace_id" in cols, f"{table} missing workspace_id"


def test_jobrun_inherits_workspace_from_parent_job(
    two_workspaces: tuple[int, int],
) -> None:
    ws_a, _ = two_workspaces
    now = dt.datetime.now(dt.UTC)
    with _factory()() as session:
        job = Job(
            workspace_id=ws_a,
            name=f"ws-test-job-{ws_a}",
            cron_expr="0 * * * *",
            run_as_user_id=_admin_user_id(),
            kind="python",
            config="{}",
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = int(job.id)

    with _factory()() as session:
        run = _start_run(session, job_id, "manual")
        assert int(run.workspace_id) == ws_a

    # log_job inherits workspace from JobRun.
    with _factory()() as session:
        run_id = session.scalar(
            __import__("sqlalchemy").select(JobRun.id).where(JobRun.job_id == job_id)
        )
    log_job(_factory(), int(run_id), None, "INFO", "test")
    with _factory()() as session:
        log_row = session.query(JobLog).filter(JobLog.job_run_id == int(run_id)).first()
        assert log_row is not None
        assert int(log_row.workspace_id) == ws_a


def test_recents_upsert_is_per_workspace(two_workspaces: tuple[int, int]) -> None:
    ws_a, ws_b = two_workspaces
    user_id = _admin_user_id()
    fqn = "main.silver.orders"
    recents_service.record_table_visit(_factory(), user_id, fqn, workspace_id=ws_a)
    recents_service.record_table_visit(_factory(), user_id, fqn, workspace_id=ws_b)
    with _factory()() as session:
        rows = (
            session.query(RecentTable)
            .filter(RecentTable.user_id == user_id, RecentTable.table_full_name == fqn)
            .all()
        )
        ws_ids = {int(r.workspace_id) for r in rows}
        assert ws_a in ws_ids
        assert ws_b in ws_ids


def test_recents_unique_constraint_blocks_same_workspace_dup(
    two_workspaces: tuple[int, int],
) -> None:
    ws_a, _ = two_workspaces
    now = dt.datetime.now(dt.UTC)
    fqn = "main.bronze.alpha"
    with _factory()() as session:
        session.add(
            RecentTable(
                workspace_id=ws_a,
                user_id=_admin_user_id(),
                table_full_name=fqn,
                last_visited_at=now,
            )
        )
        session.commit()
    with _factory()() as session:
        session.add(
            RecentTable(
                workspace_id=ws_a,
                user_id=_admin_user_id(),
                table_full_name=fqn,
                last_visited_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_list_recent_tables_filters_by_workspace(
    two_workspaces: tuple[int, int],
) -> None:
    ws_a, ws_b = two_workspaces
    user_id = _admin_user_id()
    recents_service.record_table_visit(_factory(), user_id, "main.silver.x", workspace_id=ws_a)
    recents_service.record_table_visit(_factory(), user_id, "main.gold.y", workspace_id=ws_b)

    rows_a = recents_service.top_recent_tables(_factory(), user_id, workspace_id=ws_a)
    rows_b = recents_service.top_recent_tables(_factory(), user_id, workspace_id=ws_b)
    fqns_a = {r["table_full_name"] for r in rows_a}
    fqns_b = {r["table_full_name"] for r in rows_b}
    assert "main.silver.x" in fqns_a
    assert "main.silver.x" not in fqns_b
    assert "main.gold.y" in fqns_b


def test_create_saved_query_writes_workspace_id(
    two_workspaces: tuple[int, int],
) -> None:
    ws_a, _ = two_workspaces
    user_id = _admin_user_id()
    payload = saved_queries_service.create_saved_query(
        _factory(),
        owner_id=user_id,
        title="Workspace A test",
        description=None,
        sql_text="SELECT 1",
        workspace_id=ws_a,
    )
    with _factory()() as session:
        row = session.get(SavedQuery, payload["id"])
        assert row is not None
        assert int(row.workspace_id) == ws_a
