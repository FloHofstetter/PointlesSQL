"""Tests saved-audit-query CRUD + run + export.

Covers:

* SQL allow-list / SELECT-only enforcement at the service layer.
* CRUD route + admin gate.
* Starter-row protection (PATCH/DELETE refuse).
* CSV + JSON export emit a Content-Disposition + audit_log row.
"""

from __future__ import annotations

import csv as _csv
import datetime
import json
import uuid
from io import StringIO

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import AgentRun, AuditLog, SavedAuditQuery
from pointlessql.services.audit import saved_queries as svc


@pytest.fixture(autouse=True)
def _seed_starters() -> None:
    """Re-seed starter rows for every test, since the autouse db
    fixture rebuilds the schema between runs.
    """
    svc.bootstrap_starter_rows(app.state.session_factory)


# ---------------------------------------------------------------------
# allow-list / SELECT-only
# ---------------------------------------------------------------------


def test_validate_sql_accepts_audit_table_select() -> None:
    refs = svc.validate_sql("SELECT id FROM agent_runs")
    assert refs == {"agent_runs"}


def test_validate_sql_rejects_unlisted_table() -> None:
    with pytest.raises(ValidationError):
        svc.validate_sql("SELECT * FROM delta_tables")


def test_validate_sql_rejects_update() -> None:
    with pytest.raises(ValidationError):
        svc.validate_sql("UPDATE agent_runs SET status='succeeded'")


def test_validate_sql_rejects_delete() -> None:
    with pytest.raises(ValidationError):
        svc.validate_sql("DELETE FROM agent_runs")


def test_validate_sql_rejects_drop() -> None:
    with pytest.raises(ValidationError):
        svc.validate_sql("DROP TABLE agent_runs")


def test_validate_sql_allows_join_within_allowlist() -> None:
    refs = svc.validate_sql(
        "SELECT r.principal, COUNT(o.id) "
        "FROM agent_runs r JOIN agent_run_operations o ON o.agent_run_id = r.id "
        "GROUP BY r.principal"
    )
    assert "agent_runs" in refs
    assert "agent_run_operations" in refs


# ---------------------------------------------------------------------
# starter rows
# ---------------------------------------------------------------------


def test_bootstrap_seeds_five_starter_rows() -> None:
    factory = app.state.session_factory
    with factory() as s:
        starters = list(s.scalars(select(SavedAuditQuery).where(SavedAuditQuery.is_starter)))
    assert len(starters) >= 5
    slugs = {r.slug for r in starters}
    assert "rollbacks-last-quarter" in slugs


def test_bootstrap_is_idempotent() -> None:
    factory = app.state.session_factory
    inserted_first = svc.bootstrap_starter_rows(factory)
    inserted_again = svc.bootstrap_starter_rows(factory)
    assert inserted_first == 0  # the autouse fixture already inserted them
    assert inserted_again == 0


# ---------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_route_admin_only(non_admin_client: httpx.AsyncClient) -> None:
    r = await non_admin_client.get("/api/saved-audit-queries")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_route_returns_starters_first(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.get("/api/saved-audit-queries")
    assert r.status_code == 200
    rows = r.json()["saved_audit_queries"]
    assert rows[0]["is_starter"] is True


@pytest.mark.asyncio
async def test_create_then_get_then_delete_roundtrip(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/saved-audit-queries",
        json={
            "title": "My audit",
            "description": "test",
            "sql_text": "SELECT id FROM agent_runs LIMIT 1",
        },
    )
    assert create.status_code == 200
    slug = create.json()["slug"]
    get = await admin_client.get(f"/api/saved-audit-queries/{slug}")
    assert get.status_code == 200
    delete = await admin_client.delete(f"/api/saved-audit-queries/{slug}")
    assert delete.status_code == 200
    get_again = await admin_client.get(f"/api/saved-audit-queries/{slug}")
    assert get_again.status_code == 404


@pytest.mark.asyncio
async def test_create_rejects_unlisted_table(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.post(
        "/api/saved-audit-queries",
        json={
            "title": "broken",
            "sql_text": "SELECT * FROM delta_tables",
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_starter_patch_returns_404(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.patch(
        "/api/saved-audit-queries/rollbacks-last-quarter",
        json={"title": "tampered"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_starter_delete_returns_404(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.delete("/api/saved-audit-queries/rollbacks-last-quarter")
    assert r.status_code == 404


# ---------------------------------------------------------------------
# /run + export
# ---------------------------------------------------------------------


def _seed_one_run() -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=str(uuid.uuid4()),
                principal="alice@example.com",
                agent_id="etl",
                notebook_path="x.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.commit()


@pytest.mark.asyncio
async def test_run_returns_rows_for_starter(admin_client: httpx.AsyncClient) -> None:
    _seed_one_run()
    r = await admin_client.post("/api/saved-audit-queries/top-mutating-principals-30d/run")
    assert r.status_code == 200
    body = r.json()
    assert "columns" in body
    assert "rows" in body


@pytest.mark.asyncio
async def test_run_returns_404_for_missing_slug(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.post("/api/saved-audit-queries/does-not-exist/run")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_csv_export_streams_rows(admin_client: httpx.AsyncClient) -> None:
    _seed_one_run()
    r = await admin_client.get("/api/saved-audit-queries/top-mutating-principals-30d/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    reader = _csv.reader(StringIO(r.text))
    header = next(reader)
    assert "principal" in header


@pytest.mark.asyncio
async def test_json_export_streams_payload(admin_client: httpx.AsyncClient) -> None:
    _seed_one_run()
    r = await admin_client.get("/api/saved-audit-queries/top-mutating-principals-30d/export.json")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    body = json.loads(r.text)
    assert body["slug"] == "top-mutating-principals-30d"
    assert isinstance(body["rows"], list)


@pytest.mark.asyncio
async def test_csv_export_writes_audit_log(admin_client: httpx.AsyncClient) -> None:
    await admin_client.get("/api/saved-audit-queries/top-mutating-principals-30d/export.csv")
    factory = app.state.session_factory
    with factory() as s:
        rows = list(
            s.scalars(select(AuditLog).where(AuditLog.action == "saved_audit_query.exported"))
        )
    assert rows, "expected an audit_log row of action saved_audit_query.exported"
    assert rows[-1].target.startswith("saved_audit_query:")


def test_list_paginated_starter_first_then_offset() -> None:
    """``list_paginated`` honors ``offset`` + ``limit`` and returns global total."""
    factory = app.state.session_factory
    rows_first, total_first = svc.list_paginated(factory, offset=0, limit=2)
    assert len(rows_first) == 2
    assert rows_first[0]["is_starter"] is True
    rows_next, total_next = svc.list_paginated(factory, offset=2, limit=2)
    assert total_first == total_next
    assert {r["slug"] for r in rows_first}.isdisjoint({r["slug"] for r in rows_next})


@pytest.mark.asyncio
async def test_audit_queries_html_page_renders_with_pager(
    admin_client: httpx.AsyncClient,
) -> None:
    """GET /audit/queries renders the cockpit and accepts ``?offset=``."""
    r = await admin_client.get("/audit/queries")
    assert r.status_code == 200, r.text
    # Page heading lower-cases "saved queries" per the breadcrumb style;
    # match the actual rendered title.
    assert "saved queries" in r.text
    r2 = await admin_client.get("/audit/queries?offset=0")
    assert r2.status_code == 200, r2.text
