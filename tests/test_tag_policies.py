"""Tag-driven policies: CRUD validation, merge semantics, enforcement."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, User
from pointlessql.pql import PQL
from pointlessql.pql._policies import TablePolicy
from pointlessql.services import tag_policies

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


@pytest.fixture
def factory() -> Any:
    """In-memory factory with one admin user; caches reset around it."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="admin@test.com",
                display_name="Admin",
                password_hash="x",
                is_admin=True,
                created_at=_NOW,
            )
        )
        session.commit()
    tag_policies.invalidate_caches()
    yield factory
    tag_policies.invalidate_caches()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _uc_with_tags(
    table_tags: list[dict[str, str]] | None = None,
    column_tags: dict[str, list[dict[str, str]]] | None = None,
) -> MagicMock:
    """UC stub serving get_tags for table + column securables."""
    client = MagicMock()

    async def get_tags(securable_type: str, full_name: str) -> list[dict[str, str]]:
        if securable_type == "table":
            return table_tags or []
        column = full_name.rsplit(".", 1)[-1]
        return (column_tags or {}).get(column, [])

    client.get_tags = AsyncMock(side_effect=get_tags)
    return client


_INFO = {"columns": [{"name": "email"}, {"name": "amount"}]}


# ---------------------------------------------------------------------------
# CRUD validation
# ---------------------------------------------------------------------------


def test_create_validates_effect_and_predicate(factory: Any) -> None:
    with pytest.raises(ValidationError, match="effect"):
        tag_policies.create_rule(
            factory,
            tag_key="pii",
            tag_value=None,
            effect="nope",
            expr="redact",
            created_by_user_id=1,
        )
    with pytest.raises(ValidationError, match="row-filter"):
        tag_policies.create_rule(
            factory,
            tag_key="region",
            tag_value=None,
            effect="row_filter",
            expr="not valid (((",
            created_by_user_id=1,
        )
    rule = tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    assert rule.is_active is True


def test_update_toggles_and_delete_removes(factory: Any) -> None:
    rule = tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    updated = tag_policies.update_rule(factory, rule.id, is_active=False)
    assert updated.is_active is False
    assert tag_policies.delete_rule(factory, rule.id) is True
    assert tag_policies.delete_rule(factory, rule.id) is False


# ---------------------------------------------------------------------------
# merge semantics
# ---------------------------------------------------------------------------


async def test_no_rules_short_circuits_without_tag_fetch(factory: Any) -> None:
    client = _uc_with_tags()
    base = TablePolicy(row_filter="amount > 0", column_masks={})
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=base, principal="u@x", factory=factory
    )
    assert merged is base
    client.get_tags.assert_not_awaited()


async def test_mask_rule_masks_tagged_column(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    client = _uc_with_tags(column_tags={"email": [{"key": "pii", "value": "email"}]})
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=None, principal="u@x", factory=factory
    )
    assert merged is not None
    assert "email" in merged.column_masks
    assert "amount" not in merged.column_masks
    assert merged.row_filter is None


async def test_explicit_property_mask_beats_tag_rule(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    client = _uc_with_tags(column_tags={"email": [{"key": "pii", "value": "email"}]})
    base = TablePolicy(row_filter=None, column_masks={"email": "'explicit'"})
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=base, principal="u@x", factory=factory
    )
    assert merged is not None
    assert merged.column_masks["email"] == "'explicit'"


async def test_row_filter_rule_ands_into_base(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="restricted",
        tag_value="eu",
        effect="row_filter",
        expr="region = 'eu' OR owner = current_user()",
        created_by_user_id=1,
    )
    client = _uc_with_tags(table_tags=[{"key": "restricted", "value": "eu"}])
    base = TablePolicy(row_filter="amount > 0", column_masks={})
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=base, principal="u@x", factory=factory
    )
    assert merged is not None
    assert merged.row_filter is not None
    assert "(amount > 0)" in merged.row_filter
    assert "'u@x'" in merged.row_filter  # current_user() substituted


async def test_value_scoped_rule_requires_value_match(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="restricted",
        tag_value="eu",
        effect="row_filter",
        expr="1 = 0",
        created_by_user_id=1,
    )
    client = _uc_with_tags(table_tags=[{"key": "restricted", "value": "us"}])
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=None, principal="u@x", factory=factory
    )
    assert merged is None


async def test_inactive_rule_is_ignored(factory: Any) -> None:
    rule = tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    tag_policies.update_rule(factory, rule.id, is_active=False)
    client = _uc_with_tags(column_tags={"email": [{"key": "pii", "value": "email"}]})
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=None, principal="u@x", factory=factory
    )
    assert merged is None


async def test_priority_picks_lowest_number(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="hash",
        priority=200,
        created_by_user_id=1,
    )
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        priority=10,
        created_by_user_id=1,
    )
    client = _uc_with_tags(column_tags={"email": [{"key": "pii", "value": "x"}]})
    merged = await tag_policies.apply_tag_policies(
        client, full_name="c.s.t", info=_INFO, base=None, principal="u@x", factory=factory
    )
    assert merged is not None
    assert merged.column_masks["email"] == "'***'"  # redact rendering


# ---------------------------------------------------------------------------
# end-to-end: merged policy actually governs run_sql
# ---------------------------------------------------------------------------


async def test_merged_policy_masks_rows_in_duckdb(factory: Any, tmp_path: Path) -> None:
    loc = str(tmp_path / "people")
    deltalake.write_deltalake(
        loc, pd.DataFrame({"email": ["a@x.com", "b@y.com"], "amount": [1, 2]})
    )
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    client = _uc_with_tags(column_tags={"email": [{"key": "pii", "value": "email"}]})
    merged = await tag_policies.apply_tag_policies(
        client,
        full_name="main.demo.people",
        info={"columns": [{"name": "email"}, {"name": "amount"}]},
        base=None,
        principal="u@x",
        factory=factory,
    )
    result = PQL.sql(
        "SELECT email, amount FROM main.demo.people ORDER BY amount",
        approved_tables={"main.demo.people": loc},
        table_policies={"main.demo.people": merged},
    )
    assert result.rows == [["***", 1], ["***", 2]]
