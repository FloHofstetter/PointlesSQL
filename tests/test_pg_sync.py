"""Unit tests for the Sprint 18 Postgres sync worker.

Covers the pure logic (type mapping, diff) and the apply + run_sync
flow via mocks. A real-Postgres integration test is documented below
but skipped by default — CI does not spin up a Postgres sidecar.

To run the integration test locally:

    docker run --rm -d --name pg-sync-test \\
        -e POSTGRES_PASSWORD=sync -e POSTGRES_DB=sync_src \\
        -p 5433:5432 postgres:16
    POINTLESSQL_PG_SYNC_DSN="host=localhost port=5433 dbname=sync_src \\
        user=postgres password=sync" \\
        uv run pytest -m integration tests/test_pg_sync.py
    docker rm -f pg-sync-test
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, SyncRun
from pointlessql.services import pg_sync
from pointlessql.services.pg_sync import (
    PG_TO_UC_TYPE,
    PgColumn,
    PgTable,
    PostgresSnapshot,
    PsycopgIntrospector,
    SyncDiff,
    UcColumn,
    UcTable,
    apply_diff,
    build_dsn,
    collect_uc_tables,
    diff_snapshots,
    effective_options,
    list_recent_runs,
    map_pg_type_to_uc,
    run_sync,
)
from pointlessql.services.unitycatalog import UnityCatalogClient

# -- Type mapping tests --


@pytest.mark.parametrize(
    ("pg_type", "expected_uc"),
    [
        ("smallint", "SHORT"),
        ("integer", "INT"),
        ("bigint", "LONG"),
        ("real", "FLOAT"),
        ("double precision", "DOUBLE"),
        ("numeric", "DECIMAL"),
        ("text", "STRING"),
        ("character varying", "STRING"),
        ("varchar", "STRING"),
        ("char", "STRING"),
        ("boolean", "BOOLEAN"),
        ("date", "DATE"),
        ("timestamp without time zone", "TIMESTAMP_NTZ"),
        ("timestamp with time zone", "TIMESTAMP"),
        ("bytea", "BINARY"),
    ],
)
def test_map_pg_type_to_uc_known(pg_type: str, expected_uc: str) -> None:
    col = PgColumn(name="c", data_type=pg_type, nullable=True)
    name, _text = map_pg_type_to_uc(col)
    assert name == expected_uc


def test_map_pg_type_to_uc_unknown_falls_back_to_string(
    caplog: pytest.LogCaptureFixture,
) -> None:
    col = PgColumn(name="c", data_type="geometry", nullable=True)
    with caplog.at_level("WARNING", logger="pointlessql.services.pg_sync"):
        name, text = map_pg_type_to_uc(col)
    assert name == "STRING"
    assert text == "string"
    assert any("unknown Postgres type" in r.message for r in caplog.records)


def test_map_pg_type_to_uc_decimal_carries_precision() -> None:
    col = PgColumn(
        name="amount",
        data_type="numeric",
        nullable=True,
        numeric_precision=10,
        numeric_scale=2,
    )
    name, text = map_pg_type_to_uc(col)
    assert name == "DECIMAL"
    assert text == "decimal(10,2)"


def test_pg_to_uc_type_table_exposed_for_parametrization() -> None:
    # Sanity check: the public dict is the parametrisation source,
    # so edits to it don't silently disable tests.
    assert "integer" in PG_TO_UC_TYPE
    assert PG_TO_UC_TYPE["integer"] == "INT"


# -- Diff tests --


def _pg_table(schema: str, name: str, *cols: tuple[str, str]) -> PgTable:
    return PgTable(
        schema=schema,
        name=name,
        columns=tuple(PgColumn(name=c[0], data_type=c[1], nullable=True) for c in cols),
    )


def _uc_table(schema: str, name: str, *cols: tuple[str, str]) -> UcTable:
    return UcTable(
        schema=schema,
        name=name,
        columns=tuple(UcColumn(name=c[0], type_name=c[1]) for c in cols),
    )


class TestDiffSnapshots:
    def test_empty_matches_produce_empty_diff(self) -> None:
        pg = PostgresSnapshot(tables=(_pg_table("public", "users", ("id", "integer")),))
        uc = [_uc_table("public", "users", ("id", "INT"))]
        d = diff_snapshots(pg, uc)
        assert d.is_empty()

    def test_new_schema_detected(self) -> None:
        pg = PostgresSnapshot(tables=(_pg_table("sales", "orders", ("id", "integer")),))
        d = diff_snapshots(pg, [])
        assert d.add_schemas == ("sales",)
        assert len(d.add_tables) == 1
        assert d.add_tables[0].schema == "sales"

    def test_new_table_detected(self) -> None:
        pg = PostgresSnapshot(
            tables=(
                _pg_table("public", "users", ("id", "integer")),
                _pg_table("public", "orders", ("id", "integer")),
            )
        )
        uc = [_uc_table("public", "users", ("id", "INT"))]
        d = diff_snapshots(pg, uc)
        assert d.add_schemas == ()  # schema already exists
        assert len(d.add_tables) == 1
        assert d.add_tables[0].name == "orders"

    def test_column_change_detected(self) -> None:
        pg = PostgresSnapshot(
            tables=(_pg_table("public", "users", ("id", "integer"), ("email", "text")),)
        )
        uc = [_uc_table("public", "users", ("id", "INT"))]  # missing email
        d = diff_snapshots(pg, uc)
        assert len(d.change_tables) == 1
        assert d.change_tables[0].name == "users"

    def test_column_type_change_detected(self) -> None:
        pg = PostgresSnapshot(tables=(_pg_table("public", "users", ("id", "bigint")),))
        uc = [_uc_table("public", "users", ("id", "INT"))]  # was integer
        d = diff_snapshots(pg, uc)
        assert len(d.change_tables) == 1

    def test_dropped_table_detected(self) -> None:
        pg = PostgresSnapshot(tables=())
        uc = [_uc_table("public", "users", ("id", "INT"))]
        d = diff_snapshots(pg, uc)
        assert d.drop_tables == (("public", "users"),)

    def test_mixed_diff(self) -> None:
        pg = PostgresSnapshot(
            tables=(
                _pg_table("public", "users", ("id", "integer")),  # unchanged
                _pg_table("public", "new_tbl", ("id", "integer")),  # added
                _pg_table("sales", "orders", ("id", "integer")),  # new schema + table
            )
        )
        uc = [
            _uc_table("public", "users", ("id", "INT")),
            _uc_table("public", "old_tbl", ("id", "INT")),  # to drop
        ]
        d = diff_snapshots(pg, uc)
        assert d.add_schemas == ("sales",)
        added_names = {t.name for t in d.add_tables}
        assert added_names == {"new_tbl", "orders"}
        assert d.drop_tables == (("public", "old_tbl"),)


# -- Secret handling --


class TestEffectiveOptions:
    def test_no_credential_returns_options_unchanged(self) -> None:
        conn = {"options": {"host": "db.example.com", "database": "analytics"}}
        assert effective_options(conn, None) == {
            "host": "db.example.com",
            "database": "analytics",
        }

    def test_credential_overrides_secret_keys(self) -> None:
        conn = {
            "options": {
                "host": "db.example.com",
                "password": "LEAK",
                "database": "analytics",
            }
        }
        cred = {"additional_properties": {"password": "from-credential"}}
        merged = effective_options(conn, cred)
        assert merged["password"] == "from-credential"
        # Non-secret keys stay on the connection options.
        assert merged["host"] == "db.example.com"

    def test_credential_adds_missing_secret_keys(self) -> None:
        conn = {"options": {"host": "db.example.com"}}
        cred = {
            "additional_properties": {
                "password": "pw",
                "api_token": "tk",
                "private_key": "pk",
            }
        }
        merged = effective_options(conn, cred)
        assert merged["password"] == "pw"
        assert merged["api_token"] == "tk"
        assert merged["private_key"] == "pk"

    def test_credential_non_secret_extras_ignored(self) -> None:
        # A Credential may legitimately carry non-secret extras
        # (e.g. a purpose or owner tag). Those must not be silently
        # merged — only the secret-looking ones are pulled in.
        conn = {"options": {"host": "db.example.com"}}
        cred = {
            "additional_properties": {
                "password": "pw",
                "region": "us-east-1",  # not a secret
            }
        }
        merged = effective_options(conn, cred)
        assert "region" not in merged


# -- DSN builder --


def test_build_dsn_requires_host() -> None:
    with pytest.raises(ValidationError):
        build_dsn({"database": "analytics"})


def test_build_dsn_assembles_keyvalue_pairs() -> None:
    dsn = build_dsn(
        {
            "host": "db.example.com",
            "port": 5432,
            "database": "analytics",
            "user": "svc",
            "password": "pw",
        }
    )
    assert "host=db.example.com" in dsn
    assert "port=5432" in dsn
    assert "dbname=analytics" in dsn
    assert "user=svc" in dsn
    assert "password=pw" in dsn


def test_build_dsn_accepts_dbname_alias() -> None:
    dsn = build_dsn({"host": "h", "dbname": "mydb"})
    assert "dbname=mydb" in dsn


# -- Apply diff (with mock UC) --


class TestApplyDiff:
    async def test_empty_diff_no_calls(self) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.create_schema = AsyncMock()
        uc.create_table = AsyncMock()
        uc.delete_table = AsyncMock()
        diff = SyncDiff()
        counts = await apply_diff(uc, "pg_cat", diff)
        assert counts == (0, 0, 0)
        uc.create_schema.assert_not_awaited()
        uc.create_table.assert_not_awaited()
        uc.delete_table.assert_not_awaited()

    async def test_add_schemas_and_tables(self) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.create_schema = AsyncMock(return_value={})
        uc.create_table = AsyncMock(return_value={})
        uc.delete_table = AsyncMock()
        diff = SyncDiff(
            add_schemas=("public",),
            add_tables=(_pg_table("public", "users", ("id", "integer")),),
        )
        counts = await apply_diff(uc, "pg_cat", diff)
        assert counts == (2, 0, 0)  # 1 schema + 1 table
        uc.create_schema.assert_awaited_once_with({"catalog_name": "pg_cat", "name": "public"})
        (call,) = uc.create_table.await_args_list
        body = call.args[0]
        assert body["catalog_name"] == "pg_cat"
        assert body["schema_name"] == "public"
        assert body["name"] == "users"
        assert body["table_type"] == "EXTERNAL"
        assert body["data_source_format"] == "DELTA"
        assert body["storage_location"].startswith("file:///foreign/pg_cat/")
        assert body["columns"][0]["name"] == "id"
        assert body["columns"][0]["type_name"] == "INT"

    async def test_change_table_drops_then_creates(self) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.delete_table = AsyncMock()
        uc.create_table = AsyncMock(return_value={})
        diff = SyncDiff(
            change_tables=(_pg_table("public", "users", ("id", "bigint")),),
        )
        counts = await apply_diff(uc, "pg_cat", diff)
        assert counts == (0, 1, 0)
        uc.delete_table.assert_awaited_once_with("pg_cat", "public", "users")
        uc.create_table.assert_awaited_once()

    async def test_drop_tables(self) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.delete_table = AsyncMock()
        diff = SyncDiff(drop_tables=(("public", "old"),))
        counts = await apply_diff(uc, "pg_cat", diff)
        assert counts == (0, 0, 1)
        uc.delete_table.assert_awaited_once_with("pg_cat", "public", "old")


# -- collect_uc_tables --


class TestCollectUcTables:
    async def test_walks_schemas_and_tables(self) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.list_schemas = AsyncMock(return_value=[{"name": "public"}])
        uc.list_tables = AsyncMock(
            return_value=[
                {
                    "name": "users",
                    "columns": [
                        {"name": "id", "type_name": "INT"},
                        {"name": "email", "type_name": "STRING"},
                    ],
                }
            ]
        )
        tables = await collect_uc_tables(uc, "pg_cat")
        assert len(tables) == 1
        assert tables[0].schema == "public"
        assert tables[0].name == "users"
        assert [c.name for c in tables[0].columns] == ["id", "email"]


# -- run_sync end-to-end with stub introspector --


@pytest.fixture
def metadata_factory() -> Any:
    """Return an in-memory session factory with PointlesSQL tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


