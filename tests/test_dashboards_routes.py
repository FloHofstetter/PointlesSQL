"""Sprint 57.5 — FastAPI route smoke-tests for dashboards_routes.py.

Covers all 9 endpoints (5 JSON CRUD + sub-resource refresh +
3 HTML pages).  Tests focus on the route layer: auth gates,
serialization shape, validation rejections, audit emission.

The deeper papermill / job-run plumbing for ``/dashboards/{slug}/
output`` is out of scope here — Phase 21 already covers that on
the job-run side.  This file only asserts the route is reachable
and degrades cleanly when no run is available.
"""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AuditLog, Dashboard, Job


def _wipe_dashboards_and_audit() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(Dashboard).delete()
        session.query(AuditLog).delete()
        session.commit()


def _seed_job(name: str = "j-test") -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        job = Job(
            name=name,
            cron_expr="0 0 * * *",
            run_as_user_id=1,
            kind="papermill",
            config="{}",
            is_paused=False,
            max_parallel_runs=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return int(job.id)


def _audit_actions() -> list[str]:
    factory = app.state.session_factory
    with factory() as session:
        return [r.action for r in session.query(AuditLog).all()]


@pytest.fixture(autouse=True)
def _clean_dashboards() -> None:
    _wipe_dashboards_and_audit()


# -- JSON: list / tree / create / update / delete --


async def test_list_dashboards_empty(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/dashboards")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_dashboards_tree_mirrors_list(admin_client: httpx.AsyncClient) -> None:
    job_id = _seed_job()
    create = await admin_client.post(
        "/api/dashboards",
        json={
            "slug": "demo",
            "title": "Demo",
            "notebook_path": "notebooks/demo.py",
            "job_id": job_id,
        },
    )
    assert create.status_code == 200
    tree = await admin_client.get("/api/dashboards/tree")
    list_resp = await admin_client.get("/api/dashboards")
    assert tree.status_code == 200
    assert tree.json() == list_resp.json()


async def test_create_dashboard_emits_audit(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "notebooks/d1.py"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "d1"
    assert "create_dashboard" in _audit_actions()


async def test_create_dashboard_rejects_bad_slug(
    admin_client: httpx.AsyncClient,
) -> None:
    resp = await admin_client.post(
        "/api/dashboards",
        json={"slug": "Bad Slug!", "title": "X", "notebook_path": "x.py"},
    )
    assert resp.status_code == 422


async def test_create_dashboard_rejects_duplicate_slug(
    admin_client: httpx.AsyncClient,
) -> None:
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "dup", "title": "X", "notebook_path": "x.py"},
    )
    resp = await admin_client.post(
        "/api/dashboards",
        json={"slug": "dup", "title": "Y", "notebook_path": "y.py"},
    )
    assert resp.status_code == 422


async def test_create_dashboard_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    resp = await non_admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    assert resp.status_code == 403


async def test_update_dashboard_changes_fields(
    admin_client: httpx.AsyncClient,
) -> None:
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    resp = await admin_client.patch(
        "/api/dashboards/d1",
        json={"title": "D1-renamed", "description": "new desc"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "D1-renamed"
    assert "update_dashboard" in _audit_actions()


async def test_update_dashboard_rejects_empty_title(
    admin_client: httpx.AsyncClient,
) -> None:
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    resp = await admin_client.patch("/api/dashboards/d1", json={"title": "  "})
    assert resp.status_code == 422


async def test_update_dashboard_404_on_missing_slug(
    admin_client: httpx.AsyncClient,
) -> None:
    resp = await admin_client.patch("/api/dashboards/missing", json={"title": "x"})
    assert resp.status_code == 404


async def test_delete_dashboard_emits_audit(admin_client: httpx.AsyncClient) -> None:
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    resp = await admin_client.delete("/api/dashboards/d1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "slug": "d1"}
    assert "delete_dashboard" in _audit_actions()


async def test_delete_dashboard_404_on_missing_slug(
    admin_client: httpx.AsyncClient,
) -> None:
    resp = await admin_client.delete("/api/dashboards/missing")
    assert resp.status_code == 404


async def test_refresh_dashboard_requires_bound_job(
    admin_client: httpx.AsyncClient,
) -> None:
    """Dashboard with no job_id can't be refreshed."""
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    resp = await admin_client.post("/api/dashboards/d1/refresh")
    assert resp.status_code == 422


# -- HTML pages --


async def test_dashboards_index_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/dashboards")
    assert resp.status_code == 200


async def test_dashboard_detail_renders_when_no_run(
    admin_client: httpx.AsyncClient,
) -> None:
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    resp = await admin_client.get("/dashboards/d1")
    assert resp.status_code == 200


async def test_dashboard_detail_404_on_missing_slug(
    admin_client: httpx.AsyncClient,
) -> None:
    resp = await admin_client.get("/dashboards/missing")
    assert resp.status_code == 404


async def test_dashboard_output_404_when_no_succeeded_run(
    admin_client: httpx.AsyncClient,
) -> None:
    """Output endpoint requires at least one succeeded run."""
    await admin_client.post(
        "/api/dashboards",
        json={"slug": "d1", "title": "D1", "notebook_path": "x.py"},
    )
    resp = await admin_client.get("/dashboards/d1/output")
    assert resp.status_code == 404
