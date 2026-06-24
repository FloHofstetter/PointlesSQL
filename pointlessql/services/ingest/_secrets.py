"""At-rest encryption for ``IngestSource.secrets`` credential blobs.

A source's ``secrets`` column carries connector credentials — S3 access
keys, Postgres/MySQL passwords, HTTP bearer tokens.  They used to sit as
plaintext JSON in the metadata DB, so a single read of the row yielded a
usable credential.  This module wraps them with the install master key
(:mod:`pointlessql.services.secrets`, Fernet) so the column is opaque at
rest.

Rows written before encryption stay readable: :func:`decrypt_secrets`
first tries to parse the column as JSON (legacy plaintext) and only
falls back to Fernet decryption for the opaque tokens
:func:`encrypt_secrets` produces.  A legacy row upgrades to ciphertext
on its next create/patch, which re-encrypts the whole blob.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from pointlessql.services.secrets import decrypt_value, encrypt_value

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def encrypt_secrets(plain: dict[str, Any], session_factory: sessionmaker[Session]) -> str:
    """Serialize and encrypt a secrets mapping for at-rest storage.

    Args:
        plain: The cleartext secrets mapping (may be empty).
        session_factory: Session factory used to fetch the master key.

    Returns:
        A Fernet token wrapping the JSON-encoded mapping.
    """
    return encrypt_value(json.dumps(plain), session_factory=session_factory)


def decrypt_secrets(stored: str | None, session_factory: sessionmaker[Session]) -> dict[str, Any]:
    """Return the cleartext secrets mapping from a stored column value.

    Tolerant of three shapes so a migration is unnecessary: an absent
    value yields ``{}``, legacy plaintext JSON is parsed directly, and a
    Fernet token from :func:`encrypt_secrets` is decrypted then parsed.

    Args:
        stored: The raw ``IngestSource.secrets`` column value.
        session_factory: Session factory used to fetch the master key.

    Returns:
        The decoded mapping; an empty dict when the value is absent or
        cannot be recovered.
    """
    if not stored:
        return {}
    # Legacy plaintext rows parse straight as JSON; Fernet tokens do not.
    try:
        legacy: Any = json.loads(stored)
    except ValueError:
        legacy = None
    if isinstance(legacy, dict):
        return {str(k): v for k, v in cast(dict[Any, Any], legacy).items()}
    try:
        decoded: Any = json.loads(decrypt_value(stored, session_factory=session_factory))
    except ValueError, UnicodeError:
        # SecretDecryptError subclasses ValueError; UnicodeError guards
        # the ascii-encode of a non-token value that slipped through.
        return {}
    if isinstance(decoded, dict):
        return {str(k): v for k, v in cast(dict[Any, Any], decoded).items()}
    return {}