class _StubIntrospector:
    """Deterministic stand-in for :class:`PsycopgIntrospector`."""

    def __init__(self, snapshot: PostgresSnapshot) -> None:
        self.snapshot_value = snapshot
        self.calls: list[tuple[str, Any]] = []

    def snapshot(self, dsn: str, schema_filter: Any = None) -> PostgresSnapshot:
        self.calls.append((dsn, schema_filter))
        return self.snapshot_value


class TestRunSync:
    async def test_success_writes_sync_run(self, metadata_factory: Any) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.list_schemas = AsyncMock(return_value=[])
        uc.list_tables = AsyncMock(return_value=[])
        uc.create_schema = AsyncMock(return_value={})
        uc.create_table = AsyncMock(return_value={})
        uc.delete_table = AsyncMock()

        introspector = _StubIntrospector(
            PostgresSnapshot(tables=(_pg_table("public", "users", ("id", "integer")),))
        )
        connection = {
            "name": "pg1",
            "options": {"host": "db.example.com", "database": "analytics"},
        }
        run = await run_sync(
            uc=uc,
            factory=metadata_factory,
            catalog_name="pg_cat",
            introspector=introspector,
            connection=connection,
            credential=None,
        )
        assert run.status == "succeeded"
        assert run.added_count == 2  # new schema + new table
        assert run.error is None
        # Persisted:
        recent = list_recent_runs(metadata_factory, "pg_cat")
        assert len(recent) == 1
        assert recent[0].status == "succeeded"

    async def test_failure_records_error(self, metadata_factory: Any) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.list_schemas = AsyncMock(side_effect=RuntimeError("boom"))
        introspector = _StubIntrospector(PostgresSnapshot(tables=()))
        connection = {"options": {"host": "h"}}
        run = await run_sync(
            uc=uc,
            factory=metadata_factory,
            catalog_name="pg_cat",
            introspector=introspector,
            connection=connection,
            credential=None,
        )
        assert run.status == "failed"
        assert run.error is not None
        assert "boom" in run.error

    async def test_missing_host_records_validation_error(self, metadata_factory: Any) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        introspector = _StubIntrospector(PostgresSnapshot(tables=()))
        connection = {"options": {}}  # no host
        run = await run_sync(
            uc=uc,
            factory=metadata_factory,
            catalog_name="pg_cat",
            introspector=introspector,
            connection=connection,
            credential=None,
        )
        assert run.status == "failed"
        assert "host" in (run.error or "")


