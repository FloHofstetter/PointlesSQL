"""Phase 82.5 — DP ``ingest-status`` endpoint smoke tests."""

from __future__ import annotations

import datetime
import json
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct, IngestSource

_VALID_CONTRACT = json.dumps(
    {
        "data_product": {
            "name": "Test",
            "version": "1.0.0",
            "description": "",
            "catalog": "main",
            "schema": "demo",
            "steward_email": "alice@example.com",
            "sla_minutes": 60,
            "tables": [],
        }
    }
)


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        for src in session.query(IngestSource).all():
            session.delete(src)
        for dp in (
            session.query(DataProduct)
            .filter(DataProduct.catalog_name == "main", DataProduct.schema_name == "demo")
            .all()
        ):
            session.delete(dp)
        session.commit()


@pytest.fixture(autouse=True)
def _clean() -> None:
    _wipe()
    yield
    _wipe()


def _seed_dp() -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="main",
            schema_name="demo",
            version="1.0.0",
            description="",
            sla_minutes=60,
            contract_yaml_hash="x" * 64,
            contract_json=_VALID_CONTRACT,
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.commit()
        return int(dp.id)


def _seed_source(*, target_fqn: str, ok: bool = True) -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    mapping: dict[str, Any] = {
        "source_table": "t",
        "target_fqn": target_fqn,
        "mode": "full",
        "last_pull_stats": {
            "ok": ok,
            "rows_written": 5,
            "duration_ms": 12,
            "target_fqn": target_fqn,
            "job_run_id": 0,
            "ts": now.isoformat(),
        },
    }
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name=f"src-for-{target_fqn}",
            kind="sqlite",
            config=json.dumps({"path": "/tmp/x.db"}),
            secrets="{}",
            table_mappings=json.dumps([mapping]),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


@pytest.mark.asyncio
async def test_dp_ingest_status_lists_matching_sources(
    admin_client: httpx.AsyncClient,
) -> None:
    """Sources whose target lands in the DP's schema are returned."""
    _seed_dp()
    _seed_source(target_fqn="main.demo.orders")
    _seed_source(target_fqn="main.demo.customers")
    # Unrelated source, different schema — should NOT appear.
    _seed_source(target_fqn="main.other.foo")
    res = await admin_client.get(
        "/api/data-products/main/demo/ingest-status"
    )
    assert res.status_code == 200, res.text
    sources = res.json()["sources"]
    fqns = {s["target_fqn"] for s in sources}
    assert "main.demo.orders" in fqns
    assert "main.demo.customers" in fqns
    assert "main.other.foo" not in fqns


@pytest.mark.asyncio
async def test_dp_ingest_status_404_for_missing(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown DP returns 404."""
    res = await admin_client.get(
        "/api/data-products/main/no-such-schema/ingest-status"
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_dp_ingest_status_empty_when_no_match(
    admin_client: httpx.AsyncClient,
) -> None:
    """DP with no ingest source returns an empty list."""
    _seed_dp()
    res = await admin_client.get(
        "/api/data-products/main/demo/ingest-status"
    )
    assert res.status_code == 200
    assert res.json()["sources"] == []
