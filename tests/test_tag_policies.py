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


def test_create_validates_scope(factory: Any) -> None:
    with pytest.raises(ValidationError, match="scope_type"):
        tag_policies.create_rule(
            factory,
            tag_key="pii",
            tag_value=None,
            effect="mask",
            expr="redact",
            scope_type="nope",
            created_by_user_id=1,
        )
    with pytest.raises(ValidationError, match="scope_value is required"):
        tag_policies.create_rule(
            factory,
            tag_key="pii",
            tag_value=None,
            effect="mask",
            expr="redact",
            scope_type="catalog",
            created_by_user_id=1,
        )
    with pytest.raises(ValidationError, match="dotted part"):
        tag_policies.create_rule(
            factory,
            tag_key="pii",
            tag_value=None,
            effect="mask",
            expr="redact",
            scope_type="schema",
            scope_value="main",
            created_by_user_id=1,
        )
    # A global rule discards any stray scope_value.
    glob = tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        scope_type="global",
        scope_value="ignored",
        created_by_user_id=1,
    )
    assert glob.scope_type == "global"
    assert glob.scope_value is None
    # A catalog rule keeps its one-part name.
    cat = tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        scope_type="catalog",
        scope_value="main",
        created_by_user_id=1,
    )
    assert (cat.scope_type, cat.scope_value) == ("catalog", "main")


def test_in_scope_is_case_insensitive() -> None:
    # UC names are case-insensitive; a rule scoped with a different case
    # than the queried name must still match (no silent fail-open).
    assert tag_policies._in_scope("catalog", "Main", "main.sales.t") is True
    assert tag_policies._in_scope("schema", "Main.Sales", "MAIN.SALES.orders") is True
    # A genuinely different securable still does not match.
    assert tag_policies._in_scope("catalog", "Main", "other.sales.t") is False
    assert tag_policies._in_scope("schema", "main.sales", "main.ops.t") is False


async def test_catalog_scope_only_applies_in_subtree(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        scope_type="catalog",
        scope_value="main",
        created_by_user_id=1,
    )
    client = _uc_with_tags(column_tags={"email": [{"key": "pii", "value": "x"}]})
    inside = await tag_policies.apply_tag_policies(
        client,
        full_name="main.demo.people",
        info=_INFO,
        base=None,
        principal="u@x",
        factory=factory,
    )
    assert inside is not None
    assert "email" in inside.column_masks
    # A table in a different catalog is out of scope — and the rule is
    # dropped before any tag fetch.
    outside = await tag_policies.apply_tag_policies(
        client,
        full_name="other.demo.people",
        info=_INFO,
        base=None,
        principal="u@x",
        factory=factory,
    )
    assert outside is None


async def test_schema_scope_only_applies_in_subtree(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="restricted",
        tag_value=None,
        effect="row_filter",
        expr="1 = 1",
        scope_type="schema",
        scope_value="main.demo",
        created_by_user_id=1,
    )
    client = _uc_with_tags(table_tags=[{"key": "restricted", "value": "x"}])
    inside = await tag_policies.apply_tag_policies(
        client, full_name="main.demo.t", info=_INFO, base=None, principal="u@x", factory=factory
    )
    assert inside is not None
    assert inside.row_filter is not None
    outside = await tag_policies.apply_tag_policies(
        client, full_name="main.other.t", info=_INFO, base=None, principal="u@x", factory=factory
    )
    assert outside is None


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


# ---------------------------------------------------------------------------
# cross-engine scan-plan policy preview
# ---------------------------------------------------------------------------


def _uc_for_preview(
    info: dict[str, Any],
    *,
    table_tags: list[dict[str, str]] | None = None,
    column_tags: dict[str, list[dict[str, str]]] | None = None,
) -> MagicMock:
    """UC stub that also serves get_table for the preview path."""
    client = _uc_with_tags(table_tags=table_tags, column_tags=column_tags)
    client.get_table = AsyncMock(return_value=info)
    return client


async def test_preview_reports_masks_and_filter(factory: Any) -> None:
    tag_policies.create_rule(
        factory,
        tag_key="pii",
        tag_value=None,
        effect="mask",
        expr="redact",
        created_by_user_id=1,
    )
    info = {"columns": [{"name": "email"}, {"name": "amount"}], "properties": {}}
    client = _uc_for_preview(info, column_tags={"email": [{"key": "pii", "value": "x"}]})
    out = await tag_policies.preview_scan_policy(
        client, full_name="main.demo.people", principal="ext@x", factory=factory
    )
    assert out["has_policy"] is True
    assert out["masked_columns"] == ["email"]
    assert "email" in out["column_masks"]
    assert out["table"] == "main.demo.people"
    assert out["principal"] == "ext@x"


async def test_preview_includes_property_row_filter(factory: Any) -> None:
    info = {
        "columns": [{"name": "email"}],
        "properties": {"pointlessql.row_filter": "owner = current_user()"},
    }
    client = _uc_for_preview(info)
    out = await tag_policies.preview_scan_policy(
        client, full_name="main.demo.people", principal="ext@x", factory=factory
    )
    assert out["has_policy"] is True
    assert "'ext@x'" in out["row_filter"]


async def test_preview_empty_when_no_policy(factory: Any) -> None:
    info = {"columns": [{"name": "email"}], "properties": {}}
    client = _uc_for_preview(info)
    out = await tag_policies.preview_scan_policy(
        client, full_name="main.demo.people", principal="ext@x", factory=factory
    )
    assert out["has_policy"] is False
    assert out["row_filter"] is None
    assert out["masked_columns"] == []


async def test_preview_rejects_non_three_part(factory: Any) -> None:
    client = _uc_for_preview({"columns": [], "properties": {}})
    with pytest.raises(ValidationError, match="3-part"):
        await tag_policies.preview_scan_policy(
            client, full_name="main.demo", principal="x", factory=factory
        )
