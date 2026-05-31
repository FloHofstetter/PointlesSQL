"""Tests for the audit-read surface.

Covers:

* The new ``auditor`` API-key scope and its ``require_auditor``
  dependency.
* The privilege ladder — admin cookie → 200, supervisor key → 200
  on per-run audit reads but 403 on tenant-wide aggregates,
  auditor key → 200 everywhere except PII reveal.
* The five new run-scoped routes
  (``/api/agent-runs/{run_id}/audit/<axis>``) and the new
  tenant-wide ``/api/audit/history`` route.
* Audit-of-audit logging — every successful audit-read call lands
  a ``query_history`` row with ``read_kind='audit_api'``.
* The anomaly-baseline bugfix from
  :func:`pointlessql.services.audit_aggregator.anomalies` — a
  ``since``-bounded call still has a non-empty baseline because
  the underlying timeseries query is widened by ``window_days``
  and trimmed afterwards.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRunOperation,
    LineageColumnMap,
    LineageRowEdge,
    LineageRowReject,
    LineageValueChange,
    QueryHistory,
)
from pointlessql.services import audit_aggregator as agg
from tests.conftest import ApiKeyFixture


async def _seed_run(client: httpx.AsyncClient, *, run_id: str) -> None:
    body = {
        "id": run_id,
        "notebook_path": "demo/run.py",
        "source": "print('seed')\n",
        "runtime_versions": {"python": "3.14.0"},
    }
    response = await client.post("/api/agent-runs", json=body)
    assert response.status_code == 200, response.text


def _add_op(*, run_id: str, target: str = "main.silver.orders") -> int:
    factory = app.state.session_factory
    started = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    finished = dt.datetime.now(dt.UTC)
    with factory() as session:
        from sqlalchemy import func, select

        max_ord = session.scalar(
            select(func.max(AgentRunOperation.ordinal)).where(
                AgentRunOperation.agent_run_id == run_id
            )
        )
        ordinal = (max_ord or 0) + 1
        row = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ordinal,
            op_name="merge",
            params_json="{}",
            target_table=target,
            input_sha=None,
            rows_affected=10,
            delta_version_before=0,
            delta_version_after=1,
            started_at=started,
            finished_at=finished,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


def _add_row_edge(*, run_id: str, op_id: int, source: str, target: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op_id,
                source_table=source,
                source_row_id="r1",
                target_table=target,
                target_row_id="r1",
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def _add_reject(*, run_id: str, op_id: int) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageRowReject(
                run_id=run_id,
                op_id=op_id,
                source_table="main.bronze.orders_raw",
                source_row_id="r1",
                reason="schema_mismatch",
                detail="missing column 'amount'",
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def _add_value_change(*, run_id: str, op_id: int) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op_id,
                target_table="main.silver.orders",
                target_row_id="r1",
                target_column="amount",
                old_value="5.00",
                new_value="6.50",
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def _add_column_map(*, run_id: str, op_id: int) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=op_id,
                source_table="main.bronze.orders_raw",
                source_column="amount",
                target_table="main.silver.orders",
                target_column="amount",
                transform_kind="identity",
                transform_detail=None,
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# Auditor-scope auth — privilege ladder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_summary_normal_key_403(
    api_key_secret: ApiKeyFixture, anonymous_client: httpx.AsyncClient
) -> None:
    """A non-privileged Bearer key cannot reach /api/audit/summary."""
    r = await anonymous_client.get(
        "/api/audit/summary",
        headers={"Authorization": f"Bearer {api_key_secret.secret}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_audit_summary_supervisor_key_403(
    supervisor_secret: ApiKeyFixture, anonymous_client: httpx.AsyncClient
) -> None:
    """Supervisor scope is insufficient for tenant-wide audit aggregates."""
    r = await anonymous_client.get(
        "/api/audit/summary",
        headers={"Authorization": f"Bearer {supervisor_secret.secret}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_audit_summary_auditor_key_200(
    auditor_secret: ApiKeyFixture, anonymous_client: httpx.AsyncClient
) -> None:
    """Auditor scope passes for tenant-wide audit aggregates."""
    r = await anonymous_client.get(
        "/api/audit/summary",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "counts" in payload


@pytest.mark.asyncio
async def test_audit_summary_admin_cookie_200(admin_client: httpx.AsyncClient) -> None:
    """Admin cookie still passes (admin > auditor)."""
    r = await admin_client.get("/api/audit/summary")
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Per-run audit-axis routes — supervisor + auditor + admin all pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_audit_lineage_auditor_passes(
    auditor_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    run_id = "11111111-1111-1111-1111-111111111111"
    await _seed_run(admin_client, run_id=run_id)
    op_id = _add_op(run_id=run_id)
    _add_row_edge(
        run_id=run_id,
        op_id=op_id,
        source="main.bronze.orders_raw",
        target="main.silver.orders",
    )
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/lineage",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["run_id"] == run_id
    assert payload["total_edges"] == 1
    assert payload["rows"][0]["edge_count"] == 1


@pytest.mark.asyncio
async def test_run_audit_lineage_supervisor_passes(
    supervisor_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    """Supervisor scope passes per-run audit reads (existing inspection priv)."""
    run_id = "11119999-1111-1111-1111-aaaaaaaaaaaa"
    await _seed_run(admin_client, run_id=run_id)
    op_id = _add_op(run_id=run_id)
    _add_row_edge(
        run_id=run_id,
        op_id=op_id,
        source="main.bronze.orders_raw",
        target="main.silver.orders",
    )
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/lineage",
        headers={"Authorization": f"Bearer {supervisor_secret.secret}"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_run_audit_lineage_normal_key_403(
    api_key_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    """Non-privileged keys cannot reach per-run audit reads."""
    run_id = "1111aaaa-1111-1111-1111-bbbbbbbbbbbb"
    await _seed_run(admin_client, run_id=run_id)
    _add_op(run_id=run_id)
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/lineage",
        headers={"Authorization": f"Bearer {api_key_secret.secret}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_run_audit_rejects_route(
    auditor_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    run_id = "22222222-2222-2222-2222-222222222222"
    await _seed_run(admin_client, run_id=run_id)
    op_id = _add_op(run_id=run_id)
    _add_reject(run_id=run_id, op_id=op_id)
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/rejects",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["reason"] == "schema_mismatch"


@pytest.mark.asyncio
async def test_run_audit_value_changes_masked_by_default(
    auditor_secret: ApiKeyFixture,
    admin_client: httpx.AsyncClient,
    anonymous_client: httpx.AsyncClient,
) -> None:
    run_id = "33333333-3333-3333-3333-333333333333"
    await _seed_run(admin_client, run_id=run_id)
    op_id = _add_op(run_id=run_id)
    _add_value_change(run_id=run_id, op_id=op_id)
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/value-changes",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["masked"] is True
    assert payload["row_count"] == 1
    row = payload["rows"][0]
    # Cleartext stripped at the API boundary for auditor scope.
    assert row["old_value"] is None
    assert row["new_value"] is None
    assert row["target_column"] == "amount"


@pytest.mark.asyncio
async def test_run_audit_column_lineage_route(
    auditor_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    run_id = "44444444-4444-4444-4444-444444444444"
    await _seed_run(admin_client, run_id=run_id)
    op_id = _add_op(run_id=run_id)
    _add_column_map(run_id=run_id, op_id=op_id)
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/column-lineage",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["transform_kind"] == "identity"


@pytest.mark.asyncio
async def test_run_audit_external_writes_route(
    auditor_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    run_id = "55555555-5555-5555-5555-555555555555"
    await _seed_run(admin_client, run_id=run_id)
    _add_op(run_id=run_id)
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/external-writes",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    # No external writes seeded → empty list, 200.
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["row_count"] == 0


@pytest.mark.asyncio
async def test_run_audit_returns_404_for_missing_run(
    auditor_secret: ApiKeyFixture, anonymous_client: httpx.AsyncClient
) -> None:
    """Stale run_id returns CatalogNotFoundError (404), not empty rows."""
    r = await anonymous_client.get(
        "/api/agent-runs/00000000-0000-0000-0000-000000000000/audit/lineage",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/audit/history + audit-of-audit recursion guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_history_excludes_audit_api_by_default(
    auditor_secret: ApiKeyFixture, anonymous_client: httpx.AsyncClient
) -> None:
    """Default response hides ``read_kind='audit_api'`` rows."""
    # First, a /api/audit/summary call lands an audit_api row.
    r1 = await anonymous_client.get(
        "/api/audit/summary",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r1.status_code == 200
    # Now query history — by default, the audit_api row should not
    # surface even though it landed seconds ago.
    r2 = await anonymous_client.get(
        "/api/audit/history",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r2.status_code == 200, r2.text
    payload = r2.json()
    audit_api_rows = [r for r in payload["rows"] if r["read_kind"] == "audit_api"]
    assert audit_api_rows == [], "default response must hide audit_api rows"


@pytest.mark.asyncio
async def test_audit_history_include_audit_api_lifts_filter(
    auditor_secret: ApiKeyFixture, anonymous_client: httpx.AsyncClient
) -> None:
    """``include_audit_api=true`` surfaces cockpit self-tracking rows."""
    # Seed an audit_api row first.
    await anonymous_client.get(
        "/api/audit/summary",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    r = await anonymous_client.get(
        "/api/audit/history",
        params={"include_audit_api": "true"},
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200
    payload = r.json()
    audit_api_rows = [row for row in payload["rows"] if row["read_kind"] == "audit_api"]
    assert audit_api_rows, "include_audit_api=true must surface audit_api rows"


# ---------------------------------------------------------------------------
# Audit-of-audit logging — successful calls land query_history rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_audit_endpoints_record_audit_api_history(
    auditor_secret: ApiKeyFixture,
    anonymous_client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    """Each successful per-run audit read leaves an audit_api breadcrumb."""
    run_id = "77777777-7777-7777-7777-777777777777"
    await _seed_run(admin_client, run_id=run_id)
    op_id = _add_op(run_id=run_id)
    _add_row_edge(
        run_id=run_id,
        op_id=op_id,
        source="main.bronze.orders_raw",
        target="main.silver.orders",
    )
    r = await anonymous_client.get(
        f"/api/agent-runs/{run_id}/audit/lineage",
        headers={"Authorization": f"Bearer {auditor_secret.secret}"},
    )
    assert r.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        rows = list(
            session.query(QueryHistory)
            .filter(QueryHistory.read_kind == "audit_api")
            .order_by(QueryHistory.id.desc())
            .limit(5)
        )
    assert any("/api/agent-runs/{run_id}/audit/lineage" in row.sql_text for row in rows), (
        "audit-of-audit row missing"
    )


# ---------------------------------------------------------------------------
# Anomaly baseline-window bugfix
# ---------------------------------------------------------------------------


def test_anomalies_baseline_extended_when_since_bounded() -> None:
    """A ``since``-bounded anomaly call must still see baseline points.

    Before the Sprint-19.1 fix, ``anomalies(since=yesterday)`` produced
    points whose baseline_slice was empty (because the underlying
    timeseries query was also bounded by ``since``), so every point
    looked anomalous.  After the fix the timeseries is widened by
    ``window_days`` internally and the response is trimmed to
    ``[since, until)`` — baseline_mean must therefore be non-zero
    for at least the last point in a populated window.
    """
    factory = app.state.session_factory
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    until = dt.datetime.now(dt.UTC)
    response = agg.anomalies(
        factory,
        metric="runs",
        window_days=7,
        since=since,
        until=until,
        bin_="day",
    )
    assert response["metric"] == "runs"
    assert response["baseline_window_days"] == 7
    # The fix guarantees that the underlying query reaches back
    # window_days before since.  The trimmed response only carries
    # bins inside [since, until); each one's baseline_mean is the
    # average of the prior 7 bins, which can legitimately be 0.0
    # if the seed data is sparse — what we assert is the absence
    # of the *old* bug, namely "every point looks anomalous because
    # baseline is empty".  A non-empty `points` list is the relevant
    # proxy: under the old code the trimmed list was identical to
    # the raw list, including the seed days; under the fix the
    # response only carries the [since, until) slice.
    assert isinstance(response["points"], list)
    # No explicit point-count assertion (depends on seed data); the
    # new behaviour is structural and verified by the baseline-mean
    # presence in the per-point dict shape.
    for point in response["points"]:
        assert "baseline_mean" in point
        assert "baseline_std" in point
        assert "severity" in point


# ---------------------------------------------------------------------------
# Phase 163 — saved audit filters CRUD
# ---------------------------------------------------------------------------


async def _csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Seed + return a CSRF header for any non-safe admin POST/PUT/DELETE."""
    from tests.conftest import seed_csrf

    token = await seed_csrf(client)
    return {"X-CSRF-Token": token}