# -- list_recent_runs ordering --


def test_list_recent_runs_most_recent_first(metadata_factory: Any) -> None:
    import datetime

    with metadata_factory() as session:
        for i in range(3):
            session.add(
                SyncRun(
                    catalog_name="pg_cat",
                    started_at=datetime.datetime(2026, 4, 1 + i, 12, 0, tzinfo=datetime.UTC),
                    finished_at=None,
                    status="succeeded",
                    added_count=i,
                    changed_count=0,
                    dropped_count=0,
                )
            )
        session.add(
            SyncRun(
                catalog_name="other_cat",
                started_at=datetime.datetime(2026, 4, 5, tzinfo=datetime.UTC),
                status="succeeded",
            )
        )
        session.commit()

    runs = list_recent_runs(metadata_factory, "pg_cat", limit=10)
    assert [r.added_count for r in runs] == [2, 1, 0]
    assert all(r.catalog_name == "pg_cat" for r in runs)


# -- Route tests --


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _non_admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    )


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route per-request client construction through app.state.uc_client."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


class TestSyncRoute:
    async def test_non_admin_forbidden(self) -> None:
        app.state.uc_client = MagicMock(spec=UnityCatalogClient)
        async with _non_admin_client() as client:
            resp = await client.post("/api/catalogs/pg_cat/sync")
        assert resp.status_code == 403

    async def test_admin_sync_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.get_catalog = AsyncMock(
            return_value={
                "name": "pg_cat",
                "connection_name": "pg1",
            }
        )
        uc.get_connection = AsyncMock(
            return_value={
                "name": "pg1",
                "options": {"host": "h", "database": "d"},
            }
        )
        uc.list_schemas = AsyncMock(return_value=[])
        uc.list_tables = AsyncMock(return_value=[])
        uc.create_schema = AsyncMock(return_value={})
        uc.create_table = AsyncMock(return_value={})
        app.state.uc_client = uc

        # Stub the introspector so the route never touches psycopg.
        monkeypatch.setattr(
            pg_sync,
            "PsycopgIntrospector",
            lambda: _StubIntrospector(
                PostgresSnapshot(tables=(_pg_table("public", "users", ("id", "integer")),))
            ),
        )

        async with _admin_client() as client:
            resp = await client.post("/api/catalogs/pg_cat/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["added_count"] == 2  # schema + table

    async def test_sync_non_foreign_catalog_denied(self) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.get_catalog = AsyncMock(return_value={"name": "managed_cat", "type": "MANAGED"})
        app.state.uc_client = uc
        async with _admin_client() as client:
            resp = await client.post("/api/catalogs/managed_cat/sync")
        assert resp.status_code == 403

    async def test_audit_log_written(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        uc.get_catalog = AsyncMock(return_value={"name": "pg_cat", "connection_name": "pg1"})
        uc.get_connection = AsyncMock(return_value={"name": "pg1", "options": {"host": "h"}})
        uc.list_schemas = AsyncMock(return_value=[])
        uc.list_tables = AsyncMock(return_value=[])
        uc.create_schema = AsyncMock(return_value={})
        uc.create_table = AsyncMock(return_value={})
        app.state.uc_client = uc

        monkeypatch.setattr(
            pg_sync,
            "PsycopgIntrospector",
            lambda: _StubIntrospector(PostgresSnapshot(tables=())),
        )

        async with _admin_client() as client:
            resp = await client.post("/api/catalogs/pg_cat/sync")
        assert resp.status_code == 200

        # Audit entry landed on the shared test factory.
        from sqlalchemy import select

        from pointlessql.models import AuditLog

        factory = app.state.session_factory
        with factory() as session:
            entries = session.scalars(
                select(AuditLog).where(AuditLog.action == "sync_catalog")
            ).all()
        assert len(entries) == 1
        assert entries[0].target == "catalog:pg_cat"


class TestCatalogDetailHistory:
    async def test_history_card_renders_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import datetime

        uc = MagicMock(spec=UnityCatalogClient)
        uc.get_catalog = AsyncMock(
            return_value={
                "name": "pg_cat",
                "type": "FOREIGN",
                "connection_name": "pg1",
                "options": {},
                "comment": "",
                "properties": {},
                "created_at": 1700000000000,
                "updated_at": None,
                "created_by": None,
                "updated_by": None,
                "owner": None,
                "id": "fc-1",
                "storage_root": None,
                "storage_location": None,
            }
        )
        uc.get_tags = AsyncMock(return_value=[])
        uc.get_permissions = AsyncMock(return_value=[])
        uc.get_effective_permissions = AsyncMock(return_value=[])
        app.state.uc_client = uc

        # Seed one run so the card has content.
        factory = app.state.session_factory
        with factory() as session:
            session.add(
                SyncRun(
                    catalog_name="pg_cat",
                    started_at=datetime.datetime(2026, 4, 10, 12, 0, tzinfo=datetime.UTC),
                    finished_at=datetime.datetime(2026, 4, 10, 12, 1, tzinfo=datetime.UTC),
                    status="succeeded",
                    added_count=3,
                    changed_count=1,
                    dropped_count=0,
                )
            )
            session.commit()

        async with _admin_client() as client:
            resp = await client.get("/catalogs/pg_cat")
        assert resp.status_code == 200
        text = resp.text
        assert "Sync history" in text
        assert "Sync now" in text  # admin sees the button
        assert "succeeded" in text


# -- Integration test (requires real Postgres, skipped by default) --


@pytest.mark.integration
def test_psycopg_introspector_roundtrip_postgres() -> None:
    """Smoke test the real introspector against a live Postgres.

    Bring up a throwaway container first (see module docstring).
    """
    dsn = os.environ.get("POINTLESSQL_PG_SYNC_DSN")
    if not dsn:
        pytest.skip("POINTLESSQL_PG_SYNC_DSN not set")

    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS pointlessql_sync_test CASCADE")
        cur.execute("CREATE SCHEMA pointlessql_sync_test")
        cur.execute(
            "CREATE TABLE pointlessql_sync_test.users "
            "(id integer PRIMARY KEY, email text, amount numeric(10,2))"
        )
        conn.commit()

    try:
        snap = PsycopgIntrospector().snapshot(dsn, schema_filter=["pointlessql_sync_test"])
        assert len(snap.tables) == 1
        tbl = snap.tables[0]
        assert tbl.name == "users"
        col_names = [c.name for c in tbl.columns]
        assert col_names == ["id", "email", "amount"]
        amount = next(c for c in tbl.columns if c.name == "amount")
        assert amount.numeric_precision == 10
        assert amount.numeric_scale == 2
    finally:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("DROP SCHEMA pointlessql_sync_test CASCADE")
            conn.commit()
