"""Tests for the DP-scoped "Ask this data product" routes.

Cover opening a pre-seeded session (the transcript is grounded in the
product's tables), the unconfigured-provider signal, session ownership
isolation, and the provider-not-configured turn error.  The full
LLM round-trip needs a live provider key + network, so it is exercised
by the executor unit tests instead.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.services.lens import list_session_messages

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
        - {name: amount, type: double, nullable: true}
"""


def _seed_product(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    load_contract(yaml_path, factory=app.state.session_factory)


@pytest.mark.asyncio
async def test_open_ask_session_seeds_dp_context(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Opening a session seeds a user-context + assistant-intro turn."""
    _seed_product(tmp_path)
    res = await admin_client.post("/api/data-products/main/sales_gold/ask/sessions")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["session_id"] > 0
    # no LLM key configured in the test workspace
    assert body["configured"] is False
    assert body["intro"]

    msgs = list_session_messages(app.state.session_factory, session_id=body["session_id"])
    assert [m.role for m in msgs] == ["user", "assistant"]
    # the seeded context grounds the model in this product's table FQN
    assert "main.sales_gold.orders" in (msgs[0].content or "")


@pytest.mark.asyncio
async def test_ask_message_on_unowned_session_404(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A different user cannot post into someone else's Ask session."""
    _seed_product(tmp_path)
    sid = (await admin_client.post("/api/data-products/main/sales_gold/ask/sessions")).json()[
        "session_id"
    ]
    res = await non_admin_client.post(
        f"/api/data-products/main/sales_gold/ask/sessions/{sid}/messages",
        json={"content": "hi"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_ask_message_without_provider_422(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Posting a turn with no provider key surfaces a clean 422."""
    _seed_product(tmp_path)
    sid = (await admin_client.post("/api/data-products/main/sales_gold/ask/sessions")).json()[
        "session_id"
    ]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/ask/sessions/{sid}/messages",
        json={"content": "How many orders are there?"},
    )
    assert res.status_code == 422
