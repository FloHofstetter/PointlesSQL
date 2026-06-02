"""Unit tests for the social-target anchor resolver.

``get_or_create_target`` is the idempotent anchor-row helper behind every
social surface. The tests cover its kind/parity validation (unknown kind,
the ``dp`` ↔ ``data_product_id`` parity rules) and the get-or-create
idempotency, using the seeded test workspace and unique refs per test.
"""

from __future__ import annotations

import pytest

from pointlessql.api.main import app
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social._target_resolver import (
    get_or_create_target,
    resolve_dp_target,
)


def test_unknown_kind_raises() -> None:
    with app.state.session_factory() as session:
        with pytest.raises(ValueError, match="unknown entity_kind"):
            get_or_create_target(session, workspace_id=1, kind="nope", ref="r1")


def test_dp_kind_requires_data_product_id() -> None:
    with app.state.session_factory() as session:
        with pytest.raises(ValueError, match="requires a data_product_id"):
            get_or_create_target(session, workspace_id=1, kind="dp", ref="r2")


def test_non_dp_kind_rejects_data_product_id() -> None:
    with app.state.session_factory() as session:
        with pytest.raises(ValueError, match="must not carry a data_product_id"):
            get_or_create_target(
                session, workspace_id=1, kind="table", ref="r3", data_product_id=5
            )


def test_creates_new_anchor() -> None:
    with app.state.session_factory() as session:
        target = get_or_create_target(
            session, workspace_id=1, kind="table", ref="tgt-create-unique"
        )
        assert isinstance(target, SocialTarget)
        assert target.entity_kind == "table"
        assert target.entity_ref == "tgt-create-unique"
        assert target.data_product_id is None


def test_get_or_create_is_idempotent() -> None:
    with app.state.session_factory() as session:
        first = get_or_create_target(
            session, workspace_id=1, kind="table", ref="tgt-idem-unique"
        )
        session.flush()
        second = get_or_create_target(
            session, workspace_id=1, kind="table", ref="tgt-idem-unique"
        )
        assert first.id == second.id


def test_resolve_dp_target_missing_raises_lookup() -> None:
    with app.state.session_factory() as session:
        with pytest.raises(LookupError):
            resolve_dp_target(
                session,
                workspace_id=1,
                catalog_name="nonexistent_cat",
                schema_name="nonexistent_schema",
            )
