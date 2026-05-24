"""server-side cite-token render projection.

Coverage:

* Comment ``body_md_resolved`` rewrites ``#dp:cat.sch`` to an
  internal anchor when the DP exists in the same workspace.
* Unresolvable tokens degrade gracefully — the literal substring
  stays in ``body_md_resolved`` (per ``citations.py`` docstring).
* Review ``body_md_resolved`` carries the same projection.
* Endorsement ``note_md_resolved`` carries the same projection.
* ``body_md`` (raw) is never mutated alongside the projection.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_products import DataProduct

_CONTRACT_YAML = """\
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
    """Seed ``main.sales_gold`` from a yaml on disk."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


@pytest.mark.asyncio
async def test_comment_body_md_resolved_substitutes_dp_token(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``#dp:main.sales_gold`` renders as an internal anchor."""
    _seed_product(tmp_path)
    post = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "see #dp:main.sales_gold for context"},
    )
    assert post.status_code == 200, post.text
    payload = post.json()
    assert "body_md_resolved" in payload
    assert "[#main.sales_gold](/data-products/main/sales_gold)" in (
        payload["body_md_resolved"]
    )
    # Raw body stays intact for client-side fallback rendering.
    assert payload["body_md"] == "see #dp:main.sales_gold for context"


@pytest.mark.asyncio
async def test_comment_unresolvable_token_stays_literal(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A token pointing at a non-existent DP degrades to literal text."""
    _seed_product(tmp_path)
    post = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "see #dp:ghost.missing for the bug"},
    )
    assert post.status_code == 200, post.text
    payload = post.json()
    # The ghost token must NOT be rewritten — the literal text
    # survives both fields.
    assert "#dp:ghost.missing" in payload["body_md_resolved"]
    assert "/data-products/ghost/missing" not in payload["body_md_resolved"]
    # Also negative-assert: no anchor markup ever appears.
    assert "[#ghost.missing]" not in payload["body_md_resolved"]


@pytest.mark.asyncio
async def test_comment_list_carries_resolved_for_every_row(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The list endpoint also surfaces ``body_md_resolved``."""
    _seed_product(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "row a — #dp:main.sales_gold"},
    )
    res = await admin_client.get(
        "/api/data-products/main/sales_gold/comments",
    )
    assert res.status_code == 200, res.text
    rows = res.json()["comments"]
    assert rows, "expected at least one row"
    for row in rows:
        assert "body_md_resolved" in row


@pytest.mark.asyncio
async def test_review_body_md_resolved(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Reviews carry the same ``body_md_resolved`` projection."""
    _seed_product(tmp_path)
    put = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "great DP — #dp:main.sales_gold"},
    )
    assert put.status_code == 200, put.text
    payload = put.json()
    assert "body_md_resolved" in payload
    assert "[#main.sales_gold](/data-products/main/sales_gold)" in (
        payload["body_md_resolved"]
    )


@pytest.mark.asyncio
async def test_endorsement_note_md_resolved(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Endorsements carry ``note_md_resolved`` for the same token kinds."""
    _seed_product(tmp_path)
    post = await admin_client.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={
            "endorsement_type": "verified-by-steward",
            "note_md": "ref #dp:main.sales_gold",
        },
    )
    assert post.status_code == 200, post.text
    payload = post.json()
    assert "note_md_resolved" in payload
    assert "[#main.sales_gold](/data-products/main/sales_gold)" in (
        payload["note_md_resolved"]
    )
