"""Tests for the inbound OpenLineage route.

Covers ``POST /api/lineage/openlineage`` end to end:

* Auth: requires the new ``lineage_inbound`` scope; supervisor /
  auditor / agent keys all return 403.
* Workspace scoping: edges land with the API key's workspace, never
  the body's namespace.
* Column-lineage facet: one ``inputField`` → one
  ``lineage_column_map`` row with ``producer`` / ``external_event_id``.
* Custom row-level facet (``pointlessql.lineage.row``): one
  ``inputField`` → one ``lineage_row_edges`` row.
* Idempotency: posting the same event twice produces zero new rows.
* Forward-compat: an event with an unknown facet still parses.
* Validation: missing ``eventTime`` / ``run.runId`` / ``job.namespace``
  yields 422-equivalent ``ValidationError``.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import delete

from pointlessql.api.main import app
from pointlessql.models import ApiKey, LineageColumnMap, LineageRowEdge
from pointlessql.services import api_keys as api_keys_service


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.execute(delete(LineageColumnMap).where(LineageColumnMap.producer.is_not(None)))
        session.execute(delete(LineageRowEdge).where(LineageRowEdge.producer.is_not(None)))
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.fixture
def federation_secret() -> Iterator[str]:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="fed", lineage_inbound=True
    )
    try:
        yield plaintext
    finally:
        _wipe()


@pytest.fixture
def auditor_secret() -> Iterator[str]:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="aud", auditor=True
    )
    try:
        yield plaintext
    finally:
        _wipe()


def _bearer_client(secret: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {secret}"},
    )


def _column_event(
    *,
    run_id: str = "ol-event-001",
    namespace: str = "kafka.events.us-east",
    target_table: str = "main.silver.events",
    target_column: str = "user_id",
    source_table: str = "user_signups",
    source_column: str = "uid",
    transform: str = "identity",
) -> dict[str, object]:
    return {
        "eventTime": "2026-05-06T18:30:00Z",
        "eventType": "COMPLETE",
        "run": {"runId": run_id},
        "job": {"namespace": namespace, "name": "events_to_silver"},
        "outputs": [
            {
                "namespace": "unity",
                "name": target_table,
                "facets": {
                    "columnLineage": {
                        "fields": {
                            target_column: {
                                "inputFields": [
                                    {
                                        "namespace": namespace,
                                        "name": source_table,
                                        "field": source_column,
                                        "transformations": [{"type": transform}],
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_inbound_column_facet_lands_one_column_map(federation_secret: str) -> None:
    async with _bearer_client(federation_secret) as client:
        response = await client.post("/api/lineage/openlineage", json=_column_event())
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["event_id"] == "ol-event-001"
    assert body["column_maps"] == 1
    assert body["row_edges"] == 0

    factory = app.state.session_factory
    with factory() as session:
        rows = list(
            session.query(LineageColumnMap)
            .filter(LineageColumnMap.producer == "kafka.events.us-east")
            .all()
        )
    assert len(rows) == 1
    edge = rows[0]
    assert edge.run_id is None
    assert edge.op_id is None
    assert edge.target_table == "main.silver.events"
    assert edge.target_column == "user_id"
    assert edge.source_column == "uid"
    assert edge.source_table == "kafka.events.us-east.user_signups"
    assert edge.transform_kind == "identity"
    assert edge.external_event_id == "ol-event-001"


@pytest.mark.asyncio
async def test_inbound_row_facet_lands_one_row_edge(federation_secret: str) -> None:
    event = _column_event()
    event["outputs"][0]["facets"]["pointlessql.lineage.row"] = {  # type: ignore[index]
        "inputFields": [
            {
                "namespace": "kafka.events.us-east",
                "name": "user_signups",
                "sourceRowId": "src-row-1",
                "targetRowId": "tgt-row-1",
            }
        ]
    }
    async with _bearer_client(federation_secret) as client:
        response = await client.post("/api/lineage/openlineage", json=event)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["row_edges"] == 1

    factory = app.state.session_factory
    with factory() as session:
        rows = list(
            session.query(LineageRowEdge)
            .filter(LineageRowEdge.producer == "kafka.events.us-east")
            .all()
        )
    assert len(rows) == 1
    edge = rows[0]
    assert edge.run_id is None
    assert edge.op_id is None
    assert edge.source_row_id == "src-row-1"
    assert edge.target_row_id == "tgt-row-1"


@pytest.mark.asyncio
async def test_inbound_403_without_lineage_inbound_scope(auditor_secret: str) -> None:
    async with _bearer_client(auditor_secret) as client:
        response = await client.post("/api/lineage/openlineage", json=_column_event())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_inbound_invalid_body_returns_validation_error(federation_secret: str) -> None:
    async with _bearer_client(federation_secret) as client:
        response = await client.post("/api/lineage/openlineage", json={"not": "an event"})
    assert response.status_code == 422  # ValidationError -> 422 via global handler


@pytest.mark.asyncio
async def test_inbound_idempotent_replay(federation_secret: str) -> None:
    event = _column_event(run_id="dup-1")
    async with _bearer_client(federation_secret) as client:
        first = await client.post("/api/lineage/openlineage", json=event)
        second = await client.post("/api/lineage/openlineage", json=event)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["column_maps"] == 1
    assert second.json()["column_maps"] == 0
    assert second.json()["duplicate_column_maps"] == 1

    factory = app.state.session_factory
    with factory() as session:
        rows = list(
            session.query(LineageColumnMap)
            .filter(LineageColumnMap.external_event_id == "dup-1")
            .all()
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_inbound_workspace_scoped_to_api_key(federation_secret: str) -> None:
    """The workspace_id always comes from the API key, never the event body."""
    event = _column_event(run_id="ws-test")
    async with _bearer_client(federation_secret) as client:
        response = await client.post("/api/lineage/openlineage", json=event)
    assert response.status_code == 202
    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(LineageColumnMap)
            .filter(LineageColumnMap.external_event_id == "ws-test")
            .one()
        )
    # ``fed`` was created with the default workspace (id=1).
    assert row.workspace_id == 1


@pytest.mark.asyncio
async def test_inbound_forward_compat_unknown_facet(federation_secret: str) -> None:
    event = _column_event(run_id="unknown-facet")
    event["outputs"][0]["facets"]["someBrandNewOLFacet"] = {  # type: ignore[index]
        "shape": "unknown to us",
        "fields": {"will_be": "ignored"},
    }
    async with _bearer_client(federation_secret) as client:
        response = await client.post("/api/lineage/openlineage", json=event)
    assert response.status_code == 202, response.text
    assert response.json()["column_maps"] == 1


@pytest.mark.asyncio
async def test_inbound_unknown_transform_kind_falls_back_unknown_origin(
    federation_secret: str,
) -> None:
    event = _column_event(run_id="bad-transform", transform="not-a-real-kind")
    async with _bearer_client(federation_secret) as client:
        response = await client.post("/api/lineage/openlineage", json=event)
    assert response.status_code == 202
    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(LineageColumnMap)
            .filter(LineageColumnMap.external_event_id == "bad-transform")
            .one()
        )
    assert row.transform_kind == "unknown_origin"
