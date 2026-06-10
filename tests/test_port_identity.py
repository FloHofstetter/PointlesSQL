"""Per-output-port identity assertion (E10)."""

from __future__ import annotations

import json

import pytest

from pointlessql.services.governance._port_identity import (
    PortIdentityViolation,
    assert_port_identity,
    parse_requirements,
)


def test_no_requirements_allows_anything() -> None:
    assert_port_identity(requirements_json=None, principal=None)
    assert_port_identity(requirements_json="", principal=None)
    assert_port_identity(requirements_json="not json", principal=None)


def test_anonymous_principal_blocked_when_requirements_present() -> None:
    req = json.dumps({"min_role": "consumer"})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(requirements_json=req, principal=None)
    assert exc.value.constraint == "authentication_required"


def test_oidc_audience_match_allows() -> None:
    req = json.dumps({"oidc_audiences": ["payments-api", "auth-api"]})
    assert_port_identity(
        requirements_json=req,
        principal={"oidc_aud": "payments-api", "role": "consumer"},
    )


def test_oidc_audience_mismatch_raises() -> None:
    req = json.dumps({"oidc_audiences": ["payments-api"]})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"oidc_aud": "billing-api"},
        )
    assert exc.value.constraint == "oidc_audiences"


def test_required_scopes_subset_allows() -> None:
    req = json.dumps({"required_scopes": ["read:data"]})
    assert_port_identity(
        requirements_json=req,
        principal={"scopes": ["read:data", "write:data"]},
    )


def test_missing_scope_raises() -> None:
    req = json.dumps({"required_scopes": ["read:data", "write:data"]})
    with pytest.raises(PortIdentityViolation):
        assert_port_identity(
            requirements_json=req,
            principal={"scopes": ["read:data"]},
        )


def test_min_role_allows_higher_rank() -> None:
    req = json.dumps({"min_role": "consumer"})
    assert_port_identity(
        requirements_json=req,
        principal={"role": "steward"},
    )


def test_min_role_blocks_lower_rank() -> None:
    req = json.dumps({"min_role": "steward"})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"role": "consumer"},
        )
    assert exc.value.constraint == "min_role"


def test_admin_flag_overrides_role_rank() -> None:
    req = json.dumps({"min_role": "admin"})
    assert_port_identity(
        requirements_json=req,
        principal={"role": "consumer", "is_admin": True},
    )


def test_parse_requirements_decodes_aud_list() -> None:
    parsed = parse_requirements(
        json.dumps(
            {
                "oidc_audiences": ["a", "b"],
                "required_scopes": ["read"],
                "min_role": "consumer",
            }
        )
    )
    assert parsed is not None
    assert parsed.oidc_audiences == ("a", "b")
    assert parsed.required_scopes == ("read",)
    assert parsed.min_role == "consumer"
