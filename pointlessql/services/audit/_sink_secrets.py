"""Field-level encryption for ``AuditSink.config_json`` credentials.

A sink's ``config_json`` mixes non-secret connection fields (url,
bucket, region, prefix) with credentials — the HMAC signing secret, the
AWS secret access key, an STS session token.  Storing those in cleartext
means one read of the metadata DB yields a usable credential.

These helpers encrypt *only* the sensitive keys in place with the
install master key (:mod:`pointlessql.services.secrets`), leaving every
other field readable.  That keeps the admin GET projection — which
redacts exactly :data:`SINK_SECRET_KEYS` — working without a decrypt,
and confines the change to the write path and the delivery dispatchers
that actually need the cleartext secret.

Reads tolerate legacy plaintext: a value that is not a Fernet token is
returned unchanged, so pre-encryption rows keep working and upgrade to
ciphertext on their next write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pointlessql.services.secrets import decrypt_value, encrypt_value

if TYPE_CHECKING:
    from pointlessql.types import SessionFactory

SINK_SECRET_KEYS: frozenset[str] = frozenset({"hmac_secret", "secret_access_key", "session_token"})
"""``config_json`` keys whose values are credentials encrypted at rest.

The admin GET projection redacts the same set, so encryption and
redaction never drift apart.
"""


def encrypt_sink_secrets(config: dict[str, Any], session_factory: SessionFactory) -> dict[str, Any]:
    """Return a copy of *config* with each credential value encrypted.

    Args:
        config: The cleartext sink config dict.
        session_factory: Session factory used to fetch the master key.

    Returns:
        A shallow copy where every present :data:`SINK_SECRET_KEYS`
        string value is replaced by a Fernet token; other fields are
        untouched.
    """
    out = dict(config)
    for key in SINK_SECRET_KEYS:
        value = out.get(key)
        if isinstance(value, str) and value:
            out[key] = encrypt_value(value, session_factory=session_factory)
    return out


def decrypt_sink_secrets(config: dict[str, Any], session_factory: SessionFactory) -> dict[str, Any]:
    """Return a copy of *config* with each credential value decrypted.

    Legacy plaintext rows (any value that is not a valid token) are kept
    as-is, so a config written before encryption still delivers.

    Args:
        config: The stored sink config dict (credentials may be tokens).
        session_factory: Session factory used to fetch the master key.

    Returns:
        A shallow copy where every recoverable :data:`SINK_SECRET_KEYS`
        token is replaced by its cleartext.
    """
    out = dict(config)
    for key in SINK_SECRET_KEYS:
        value = out.get(key)
        if isinstance(value, str) and value:
            try:
                out[key] = decrypt_value(value, session_factory=session_factory)
            except ValueError, UnicodeError:
                # Legacy plaintext or already-clear value — keep as-is.
                pass
    return out
