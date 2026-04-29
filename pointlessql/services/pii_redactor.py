"""Write-time PII redaction for value-change rows (Sprint 20.1).

Phase 18.2 added render-time masking that gates cleartext behind an
admin role at the API boundary.  Sprint 20.1 closes the
cleartext-at-rest gap: when ``settings.audit.pii_mode`` is anything
other than ``store_clear``, the bulk-insert into
``lineage_value_changes`` redacts ``old_value`` / ``new_value`` for
columns deemed PII *before* the row hits SQLite.

Two PII-detection paths run in OR order:

1. **Pattern-based.**  A column whose name matches one of a small
   set of well-known PII patterns is redacted regardless of soyuz
   tags.  Cheap, deterministic, no network round-trip.  Catches the
   common ``email``, ``phone``, ``ssn``, ``credit_card``, ``iban``,
   ``passport`` type names that operators forget to tag explicitly.
2. **Soyuz tag.**  Asynchronously read at row-trace render time by
   :mod:`pointlessql.services.pii_resolver`.  Not consulted from
   this sync write path — adding a sync soyuz round-trip per merge
   would dominate per-write cost.  Tagged-but-non-pattern columns
   stay un-redacted at write time and rely on the existing render-
   time masking to suppress cleartext from non-admin viewers.

Three modes (``settings.audit.pii_mode``):

* ``store_clear`` — pre-Phase-20 behaviour, no redaction.
* ``hash_only`` — equality-joinable HMAC-SHA256, hex-encoded, first
  16 chars.  Equality across runs lets analysts pivot rows by
  hashed identity (e.g. "every change to the same email") without
  exposing cleartext.
* ``redact_with_audit_log`` — replace with the literal
  ``"<redacted>"`` and append one ``audit_log`` row per redaction
  call (one row regardless of how many cells were masked, to keep
  the trail bounded).
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import re
import secrets
from typing import TYPE_CHECKING

from sqlalchemy import select

from pointlessql.models.system_keys import SystemKey

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

PII_NAME_PATTERN = re.compile(
    r"(?ix)"
    r"(?:^|_)"  # word boundary on the left
    r"(?:"
    r"pii"
    r"|email|e_mail|mail"
    r"|phone|mobile|tel|telephone|fax"
    r"|ssn|social_security|nationalid|national_id|tax_id"
    r"|passport|driver_?licen|drivers_?licen"
    r"|credit_?card|cc_num|cardnumber|card_no|iban|bic|swift"
    r"|account_?number|acct_?num"
    r"|password|passwd|pwd|secret|token|api_?key"
    r"|first_?name|last_?name|full_?name|given_?name|family_?name"
    r"|address|street|postal|zipcode|zip_?code|postcode"
    r"|dob|birth|date_?of_?birth|birthday"
    r"|gender|race|ethnicity|religion"
    r")"
    r"(?:$|_|\d)",  # word boundary on the right
)
"""Regex matching column names that carry obvious PII.

Liberal on purpose: false positives mask non-PII columns
(low-impact: a hash is harder to read), false negatives leak
cleartext (high-impact).  Operators wanting tighter control set
tags in soyuz and rely on the Phase-18 render-time masking
instead.
"""

PII_HASH_SECRET_NAME = "pii_hash"
"""``system_keys.name`` row holding the lazily-generated PII hash secret."""

REDACTED_PLACEHOLDER = "<redacted>"
"""Literal value substituted under ``redact_with_audit_log`` mode."""

HASH_PREFIX_BYTES = 8
"""Bytes from the HMAC-SHA256 digest kept in the stored hex (16 hex chars)."""


def is_pii_by_name(column_name: str | None) -> bool:
    """Return ``True`` iff the column name matches a known-PII pattern.

    Args:
        column_name: Column identifier from ``ValueChangeSpec.target_column``.
            Empty / ``None`` returns ``False``.

    Returns:
        ``True`` when the regex fires; ``False`` otherwise.
    """
    if not column_name:
        return False
    return bool(PII_NAME_PATTERN.search(column_name))


def _generate_secret_bytes() -> str:
    """Return a fresh 32-byte URL-safe random token."""
    return secrets.token_urlsafe(32)


def get_or_create_pii_hash_secret(session_factory: sessionmaker[Session]) -> str:
    """Return the install's PII hash secret, generating one on first call.

    The secret lives under ``system_keys.name='pii_hash'``.  When the
    row is missing the function inserts one with a freshly-generated
    32-byte URL-safe token.  Concurrent first-callers race on the
    UNIQUE(name) constraint; the loser re-reads the row.

    Args:
        session_factory: SQLAlchemy session factory.

    Returns:
        The persisted secret string.

    Raises:
        Exception: When both the INSERT and the post-conflict
            re-read fail.  Callers in the redactor swallow this and
            fall back to ``redact_with_audit_log`` mode.
    """
    with session_factory() as session:
        row = session.scalar(
            select(SystemKey).where(SystemKey.name == PII_HASH_SECRET_NAME)
        )
        if row is not None:
            return row.value
        new_secret = _generate_secret_bytes()
        new_row = SystemKey(
            name=PII_HASH_SECRET_NAME,
            value=new_secret,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(new_row)
        try:
            session.commit()
            return new_secret
        except Exception:  # noqa: BLE001 — re-read on UNIQUE conflict
            session.rollback()
            row = session.scalar(
                select(SystemKey).where(SystemKey.name == PII_HASH_SECRET_NAME)
            )
            if row is None:
                raise
            return row.value


def hash_value(value: str | None, *, secret: str) -> str | None:
    """HMAC-SHA256 hash *value* with *secret*, hex-encoded prefix.

    ``None`` (representing a true SQL NULL) round-trips as ``None``
    so analysts can still distinguish "this cell was never set" from
    "this cell was masked".  Empty string hashes normally.

    Args:
        value: Cleartext or ``None``.
        secret: The pre-shared PII hash secret.

    Returns:
        ``HEX(HMAC-SHA256(secret, value))[:16]`` or ``None``.
    """
    if value is None:
        return None
    digest = hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()[:HASH_PREFIX_BYTES]
    return digest.hex()


def redact_value(value: str | None) -> str | None:
    """Return :data:`REDACTED_PLACEHOLDER` for non-NULL inputs.

    Args:
        value: Cleartext or ``None``.

    Returns:
        ``REDACTED_PLACEHOLDER`` for any non-NULL string input,
        ``None`` for NULL.
    """
    if value is None:
        return None
    return REDACTED_PLACEHOLDER
