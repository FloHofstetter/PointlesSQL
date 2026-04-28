"""Stringy masking helpers for PII-tagged values.

Lineage value-changes (Sprint 15.7) store cleartext old/new values
in the metadata DB.  Sprint 18.2 keeps the cleartext at rest (the
audit trail must be byte-faithful) but renders a masked form in
the UI when the column is PII-tagged.  The reveal endpoint
returns the cleartext only after writing an ``audit_log`` row of
``action='pii.value_revealed'``.

The mask shape tries to preserve enough structure that a reviewer
can still see "this is an email" / "this is a 16-digit number" /
"this is a phone number" without seeing the actual content.  The
detection is purely regex-on-the-value — no soyuz call — so it's
free to run on every cell.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DIGIT_RUN_RE = re.compile(r"^\+?\d[\d\s\-]{4,}$")
_DIGIT_ONLY_RE = re.compile(r"^\d+$")


def _detect_kind(value: str) -> str:
    """Best-effort classification of the value's shape.

    Args:
        value: Stringified cell content.

    Returns:
        ``"email"`` / ``"phone"`` / ``"numeric"`` / ``"default"``.
    """
    if _EMAIL_RE.match(value):
        return "email"
    if _DIGIT_ONLY_RE.match(value):
        return "numeric"
    if _DIGIT_RUN_RE.match(value):
        return "phone"
    return "default"


def mask_value(value: str | None, *, kind: str | None = None) -> str:
    """Return a render-safe placeholder for a PII-tagged cell.

    Args:
        value: Cleartext value (or ``None``).  ``None`` always
            renders as ``"NULL"`` to match the existing template
            convention.
        kind: Optional override of the auto-detected mask shape.
            Pass ``"email"`` / ``"phone"`` / ``"numeric"`` /
            ``"default"`` to skip the regex.

    Returns:
        The masked string suitable for direct template render.
    """
    if value is None:
        return "NULL"
    if kind is None:
        kind = _detect_kind(value)
    if kind == "email":
        return "***@***.***"
    if kind == "phone":
        digits = re.sub(r"\D", "", value)
        return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***-***-****"
    if kind == "numeric":
        if len(value) <= 4:
            return "*" * len(value)
        return value[0] + ("*" * (len(value) - 2)) + value[-1]
    # default: keep the first + last visible character.
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + ("*" * max(3, len(value) - 2)) + value[-1]
