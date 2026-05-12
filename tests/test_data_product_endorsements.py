"""Tests for the Phase-72.4 typed manual endorsements.

Covers:

* Apply each of the 4 types (admin) → 4 separate rows.
* Re-applying an active type is a no-op (returns existing row).
* DELETE flips ``removed_at``; idempotent.
* Re-apply after DELETE creates a new row.
* Unknown type → 400.
* ``verified-by-steward`` accepts auditor; other types 403 for auditor.
* Audit-log row created on each apply + remove.
* Cross-workspace iso.
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.audit._log import AuditLog
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_products import DataProduct
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


@pytest.fixture
async def auditor_client(
    auth_cookies: dict[str, str],
) -> AsyncIterator[httpx.AsyncClient]:
    """Pre-authenticated client whose user has ``is_auditor=True``."""
    factory = app.state.session_factory
    with factory() as session:
        u = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        u.is_admin = False
        u.is_auditor = True
        session.add(u)
        session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=auth_cookies,
    ) as client:
        yield client


def _seed_dp(tmp_path: Path) -> int:
    """Seed one data product; return its id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


# ---------------------------------------------------------------------------
# Apply happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_each_type(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Admin can apply each of the four typed endorsements."""
    _seed_dp(tmp_path)
    for et in (
        "verified-by-steward",
        "production-ready",
        "deprecated",
        "under-review",
    ):
        res = await admin_client.post(
            "/api/data-products/main/sales_gold/endorsements",
            json={"endorsement_type": et, "note_md": f"reason for {et}"},
        )
        assert res.status_code == 200, f"{et}: {res.text}"
        assert res.json()["endorsement_type"] == et


@pytest.mark.asyncio
async def test_apply_unknown_type_400(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown endorsement_type returns 400."""
    _seed_dp(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "wat-is-this"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_apply_active_type_is_idempotent(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Re-applying an active type returns the existing row (no duplicate)."""
    _seed_dp(tmp_path)
    first = await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    second = await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    assert first.json()["id"] == second.json()["id"]
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductEndorsement)).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Remove + re-apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_flips_removed_at_idempotent(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """DELETE sets ``removed_at``; second DELETE returns same row state."""
    _seed_dp(tmp_path)
    applied = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/endorsements",
            json={"endorsement_type": "deprecated"},
        )
    ).json()
    first = await admin_client.delete(
        f"/api/data-products/main/sales_gold/endorsements/{applied['id']}"
    )
    assert first.status_code == 200
    assert first.json()["removed_at"] is not None
    second = await admin_client.delete(
        f"/api/data-products/main/sales_gold/endorsements/{applied['id']}"
    )
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_reapply_after_remove_creates_new_row(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """After remove, applying the same type again creates a fresh row."""
    _seed_dp(tmp_path)
    first = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/endorsements",
            json={"endorsement_type": "under-review"},
        )
    ).json()
    await admin_client.delete(
        f"/api/data-products/main/sales_gold/endorsements/{first['id']}"
    )
    second = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/endorsements",
            json={"endorsement_type": "under-review"},
        )
    ).json()
    assert second["id"] != first["id"]
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductEndorsement)).scalars().all()
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# Auditor scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auditor_can_apply_verified_by_steward(
    tmp_path: Path, auditor_client: httpx.AsyncClient
) -> None:
    """An auditor can apply ``verified-by-steward``."""
    _seed_dp(tmp_path)
    res = await auditor_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_auditor_cannot_apply_production_ready(
    tmp_path: Path, auditor_client: httpx.AsyncClient
) -> None:
    """An auditor is blocked from non-verification types (403)."""
    _seed_dp(tmp_path)
    res = await auditor_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Audit-log mirror
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_writes_audit_log_row(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Each apply drops ``endorsement.applied`` into audit_log."""
    _seed_dp(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(AuditLog).where(AuditLog.action == "endorsement.applied")
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].target == "data_product:main.sales_gold"


@pytest.mark.asyncio
async def test_remove_writes_audit_log_row(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Each remove drops ``endorsement.removed`` into audit_log."""
    _seed_dp(tmp_path)
    applied = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/endorsements",
            json={"endorsement_type": "production-ready"},
        )
    ).json()
    await admin_client.delete(
        f"/api/data-products/main/sales_gold/endorsements/{applied['id']}"
    )
    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(AuditLog).where(AuditLog.action == "endorsement.removed")
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Cross-workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_workspace_iso(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A workspace-1 endorsement is invisible from workspace 2."""
    _seed_dp(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Workspace(
                id=2, slug="second", name="Second",
                description="iso", created_at=now,
            )
        )
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        session.add(
            WorkspaceMember(
                workspace_id=2, user_id=nonadmin.id, role="member",
                created_at=now,
            )
        )
        nonadmin.default_workspace_id = 2
        session.add(nonadmin)
        session.commit()
    res = await non_admin_client.get(
        "/api/data-products/main/sales_gold/endorsements",
        headers={"X-Workspace": "second"},
    )
    assert res.status_code == 404
