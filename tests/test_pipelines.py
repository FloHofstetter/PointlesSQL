"""Tests for declarative pipelines (validation, DAG, engine, routes)."""

from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import deltalake
import httpx
import pandas as pd
import pytest
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo

import pointlessql.models.pipelines  # noqa: F401 — register tables on Base
from pointlessql.api.main import app
from pointlessql.services import pipelines as svc
from pointlessql.services.pipelines import PipelineValidationError, _engine


def _factory():
    return app.state.session_factory


# ---------------------------------------------------------------------------
# validation + DAG
# ---------------------------------------------------------------------------


def _dataset(name: str, sql: str, kind: str = "materialized_view", **extra: Any) -> dict:
    return {"name": name, "kind": kind, "sql": sql, **extra}


def test_validate_datasets_normalises_and_orders() -> None:
    datasets = svc.validate_datasets(
        [
            _dataset("c.gold.daily", "SELECT region FROM c.silver.events"),
            _dataset("c.silver.events", "SELECT * FROM c.bronze.raw"),
        ]
    )
    ordered = svc.topological_order(datasets)
    assert [d["name"] for d in ordered] == ["c.silver.events", "c.gold.daily"]
    assert datasets[0]["refs"] == ["c.silver.events"]


@pytest.mark.parametrize(
    ("datasets", "match"),
    [
        ([], "at least one"),
        ([_dataset("two.part", "SELECT 1 FROM a.b.c")], "catalog.schema.table"),
        ([_dataset("a.b.c", "DROP TABLE x")], "SQL"),
        ([_dataset("a.b.c", "SELECT * FROM a.b.c")], "reads itself"),
        (
            [
                _dataset(
                    "a.b.st",
                    "SELECT * FROM a.b.x JOIN a.b.y ON TRUE",
                    kind="streaming_table",
                )
            ],
            "exactly one source",
        ),
        (
            [
                _dataset(
                    "a.b.c",
                    "SELECT 1 FROM a.b.x",
                    expectations=[{"name": "e", "constraint": "1=1", "action": "explode"}],
                )
            ],
            "action",
        ),
        (
            [
                _dataset("a.b.c", "SELECT 1 FROM a.b.d"),
                _dataset("a.b.d", "SELECT 1 FROM a.b.c"),
            ],
            "cycle",
        ),
    ],
)
def test_validate_datasets_rejects(datasets: list, match: str) -> None:
    with pytest.raises(PipelineValidationError, match=match):
        svc.validate_datasets(datasets)


def test_crud_roundtrip() -> None:
    row = svc.create_pipeline(
        _factory(),
        workspace_id=1,
        title="Daily revenue",
        description=None,
        owner_id=1,
        datasets=[_dataset("c.gold.rev", "SELECT * FROM c.silver.orders")],
    )
    assert row.slug.startswith("daily-revenue-")
    assert svc.get_pipeline(_factory(), workspace_id=1, slug=row.slug) is not None
    with pytest.raises(PipelineValidationError, match="cycle"):
        svc.update_pipeline(
            _factory(),
            pipeline_id=row.id,
            datasets=[
                _dataset("a.b.c", "SELECT 1 FROM a.b.d"),
                _dataset("a.b.d", "SELECT 1 FROM a.b.c"),
            ],
        )
    assert svc.delete_pipeline(_factory(), pipeline_id=row.id)


# ---------------------------------------------------------------------------
# engine — real Delta tables, soyuz writes mocked like the lineage harness
# ---------------------------------------------------------------------------


@contextmanager
def _patched_writes(storage_root: str):
    """Mock the soyuz syncs PQL's write path resolves at runtime."""
    with ExitStack() as stack:
        mget = stack.enter_context(patch("pointlessql.pql._write._get_table"))
        mschema = stack.enter_context(patch("pointlessql.pql._write._get_schema"))
        mcreate = stack.enter_context(patch("pointlessql.pql._write._create_table"))
        mget.sync.side_effect = UnexpectedStatus(404, b"Not Found")
        mschema.sync.return_value = SchemaInfo(storage_root=storage_root, name="gold")
        mcreate.sync.return_value = TableInfo(name="t")
        yield


