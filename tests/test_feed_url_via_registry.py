"""Phase 77.0.I — feed URL builder via entity registry.

Coverage:

* ``/api/feed`` rows for comments and reviews carry
  ``entity_kind: 'dp'`` + ``entity_ref: 'cat.sch'`` + an
  ``/data-products/cat/sch`` ``source_url`` built via the
  entity registry.  The pre-77.0 hard-coded
  ``/data-products/#<id>`` fragment-anchor is replaced.
* Notification rows expose ``source_entity_kind`` /
  ``source_entity_ref`` on the row payload so the frontend can
  route the click-through via the registry once 77.1+ ships
  non-DP follow surfaces.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import (
    DataProductComment,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification

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


def _seed_dp(tmp_path: Path) -> int:
    """Seed ``main.sales_gold`` and return its id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


@pytest.fixture
def clean_inbox() -> Iterator[None]:
    """Wipe ``user_notifications`` before + after each test."""
    factory = app.state.session_factory
    with factory() as session:
        session.execute(delete(UserNotification))
        session.commit()
    yield
    with factory() as session:
        session.execute(delete(UserNotification))
        session.commit()


@pytest.mark.asyncio
async def test_feed_comment_row_carries_entity_kind_and_registry_url(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    clean_inbox: None,
) -> None:
    """Followed-users overlay rows expose kind + ref + registry URL."""
    del clean_inbox
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        admin_id = int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )
        from pointlessql.services.social import get_or_create_target

        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        session.add(
            DataProductComment(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=int(anchor.id),
                author_user_id=admin_id,
                body_md="phase77i feed test",
                mentioned_user_ids_json="[]",
                category="general",
                is_accepted_answer=False,
                created_at=now,
            )
        )
        session.commit()
    # The admin follows their own author id (synthetic — the
    # filter='my' branch produces the same rows regardless).
    res = await admin_client.get("/api/feed?filter=my")
    assert res.status_code == 200, res.text
    rows = res.json()["rows"]
    comment_rows = [r for r in rows if r.get("kind") == "comment"]
    assert comment_rows, "no comment row in feed"
    row = comment_rows[0]
    assert row["entity_kind"] == "dp"
    assert row["entity_ref"] == "main.sales_gold"
    # Pre-77.0.I shape was ``/data-products/#<id>`` — gone now.
    assert row["source_url"] == "/data-products/main/sales_gold"


@pytest.mark.asyncio
async def test_feed_notification_row_carries_polymorphic_source_markers(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    clean_inbox: None,
) -> None:
    """Inbox rows surface the polymorphic source_entity_* columns."""
    del clean_inbox, tmp_path
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        admin_id = int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )
        session.add(
            UserNotification(
                workspace_id=1,
                recipient_user_id=admin_id,
                event_type="phase77i.synth.event",
                source_entity_kind="table",
                source_entity_ref="main.sales_gold.orders",
                source_url=(
                    "/catalogs/main/schemas/sales_gold/tables/orders"
                ),
                summary_md="phase77i notification test",
                actor_user_id=None,
                created_at=now,
            )
        )
        session.commit()
    res = await admin_client.get("/api/feed?filter=all")
    assert res.status_code == 200, res.text
    rows = res.json()["rows"]
    matching = [r for r in rows if r.get("event_type") == "phase77i.synth.event"]
    assert matching, "no notification row in feed"
    row = matching[0]
    assert row["entity_kind"] == "table"
    assert row["entity_ref"] == "main.sales_gold.orders"
    assert row["source_url"] == (
        "/catalogs/main/schemas/sales_gold/tables/orders"
    )
