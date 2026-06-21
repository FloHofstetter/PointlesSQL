"""Shared validation for dotted Unity Catalog scope names.

Tag policies and predictive-optimization policies both scope a rule to a
catalog / schema / table securable named by its dotted path.  The
depth check and its error message are identical across the two surfaces,
so they live here: a future change to how a scope name is parsed (quoted
identifiers, reworded errors) lands once instead of drifting between two
hand-copied validators.
"""

from __future__ import annotations

from pointlessql.exceptions import ValidationError


def split_dotted_scope(scope_type: str, value: str, expected_parts: int) -> list[str]:
    """Split a dotted securable name and assert it has the expected depth.

    Args:
        scope_type: The scope kind, used only to phrase the error.
        value: The trimmed dotted name (e.g. ``main.sales``).
        expected_parts: Dot-separated parts the scope kind requires
            (catalog = 1, schema = 2, table = 3).

    Returns:
        The name's parts — guaranteed non-empty and of the expected
        length.

    Raises:
        ValidationError: When any part is empty or the part count does
            not match *expected_parts*.
    """
    parts = value.split(".")
    if any(not part for part in parts):
        raise ValidationError("scope_value must not contain empty name parts")
    if len(parts) != expected_parts:
        raise ValidationError(
            f"a {scope_type} scope_value must have {expected_parts} dotted part(s), "
            f"got {len(parts)}"
        )
    return parts
