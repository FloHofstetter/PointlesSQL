"""AuditSink credential fields are Fernet-encrypted at rest.

``config_json`` mixes non-secret connection fields with credentials
(HMAC secret, AWS secret access key, session token).  These tests pin
the field-level encrypt-on-write / decrypt-on-read contract, the
legacy-plaintext tolerance, and that non-secret fields stay readable.
"""

from __future__ import annotations

import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AuditSink
from pointlessql.services.audit._sink_secrets import (  # pyright: ignore[reportPrivateUsage]
    SINK_SECRET_KEYS,
    decrypt_sink_secrets,
    encrypt_sink_secrets,
)
from pointlessql.services.audit.sinks import (
    _decode_config,  # pyright: ignore[reportPrivateUsage]
)


def test_round_trip_only_touches_secret_keys() -> None:
    """Secrets encrypt to opaque tokens; other fields stay verbatim."""
    factory = app.state.session_factory
    cfg = {"bucket": "b", "region": "us-east-1", "secret_access_key": "shh"}
    enc = encrypt_sink_secrets(cfg, factory)
    assert enc["bucket"] == "b"
    assert enc["region"] == "us-east-1"
    assert enc["secret_access_key"] != "shh"
    assert "shh" not in enc["secret_access_key"]
    assert decrypt_sink_secrets(enc, factory) == cfg


def test_legacy_plaintext_is_tolerated() -> None:
    """A pre-encryption plaintext secret decrypts to itself."""
    factory = app.state.session_factory
    assert decrypt_sink_secrets({"secret_access_key": "legacy"}, factory) == {
        "secret_access_key": "legacy"
    }


def test_secret_keys_match_redaction_set() -> None:
    """Encryption set is exactly the keys the GET path redacts."""
    assert SINK_SECRET_KEYS == frozenset({"hmac_secret", "secret_access_key", "session_token"})


@pytest.mark.asyncio
async def test_created_sink_persists_ciphertext(admin_client: httpx.AsyncClient) -> None:
    """POST stores ciphertext secrets; GET redacts; dispatch decrypts."""
    secret = "AWS-SECRET-DO-NOT-LEAK"
    res = await admin_client.post(
        "/api/admin/audit-sinks",
        json={
            "name": "enc-s3-sink",
            "type": "s3",
            "config": {
                "bucket": "audit-bucket",
                "region": "eu-central-1",
                "access_key_id": "AKIAEXAMPLE",
                "secret_access_key": secret,
            },
        },
    )
    assert res.status_code == 200, res.text
    # GET projection redacts the secret but keeps non-secret fields.
    cfg_view = res.json()["config"]
    assert cfg_view["secret_access_key"] == "<redacted>"
    assert cfg_view["bucket"] == "audit-bucket"
    assert cfg_view["access_key_id"] == "AKIAEXAMPLE"

    sink_id = res.json()["id"]
    with app.state.session_factory() as session:
        row = session.get(AuditSink, sink_id)
        assert row is not None
        stored = row.config_json
    parsed = json.loads(stored)
    # The credential is ciphertext at rest; non-secret fields are clear.
    assert secret not in stored
    assert parsed["secret_access_key"] != secret
    assert parsed["bucket"] == "audit-bucket"
    # The dispatch decode recovers the cleartext for delivery.
    with app.state.session_factory() as session:
        row = session.get(AuditSink, sink_id)
        assert row is not None
        decoded = _decode_config(row, app.state.session_factory)
    assert decoded["secret_access_key"] == secret