def _read_target(path: str) -> pd.DataFrame:
    return deltalake.DeltaTable(path).to_pyarrow_table().to_pandas()


def test_engine_mv_and_streaming_end_to_end(tmp_path, monkeypatch) -> None:
    bronze_path = str(tmp_path / "bronze")
    deltalake.write_deltalake(
        bronze_path,
        pd.DataFrame({"region": ["emea", "apac"], "amount": [10, -5]}),
        configuration={"delta.enableChangeDataFeed": "true"},
    )
    warehouse = str(tmp_path / "warehouse")
    bronze_fqn = "c.bronze.orders"
    mv_fqn = "c.gold.revenue"
    st_fqn = "c.gold.events"

    pipeline = svc.create_pipeline(
        _factory(),
        workspace_id=1,
        title="e2e",
        description=None,
        owner_id=1,
        datasets=[
            _dataset(
                mv_fqn,
                f"SELECT region, sum(amount) AS revenue FROM {bronze_fqn} GROUP BY 1",
            ),
            _dataset(
                st_fqn,
                f"SELECT region, amount FROM {bronze_fqn}",
                kind="streaming_table",
                expectations=[
                    {"name": "positive_amount", "constraint": "amount > 0", "action": "drop"}
                ],
            ),
        ],
    )

    targets = {
        mv_fqn: f"{warehouse}/revenue",
        st_fqn: f"{warehouse}/events",
    }
    monkeypatch.setattr(_engine, "_get_table_storage", lambda client, fqn: targets[fqn])

    with _patched_writes(warehouse):
        run_id = svc.run_pipeline_sync(
            _factory(),
            pipeline_id=pipeline.id,
            triggered_by="flo@test.com",
            external={bronze_fqn: bronze_path},
            external_policies={},
            client=MagicMock(),
        )
    runs = svc.list_runs(_factory(), pipeline_id=pipeline.id)
    run = next(r for r in runs if r.id == run_id)
    assert run.status == "ok", run.error
    metrics = {m["dataset"]: m for m in json.loads(run.metrics)}
    assert metrics[mv_fqn]["rows_written"] == 2
    # the drop expectation removed the negative row from the backfill
    assert metrics[st_fqn]["rows_written"] == 1
    assert metrics[st_fqn]["expectations"][0]["violations"] == 1
    # PQL writes land under <warehouse>/<bare table name>
    assert len(_read_target(f"{warehouse}/revenue")) == 2
    assert _read_target(f"{warehouse}/events")["amount"].tolist() == [10]

    # incremental second run: only the appended rows flow into the ST
    deltalake.write_deltalake(
        bronze_path,
        pd.DataFrame({"region": ["emea"], "amount": [99]}),
        mode="append",
    )
    with _patched_writes(warehouse):
        run2 = svc.run_pipeline_sync(
            _factory(),
            pipeline_id=pipeline.id,
            triggered_by="flo@test.com",
            external={bronze_fqn: bronze_path},
            external_policies={},
            client=MagicMock(),
        )
    runs = svc.list_runs(_factory(), pipeline_id=pipeline.id)
    run = next(r for r in runs if r.id == run2)
    assert run.status == "ok", run.error
    metrics = {m["dataset"]: m for m in json.loads(run.metrics)}
    assert metrics[st_fqn]["rows_written"] == 1
    events = _read_target(f"{warehouse}/events")
    assert sorted(events["amount"].tolist()) == [10, 99]

    # third run with nothing new: the streaming table skips
    with _patched_writes(warehouse):
        run3 = svc.run_pipeline_sync(
            _factory(),
            pipeline_id=pipeline.id,
            triggered_by="flo@test.com",
            external={bronze_fqn: bronze_path},
            external_policies={},
            client=MagicMock(),
        )
    runs = svc.list_runs(_factory(), pipeline_id=pipeline.id)
    run = next(r for r in runs if r.id == run3)
    metrics = {m["dataset"]: m for m in json.loads(run.metrics)}
    assert metrics[st_fqn]["skipped"] is True


