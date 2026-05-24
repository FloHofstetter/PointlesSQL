"""Tests for the follow-up B.1 — schema_changed emit on reload.

Covers the three legs:

* First reload (no prior cached row) → no emit (creation, not
  a change).
* Re-reload with byte-identical yaml → no emit (hash matches).
* Re-reload with edited yaml → exactly one
  ``EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED`` row in
  ``governance_events``.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED,
)

YAML_V1 = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: v1
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

YAML_V2 = """\
data_product:
  name: Sales Orders
  version: "1.1.0"
  description: v2 description
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
        - {name: customer_id, type: long, nullable: true}
"""


def _set_yaml_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Wire ``settings.data_products.yaml_search_paths`` to *tmp_path*.

    Uses ``monkeypatch.setattr`` so the patched attribute is restored
    after the test exits — otherwise subsequent tests in the same
    session see a stale ``yaml_search_paths`` and the
    ``test_reload_400_when_search_paths_empty`` assertion flips.

    Returns the seeded yaml path so callers can rewrite its contents
    between reloads.
    """
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(YAML_V1, encoding="utf-8")
    monkeypatch.setattr(
        app.state.settings.data_products,
        "yaml_search_paths",
        (yaml_path,),
    )
    return yaml_path


def _count_schema_changed_events() -> int:
    """Count persisted ``schema_changed`` envelopes in governance_events."""
    factory = app.state.session_factory
    with factory() as session:
        return len(
            session.execute(
                select(GovernanceEvent).where(
                    GovernanceEvent.event_type == EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_first_reload_no_emit(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First reload populates the cache but does NOT emit."""
    _set_yaml_paths(monkeypatch, tmp_path)
    res = await admin_client.post("/api/data-products/reload")
    assert res.status_code == 200
    assert _count_schema_changed_events() == 0


@pytest.mark.asyncio
async def test_idempotent_reload_no_emit(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-reloading byte-identical yaml does NOT emit."""
    _set_yaml_paths(monkeypatch, tmp_path)
    first = await admin_client.post("/api/data-products/reload")
    assert first.status_code == 200
    second = await admin_client.post("/api/data-products/reload")
    assert second.status_code == 200
    assert _count_schema_changed_events() == 0


@pytest.mark.asyncio
async def test_edited_yaml_emits_once(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing the yaml + re-reloading emits exactly one schema_changed event."""
    yaml_path = _set_yaml_paths(monkeypatch, tmp_path)
    first = await admin_client.post("/api/data-products/reload")
    assert first.status_code == 200
    # Edit the yaml: bump version + add a column.
    yaml_path.write_text(YAML_V2, encoding="utf-8")
    second = await admin_client.post("/api/data-products/reload")
    assert second.status_code == 200
    assert _count_schema_changed_events() == 1

    factory = app.state.session_factory
    with factory() as session:
        envelope = (
            session.execute(
                select(GovernanceEvent).where(
                    GovernanceEvent.event_type == EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED
                )
            )
            .scalars()
            .one()
        )
    payload = json.loads(envelope.payload_json)["data"]
    assert payload["data_product_ref"] == "main.sales_gold"
    assert payload["previous_hash"] != payload["new_hash"]
