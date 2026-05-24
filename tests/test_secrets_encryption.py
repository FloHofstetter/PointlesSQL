"""authenticated-encryption helper for at-rest secrets."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.services.secrets import (
    MASTER_KEY_NAME,
    SecretDecryptError,
    decrypt_value,
    encrypt_value,
    get_or_create_master_key,
)


def _factory(_test_engine: tuple[Engine, sessionmaker]) -> sessionmaker:  # type: ignore[type-arg]
    return _test_engine[1]


def test_encrypt_decrypt_roundtrip(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    plaintext = "ghp_dummy_token_value_for_test"  # pragma: allowlist secret
    token = encrypt_value(plaintext, session_factory=factory)
    assert token != plaintext
    assert decrypt_value(token, session_factory=factory) == plaintext


def test_two_encryptions_produce_different_tokens(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    plaintext = "same input"
    token_a = encrypt_value(plaintext, session_factory=factory)
    token_b = encrypt_value(plaintext, session_factory=factory)
    assert token_a != token_b
    assert decrypt_value(token_a, session_factory=factory) == plaintext
    assert decrypt_value(token_b, session_factory=factory) == plaintext


def test_master_key_get_or_create_idempotent(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    key_first = get_or_create_master_key(factory)
    key_second = get_or_create_master_key(factory)
    assert key_first == key_second
    # Sanity: it's a valid Fernet key.
    Fernet(key_first.encode("ascii"))


def test_decrypt_fails_on_tampered_token(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    plaintext = "secret"
    token = encrypt_value(plaintext, session_factory=factory)
    # Flip a byte in the middle of the token.  Fernet detects it via HMAC.
    mutated = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(SecretDecryptError):
        decrypt_value(mutated, session_factory=factory)


def test_master_key_named_in_system_keys(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    get_or_create_master_key(factory)
    from sqlalchemy import select

    from pointlessql.models.system_keys import SystemKey

    with factory() as session:
        rows = list(
            session.execute(select(SystemKey).where(SystemKey.name == MASTER_KEY_NAME)).scalars()
        )
    assert len(rows) == 1
    # We need *app* imported above to keep the test import-graph honest with the
    # rest of the test suite (some plugins eagerly bind app.state).
    assert app is not None
