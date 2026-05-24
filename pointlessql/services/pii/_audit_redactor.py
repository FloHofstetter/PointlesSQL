"""Audit-detail PII redaction.

The :func:`audit/_core.log_action` call ships ``detail`` dicts straight
into ``audit_log.detail`` via :func:`json.dumps`.  Routes that pass
payloads with keys like ``email``, ``token``, ``phone``, ``ssn`` land
cleartext at rest.  This module walks the dict recursively and applies
redaction to values whose KEY matches the existing
:data:`pointlessql.services.pii._redactor.PII_NAME_PATTERN` regex.

Behaviour mirrors :mod:`pointlessql.services.pii._redactor`:

* ``store_clear`` mode → pass-through (no-op).
* ``hash_only`` → HMAC-SHA256 first 16 hex chars (equality-joinable).
* ``redact_with_audit_log`` →
  :data:`REDACTED_PLACEHOLDER` literal.

The function is sync (mirrors :func:`log_action` which is sync); the
existing hash-secret accessor is reused.  Lists are walked
element-wise; strings inside non-PII keys pass through.  ``None``
values short-circuit.

Phase 121.7c — opt-in by ``settings.audit.redact_detail_payloads``,
default OFF for backward-compat.  Operators flip ON after auditing
existing detail payload shapes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.services.pii._redactor import (
    REDACTED_PLACEHOLDER,
    get_or_create_pii_hash_secret,
    hash_value,
    is_pii_by_name,
    redact_value,
)


def redact_audit_detail(
    detail: str | dict[str, Any] | None,
    *,
    mode: str = "redact_with_audit_log",
    session_factory: sessionmaker[Session] | None = None,
) -> str | dict[str, Any] | None:
    """Recursively redact PII-keyed values in *detail*.

    Args:
        detail: The audit detail payload — mirrors the input contract
            of :func:`pointlessql.services.audit._core.log_action`.
            ``None`` and ``str`` pass through unchanged (strings are
            opaque from a PII perspective — no per-key context exists).
        mode: One of ``store_clear`` / ``hash_only`` /
            ``redact_with_audit_log``.  Default mirrors the strictest
            existing mode.
        session_factory: Required for ``hash_only`` mode (fetches the
            install-global secret via
            :func:`get_or_create_pii_hash_secret`).  Ignored in other
            modes.

    Returns:
        The same payload shape with PII-keyed values redacted /
        hashed.  Cleartext is returned for ``store_clear`` mode.
        Lists nested inside dict values are walked element-wise.
    """
    if detail is None or isinstance(detail, str) or mode == "store_clear":
        return detail
    secret: str | None = None
    if mode == "hash_only" and session_factory is not None:
        secret = get_or_create_pii_hash_secret(session_factory)
    walked = _walk(detail, mode, secret)
    assert isinstance(walked, dict)
    return walked


def _walk(node: Any, mode: str, secret: str | None) -> Any:
    """Recursively descend into *node* applying :func:`_scrub` on PII keys."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():  # type: ignore[reportUnknownVariableType]
            key_str = str(key)
            if is_pii_by_name(key_str):
                out[key_str] = _scrub(value, mode, secret)
            else:
                out[key_str] = _walk(value, mode, secret)
        return out
    if isinstance(node, list):
        return [_walk(item, mode, secret) for item in node]  # type: ignore[reportUnknownVariableType]
    return node


def _scrub(value: Any, mode: str, secret: str | None) -> Any:
    """Return the redacted / hashed form of *value* for ``mode``."""
    if value is None:
        return None
    if mode == "hash_only" and secret is not None and isinstance(value, str):
        return hash_value(value, secret=secret)
    if isinstance(value, str):
        return redact_value(value)
    return REDACTED_PLACEHOLDER
