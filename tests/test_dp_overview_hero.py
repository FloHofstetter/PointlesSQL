"""DP overview hero + releases + forks + heatmap.

Smoke tests that the new endpoints return the expected envelope.
The HTML hero card lives in ``data_product.html`` and is rendered
client-side from these JSON surfaces; we only check the JSON
contract here.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    BranchAuditLog,
    DataProduct,
    DataProductRelease,
)

_VALID_CONTRACT = json.dumps(
    {
        "name": "Test",
        "version": "1.0.0",
        "description": "",
        "catalog": "main",
        "schema": "demo",
        "steward_email": "alice@example.com",
        "sla_minutes": 60,
        "tables": [],
    }
)


def _wipe() -> None:
    factory = app.state.session_factory
    # AuditLog enforces append-only via service-layer guard; cleaned
    # up via the dedicated retention helper that opens the
    # contextvar scope.
    from pointlessql.services.audit._core import _allow_audit_mutation

    with factory() as session:
        for cls in (DataProductRelease, BranchAuditLog, DataProduct):
            for r in session.query(cls).all():
                session.delete(r)
        with _allow_audit_mutation():
            for r in session.query(AuditLog).all():
                session.delete(r)
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


def _seed_release(dp_id: int, *, version: str = "1.0.1") -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            DataProductRelease(
                data_product_id=dp_id,
                version=version,
                contract_yaml_hash="y" * 64,
                released_at=now,
                signed_off_by_email="alice@example.com",
            )
        )
        session.commit()


def _seed_branch_audit(*, branch: str, action: str = "create") -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            BranchAuditLog(
                branch_schema_fqn=branch,
                parent_schema_fqn="main.demo",
                action=action,
                run_id=None,
                payload_json="{}",
                created_at=now,
            )
        )
        session.commit()


def _seed_audit_target(target: str, *, days_ago: int) -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)
    with factory() as session:
        session.add(
            AuditLog(
                workspace_id=1,
                user_id=1,
                user_email="alice@example.com",
                actor_role="admin",
                action="view",
                target=target,
                detail=None,
                created_at=now,
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_releases_endpoint_returns_seeded_rows(
    admin_client: httpx.AsyncClient,
) -> None:
    """JSON releases endpoint returns seeded rows newest-first."""
    dp_id = _seed_dp()
    _seed_release(dp_id, version="1.0.1")
    _seed_release(dp_id, version="1.0.2")
    res = await admin_client.get("/api/data-products/main/demo/releases")
    assert res.status_code == 200
    payload = res.json()["releases"]
    assert len(payload) == 2
    assert payload[0]["version"] in {"1.0.1", "1.0.2"}


@pytest.mark.asyncio
async def test_releases_atom_feed(admin_client: httpx.AsyncClient) -> None:
    """Atom feed renders well-formed XML for the seeded releases."""
    dp_id = _seed_dp()
    _seed_release(dp_id, version="1.0.1")
    res = await admin_client.get("/api/data-products/main/demo/releases.atom")
    assert res.status_code == 200
    assert "application/atom+xml" in res.headers["content-type"]
    assert "<feed" in res.text
    assert "1.0.1" in res.text


@pytest.mark.asyncio
async def test_releases_404_for_unknown_dp(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown DP returns 404."""
    res = await admin_client.get("/api/data-products/main/nope/releases")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_forks_endpoint_lists_branches(
    admin_client: httpx.AsyncClient,
) -> None:
    """Forks endpoint returns one row per branch with parent==DP schema."""
    _seed_dp()
    _seed_branch_audit(branch="main.demo_branch1", action="create")
    _seed_branch_audit(branch="main.demo_branch1", action="promote")
    _seed_branch_audit(branch="main.other_branch", action="create")
    res = await admin_client.get("/api/data-products/main/demo/forks")
    assert res.status_code == 200
    forks = res.json()["forks"]
    fqns = {f["branch_schema_fqn"] for f in forks}
    assert "main.demo_branch1" in fqns
    # Picked the latest action.
    promote = next(f for f in forks if f["branch_schema_fqn"] == "main.demo_branch1")
    assert promote["last_action"] == "promote"


@pytest.mark.asyncio
async def test_heatmap_zero_fills_year(
    admin_client: httpx.AsyncClient,
) -> None:
    """Heatmap returns 365 cells; recent audit row shows up."""
    _seed_dp()
    _seed_audit_target("dp:main.demo", days_ago=5)
    _seed_audit_target("dp:main.demo", days_ago=5)
    _seed_audit_target("dp:other.demo", days_ago=1)  # ignored
    res = await admin_client.get("/api/data-products/main/demo/heatmap")
    assert res.status_code == 200
    body = res.json()
    assert len(body["cells"]) == 365
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_dp_page_renders_hero_blocks(
    admin_client: httpx.AsyncClient,
) -> None:
    """The DP page contains every new section."""
    _seed_dp()
    res = await admin_client.get("/data-products/main/demo")
    assert res.status_code == 200
    body = res.text
    assert "pql-dp-health-hero" in body
    assert "pql-dp-readme-hero" in body
    assert "pql-dp-consume-hero" in body
    assert "pql-dp-schema-glance" in body
    assert "pql-dp-releases" in body
    assert "pql-dp-heatmap" in body
    assert "pql-dp-forks" in body
