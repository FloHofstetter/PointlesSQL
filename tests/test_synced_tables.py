"""Tests for synced tables — reverse-ETL Delta → SQL plus the lookup API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import deltalake
import httpx
import pandas as pd
import pytest
import sqlalchemy as sa

# Register the table on Base.metadata before conftest's session-scoped
# create_all builds the schema.
import pointlessql.models.synced_tables  # noqa: F401
from pointlessql.api import online_tables_routes
from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.services import synced_tables as service

# The router is not registered in the app bootstrap yet (the
# integrating session owns that wiring); mount it here so the route
# tests exercise the real middleware stack.  Guarded so the include
# becomes a no-op once the bootstrap registers it.
if not any(getattr(route, "path", "") == "/api/online-tables" for route in app.routes):
    app.include_router(online_tables_routes.router)


def _client(cookies: dict[str, str] | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


@pytest.fixture
def factory():
    return app.state.session_factory


def _create(factory, **overrides: Any):
    params: dict[str, Any] = {
        "workspace_id": 1,
        "name": "users",
        "source_fqn": "shop.gold.users",
        "target_url": "sqlite:///:memory:",
        "target_table": "users_online",
        "primary_keys": "id",
        "mode": "full",
        "principal": "test@test.com",
    }
    params.update(overrides)
    return service.create_synced_table(factory, **params)


def _write_source(path: Path, frame: pd.DataFrame, **kwargs: Any) -> None:
    deltalake.write_deltalake(str(path), frame, **kwargs)


def _read_target(url: str, table: str) -> list[tuple[Any, ...]]:
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sa.text(f'SELECT * FROM "{table}" ORDER BY id')).all()
        return [tuple(row) for row in rows]
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# CRUD + validation
# ---------------------------------------------------------------------------


def test_create_list_get_delete_roundtrip(factory) -> None:
    row = _create(factory)
    assert row.status == "idle"
    assert row.mode == "full"
    assert row.created_by == "test@test.com"
    assert row.last_synced_version is None

    rows = service.list_synced_tables(factory, workspace_id=1)
    assert [r.name for r in rows] == ["users"]
    fetched = service.get_synced_table(factory, workspace_id=1, name="users")
    assert fetched is not None and fetched.id == row.id

    assert service.delete_synced_table(factory, synced_table_id=row.id) is True
    assert service.get_synced_table(factory, workspace_id=1, name="users") is None
    assert service.delete_synced_table(factory, synced_table_id=row.id) is False


def test_create_validation_rejections(factory) -> None:
    with pytest.raises(ValueError, match="name"):
        _create(factory, name="has space")
    with pytest.raises(ValueError, match="three parts"):
        _create(factory, source_fqn="gold.users")
    with pytest.raises(ValueError, match="mode"):
        _create(factory, mode="incremental")
    with pytest.raises(ValueError, match="primary_keys"):
        _create(factory, mode="cdf", primary_keys=None)
    with pytest.raises(ValueError, match="target_table"):
        _create(factory, target_table="users; DROP TABLE x")
    with pytest.raises(ValueError, match="primary key column"):
        _create(factory, primary_keys="id, 1bad")
    _create(factory)
    with pytest.raises(ValueError, match="already exists"):
        _create(factory)


def test_target_url_stored_verbatim_with_placeholder(factory) -> None:
    url = "postgresql://app:{{secrets/warehouse/pg-password}}@db/serving"
    row = _create(factory, target_url=url)
    assert row.target_url == url


def test_set_status_rejects_unknown_state(factory) -> None:
    row = _create(factory)
    with pytest.raises(ValueError, match="status"):
        service.set_status(factory, synced_table_id=row.id, status="exploded")


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------


def test_full_sync_end_to_end(factory, tmp_path: Path) -> None:
    source = tmp_path / "delta"
    _write_source(source, pd.DataFrame({"id": [1, 2], "name": ["a", "b"]}))
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    row = _create(factory, target_url=target_url)

    result = service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))

    assert result == {"name": "users", "mode": "full", "rows_affected": 2, "version": 0}
    assert _read_target(target_url, "users_online") == [(1, "a"), (2, "b")]
    refreshed = service.get_synced_table(factory, workspace_id=1, name="users")
    assert refreshed is not None
    assert refreshed.status == "ok"
    assert refreshed.last_synced_version == 0
    assert refreshed.rows_synced == 2
    assert refreshed.last_synced_at is not None
    assert refreshed.last_error is None


def test_full_sync_replaces_target(factory, tmp_path: Path) -> None:
    source = tmp_path / "delta"
    _write_source(source, pd.DataFrame({"id": [1], "name": ["a"]}))
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    row = _create(factory, target_url=target_url)
    service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))
    _write_source(source, pd.DataFrame({"id": [7], "name": ["z"]}), mode="overwrite")

    service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))

    assert _read_target(target_url, "users_online") == [(7, "z")]


def test_sync_failure_records_error_and_reraises(factory, tmp_path: Path) -> None:
    row = _create(factory, target_url=f"sqlite:///{tmp_path / 'target.db'}")
    with pytest.raises(Exception, match=".+"):
        service.sync_once(
            factory, synced_table_id=row.id, storage_location=str(tmp_path / "missing")
        )
    refreshed = service.get_synced_table(factory, workspace_id=1, name="users")
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.last_error


# ---------------------------------------------------------------------------
# CDF sync
# ---------------------------------------------------------------------------


def test_cdf_sync_initial_load_then_incremental(factory, tmp_path: Path) -> None:
    source = tmp_path / "delta"
    _write_source(
        source,
        pd.DataFrame({"id": [1, 2], "name": ["a", "b"]}),
        configuration={"delta.enableChangeDataFeed": "true"},
    )
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    row = _create(factory, target_url=target_url, mode="cdf", primary_keys="id")

    first = service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))
    assert first["rows_affected"] == 2
    assert first["version"] == 0

    # Plain insert plus a MERGE-style change (re-append of an existing
    # key); the apply path deletes by PK before inserting, so the
    # second write acts as an upsert on the target.
    _write_source(source, pd.DataFrame({"id": [3], "name": ["c"]}), mode="append")
    _write_source(source, pd.DataFrame({"id": [2], "name": ["b2"]}), mode="append")

    second = service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))
    assert second["rows_affected"] == 2
    assert second["version"] == 2
    assert _read_target(target_url, "users_online") == [(1, "a"), (2, "b2"), (3, "c")]
    refreshed = service.get_synced_table(factory, workspace_id=1, name="users")
    assert refreshed is not None
    assert refreshed.last_synced_version == 2
    assert refreshed.rows_synced == 4
    assert refreshed.status == "ok"


def test_cdf_sync_applies_deletes_and_noops_when_idle(factory, tmp_path: Path) -> None:
    source = tmp_path / "delta"
    _write_source(
        source,
        pd.DataFrame({"id": [1, 2], "name": ["a", "b"]}),
        configuration={"delta.enableChangeDataFeed": "true"},
    )
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    row = _create(factory, target_url=target_url, mode="cdf", primary_keys="id")
    service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))

    idle = service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))
    assert idle["rows_affected"] == 0
    assert idle["version"] == 0

    deltalake.DeltaTable(str(source)).delete("id = 1")
    after_delete = service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))
    assert after_delete["version"] == 1
    assert _read_target(target_url, "users_online") == [(2, "b")]


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


@pytest.fixture
def synced_target(factory, tmp_path: Path):
    source = tmp_path / "delta"
    _write_source(source, pd.DataFrame({"id": [1, 2], "name": ["a", "b"]}))
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    row = _create(factory, target_url=target_url)
    service.sync_once(factory, synced_table_id=row.id, storage_location=str(source))
    return row, target_url, source


def test_lookup_happy_path(factory, synced_target) -> None:
    row, _, _ = synced_target
    rows = service.lookup(factory, synced_table_id=row.id, key_column="id", key_value="1")
    assert rows == [{"id": 1, "name": "a"}]


def test_lookup_rejects_non_primary_key_column(factory, synced_target) -> None:
    row, _, _ = synced_target
    with pytest.raises(ValueError, match="primary keys"):
        service.lookup(factory, synced_table_id=row.id, key_column="name", key_value="a")


def test_lookup_handles_injection_shaped_value(factory, synced_target) -> None:
    row, target_url, _ = synced_target
    rows = service.lookup(
        factory,
        synced_table_id=row.id,
        key_column="id",
        key_value="1 OR 1=1; DROP TABLE users_online; --",
    )
    assert rows == []
    # The value was bound, not interpolated — the target survived.
    assert _read_target(target_url, "users_online") == [(1, "a"), (2, "b")]


def test_lookup_rejects_injection_shaped_column(factory, synced_target) -> None:
    row, _, _ = synced_target
    with pytest.raises(ValueError, match="key_column"):
        service.lookup(
            factory,
            synced_table_id=row.id,
            key_column='id" OR "1"="1',
            key_value="1",
        )


# ---------------------------------------------------------------------------
# Scheduler executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_executor_requires_synced_table_id() -> None:
    with pytest.raises(ValidationError, match="synced_table_id"):
        await service.sync_executor(1, {"email": "test@test.com"}, {}, object())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_create_list_sync_lookup(uc_client_stub, tmp_path: Path) -> None:
    source = tmp_path / "delta"
    _write_source(source, pd.DataFrame({"id": [1, 2], "name": ["a", "b"]}))
    uc_client_stub.get_table.return_value = {"storage_location": str(source)}
    target_url = f"sqlite:///{tmp_path / 'target.db'}"

    async with _client(app.state._test_auth_cookie) as client:
        created = await client.post(
            "/api/online-tables",
            json={
                "name": "users",
                "source_fqn": "shop.gold.users",
                "target_url": target_url,
                "target_table": "users_online",
                "primary_keys": "id",
                "mode": "full",
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["status"] == "idle"

        listing = await client.get("/api/online-tables")
        assert listing.status_code == 200
        names = [t["name"] for t in listing.json()["online_tables"]]
        assert names == ["users"]

        synced = await client.post("/api/online-tables/users/sync")
        assert synced.status_code == 200, synced.text
        body = synced.json()
        assert body["rows_affected"] == 2
        assert body["table"]["status"] == "ok"
        uc_client_stub.get_table.assert_awaited_with("shop", "gold", "users")

        found = await client.get("/api/online-tables/users/lookup?key_column=id&key=2")
        assert found.status_code == 200
        assert found.json() == {"rows": [{"id": 2, "name": "b"}], "row_count": 1}

        rejected = await client.get("/api/online-tables/users/lookup?key_column=name&key=b")
        assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_route_create_requires_authentication() -> None:
    async with _client() as client:
        resp = await client.post(
            "/api/online-tables",
            json={
                "name": "anon",
                "source_fqn": "a.b.c",
                "target_url": "sqlite:///:memory:",
                "target_table": "t",
            },
        )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_route_create_rejects_bad_payload() -> None:
    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            "/api/online-tables",
            json={
                "name": "bad",
                "source_fqn": "not-three-part",
                "target_url": "sqlite:///:memory:",
                "target_table": "t",
            },
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_route_delete_requires_admin_or_creator(factory) -> None:
    _create(factory, principal="someone-else@test.com")
    async with _client(app.state._test_non_admin_cookie) as client:
        denied = await client.delete("/api/online-tables/users")
        assert denied.status_code == 403
    async with _client(app.state._test_auth_cookie) as client:
        deleted = await client.delete("/api/online-tables/users")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}
    async with _client(app.state._test_auth_cookie) as client:
        missing = await client.delete("/api/online-tables/users")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_route_delete_allows_creator(factory) -> None:
    _create(factory, principal="nonadmin@test.com")
    async with _client(app.state._test_non_admin_cookie) as client:
        deleted = await client.delete("/api/online-tables/users")
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_browser_page_renders() -> None:
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get("/online-tables")
    assert page.status_code == 200
    assert 'x-data="onlineTables()"' in page.text
    assert "online_tables.js" in page.text