def test_engine_fail_expectation_fails_the_run(tmp_path, monkeypatch) -> None:
    bronze_path = str(tmp_path / "bronze")
    deltalake.write_deltalake(bronze_path, pd.DataFrame({"amount": [-1]}))
    warehouse = str(tmp_path / "warehouse")
    pipeline = svc.create_pipeline(
        _factory(),
        workspace_id=1,
        title="failing",
        description=None,
        owner_id=1,
        datasets=[
            _dataset(
                "c.gold.strict",
                "SELECT amount FROM c.bronze.raw",
                expectations=[{"name": "positive", "constraint": "amount > 0", "action": "fail"}],
            )
        ],
    )
    monkeypatch.setattr(_engine, "_get_table_storage", lambda client, fqn: f"{warehouse}/x")
    with _patched_writes(warehouse):
        run_id = svc.run_pipeline_sync(
            _factory(),
            pipeline_id=pipeline.id,
            triggered_by=None,
            external={"c.bronze.raw": bronze_path},
            external_policies={},
            client=MagicMock(),
        )
    run = next(r for r in svc.list_runs(_factory(), pipeline_id=pipeline.id) if r.id == run_id)
    assert run.status == "failed"
    assert "positive" in (run.error or "")


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


def _client(cookies: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


@pytest.mark.asyncio
async def test_pipeline_routes_crud_and_pages(uc_client_stub) -> None:
    async with _client(app.state._test_auth_cookie) as client:
        created = await client.post(
            "/api/pipelines",
            json={
                "title": "Route Pipe",
                "datasets": [
                    {
                        "name": "c.gold.t",
                        "kind": "materialized_view",
                        "sql": "SELECT 1 AS x FROM c.silver.s",
                        "expectations": [],
                    }
                ],
            },
        )
        assert created.status_code == 200, created.text
        slug = created.json()["slug"]

        listing = await client.get("/api/pipelines")
        assert slug in [p["slug"] for p in listing.json()["pipelines"]]

        bad = await client.patch(
            f"/api/pipelines/{slug}",
            json={"datasets": [{"name": "nope", "kind": "x", "sql": ""}]},
        )
        assert bad.status_code == 422

        page = await client.get("/pipelines")
        assert page.status_code == 200
        assert "pipelines.js" in page.text
        detail = await client.get(f"/pipelines/{slug}")
        assert detail.status_code == 200
        assert "pipeline_detail.js" in detail.text

        gone = await client.delete(f"/api/pipelines/{slug}")
        assert gone.json()["deleted"] is True


@pytest.mark.asyncio
async def test_run_endpoint_enforces_and_dispatches(uc_client_stub, monkeypatch) -> None:
    uc_client_stub.get_table.return_value = {
        "storage_location": "memory://orders",
        "owner": "test@test.com",
        "properties": {},
    }

    seen: dict[str, Any] = {}

    def _fake_run(factory: Any, **kwargs: Any) -> int:
        seen.update(kwargs)
        from pointlessql.models.pipelines import PipelineRun
        from pointlessql.services.pipelines._engine import _utcnow

        with factory() as session:
            run = PipelineRun(
                pipeline_id=kwargs["pipeline_id"],
                status="ok",
                triggered_by=kwargs["triggered_by"],
                metrics="[]",
                started_at=_utcnow(),
                finished_at=_utcnow(),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    monkeypatch.setattr("pointlessql.services.pipelines.run_pipeline_sync", _fake_run)
    monkeypatch.setattr(
        "pointlessql.services.soyuz_client.make_principal_client",
        lambda settings, principal: MagicMock(),
    )

    async with _client(app.state._test_auth_cookie) as client:
        created = await client.post(
            "/api/pipelines",
            json={
                "title": "Runner",
                "datasets": [
                    {
                        "name": "c.gold.out",
                        "kind": "materialized_view",
                        "sql": "SELECT 1 AS x FROM c.silver.src",
                        "expectations": [],
                    }
                ],
            },
        )
        slug = created.json()["slug"]
        ran = await client.post(f"/api/pipelines/{slug}/run")
    assert ran.status_code == 200, ran.text
    assert ran.json()["status"] == "ok"
    assert seen["external"] == {"c.silver.src": "memory://orders"}
    assert seen["triggered_by"] == "test@test.com"
