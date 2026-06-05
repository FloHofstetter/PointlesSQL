"""Mutation-killing tests for the per-output-port identity assertion.

Pins two observable behaviours of
:mod:`pointlessql.services.governance._port_identity` that the
existing governance suite left unchecked:

* a non-string, non-collection ``oidc_aud`` claim degrades to an empty
  observed-audience set (constraint fails cleanly, no ``TypeError``);
* the raised :class:`PortIdentityViolation` carries a human-readable
  ``detail`` that names the failing constraint — the string the
  central error map renders into the HTTP 403 body.
"""

from __future__ import annotations

import json

import pytest

from pointlessql.services.governance._port_identity import (
    PortIdentityViolation,
    assert_port_identity,
)


def test_port_identity_non_collection_aud_is_empty_set_not_none() -> None:
    """A scalar non-string ``oidc_aud`` yields an empty observed set.

    The fall-through branch must produce a real (empty) set so the
    intersection check runs and the constraint fails with an empty
    observed list — not ``None``, which would raise ``TypeError`` on the
    ``& set(...)`` intersection.
    """
    req = json.dumps({"oidc_audiences": ["payments-api"]})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"oidc_aud": 12345},
        )
    assert exc.value.constraint == "oidc_audiences"
    assert exc.value.observed == []


def test_port_identity_violation_detail_names_constraint() -> None:
    """The violation's ``detail`` carries the failing-constraint message.

    The central error handler renders ``detail`` into the 403 body, so
    the constructed message must embed the constraint name verbatim and
    not collapse to a null detail.
    """
    req = json.dumps({"min_role": "steward"})
    with pytest.raises(PortIdentityViolation) as exc:
        assert_port_identity(
            requirements_json=req,
            principal={"role": "consumer"},
        )
    assert exc.value.detail == "port identity constraint failed: min_role"
    assert str(exc.value) == "port identity constraint failed: min_role"


def test_port_identity_violation_detail_for_direct_construction() -> None:
    """Direct construction wires the constraint into ``detail``/``str``.

    Pins the constructor's message independently of any single call
    site, so the detail string stays bound to the constraint name.
    """
    exc = PortIdentityViolation("required_scopes", ["write:data"])
    assert exc.detail == "port identity constraint failed: required_scopes"
    assert str(exc) == "port identity constraint failed: required_scopes"
    assert exc.constraint == "required_scopes"
    assert exc.observed == ["write:data"]
