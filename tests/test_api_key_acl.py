"""Tests for the Phase 120 ACL check helpers (pure functions)."""

from __future__ import annotations

import pytest

from pointlessql.services.api_keys._acl import (
    CatalogGrant,
    IpGrant,
    check_catalog_allowed,
    check_ip_allowed,
    validate_cidr,
)


# ---------------------------------------------------------------------------
# Catalog check
# ---------------------------------------------------------------------------


def test_catalog_zero_grants_is_unrestricted() -> None:
    result = check_catalog_allowed([], "SELECT * FROM main.sales.orders")
    assert result.allowed is True


def test_catalog_exact_grant_allows_matching_table() -> None:
    grants = [CatalogGrant("main", "sales")]
    assert check_catalog_allowed(grants, "SELECT * FROM main.sales.orders").allowed


def test_catalog_exact_grant_denies_other_schema() -> None:
    grants = [CatalogGrant("main", "sales")]
    result = check_catalog_allowed(grants, "SELECT * FROM main.payroll.salaries")
    assert result.allowed is False
    assert result.denied_catalog == "main"
    assert result.denied_schema == "payroll"


def test_catalog_wildcard_schema_allows_any_schema() -> None:
    grants = [CatalogGrant("main", None)]
    assert check_catalog_allowed(grants, "SELECT * FROM main.payroll.t").allowed
    assert check_catalog_allowed(grants, "SELECT * FROM main.sales.t").allowed


def test_catalog_grant_does_not_leak_across_catalogs() -> None:
    grants = [CatalogGrant("main", None)]
    result = check_catalog_allowed(grants, "SELECT * FROM other.sales.orders")
    assert result.allowed is False
    assert result.denied_catalog == "other"


def test_catalog_default_catalog_qualifies_two_part_ref() -> None:
    grants = [CatalogGrant("main", "sales")]
    result = check_catalog_allowed(
        grants, "SELECT * FROM sales.orders", default_catalog="main"
    )
    assert result.allowed is True


def test_catalog_default_catalog_and_schema_qualify_one_part_ref() -> None:
    grants = [CatalogGrant("main", "sales")]
    result = check_catalog_allowed(
        grants,
        "SELECT * FROM orders",
        default_catalog="main",
        default_schema="sales",
    )
    assert result.allowed is True


def test_catalog_multiple_tables_all_must_match() -> None:
    grants = [CatalogGrant("main", "sales")]
    sql = "SELECT * FROM main.sales.orders JOIN main.payroll.salaries USING (id)"
    result = check_catalog_allowed(grants, sql)
    assert result.allowed is False
    assert result.denied_schema == "payroll"


def test_catalog_unparseable_sql_is_treated_as_unrelated() -> None:
    """Garbage SQL → ACL check defers to downstream parse-error handling."""
    grants = [CatalogGrant("main", "sales")]
    assert check_catalog_allowed(grants, "SLECT FROM 12 INVALID").allowed


def test_catalog_table_without_catalog_passes_through_to_uc() -> None:
    """1-part ref with no default catalog → ACL not applicable; UC enforces."""
    grants = [CatalogGrant("main", "sales")]
    # SELECT with no catalog/schema and no defaults → can't be checked by ACL.
    assert check_catalog_allowed(grants, "SELECT 1 AS x").allowed


# ---------------------------------------------------------------------------
# IP check
# ---------------------------------------------------------------------------


def test_ip_zero_grants_is_unrestricted() -> None:
    assert check_ip_allowed([], "10.0.0.42") is True


def test_ip_inside_cidr_is_allowed() -> None:
    grants = [IpGrant("10.0.0.0/8")]
    assert check_ip_allowed(grants, "10.255.7.1") is True


def test_ip_outside_cidr_is_denied() -> None:
    grants = [IpGrant("10.0.0.0/8")]
    assert check_ip_allowed(grants, "192.168.1.1") is False


def test_ip_multiple_cidrs_any_match_allows() -> None:
    grants = [IpGrant("10.0.0.0/8"), IpGrant("192.168.0.0/16")]
    assert check_ip_allowed(grants, "192.168.5.5") is True


def test_ip_none_source_fails_closed_when_grants_present() -> None:
    grants = [IpGrant("10.0.0.0/8")]
    assert check_ip_allowed(grants, None) is False


def test_ip_unparseable_source_is_denied() -> None:
    grants = [IpGrant("10.0.0.0/8")]
    assert check_ip_allowed(grants, "not-an-ip") is False


def test_ip_ipv6_cidr_works() -> None:
    grants = [IpGrant("2001:db8::/32")]
    assert check_ip_allowed(grants, "2001:db8:1::1") is True
    assert check_ip_allowed(grants, "2001:db9::1") is False


# ---------------------------------------------------------------------------
# validate_cidr
# ---------------------------------------------------------------------------


def test_validate_cidr_accepts_canonical_form() -> None:
    assert validate_cidr("10.0.0.0/8") == "10.0.0.0/8"
    assert validate_cidr("2001:db8::/32") == "2001:db8::/32"


def test_validate_cidr_strips_host_bits() -> None:
    assert validate_cidr("10.5.7.3/8") == "10.0.0.0/8"


def test_validate_cidr_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid CIDR"):
        validate_cidr("not-a-cidr")
    with pytest.raises(ValueError, match="invalid CIDR"):
        validate_cidr("999.999.999.999/8")
