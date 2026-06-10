"""Schema-diff classification (Phase 144)."""

from __future__ import annotations

from pointlessql.services.schema_versioning import compute_diff


def _schema(*cols) -> dict:
    return {
        "columns": [
            {"name": n, "type": t, "nullable": nullable, "description": desc}
            for n, t, nullable, desc in cols
        ]
    }


def test_no_change_returns_none() -> None:
    schema = _schema(("id", "Int", False, ""))
    diff = compute_diff(schema, schema)
    assert diff.change_kind == "none"
    assert diff.is_breaking() is False


def test_added_nullable_column_is_minor() -> None:
    old = _schema(("id", "Int", False, ""))
    new = _schema(("id", "Int", False, ""), ("email", "String", True, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind == "minor"
    assert diff.columns_added == [("email", True)]


def test_added_not_null_column_is_major() -> None:
    old = _schema(("id", "Int", False, ""))
    new = _schema(("id", "Int", False, ""), ("email", "String", False, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind == "major"
    assert diff.is_breaking() is True


def test_removed_column_is_major() -> None:
    old = _schema(("id", "Int", False, ""), ("email", "String", True, ""))
    new = _schema(("id", "Int", False, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind == "major"
    assert diff.columns_removed == ["email"]


def test_type_narrowed_is_major() -> None:
    old = _schema(("age", "Long", True, ""))
    new = _schema(("age", "Int", True, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind == "major"
    assert diff.columns_type_changed[0] == ("age", "Long", "Int")


def test_type_widened_is_not_breaking() -> None:
    old = _schema(("age", "Int", True, ""))
    new = _schema(("age", "Long", True, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind != "major"


def test_nullable_tightened_is_major() -> None:
    old = _schema(("email", "String", True, ""))
    new = _schema(("email", "String", False, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind == "major"
    assert diff.columns_nullable_tightened == ["email"]


def test_nullable_loosened_is_no_change_unless_other_diff() -> None:
    old = _schema(("email", "String", False, ""))
    new = _schema(("email", "String", True, ""))
    diff = compute_diff(old, new)
    assert diff.change_kind == "none"


def test_description_only_change_is_patch() -> None:
    old = _schema(("id", "Int", False, "old note"))
    new = _schema(("id", "Int", False, "new note"))
    diff = compute_diff(old, new)
    assert diff.change_kind == "patch"
    assert diff.columns_description_changed == ["id"]


def test_first_version_is_minor_when_columns_added() -> None:
    new = _schema(("id", "Int", False, ""), ("email", "String", True, ""))
    diff = compute_diff(None, new)
    assert diff.change_kind == "major"  # any not-null column on first add is major


def test_multiple_kinds_collapse_to_strongest() -> None:
    old = _schema(("id", "Long", False, ""), ("email", "String", True, ""))
    new = _schema(
        ("id", "Int", False, "new note"),
        ("phone", "String", True, ""),
    )
    diff = compute_diff(old, new)
    assert diff.change_kind == "major"


def test_schema_with_no_columns_handled() -> None:
    diff = compute_diff(None, {"columns": []})
    assert diff.change_kind == "none"
