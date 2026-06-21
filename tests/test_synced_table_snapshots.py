"""Tests for synced-table snapshots / branches."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.exceptions import ValidationError
from pointlessql.models import SyncedTable, Workspace
from pointlessql.services import synced_table_snapshots as snapshots


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(slug=f"snap-{uuid.uuid4().hex[:10]}", name="Snapshot test", created_at=now)
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed_synced_table(ws: int, *, name: str, version: int = 5, rows: int = 100) -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        table = SyncedTable(
            workspace_id=ws,
            name=name,
            source_fqn="main.s.t",
            target_url="sqlite://",
            target_table="t",
            mode="full",
            status="ok",
            last_synced_version=version,
            rows_synced=rows,
            created_at=now,
            updated_at=now,
        )
        session.add(table)
        session.commit()
        session.refresh(table)
        return int(table.id)


def test_create_captures_state_and_lists() -> None:
    ws = _fresh_workspace()
    tid = _seed_synced_table(ws, name="t1", version=7, rows=42)
    snap = snapshots.create_snapshot(
        _factory(), synced_table_id=tid, name="exp", note="trying", created_by="a@x"
    )
    assert snap["source_version"] == 7
    assert snap["rows_snapshot"] == 42
    assert snap["status"] == "active"
    listed = snapshots.list_snapshots(_factory(), synced_table_id=tid)
    assert [s["name"] for s in listed] == ["exp"]


def test_create_validations() -> None:
    ws = _fresh_workspace()
    tid = _seed_synced_table(ws, name="t2")
    with pytest.raises(ValidationError, match="required"):
        snapshots.create_snapshot(_factory(), synced_table_id=tid, name="")
    snapshots.create_snapshot(_factory(), synced_table_id=tid, name="dup")
    with pytest.raises(ValidationError, match="already exists"):
        snapshots.create_snapshot(_factory(), synced_table_id=tid, name="dup")
    with pytest.raises(ValidationError, match="not found"):
        snapshots.create_snapshot(_factory(), synced_table_id=987654, name="x")


def test_promote_demotes_sibling() -> None:
    ws = _fresh_workspace()
    tid = _seed_synced_table(ws, name="t3")
    a = snapshots.create_snapshot(_factory(), synced_table_id=tid, name="a")
    b = snapshots.create_snapshot(_factory(), synced_table_id=tid, name="b")
    snapshots.promote_snapshot(_factory(), snapshot_id=a["id"], synced_table_id=tid)
    snapshots.promote_snapshot(_factory(), snapshot_id=b["id"], synced_table_id=tid)
    by_name = {s["name"]: s for s in snapshots.list_snapshots(_factory(), synced_table_id=tid)}
    assert by_name["b"]["status"] == "promoted"
    # Only one promoted baseline — the earlier promote was demoted.
    assert by_name["a"]["status"] == "active"


def test_discard_and_delete() -> None:
    ws = _fresh_workspace()
    tid = _seed_synced_table(ws, name="t4")
    a = snapshots.create_snapshot(_factory(), synced_table_id=tid, name="a")
    discarded = snapshots.discard_snapshot(_factory(), snapshot_id=a["id"], synced_table_id=tid)
    assert discarded["status"] == "discarded"
    assert snapshots.delete_snapshot(_factory(), snapshot_id=a["id"], synced_table_id=tid) is True
    assert snapshots.delete_snapshot(_factory(), snapshot_id=a["id"], synced_table_id=tid) is False


def test_mutations_reject_foreign_table_snapshot() -> None:
    # A snapshot may only be promoted / discarded / deleted through its
    # owning table — passing another table's id must look like a miss so
    # one tenant can never touch another tenant's snapshot by id.
    ws = _fresh_workspace()
    owner = _seed_synced_table(ws, name="owner")
    other = _seed_synced_table(ws, name="other")
    snap = snapshots.create_snapshot(_factory(), synced_table_id=owner, name="s")
    with pytest.raises(ValidationError, match="not found"):
        snapshots.promote_snapshot(_factory(), snapshot_id=snap["id"], synced_table_id=other)
    with pytest.raises(ValidationError, match="not found"):
        snapshots.discard_snapshot(_factory(), snapshot_id=snap["id"], synced_table_id=other)
    assert (
        snapshots.delete_snapshot(_factory(), snapshot_id=snap["id"], synced_table_id=other)
        is False
    )
    # The snapshot is untouched and still deletable through its own table.
    assert (
        snapshots.delete_snapshot(_factory(), snapshot_id=snap["id"], synced_table_id=owner) is True
    )


@pytest.mark.asyncio
async def test_route_snapshot_lifecycle(admin_client: httpx.AsyncClient) -> None:
    name = f"ot-{uuid.uuid4().hex[:8]}"
    _seed_synced_table(1, name=name, version=3, rows=10)

    created = await admin_client.post(
        f"/api/online-tables/{name}/snapshots", json={"name": "s1", "note": "exp"}
    )
    assert created.status_code == 200, created.text
    snap: dict[str, Any] = created.json()["snapshot"]
    assert snap["source_version"] == 3
    sid = snap["id"]

    listed = await admin_client.get(f"/api/online-tables/{name}/snapshots")
    assert any(s["id"] == sid for s in listed.json()["snapshots"])

    promoted = await admin_client.post(f"/api/online-tables/{name}/snapshots/{sid}/promote")
    assert promoted.json()["snapshot"]["status"] == "promoted"

    discarded = await admin_client.post(f"/api/online-tables/{name}/snapshots/{sid}/discard")
    assert discarded.json()["snapshot"]["status"] == "discarded"

    deleted = await admin_client.delete(f"/api/online-tables/{name}/snapshots/{sid}")
    assert deleted.json()["deleted"] is True
