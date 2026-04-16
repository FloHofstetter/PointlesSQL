"""Three-part Unity Catalog name parsing."""

from __future__ import annotations

from pointlessql.exceptions import ValidationError


def parse_full_name(full_name: str) -> tuple[str, str, str]:
    """Parse a three-part UC name into (catalog, schema, table).

    Args:
        full_name: Dot-separated name like ``"catalog.schema.table"``.

    Returns:
        A tuple of ``(catalog_name, schema_name, table_name)``.

    Raises:
        ValidationError: If the name does not have exactly three non-empty
            parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3:
        msg = (
            f"Expected a three-part name 'catalog.schema.table', "
            f"got {len(parts)} part(s): {full_name!r}"
        )
        raise ValidationError(msg)
    catalog, schema, table = (p.strip() for p in parts)
    if not catalog or not schema or not table:
        msg = f"Name parts must not be empty: {full_name!r}"
        raise ValidationError(msg)
    return catalog, schema, table
