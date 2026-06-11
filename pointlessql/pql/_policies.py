"""Row filters + column masks — governance policies on the read path.

Policies live as plain Unity Catalog **table properties** (so they
ride the existing metadata surface, are visible in the properties
card, and need no schema change):

* ``pointlessql.row_filter`` — a SQL predicate every non-exempt read
  is filtered by.  ``current_user()`` inside the predicate is
  replaced with the reading principal's e-mail literal before
  compilation.
* ``pointlessql.mask.<column>`` — a mask for one column.  Either a
  builtin (``redact`` → ``'***'``, ``hash`` → SHA-256 hex,
  ``null`` → ``NULL``) or a SQL expression template containing
  ``{col}`` (e.g. ``concat(left({col}, 2), '***')``).

Enforcement happens where every PQL read is funnelled anyway: the
DuckDB view registered per approved table becomes a SELECT that
applies the masks and the filter, so no query shape can bypass it.
Admins and table owners are exempt (they administer the policy);
exemption is decided by the route layer, which simply omits the
policy for exempt principals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

ROW_FILTER_PROPERTY = "pointlessql.row_filter"
"""Table property carrying the row-filter predicate."""

MASK_PROPERTY_PREFIX = "pointlessql.mask."
"""Prefix of per-column mask properties (suffix = column name)."""

_BUILTIN_MASKS = {
    "redact": "'***'",
    "null": "NULL",
    "hash": "sha256(CAST({col} AS VARCHAR))",
}

_CURRENT_USER_RE = re.compile(r"current_user\s*\(\s*\)", re.IGNORECASE)


def _empty_masks() -> dict[str, str]:
    """Typed default factory for :class:`TablePolicy.column_masks`."""
    return {}


@dataclass(frozen=True)
class TablePolicy:
    """Effective read policy of one table for one principal."""

    row_filter: str | None = None
    column_masks: dict[str, str] = field(default_factory=_empty_masks)

    def is_empty(self) -> bool:
        """Whether the policy changes nothing."""
        return self.row_filter is None and not self.column_masks


def render_mask(mask_spec: str, column: str) -> str:
    """Turn a mask spec into a SQL expression for *column*.

    Args:
        mask_spec: Builtin name or a ``{col}`` template.
        column: The masked column's name.

    Returns:
        The SQL expression replacing the raw column.

    Raises:
        ValueError: When the spec is empty, contains a statement
            separator, or fails to parse as an expression.
    """
    spec = (mask_spec or "").strip()
    if not spec:
        raise ValueError(f"empty mask spec for column {column!r}")
    template = _BUILTIN_MASKS.get(spec.lower(), spec)
    rendered = template.replace("{col}", f'"{column}"')
    if ";" in rendered:
        raise ValueError(f"mask for column {column!r} must be a single expression")
    try:
        sqlglot.parse_one(rendered, dialect="duckdb", into=exp.Condition)
    except ParseError as exc:
        raise ValueError(f"mask for column {column!r} does not parse: {exc}") from exc
    return rendered


def validate_row_filter(predicate: str) -> str:
    """Validate a row-filter predicate (with ``current_user()`` stubbed).

    Args:
        predicate: The raw predicate from the table property.

    Returns:
        The predicate unchanged (validation only).

    Raises:
        ValueError: When the predicate is empty, multi-statement, or
            fails to parse.
    """
    candidate = (predicate or "").strip()
    if not candidate:
        raise ValueError("row filter must be a non-empty predicate")
    if ";" in candidate:
        raise ValueError("row filter must be a single predicate")
    probe = _CURRENT_USER_RE.sub("'probe@example.com'", candidate)
    try:
        sqlglot.parse_one(probe, dialect="duckdb", into=exp.Condition)
    except ParseError as exc:
        raise ValueError(f"row filter does not parse: {exc}") from exc
    return candidate


def extract_table_policy(
    table_info: dict[str, Any], *, principal: str | None
) -> TablePolicy | None:
    """Build the effective policy from a table's properties.

    A malformed stored policy propagates the validators'
    :class:`ValueError` — failing the read beats silently skipping
    enforcement.

    Args:
        table_info: The UC table info dict (needs ``properties``).
        principal: Reading principal — substituted for
            ``current_user()`` in the filter predicate.

    Returns:
        The policy, or ``None`` when the table carries none.
    """
    raw_properties: object = table_info.get("properties") or {}
    if not isinstance(raw_properties, dict):
        return None
    properties = cast("dict[str, Any]", raw_properties)
    row_filter: str | None = None
    raw_filter = properties.get(ROW_FILTER_PROPERTY)
    if isinstance(raw_filter, str) and raw_filter.strip():
        validated = validate_row_filter(raw_filter)
        literal = (principal or "").replace("'", "''")
        row_filter = _CURRENT_USER_RE.sub(f"'{literal}'", validated)
    masks: dict[str, str] = {}
    for key, value in properties.items():
        if not key.startswith(MASK_PROPERTY_PREFIX):
            continue
        column = key[len(MASK_PROPERTY_PREFIX) :]
        if not column or not isinstance(value, str):
            continue
        masks[column] = render_mask(value, column)
    if row_filter is None and not masks:
        return None
    return TablePolicy(row_filter=row_filter, column_masks=masks)


def coerce_policy(value: TablePolicy | dict[str, Any] | None) -> TablePolicy | None:
    """Accept either a :class:`TablePolicy` or its dict form.

    Kernel transfers serialise policies as plain dicts inside the
    bootstrap snippet; this rebuilds the dataclass on the far side.

    Args:
        value: Policy object, its dict form, or ``None``.

    Returns:
        The coerced policy, or ``None``.
    """
    if value is None or isinstance(value, TablePolicy):
        return value
    return TablePolicy(
        row_filter=value.get("row_filter"),
        column_masks=dict(value.get("column_masks") or {}),
    )


def policy_view_sql(
    *, view_name: str, base_relation: str, columns: list[str], policy: TablePolicy
) -> str:
    """Compose the ``CREATE VIEW`` that applies *policy*.

    Args:
        view_name: The dotted UC name the user's SQL binds to.
        base_relation: Internal registration the view selects from.
        columns: The table's physical column names (in order).
        policy: The effective policy.

    Returns:
        A ``CREATE OR REPLACE TEMPORARY VIEW`` statement.
    """
    select_list = ", ".join(
        f'{policy.column_masks[column]} AS "{column}"'
        if column in policy.column_masks
        else f'"{column}"'
        for column in columns
    )
    where = f" WHERE {policy.row_filter}" if policy.row_filter else ""
    return (
        f'CREATE OR REPLACE TEMPORARY VIEW "{view_name}" AS '
        f'SELECT {select_list} FROM "{base_relation}"{where}'
    )
