"""Tests for the Phase 121.6 Item A ``RefKind`` registry."""

from __future__ import annotations

import pytest

from pointlessql.api.social_routes._ref_kinds import (
    _REF_KINDS,
    RefKind,
    find_ref_kind,
    register_ref_kind,
)


def test_find_ref_kind_returns_spec_for_registered_kind() -> None:
    spec = find_ref_kind("table")
    assert spec is not None
    assert spec.key == "table"


def test_find_ref_kind_returns_none_for_unknown_kind() -> None:
    assert find_ref_kind("nope_not_a_kind") is None


def test_register_duplicate_kind_raises() -> None:
    """Double-registration is a loud error to surface naming collisions."""
    with pytest.raises(ValueError, match="already registered"):
        register_ref_kind(
            RefKind(
                key="table",
                validate=lambda _r: True,
                message="dup",
            )
        )


def test_register_new_kind_appends() -> None:
    """New kinds are appended and discoverable via find."""
    key = "_unit_test_kind_phase121"
    assert find_ref_kind(key) is None
    spec = RefKind(key=key, validate=lambda r: r == "ok", message="bad")
    try:
        register_ref_kind(spec)
        assert find_ref_kind(key) is spec
        assert spec.validate("ok") is True
        assert spec.validate("bad") is False
    finally:
        _REF_KINDS.remove(spec)


@pytest.mark.parametrize(
    ("kind", "good_refs", "bad_refs"),
    [
        ("table", ["cat.sch.tab"], ["", "cat", "cat.sch", "cat.sch.", ".sch.tab"]),
        (
            "branch",
            ["cat.sch__branch_xyz"],
            ["", "cat.sch", "branchname"],
        ),
        ("model", ["cat.sch.mdl"], ["cat.sch"]),
        (
            "run",
            ["abcdef12-3456-7890-abcd-ef1234567890"],
            ["short", "abcdef12-3456-7890-abcd"],
        ),
        ("issue", ["1", "999"], ["", "abc", "1a"]),
        ("schema", ["cat.sch"], ["", "cat"]),
        ("catalog", ["cat"], ["", "cat.sch", "cat/sch"]),
        (
            "notebook",
            ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
            ["short", "aaaa"],
        ),
        ("saved_query", ["my-slug"], ["", "with/slash"]),
        ("workspace", ["my-ws"], ["", "with/slash", "with.dot"]),
        (
            "notebook_cell",
            [
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:"
                "ffffffff-aaaa-bbbb-cccc-dddddddddddd"
            ],
            ["no-colon-pair", "short:short", ""],
        ),
    ],
)
def test_ref_kind_validators(
    kind: str, good_refs: list[str], bad_refs: list[str]
) -> None:
    """Every registered kind validates its happy + sad refs."""
    spec = find_ref_kind(kind)
    assert spec is not None
    for good in good_refs:
        assert spec.validate(good), f"{kind}: {good!r} should validate"
    for bad in bad_refs:
        assert not spec.validate(bad), f"{kind}: {bad!r} should NOT validate"


def test_registry_holds_eleven_polymorphic_kinds() -> None:
    """The 11 polymorphic kinds enumerated by Phase 77 are all registered."""
    keys = {spec.key for spec in _REF_KINDS}
    expected = {
        "table",
        "branch",
        "model",
        "run",
        "issue",
        "schema",
        "catalog",
        "notebook",
        "saved_query",
        "workspace",
        "notebook_cell",
    }
    assert expected.issubset(keys)
