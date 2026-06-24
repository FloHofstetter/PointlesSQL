"""IngestSource credential blobs are Fernet-encrypted at rest.

The ``secrets`` column carries connector credentials (S3 keys, DB
passwords, bearer tokens).  These tests pin the encrypt-on-write /
decrypt-on-read contract and the legacy-plaintext tolerance that lets
pre-encryption rows keep working until their next write.
"""

from __future__ import annotations

import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import IngestSource
from pointlessql.services.ingest._secrets import (  # pyright: ignore[reportPrivateUsage]
    decrypt_secrets,
    encrypt_secrets,
)


def test_round_trip() -> None:
    """A dict survives encrypt → decrypt unchanged."""
    factory = app.state.session_factory
    plain = {"aws_access_key_id": "AKIAEXAMPLE", "aws_secret_access_key": "shh"}
    assert decrypt_secrets(encrypt_secrets(plain, factory), factory) == plain


def test_token_is_opaque_ciphertext() -> None:
    """The stored token hides the cleartext and is not JSON."""
    factory = app.state.session_factory
    token = encrypt_secrets({"password": "hunter2"}, factory)
    assert "hunter2" not in token
    with pytest.raises(ValueError):
        json.loads(token)  # a Fernet token never parses as JSON


def test_legacy_plaintext_is_tolerated() -> None:
    """Rows written before encryption decrypt straight from JSON."""
    factory = app.state.session_factory
    assert decrypt_secrets('{"password": "old-plaintext"}', factory) == {
        "password": "old-plaintext"
    }


@pytest.mark.parametrize("stored", [None, "", "not-json-not-a-token"])
def test_unrecoverable_values_yield_empty(stored: str | None) -> None:
    """Absent or garbage column values degrade to an empty dict."""
    assert decrypt_secrets(stored, app.state.session_factory) == {}


@pytest.mark.asyncio
async def test_created_source_persists_ciphertext(admin_client: httpx.AsyncClient) -> None:
    """POST stores ciphertext; GET reports redacted keys only."""
    secret_value = "SUPER-SECRET-S3-KEY"
    res = await admin_client.post(
        "/api/ingest/sources",
        json={
            "name": "enc-test",
            "kind": "s3",
            "config": {"url": "s3://bucket/x.csv"},
            "secrets": {"aws_secret_access_key": secret_value},
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()["source"]
    source_id = body["id"]
    # The GET projection redacts the value but still reports the key.
    assert body["secrets"] == {"aws_secret_access_key": "***"}

    with app.state.session_factory() as session:
        row = session.get(IngestSource, source_id)
        assert row is not None
        stored = row.secrets
    # The persisted column is ciphertext: cleartext absent, not JSON.
    assert secret_value not in stored
    with pytest.raises(ValueError):
        json.loads(stored)
    # …and it decrypts back to the original.
    assert decrypt_secrets(stored, app.state.session_factory) == {
        "aws_secret_access_key": secret_value
    }
