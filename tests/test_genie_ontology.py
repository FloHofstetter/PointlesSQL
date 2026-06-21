"""Tests for the Genie Ontology authority ranking + table suggestions.

The PageRank service tests run in a freshly-created workspace so the
session-scoped test DB (no per-test rollback) cannot leak lineage edges
between cases; the route tests hit the default workspace with
uniquely-named tables and assert presence rather than absolute order.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import LineageRowEdge, User, Workspace
from pointlessql.services import genie as genie_service


def _factory():
    return fastapi_app.state.session_factory


def _admin_id() -> int:
    with _factory()() as session:
        return int(session.scalar(select(User.id).where(User.email == "test@test.com")) or 0)


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(
            slug=f"ontology-{uuid.uuid4().hex[:10]}",
            name="Ontology test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed_edges(workspace_id: int, edges: list[tuple[str, str]]) -> None:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for index, (source, target) in enumerate(edges):
            session.add(
                LineageRowEdge(
                    workspace_id=workspace_id,
                    source_table=source,
                    source_row_id=f"s{index}",
                    target_table=target,
                    target_row_id=f"t{index}",
                    created_at=now,
                )
            )
        session.commit()


def test_authority_ranks_hub_table_first() -> None:
    ws = _fresh_workspace()
    # a, b, c, d all feed the hub; a also feeds b.
    _seed_edges(
        ws,
        [
            ("cat.sch.a", "cat.sch.hub"),
            ("cat.sch.b", "cat.sch.hub"),
            ("cat.sch.c", "cat.sch.hub"),
            ("cat.sch.d", "cat.sch.hub"),
            ("cat.sch.a", "cat.sch.b"),
        ],
    )
    ranked = genie_service.compute_table_authority(_factory(), workspace_id=ws)

    assert ranked[0]["table"] == "cat.sch.hub"
    top = ranked[0]
    assert top["in_degree"] == 4
    assert top["out_degree"] == 0
    # Every node from the edge set is ranked, and ranks are positive.
    assert {item["table"] for item in ranked} == {
        "cat.sch.a",
        "cat.sch.b",
        "cat.sch.c",
        "cat.sch.d",
        "cat.sch.hub",
    }
    assert all(item["score"] > 0 for item in ranked)


def test_authority_drops_self_loops_and_empty_is_empty() -> None:
    empty_ws = _fresh_workspace()
    assert genie_service.compute_table_authority(_factory(), workspace_id=empty_ws) == []

    loop_ws = _fresh_workspace()
    _seed_edges(loop_ws, [("cat.sch.x", "cat.sch.x")])
    assert genie_service.compute_table_authority(_factory(), workspace_id=loop_ws) == []


def test_suggest_excludes_curated_tables() -> None:
    ws = _fresh_workspace()
    _seed_edges(
        ws,
        [
            ("cat.sch.a", "cat.sch.hub"),
            ("cat.sch.b", "cat.sch.hub"),
            ("cat.sch.a", "cat.sch.b"),
        ],
    )
    suggestions = genie_service.suggest_tables_for_space(
        _factory(), workspace_id=ws, curated=["cat.sch.hub"]
    )
    tables = {item["table"] for item in suggestions}
    assert "cat.sch.hub" not in tables  # already curated
    assert "cat.sch.a" in tables


@pytest.mark.asyncio
async def test_route_authority(admin_client: httpx.AsyncClient) -> None:
    token = uuid.uuid4().hex[:8]
    hub = f"cat.sch.hub_{token}"
    leaf = f"cat.sch.leaf_{token}"
    _seed_edges(1, [(leaf, hub)])

    response = await admin_client.get("/api/genie/ontology/authority")
    assert response.status_code == 200, response.text
    tables = {row["table"] for row in response.json()["tables"]}
    assert hub in tables
    assert leaf in tables


@pytest.mark.asyncio
async def test_route_suggested_tables_excludes_curated(admin_client: httpx.AsyncClient) -> None:
    token = uuid.uuid4().hex[:8]
    hub = f"cat.sch.hub_{token}"
    leaf = f"cat.sch.leaf_{token}"
    _seed_edges(1, [(leaf, hub)])
    space = genie_service.create_space(
        _factory(), workspace_id=1, title=f"ont-{token}", description=None, owner_id=_admin_id()
    )
    genie_service.update_space(_factory(), space_id=space.id, tables=[hub])

    response = await admin_client.get(f"/api/genie/spaces/{space.slug}/suggested-tables")
    assert response.status_code == 200, response.text
    suggested = {row["table"] for row in response.json()["suggestions"]}
    assert hub not in suggested  # curated
    assert leaf in suggested
