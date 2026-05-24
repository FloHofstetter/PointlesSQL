"""Smoke tests for the ⋯-action menu macro.

Verifies the macro renders into the DP and Run detail pages so the
Copy-link / Copy-citation / Mute-notifications items reach the DOM
that the document-level handlers register against.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.data_products import load_contract

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


def _seed_dp(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    load_contract(yaml_path, factory=app.state.session_factory)


@pytest.mark.asyncio
async def test_dp_page_renders_entity_actions_menu(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """The DP detail page surfaces the macro with the DP citation token."""
    _seed_dp(tmp_path)
    res = await admin_client.get("/data-products/main/sales_gold")
    assert res.status_code == 200
    body = res.text
    assert "pql-entity-actions" in body
    assert "pql-entity-mute-btn" in body
    assert 'data-pql-mute-kind="dp"' in body
    assert "#dp:main.sales_gold" in body
    assert 'data-pql-copy="/data-products/main/sales_gold"' in body
