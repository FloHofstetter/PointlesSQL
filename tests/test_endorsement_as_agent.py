"""Phase 76.5.1 — ``?as_agent=`` on endorsements POST.

Coverage:

* Agent's principal_user can apply an endorsement *as* the agent
  and the row carries both ``applied_by_user_id`` (principal)
  and ``applied_by_agent_id`` (the agent's PK).
* A different user trying the same slug gets 403.
* Unknown slug returns 404.
* Audit-log row carries ``agent_id`` + ``principal_user_id``.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.audit import AuditLog
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_products import DataProduct

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: test@test.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_product(tmp_path: Path) -> int:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _admin_user_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


@pytest.mark.asyncio
async def test_endorsement_as_agent_principal_ok(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Principal of an agent applies an endorsement under the agent identity."""
    dp_id = _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Endorse Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]

    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/endorsements?as_agent={slug}",
        json={"endorsement_type": "verified-by-steward", "note_md": "ok"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["agent"] is not None
    assert payload["agent"]["slug"] == slug
    assert payload["applied_by"]["user_id"] == principal_id

    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductEndorsement).where(
                DataProductEndorsement.data_product_id == dp_id,
                DataProductEndorsement.endorsement_type == "verified-by-steward",
                DataProductEndorsement.removed_at.is_(None),
            )
        ).scalar_one()
        assert row.applied_by_user_id == principal_id
        assert row.applied_by_agent_id is not None


@pytest.mark.asyncio
async def test_endorsement_as_agent_non_principal_rejected(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-principal cannot speak as someone else's agent."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Owners Endorser",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    res = await non_admin_client.post(
        f"/api/data-products/main/sales_gold/endorsements?as_agent={slug}",
        json={"endorsement_type": "verified-by-steward"},
    )
    # 403 from AuthorizationError; the non-admin is not steward
    # either, so 403 also masks the steward-gate.  Either way the
    # agent-impersonation branch never lands.
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_endorsement_as_unknown_agent_404(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown ``?as_agent=`` slug returns 404."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements?as_agent=ghost",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_endorsement_audit_carries_agent_id(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The audit_log row written on apply carries both ids."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Auditor Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/endorsements?as_agent={slug}",
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
        assert rows, "audit row missing"
        # The most recent row is the one we just wrote.
        detail = json.loads(rows[-1].detail or "{}")
        assert "agent_id" in detail
        assert detail["principal_user_id"] == principal_id
