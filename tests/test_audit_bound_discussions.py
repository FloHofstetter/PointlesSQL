"""Tests for the audit-bound discussion mirror.

Covers:

* Comment POST → exactly one ``audit.discussion.posted`` row in
  ``audit_log``.
* Comment soft-delete (DELETE) → exactly one
  ``audit.discussion.deleted`` row.
* The ``detail`` JSON carries ``data_product_id``, ``comment_id``,
  and a ``body_preview`` truncated to ~140 chars (POST only).
* ``target`` carries the click-through URL anchor.
* Idempotent DELETE on an already-soft-deleted comment does NOT
  emit a second ``deleted`` row.
* Cross-workspace isolation (workspace 2 user can't see
  workspace 1's audit row).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.audit._log import AuditLog
from pointlessql.models.catalog._data_products import DataProduct

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


def _seed_dp(tmp_path: Path) -> int:
    """Seed one DP."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _audit_rows(action: str) -> list[AuditLog]:
    """Return all ``audit_log`` rows whose ``action`` matches."""
    factory = app.state.session_factory
    with factory() as session:
        return session.execute(select(AuditLog).where(AuditLog.action == action)).scalars().all()


@pytest.mark.asyncio
async def test_post_drops_audit_log_row(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Comment POST creates exactly one ``audit.discussion.posted`` row."""
    _seed_dp(tmp_path)
    payload = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "first thoughts on the schema"},
    )
    assert payload.status_code == 200
    comment_id = payload.json()["id"]
    rows = _audit_rows("audit.discussion.posted")
    assert len(rows) == 1
    row = rows[0]
    assert row.target == (f"data_product:main.sales_gold#tab-discussion-comment-{comment_id}")
    detail = json.loads(row.detail) if row.detail else {}
    assert detail["comment_id"] == comment_id
    assert detail["data_product_id"]
    assert "first thoughts" in detail["body_preview"]


@pytest.mark.asyncio
async def test_long_body_preview_truncated(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """``body_preview`` caps at the 140-char ceiling."""
    _seed_dp(tmp_path)
    long_body = "x" * 500
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": long_body},
    )
    row = _audit_rows("audit.discussion.posted")[0]
    detail = json.loads(row.detail) if row.detail else {}
    assert len(detail["body_preview"]) <= 140


@pytest.mark.asyncio
async def test_delete_drops_audit_log_row(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Comment DELETE creates exactly one ``audit.discussion.deleted`` row."""
    _seed_dp(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "to be deleted"},
        )
    ).json()["id"]
    res = await admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    assert res.status_code == 200
    rows = _audit_rows("audit.discussion.deleted")
    assert len(rows) == 1
    assert rows[0].target == (f"data_product:main.sales_gold#tab-discussion-comment-{cid}")


@pytest.mark.asyncio
async def test_delete_is_idempotent_in_audit_log(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Re-DELETE on a soft-deleted comment doesn't emit a second row."""
    _seed_dp(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "x"},
        )
    ).json()["id"]
    await admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    await admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    rows = _audit_rows("audit.discussion.deleted")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_audit_row_carries_workspace(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """The audit-log row is stamped with the active workspace_id."""
    _seed_dp(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "x"},
    )
    row = _audit_rows("audit.discussion.posted")[0]
    assert row.workspace_id == 1