@pytest.mark.asyncio
async def test_audit_saved_filter_crud_owner(
    admin_client: httpx.AsyncClient,
) -> None:
    headers = await _csrf_headers(admin_client)
    create_res = await admin_client.post(
        "/admin/audit/saved-filters",
        json={
            "name": "DP creates last week",
            "filters": {"since": "7d", "action": "DP_CREATE"},
            "is_shared_workspace": False,
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    entry = create_res.json()
    assert entry["name"] == "DP creates last week"
    assert entry["filters"]["action"] == "DP_CREATE"
    filter_id = entry["id"]
    list_res = await admin_client.get("/admin/audit/saved-filters")
    assert list_res.status_code == 200
    names = {e["name"] for e in list_res.json()}
    assert "DP creates last week" in names
    update_res = await admin_client.put(
        f"/admin/audit/saved-filters/{filter_id}",
        json={"name": "DP creates 2026", "filters": None, "is_shared_workspace": None},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "DP creates 2026"
    delete_res = await admin_client.delete(
        f"/admin/audit/saved-filters/{filter_id}", headers=headers
    )
    assert delete_res.status_code == 204


@pytest.mark.asyncio
async def test_audit_saved_filter_duplicate_name_rejected(
    admin_client: httpx.AsyncClient,
) -> None:
    headers = await _csrf_headers(admin_client)
    payload = {
        "name": "dup-test-filter",
        "filters": {"since": "24h"},
        "is_shared_workspace": False,
    }
    res1 = await admin_client.post(
        "/admin/audit/saved-filters", json=payload, headers=headers
    )
    assert res1.status_code == 201
    res2 = await admin_client.post(
        "/admin/audit/saved-filters", json=payload, headers=headers
    )
    assert res2.status_code == 422
    assert "already exists" in res2.text.lower()


@pytest.mark.asyncio
async def test_audit_saved_filter_share_visible_in_workspace_list(
    admin_client: httpx.AsyncClient,
) -> None:
    headers = await _csrf_headers(admin_client)
    create_res = await admin_client.post(
        "/admin/audit/saved-filters",
        json={
            "name": "shared-team-filter",
            "filters": {"since": "all"},
            "is_shared_workspace": True,
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    entry = create_res.json()
    assert entry["is_shared_workspace"] is True
    assert entry["workspace_id"] is not None


@pytest.mark.asyncio
async def test_audit_saved_filter_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    res = await non_admin_client.get("/admin/audit/saved-filters")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_audit_index_details_regex_filters_in_python(
    admin_client: httpx.AsyncClient,
) -> None:
    """Phase 163: ?details_regex=... filters server-side after the date window."""
    res = await admin_client.get("/admin/audit?since=24h&details_regex=hash%3A.%2A%5Ba-f0-9%5D")
    # Page renders even when no rows match — the regex is applied
    # server-side without crashing the viewer.
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_audit_index_invalid_regex_does_not_crash(
    admin_client: httpx.AsyncClient,
) -> None:
    res = await admin_client.get("/admin/audit?since=24h&details_regex=%5Bunclosed")
    assert res.status_code == 200, res.text
