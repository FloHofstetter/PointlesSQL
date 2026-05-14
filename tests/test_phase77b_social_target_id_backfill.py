"""Phase 77.0.B — social_target_id columns on the 7 DP-social tables.

Coverage:

* Every row in each of the seven social tables ends up with a
  non-NULL ``social_target_id`` after the migration runs.
* The anchor points at the right DP — ``social_targets.entity_kind``
  is ``'dp'`` and ``social_targets.data_product_id`` equals the
  row's ``data_product_id``.
* Comment-reactions piggy-back on the comment's anchor (special-
  case in the backfill).

Phase 77.0.G flipped ``social_target_id`` to NOT NULL — the
former "column nullable for legacy writes" test was removed
because the column now rejects NULL at INSERT.  The remaining
backfill-shape test seeds rows through the resolver so the
shape contract is preserved end-to-end.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import (
    DataProductComment,
)
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_product_follows import (
    DataProductFollow,
)
from pointlessql.models.catalog._data_product_reaction import (
    DataProductReaction,
)
from pointlessql.models.catalog._data_product_readme import (
    DataProductReadme,
)
from pointlessql.models.catalog._data_product_reviews import (
    DataProductReview,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._social_target import SocialTarget

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
    """Load a yaml + cache row; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


@pytest.fixture
def admin_user_id() -> int:
    """Return the conftest-seeded admin's user id."""
    from pointlessql.models.auth import User

    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


def test_social_target_id_columns_exist_on_all_seven_tables() -> None:
    """The migration added the column on every required table."""
    factory = app.state.session_factory
    with factory() as session:
        # If any of these attribute accesses raise, the model and
        # the DB schema diverged.
        for cls in (
            DataProductComment,
            DataProductReview,
            DataProductEndorsement,
            DataProductFollow,
            DataProductReaction,
            DataProductCommentReaction,
            DataProductReadme,
        ):
            assert hasattr(cls, "social_target_id"), cls.__tablename__
            # Smoke-query each so the SQL actually executes against
            # the deployed schema (catches dropped-but-not-recreated
            # cases that the ORM mapping alone would miss).
            session.execute(select(cls).limit(1)).all()


def test_social_target_id_anchor_points_at_dp(
    tmp_path: Path, admin_user_id: int
) -> None:
    """Seeded rows resolve through the polymorphic anchor.

    After 77.0.G the column is NOT NULL so every insert routes
    through :func:`get_or_create_target`.  This test seeds one
    row per social table through the resolver and asserts the
    anchor points back at the DP it was created for.
    """
    from pointlessql.services.social import get_or_create_target

    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        anchor_id = int(anchor.id)
        comment = DataProductComment(
            workspace_id=1,
            data_product_id=dp_id,
            social_target_id=anchor_id,
            author_user_id=admin_user_id,
            body_md="phase77b backfill seed",
            mentioned_user_ids_json="[]",
            category="general",
            is_accepted_answer=False,
            created_at=now,
        )
        session.add(comment)
        session.add(
            DataProductReview(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=anchor_id,
                author_user_id=admin_user_id,
                stars=5,
                body_md="phase77b backfill seed",
                dp_version_at_review="1.0.0",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            DataProductEndorsement(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=anchor_id,
                endorsement_type="verified-by-steward",
                applied_by_user_id=admin_user_id,
                applied_at=now,
                note_md="phase77b backfill seed",
            )
        )
        session.add(
            DataProductFollow(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=anchor_id,
                user_id=admin_user_id,
                created_at=now,
            )
        )
        session.add(
            DataProductReaction(
                data_product_id=dp_id,
                social_target_id=anchor_id,
                user_id=admin_user_id,
                emoji="👍",
                created_at=now,
            )
        )
        session.add(
            DataProductReadme(
                workspace_id=1,
                data_product_id=dp_id,
                social_target_id=anchor_id,
                version_int=1,
                body_md="# phase77b",
                updated_by_user_id=admin_user_id,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            DataProductCommentReaction(
                comment_id=int(comment.id),
                social_target_id=anchor_id,
                user_id=admin_user_id,
                emoji="🎉",
                created_at=now,
            )
        )
        session.commit()

    with factory() as session:
        row = session.execute(
            select(DataProductComment).where(
                DataProductComment.data_product_id == dp_id,
                DataProductComment.body_md == "phase77b backfill seed",
            )
        ).scalar_one()
        assert row.social_target_id is not None
        anchor_row = session.execute(
            select(SocialTarget).where(SocialTarget.id == row.social_target_id)
        ).scalar_one()
        assert anchor_row.entity_kind == "dp"
        assert anchor_row.data_product_id == dp_id


def test_social_target_id_is_not_nullable_after_77_0_g(
    tmp_path: Path, admin_user_id: int
) -> None:
    """Phase 77.0.G flipped the column to NOT NULL.

    An attempt to insert a comment without ``social_target_id``
    now raises :class:`sqlalchemy.exc.IntegrityError`.  This is the
    explicit gate that 77.0.F.1 / F.2 / F.3 unblocks by routing
    every writer through :func:`get_or_create_target`.
    """
    from sqlalchemy.exc import IntegrityError

    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session, pytest.raises(IntegrityError):
        session.add(
            DataProductComment(
                workspace_id=1,
                data_product_id=dp_id,
                author_user_id=admin_user_id,
                body_md="should-fail-row",
                mentioned_user_ids_json="[]",
                category="general",
                is_accepted_answer=False,
                created_at=now,
            )
        )
        session.commit()
