"""Tests for the data-product README surface.

Covers PUT version-bump + idempotency on unchanged body, the
404 paths (no README + missing version), the steward-or-admin
edit gate, the unified-diff helper, and cross-workspace
isolation.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._entity_readme import EntityReadme
from pointlessql.models.workspace import Workspace, WorkspaceMember

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + load it; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


# ---------------------------------------------------------------------------
# PUT version-bump + idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_creates_v1(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """First PUT creates ``version_int=1``."""
    _seed_product(tmp_path)
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "# Sales\n\nFirst draft."},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["version_int"] == 1
    assert "First draft" in body["body_md"]


@pytest.mark.asyncio
async def test_second_put_bumps_version(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """A second PUT with new body creates v2 + keeps v1."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "v1 body"},
    )
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "v2 body"},
    )
    assert res.json()["version_int"] == 2
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(EntityReadme)).scalars().all()
        versions = sorted(r.version_int for r in rows)
        assert versions == [1, 2]


@pytest.mark.asyncio
async def test_put_is_no_op_on_unchanged_body(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unchanged body doesn't create a v+1 row."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "same"},
    )
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "same"},
    )
    assert res.json()["version_int"] == 1


# ---------------------------------------------------------------------------
# GET paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_404_when_no_readme(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """No README → 404 on the latest endpoint."""
    _seed_product(tmp_path)
    res = await admin_client.get("/api/data-products/main/sales_gold/readme")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_specific_version_round_trip(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``v/1`` still returns v1 after v2 exists."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "v1 body"},
    )
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "v2 body"},
    )
    res = await admin_client.get("/api/data-products/main/sales_gold/readme/v/1")
    assert res.status_code == 200
    assert res.json()["body_md"] == "v1 body"


@pytest.mark.asyncio
async def test_history_lists_versions_desc(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """History endpoint lists every version, newest first."""
    _seed_product(tmp_path)
    for n in range(3):
        await admin_client.put(
            "/api/data-products/main/sales_gold/readme",
            json={"body_md": f"v{n + 1}"},
        )
    res = await admin_client.get("/api/data-products/main/sales_gold/readme/history")
    versions = res.json()["versions"]
    assert [v["version_int"] for v in versions] == [3, 2, 1]


# ---------------------------------------------------------------------------
# Edit gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_steward_non_admin_cannot_edit(
    tmp_path: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-steward non-admin gets 403 on PUT."""
    _seed_product(tmp_path)
    res = await non_admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "x"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_steward_can_edit(tmp_path: Path, non_admin_client: httpx.AsyncClient) -> None:
    """When the caller IS the steward, PUT passes."""
    _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        dp = session.execute(select(DataProduct)).scalar_one()
        dp.steward_user_id = nonadmin.id
        session.add(dp)
        session.commit()
    res = await non_admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "by steward"},
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_between_versions(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Unified diff includes the expected +/- markers."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "alpha\nbeta\ngamma"},
    )
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "alpha\nDELTA\ngamma"},
    )
    res = await admin_client.get("/api/data-products/main/sales_gold/readme/diff?from=1&to=2")
    assert res.status_code == 200
    diff = res.json()["diff"]
    assert "-beta" in diff
    assert "+DELTA" in diff


@pytest.mark.asyncio
async def test_diff_missing_version_404(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Diff endpoint 404s when one of the requested versions doesn't exist."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "only"},
    )
    res = await admin_client.get("/api/data-products/main/sales_gold/readme/diff?from=1&to=99")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Cross-workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readme_cross_workspace_isolated(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A README in workspace 1 is invisible from workspace 2."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "ws1 only"},
    )
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Workspace(
                id=2,
                slug="second",
                name="Second",
                description="iso test",
                created_at=now,
            )
        )
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        session.add(
            WorkspaceMember(
                workspace_id=2,
                user_id=nonadmin.id,
                role="member",
                created_at=now,
            )
        )
        nonadmin.default_workspace_id = 2
        session.add(nonadmin)
        session.commit()
    res = await non_admin_client.get(
        "/api/data-products/main/sales_gold/readme",
        headers={"X-Workspace": "second"},
    )
    assert res.status_code == 404
