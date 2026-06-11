"""Tests for row filters + column masks (extraction, rendering, execution)."""

from __future__ import annotations

import pandas as pd
import pytest

from pointlessql.pql import PQL
from pointlessql.pql._policies import (
    MASK_PROPERTY_PREFIX,
    ROW_FILTER_PROPERTY,
    TablePolicy,
    coerce_policy,
    extract_table_policy,
    policy_view_sql,
    render_mask,
    validate_row_filter,
)

# ---------------------------------------------------------------------------
# extraction + rendering
# ---------------------------------------------------------------------------


def test_extract_policy_from_properties() -> None:
    info = {
        "properties": {
            ROW_FILTER_PROPERTY: "region = 'emea' OR owner = current_user()",
            f"{MASK_PROPERTY_PREFIX}email": "redact",
            f"{MASK_PROPERTY_PREFIX}salary": "null",
            "delta.appendOnly": "true",
        }
    }
    policy = extract_table_policy(info, principal="flo@test.com")
    assert policy is not None
    assert policy.row_filter == "region = 'emea' OR owner = 'flo@test.com'"
    assert policy.column_masks["email"] == "'***'"
    assert policy.column_masks["salary"] == "NULL"
    assert "delta.appendOnly" not in policy.column_masks


def test_extract_policy_none_without_properties() -> None:
    assert extract_table_policy({"properties": {}}, principal="x@y.de") is None
    assert extract_table_policy({}, principal=None) is None


def test_extract_policy_rejects_malformed_filter() -> None:
    info = {"properties": {ROW_FILTER_PROPERTY: "region = ; DROP"}}
    with pytest.raises(ValueError, match="single predicate"):
        extract_table_policy(info, principal="x@y.de")


def test_render_mask_template_and_validation() -> None:
    assert render_mask("concat(left({col}, 2), '***')", "email") == (
        "concat(left(\"email\", 2), '***')"
    )
    assert "sha256" in render_mask("hash", "ssn")
    with pytest.raises(ValueError, match="does not parse"):
        render_mask("CASE WHEN", "broken")
    with pytest.raises(ValueError, match="single expression"):
        render_mask("1; DROP TABLE x", "evil")


def test_validate_row_filter_substitutes_current_user_for_probe() -> None:
    assert validate_row_filter("owner = current_user()") == "owner = current_user()"
    with pytest.raises(ValueError, match="does not parse"):
        validate_row_filter("region = = 'x'")


def test_coerce_policy_roundtrip() -> None:
    policy = TablePolicy(row_filter="a = 1", column_masks={"b": "'***'"})
    assert coerce_policy(policy) is policy
    rebuilt = coerce_policy({"row_filter": "a = 1", "column_masks": {"b": "'***'"}})
    assert rebuilt == policy
    assert coerce_policy(None) is None


def test_policy_view_sql_shapes() -> None:
    policy = TablePolicy(row_filter="region = 'emea'", column_masks={"email": "'***'"})
    sql = policy_view_sql(
        view_name="c.s.t",
        base_relation="__pql_base_c_s_t",
        columns=["region", "email"],
        policy=policy,
    )
    assert sql.startswith('CREATE OR REPLACE TEMPORARY VIEW "c.s.t" AS ')
    assert "'***' AS \"email\"" in sql
    assert '"region"' in sql
    assert sql.endswith("WHERE region = 'emea'")


# ---------------------------------------------------------------------------
# end to end — a real Delta table through PQL.sql with a policy
# ---------------------------------------------------------------------------


def test_policy_enforced_end_to_end(tmp_path) -> None:
    import deltalake

    frame = pd.DataFrame(
        {
            "region": ["emea", "emea", "apac"],
            "email": ["a@x.de", "b@x.de", "c@x.de"],
            "amount": [10, 20, 40],
        }
    )
    path = str(tmp_path / "orders")
    deltalake.write_deltalake(path, frame)
    fqn = "shop.gold.orders"
    policy = TablePolicy(
        row_filter="region = 'emea'",
        column_masks={"email": "'***'"},
    )

    governed = PQL.sql(
        f"SELECT region, email, amount FROM {fqn} ORDER BY amount",
        approved_tables={fqn: path},
        table_policies={fqn: policy},
    )
    assert governed.row_count == 2
    assert all(row[1] == "***" for row in governed.rows)
    assert {row[0] for row in governed.rows} == {"emea"}

    # the same query without a policy sees everything — exemption is
    # simply "no policy passed" (admins / owners).
    raw = PQL.sql(
        f"SELECT region, email, amount FROM {fqn} ORDER BY amount",
        approved_tables={fqn: path},
    )
    assert raw.row_count == 3
    assert raw.rows[0][1] == "a@x.de"

    # dict-form policies (the kernel transfer shape) behave identically,
    # and aggregates cannot leak masked/filtered values.
    total = PQL.sql(
        f"SELECT sum(amount) FROM {fqn}",
        approved_tables={fqn: path},
        table_policies={fqn: {"row_filter": "region = 'emea'", "column_masks": {}}},
    )
    assert total.rows[0][0] == 30
