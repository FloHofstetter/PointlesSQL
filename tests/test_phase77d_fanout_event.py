"""Phase 77.0.D — polymorphic ``fanout_event`` dispatcher.

Coverage:

* ``fanout_event(kind='dp', ref='cat.sch', ...)`` writes a
  ``user_notifications`` row that carries:
  - ``source_entity_kind = 'dp'``
  - ``source_entity_ref = 'cat.sch'``
  - ``source_data_product_id`` populated as before for back-compat
* ``fanout_event(kind='table', ...)`` carries kind+ref but no
  ``source_data_product_id`` and resolves zero followers (no
  follower table for tables in 77.0); ``extra_recipients`` is
  the only path for non-DP events until 77.1+ ships per-kind
  follow tables.
* Legacy ``fanout_dataproduct_event(data_product_id=..., ...)``
  wrapper resolves the DP FQN and dispatches via fanout_event
  with the same per-row outcome as before — zero behaviour
  drift for the existing call sites.
* Actor is removed from the recipient set.
* Per-user inbox opt-out via
  ``users.notification_prefs_json`` is honoured for the new path.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_follows import (
    DataProductFollow,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.services.notifications import (
    fanout_dataproduct_event,
    fanout_event,
)

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
    """Return the seeded DP id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


@pytest.fixture
def admin_user_id() -> int:
    """conftest-seeded admin id."""
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


@pytest.fixture
def nonadmin_user_id() -> int:
    """conftest-seeded non-admin id."""
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "nonadmin@test.com")
            ).scalar_one()
        )


@pytest.fixture
def clean_notifications() -> Iterator[None]:
    """Wipe ``user_notifications`` before + after each test.

    The conftest seeds the DB once per session; tests in this
    module assert on the *exact* rows the call produced, so we
    need a clean slate.
    """
    factory = app.state.session_factory
    with factory() as session:
        session.execute(delete(UserNotification))
        session.commit()
    yield
    with factory() as session:
        session.execute(delete(UserNotification))
        session.commit()


def test_fanout_event_dp_stamps_polymorphic_marker(
    tmp_path: Path,
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_notifications: None,
) -> None:
    """kind='dp' fan-out writes both legacy + polymorphic columns."""
    del clean_notifications
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    # Non-admin follows the DP so they're a real recipient.
    with factory() as session:
        from datetime import UTC, datetime

        from pointlessql.services.social import get_or_create_target
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        session.add(
            DataProductFollow(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=int(anchor.id),
                user_id=nonadmin_user_id,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    fanout_event(
        factory,
        event_type="phase77d.test.dp_marker",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=admin_user_id,
        source_url="/data-products/main/sales_gold#tab-discussion",
        summary_md="phase77d marker test",
        data_product_id=dp_id,
    )
    with factory() as session:
        rows = (
            session.execute(
                select(UserNotification).where(
                    UserNotification.event_type == "phase77d.test.dp_marker",
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.recipient_user_id == nonadmin_user_id
        assert row.source_entity_kind == "dp"
        assert row.source_entity_ref == "main.sales_gold"
        # Legacy column populated for backward compat.
        assert row.source_data_product_id == dp_id


def test_fanout_event_table_stamps_polymorphic_only_no_dp_id(
    tmp_path: Path,
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_notifications: None,
) -> None:
    """kind='table' fan-out leaves source_data_product_id NULL.

    Non-DP kinds have no follower table in 77.0, so the only
    way to reach a recipient is via ``extra_recipients``.  Use
    that path here to verify the polymorphic columns are
    populated and the legacy column is left NULL.
    """
    del clean_notifications
    del tmp_path
    factory = app.state.session_factory
    fanout_event(
        factory,
        event_type="phase77d.test.table_marker",
        entity_kind="table",
        entity_ref="main.sales_gold.orders",
        workspace_id=1,
        actor_user_id=admin_user_id,
        source_url="/catalogs/main/schemas/sales_gold/tables/orders",
        summary_md="phase77d table marker",
        extra_recipients=[nonadmin_user_id],
    )
    with factory() as session:
        row = session.execute(
            select(UserNotification).where(
                UserNotification.event_type == "phase77d.test.table_marker",
            )
        ).scalar_one()
        assert row.source_entity_kind == "table"
        assert row.source_entity_ref == "main.sales_gold.orders"
        # Legacy column NOT populated for non-DP kinds.
        assert row.source_data_product_id is None


def test_legacy_fanout_dataproduct_event_wrapper_dispatches_correctly(
    tmp_path: Path,
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_notifications: None,
) -> None:
    """Legacy wrapper produces the same per-row outcome as before."""
    del clean_notifications
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        from datetime import UTC, datetime

        from pointlessql.services.social import get_or_create_target
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        session.add(
            DataProductFollow(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=int(anchor.id),
                user_id=nonadmin_user_id,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    fanout_dataproduct_event(
        factory,
        event_type="phase77d.test.legacy_wrapper",
        data_product_id=dp_id,
        workspace_id=1,
        actor_user_id=admin_user_id,
        source_url="/data-products/main/sales_gold",
        summary_md="legacy wrapper test",
    )
    with factory() as session:
        row = session.execute(
            select(UserNotification).where(
                UserNotification.event_type == "phase77d.test.legacy_wrapper",
            )
        ).scalar_one()
        # The wrapper now stamps both columns.
        assert row.source_entity_kind == "dp"
        assert row.source_entity_ref == "main.sales_gold"
        assert row.source_data_product_id == dp_id


def test_fanout_event_skips_actor(
    tmp_path: Path,
    admin_user_id: int,
    clean_notifications: None,
) -> None:
    """The actor is never in their own inbox."""
    del clean_notifications
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        from datetime import UTC, datetime

        from pointlessql.services.social import get_or_create_target

        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        session.add(
            DataProductFollow(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=int(anchor.id),
                user_id=admin_user_id,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    count = fanout_event(
        factory,
        event_type="phase77d.test.actor_skip",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=admin_user_id,
        source_url="/data-products/main/sales_gold",
        summary_md="actor skip",
        data_product_id=dp_id,
    )
    assert count == 0
    with factory() as session:
        rows = (
            session.execute(
                select(UserNotification).where(
                    UserNotification.event_type == "phase77d.test.actor_skip",
                )
            )
            .scalars()
            .all()
        )
        assert rows == []


def test_fanout_event_honours_per_user_inbox_opt_out(
    tmp_path: Path,
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_notifications: None,
) -> None:
    """A recipient with inbox=False for the event_type is filtered out."""
    del clean_notifications
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        from datetime import UTC, datetime

        # follower + opted-out pref
        from pointlessql.services.social import get_or_create_target
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        session.add(
            DataProductFollow(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=int(anchor.id),
                user_id=nonadmin_user_id,
                created_at=datetime.now(UTC),
            )
        )
        user = session.execute(
            select(User).where(User.id == nonadmin_user_id)
        ).scalar_one()
        user.notification_prefs_json = json.dumps(
            {"phase77d.test.opt_out": {"inbox": False}}
        )
        session.commit()
    fanout_event(
        factory,
        event_type="phase77d.test.opt_out",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=admin_user_id,
        source_url="/data-products/main/sales_gold",
        summary_md="opt-out test",
        data_product_id=dp_id,
    )
    with factory() as session:
        rows = (
            session.execute(
                select(UserNotification).where(
                    UserNotification.event_type == "phase77d.test.opt_out",
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
        # restore prefs so other tests stay clean
        user = session.execute(
            select(User).where(User.id == nonadmin_user_id)
        ).scalar_one()
        user.notification_prefs_json = "{}"
        session.commit()
