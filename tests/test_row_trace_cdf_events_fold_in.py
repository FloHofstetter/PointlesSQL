"""Phase 40.7 fold-in: CDF events on row-trace walkback steps.

Mirrors the Phase 15.7 ``value_changes`` per-step attach pattern but
reads from ``cdf_tail_events``: every walkback step gets a
``cdf_events`` list of foreign-Delta CDF captures matching its
``(table, row_id)``.  Walkback semantics stay unchanged — CDF
captures are contextual metadata, never new walkback steps.
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    CdfTailEvent,
    CdfTailSubscription,
    LineageRowEdge,
)
from pointlessql.services import workspaces as workspaces_service
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub the per-principal UC client so SELECT-privilege checks pass."""
    mock = MagicMock(spec=UnityCatalogClient)
    mock.get_table = AsyncMock(return_value={})
    mock.get_effective_permissions = AsyncMock(return_value=[])
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: mock),
    )
    import pointlessql.db as _db

    monkeypatch.setattr(_db, "get_session_factory", lambda: app.state.session_factory)
    return mock


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_edge_and_events(
    *,
    table: str,
    row_id: str,
    versions: list[int],
    workspace_id: int = 1,
) -> int:
    """Seed one walkback edge + one CDF subscription + N events.

    Returns the subscription id so tests can clean up if needed.
    Edge is depth-0-only (no source predecessor) so the walkback
    surface a single step we can attach events to.
    """
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    edge_id = str(uuid.uuid4())[:16]
    with factory() as session:
        session.add(
            LineageRowEdge(
                workspace_id=workspace_id,
                run_id=None,
                op_id=None,
                source_table="bronze.raw.orders",
                source_row_id=f"src-{edge_id}",
                target_table=table,
                target_row_id=row_id,
                created_at=now,
            )
        )
        sub = CdfTailSubscription(
            workspace_id=workspace_id,
            table_full_name=table,
            row_id_column="id",
            producer_label=f"cdf-tail:{table}",
            is_active=True,
            created_at=now,
        )
        session.add(sub)
        session.flush()
        sub_id = sub.id
        for v in versions:
            session.add(
                CdfTailEvent(
                    workspace_id=workspace_id,
                    subscription_id=sub_id,
                    table_full_name=table,
                    delta_version=v,
                    row_id=row_id,
                    change_type="insert" if v == versions[0] else "update_postimage",
                    producer_label=f"cdf-tail:{table}",
                    commit_timestamp=now,
                    created_at=now,
                )
            )
        session.commit()
        return sub_id


@pytest.mark.asyncio
async def test_walk_back_attaches_cdf_events_to_step(uc_mock: MagicMock) -> None:
    """Walkback emits ``cdf_events`` per step ordered by ``delta_version``."""
    table = "demo.silver.tracked_fold_in"
    row_id = "row-fold-001"
    _seed_edge_and_events(table=table, row_id=row_id, versions=[3, 7, 11])

    async with _admin_client() as client:
        resp = await client.get(
            "/api/lineage/row-trace",
            params={"table": table, "row_id": row_id},
        )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    steps = payload["steps"]
    assert len(steps) >= 1
    head = steps[0]
    assert head["table"] == table
    assert head["row_id"] == row_id
    assert "cdf_events" in head
    versions = [ev["delta_version"] for ev in head["cdf_events"]]
    assert versions == [3, 7, 11]


@pytest.mark.asyncio
async def test_walk_back_steps_without_cdf_events_get_empty_list(
    uc_mock: MagicMock,
) -> None:
    """Step without matching CDF events still has the ``cdf_events`` key."""
    table = "demo.silver.no_cdf_yet"
    row_id = "row-no-cdf-001"
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageRowEdge(
                workspace_id=1,
                run_id=None,
                op_id=None,
                source_table="bronze.raw.orders",
                source_row_id="src-no-cdf",
                target_table=table,
                target_row_id=row_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    async with _admin_client() as client:
        resp = await client.get(
            "/api/lineage/row-trace",
            params={"table": table, "row_id": row_id},
        )
    assert resp.status_code == 200, resp.text
    head = resp.json()["steps"][0]
    assert head["cdf_events"] == []


@pytest.mark.asyncio
async def test_walk_back_workspace_isolation(uc_mock: MagicMock) -> None:
    """CDF events from a different workspace must not leak into the trace."""
    table = "demo.silver.cross_ws"
    row_id = "row-cross-ws-001"
    other = workspaces_service.create_workspace(
        app.state.session_factory, slug="ws-cdf-other", name="Other"
    )
    other_ws_id = other.id

    _seed_edge_and_events(
        table=table, row_id=row_id, versions=[42], workspace_id=other_ws_id
    )

    async with _admin_client() as client:
        resp = await client.get(
            "/api/lineage/row-trace",
            params={"table": table, "row_id": row_id},
        )
    assert resp.status_code == 200, resp.text
    steps = resp.json()["steps"]
    if steps:
        for step in steps:
            assert step["cdf_events"] == [], (
                f"Workspace-{other_ws_id} CDF events leaked into the default "
                f"workspace's trace: {step['cdf_events']}"
            )
