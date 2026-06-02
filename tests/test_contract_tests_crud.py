"""Unit tests for the data-product contract-test CRUD service.

Covers ``declare_contract_test`` validation (unknown assertion kind /
severity, blank name), its idempotent create-then-update behaviour, dict
spec serialisation, and the list/delete helpers. The test engine does not
enforce foreign keys, so a synthetic ``data_product_id`` is fine; names are
unique per case to avoid the per-product unique constraint colliding.
"""

from __future__ import annotations

import pytest

from pointlessql.api.main import app
from pointlessql.services.contract_tests._crud import (
    declare_contract_test,
    delete_contract_test,
    list_contract_tests,
)

_DP = 4301


def _factory():
    return app.state.session_factory


def _declare(name: str, **over):
    kwargs = {
        "data_product_id": _DP,
        "name": name,
        "assertion_kind": "row_count_range",
        "assertion_spec_json": '{"min": 1}',
        "severity": "warn",
    }
    kwargs.update(over)
    return declare_contract_test(_factory(), **kwargs)


# --- validation -----------------------------------------------------------


def test_unknown_assertion_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown assertion_kind"):
        _declare("ct-bad-kind", assertion_kind="nope")


def test_unknown_severity_raises() -> None:
    with pytest.raises(ValueError, match="unknown severity"):
        _declare("ct-bad-sev", severity="critical")


def test_blank_name_raises() -> None:
    with pytest.raises(ValueError, match="name is required"):
        _declare("   ")


# --- declare (create + idempotent update) ---------------------------------


def test_declare_creates() -> None:
    out = _declare("ct-create")
    assert out["name"] == "ct-create"
    assert out["assertion_kind"] == "row_count_range"
    assert out["severity"] == "warn"


def test_declare_is_idempotent_update() -> None:
    first = _declare("ct-idem", severity="warn")
    second = _declare("ct-idem", severity="error")
    assert first["id"] == second["id"]
    assert second["severity"] == "error"


def test_declare_accepts_dict_spec() -> None:
    out = _declare("ct-dictspec", assertion_spec_json={"min": 5, "max": 9})
    # Serialised back to a JSON string somewhere in the payload.
    assert out["name"] == "ct-dictspec"


# --- list / delete --------------------------------------------------------


def test_list_contract_tests() -> None:
    _declare("ct-list")
    names = {t["name"] for t in list_contract_tests(_factory(), data_product_id=_DP)}
    assert "ct-list" in names


def test_delete_contract_test() -> None:
    created = _declare("ct-delete")
    assert delete_contract_test(_factory(), contract_test_id=created["id"]) is True
    assert delete_contract_test(_factory(), contract_test_id=created["id"]) is False
