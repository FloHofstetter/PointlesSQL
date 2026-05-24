"""Authenticated encryption for at-rest secrets.

introduces git-backed workspaces, which need to persist
auth credentials (deploy keys, PATs, OAuth tokens) for each repo.
Earlier persistence shapes — :class:`SystemKey` for the PII hash,
the audit-sink credentials envelope — encode the secret with
base64url, which is *not* encryption (anyone with read access to
the DB can decode the bytes).  For credentials that grant
push/pull rights to a third-party service that gap is no longer
acceptable.

This module wraps :class:`cryptography.fernet.Fernet` with two
public functions, :func:`encrypt_value` and :func:`decrypt_value`,
both keyed off a single install-scoped master key stored in the
``system_keys`` table under :data:`MASTER_KEY_NAME`.  The master
key is generated on first use (idempotent under UNIQUE-conflict
recovery, mirroring
:func:`pointlessql.services.pii._redactor.get_or_create_pii_hash_secret`)
and never rotated automatically — callers that want rotation
must re-encrypt every dependent row themselves.

Why Fernet:

* Authenticated (HMAC-SHA-256 over AES-128-CBC + IV) — tampering
  is detected.
* Self-contained — the ciphertext token carries the IV and the
  HMAC, no separate metadata.
* Time-stamped — every token is bound to the time it was
  generated, which matters if we ever add a TTL policy.

What this is NOT:

* Not a workspace-scoped key — one master key per install, every
  workspace's secrets share it.  Phase 52+ may introduce
  per-workspace keys for stricter blast-radius containment;
  callers that need that today should not rely on these helpers.
* Not a key-rotation system — :func:`rotate_master_key` is
  deliberately absent.  When the time comes to rotate, write a
  one-shot CLI that decrypts every row with the old key and
  re-encrypts with the new.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from pointlessql.models.system_keys import SystemKey

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

MASTER_KEY_NAME = "repo_secrets_master"  # pragma: allowlist secret
"""``system_keys.name`` row holding the install-scoped Fernet master key."""


class SecretDecryptError(ValueError):
    """Raised when ciphertext fails authentication.

    Wraps :class:`cryptography.fernet.InvalidToken` into a project
    type so callers don't import cryptography just to ``except``.
    Surfacing this means the ciphertext was tampered with, the
    master key was rotated without re-encrypting dependents, or
    the bytes never were Fernet output to begin with.
    """


def _generate_master_key() -> str:
    """Return a fresh URL-safe Fernet key (32 bytes base64url)."""
    return Fernet.generate_key().decode("ascii")


def get_or_create_master_key(session_factory: sessionmaker[Session]) -> str:
    """Return the install's master key, generating one on first call.

    The key lives under ``system_keys.name='repo_secrets_master'``.
    When the row is missing the function inserts one with a
    freshly-generated Fernet key.  Concurrent first-callers race on
    the UNIQUE(name) constraint; the loser re-reads the row.

    Args:
        session_factory: SQLAlchemy session factory.

    Returns:
        The persisted master key string (base64url, suitable for
        passing directly to :class:`Fernet`).

    Raises:
        Exception: When both the INSERT and the post-conflict
            re-read fail.  Callers in services should let this
            propagate — without the master key, nothing in the
            workspace-repo subsystem can run.
    """
    with session_factory() as session:
        row = session.scalar(select(SystemKey).where(SystemKey.name == MASTER_KEY_NAME))
        if row is not None:
            return row.value
        new_key = _generate_master_key()
        new_row = SystemKey(
            name=MASTER_KEY_NAME,
            value=new_key,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(new_row)
        try:
            session.commit()
            return new_key
        except Exception:  # noqa: BLE001 — re-read on UNIQUE conflict
            session.rollback()
            row = session.scalar(select(SystemKey).where(SystemKey.name == MASTER_KEY_NAME))
            if row is None:
                raise
            return row.value


def encrypt_value(plaintext: str, *, session_factory: sessionmaker[Session]) -> str:
    """Encrypt *plaintext* with the install master key.

    Args:
        plaintext: Cleartext to encrypt.  Must be a string; callers
            wanting to encrypt arbitrary bytes should base64url them
            first.
        session_factory: SQLAlchemy session factory used to fetch
            the master key (lazy get-or-create).

    Returns:
        Fernet token (URL-safe base64).  Two encryptions of the same
        plaintext produce different tokens because Fernet bakes in a
        fresh IV + timestamp on every call.
    """
    key = get_or_create_master_key(session_factory)
    fernet = Fernet(key.encode("ascii"))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(token: str, *, session_factory: sessionmaker[Session]) -> str:
    """Decrypt *token* produced by :func:`encrypt_value`.

    Args:
        token: Fernet token previously produced by
            :func:`encrypt_value` against the same install's master
            key.
        session_factory: SQLAlchemy session factory used to fetch
            the master key.

    Returns:
        The original cleartext string.

    Raises:
        SecretDecryptError: The ciphertext failed authentication —
            either tampered with, encrypted under a different key,
            or never a Fernet token to begin with.
    """
    key = get_or_create_master_key(session_factory)
    fernet = Fernet(key.encode("ascii"))
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptError(
            "ciphertext failed authentication; either tampered with or "
            "encrypted under a different master key"
        ) from exc
