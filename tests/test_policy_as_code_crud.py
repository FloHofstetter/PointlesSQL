"""Unit tests for the Cedar policy-module CRUD service.

Covers create validation (blank name / source, duplicate-name conflict),
the get/list reads (including the disabled filter), the in-place update
(version bumps only on source change), the enable toggle (no version
bump), and delete. Rows live in the seeded test workspace; names are
unique per test to avoid the unique-constraint colliding across cases.
"""

from __future__ import annotations

import pytest

from pointlessql.api.main import app
from pointlessql.services.policy_as_code._crud import (
    create_module,
    delete_module,
    get_module,
    list_modules,
    set_module_enabled,
    update_module,
)

def _factory():
    return app.state.session_factory


_SRC = 'permit(principal, action, resource);'


# --- create validation ----------------------------------------------------


def test_create_blank_name_raises() -> None:
    with pytest.raises(ValueError, match="name is required"):
        create_module(
            _factory(), workspace_id=1, name="  ", cedar_source=_SRC, created_by_user_id=None
        )


def test_create_blank_source_raises() -> None:
    with pytest.raises(ValueError, match="cedar_source is required"):
        create_module(
            _factory(), workspace_id=1, name="pm-blank-src", cedar_source="", created_by_user_id=None
        )


def test_create_returns_serialised_module() -> None:
    out = create_module(
        _factory(),
        workspace_id=1,
        name="  pm-create  ",
        cedar_source=_SRC,
        created_by_user_id=None,
    )
    assert out["name"] == "pm-create"  # stripped
    assert out["version"] == 1
    assert out["enabled"] is True


def test_create_duplicate_name_raises() -> None:
    create_module(
        _factory(), workspace_id=1, name="pm-dup", cedar_source=_SRC, created_by_user_id=None
    )
    with pytest.raises(ValueError, match="already exists"):
        create_module(
            _factory(), workspace_id=1, name="pm-dup", cedar_source=_SRC, created_by_user_id=None
        )


# --- get / list -----------------------------------------------------------


def test_get_module_found_and_missing() -> None:
    created = create_module(
        _factory(), workspace_id=1, name="pm-get", cedar_source=_SRC, created_by_user_id=None
    )
    assert get_module(_factory(), module_id=created["id"])["name"] == "pm-get"
    assert get_module(_factory(), module_id=999999) is None


def test_list_modules_disabled_filter() -> None:
    created = create_module(
        _factory(),
        workspace_id=1,
        name="pm-disabled",
        cedar_source=_SRC,
        created_by_user_id=None,
        enabled=False,
    )
    all_names = {m["name"] for m in list_modules(_factory(), workspace_id=1)}
    enabled_names = {
        m["name"] for m in list_modules(_factory(), workspace_id=1, include_disabled=False)
    }
    assert created["name"] in all_names
    assert created["name"] not in enabled_names


# --- update / enable ------------------------------------------------------


def test_update_source_bumps_version() -> None:
    created = create_module(
        _factory(), workspace_id=1, name="pm-update", cedar_source=_SRC, created_by_user_id=None
    )
    updated = update_module(
        _factory(), module_id=created["id"], cedar_source="forbid(principal, action, resource);"
    )
    assert updated["version"] == 2


def test_update_missing_returns_none() -> None:
    assert update_module(_factory(), module_id=999999, cedar_source=_SRC) is None


def test_set_enabled_does_not_bump_version() -> None:
    created = create_module(
        _factory(), workspace_id=1, name="pm-toggle", cedar_source=_SRC, created_by_user_id=None
    )
    toggled = set_module_enabled(_factory(), module_id=created["id"], enabled=False)
    assert toggled["enabled"] is False
    assert toggled["version"] == 1  # enable toggle keeps the version


# --- delete ---------------------------------------------------------------


def test_delete_module() -> None:
    created = create_module(
        _factory(), workspace_id=1, name="pm-delete", cedar_source=_SRC, created_by_user_id=None
    )
    assert delete_module(_factory(), module_id=created["id"]) is True
    assert delete_module(_factory(), module_id=created["id"]) is False
