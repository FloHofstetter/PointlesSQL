"""Pure-Python schema diff with semver classification.

Schema shape (canonical):

    {
      "columns": [
        {"name": "id",     "type": "Int",    "nullable": False, "description": "..."},
        {"name": "email",  "type": "String", "nullable": True,  "description": "..."},
        ...
      ]
    }

Classification rules (deterministic, in order):

* Column removed                    → MAJOR.
* Column type narrowed              → MAJOR.
* NOT-NULL added on existing column → MAJOR.
* Column added NOT NULL             → MAJOR.
* Column added nullable / w/ default → MINOR.
* Description change                → PATCH.
* No structural change              → NONE.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: Type-narrowing pairs (old, new).  Crossing one of these counts as a
#: breaking change.  The list is intentionally small — extend it when
#: a real-world Delta schema produces a narrowing not on the list.
NARROWING_PAIRS: tuple[tuple[str, str], ...] = (
    ("Long", "Int"),
    ("Long", "Short"),
    ("Long", "Byte"),
    ("Int", "Short"),
    ("Int", "Byte"),
    ("Short", "Byte"),
    ("Float", "Int"),
    ("Float", "Short"),
    ("Float", "Byte"),
    ("Double", "Float"),
    ("Double", "Int"),
    ("String", "Date"),
    ("String", "Timestamp"),
    ("String", "Int"),
    ("Decimal", "Float"),
)


@dataclasses.dataclass(slots=True, frozen=True)
class SchemaDiff:
    """Classified diff between two schemas.

    Attributes:
        change_kind: One of ``major`` / ``minor`` / ``patch`` /
            ``none`` (no-op).
        columns_removed: List of names removed in the new schema.
        columns_added: List of name-with-nullable tuples added.
        columns_type_changed: List of ``(name, old_type, new_type)``.
        columns_nullable_tightened: Columns that flipped from True
            to False on ``nullable``.
        columns_description_changed: Columns whose description differs.
    """

    change_kind: str
    columns_removed: list[str]
    columns_added: list[tuple[str, bool]]
    columns_type_changed: list[tuple[str, str, str]]
    columns_nullable_tightened: list[str]
    columns_description_changed: list[str]

    def is_breaking(self) -> bool:
        """Return True when the diff requires a MAJOR bump."""
        return self.change_kind == "major"


def compute_diff(
    old_schema: dict[str, Any] | None,
    new_schema: dict[str, Any],
) -> SchemaDiff:
    """Classify the diff between *old_schema* and *new_schema*.

    Args:
        old_schema: Previously-registered schema or ``None`` when no
            prior version exists.
        new_schema: The schema the writer is presenting now.

    Returns:
        :class:`SchemaDiff` with the strongest applicable
        ``change_kind``.
    """
    old_columns = _index(old_schema)
    new_columns = _index(new_schema)

    removed = [name for name in old_columns if name not in new_columns]
    added: list[tuple[str, bool]] = []
    type_changed: list[tuple[str, str, str]] = []
    nullable_tightened: list[str] = []
    description_changed: list[str] = []

    for name, new_col in new_columns.items():
        old_col = old_columns.get(name)
        if old_col is None:
            added.append((name, bool(new_col.get("nullable", True))))
            continue
        old_type = str(old_col.get("type", ""))
        new_type = str(new_col.get("type", ""))
        if old_type != new_type:
            type_changed.append((name, old_type, new_type))
        old_nullable = bool(old_col.get("nullable", True))
        new_nullable = bool(new_col.get("nullable", True))
        if old_nullable and not new_nullable:
            nullable_tightened.append(name)
        old_desc = str(old_col.get("description") or "")
        new_desc = str(new_col.get("description") or "")
        if old_desc != new_desc:
            description_changed.append(name)

    if (
        removed
        or _has_breaking_type_change(type_changed)
        or nullable_tightened
        or _has_not_null_addition(added)
    ):
        change_kind = "major"
    elif added:
        change_kind = "minor"
    elif description_changed:
        change_kind = "patch"
    else:
        change_kind = "none"

    return SchemaDiff(
        change_kind=change_kind,
        columns_removed=removed,
        columns_added=added,
        columns_type_changed=type_changed,
        columns_nullable_tightened=nullable_tightened,
        columns_description_changed=description_changed,
    )


def _index(schema: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return a name-keyed column dict; missing schema → empty dict."""
    if not schema:
        return {}
    columns = schema.get("columns")
    if not isinstance(columns, list):
        return {}
    by_name: dict[str, dict[str, Any]] = {}
    for entry in columns:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        by_name[name] = entry
    return by_name


def _has_breaking_type_change(
    type_changed: list[tuple[str, str, str]],
) -> bool:
    """Return True if any change in *type_changed* is a narrowing."""
    for _, old_type, new_type in type_changed:
        if (old_type, new_type) in NARROWING_PAIRS:
            return True
    return False


def _has_not_null_addition(added: list[tuple[str, bool]]) -> bool:
    """Return True if any added column is NOT NULL (nullable=False)."""
    return any(not nullable for _, nullable in added)
