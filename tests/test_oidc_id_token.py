"""The OIDC callback validates the id_token before trusting any claims.

Without signature/nonce/aud/iss verification the SSO flow accepted a
forged or replayed id_token.  These tests mint real RS256 tokens against
a throwaway keypair and pin every rejection path of
``verify_id_token``.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pointlessql.services import oidc as oidc_service

_ISSUER = "https://fake-idp.example"
_AUD = "test-client-id"
_JWKS_URI = "https://fake-idp.example/jwks"
_NONCE = "the-login-nonce"
_DISCOVERY: dict[str, Any] = {"issuer": _ISSUER, "jwks_uri": _JWKS_URI}


@pytest.fixture
def rsa_key() -> rsa.RSAPrivateKey:
    """A throwaway 2048-bit RSA signing key for the fake provider."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(key: rsa.RSAPrivateKey, *, kid: str = "test-key") -> dict[str, Any]:
    """Build a JWKS document exposing *key*'s public half."""
    jwk: dict[str, Any] = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def _id_token(key: rsa.RSAPrivateKey, *, kid: str = "test-key", **overrides: Any) -> str:
    """Mint a signed id_token, overriding any default claim."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "aud": _AUD,
        "sub": "user-123",
        "email": "sso@example.com",
        "nonce": _NONCE,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def _client(jwks: dict[str, Any]) -> AsyncMock:
    """An httpx client double whose GET returns *jwks*."""
    oidc_service._jwks_cache.clear()  # pyright: ignore[reportPrivateUsage]
    resp = MagicMock()
    resp.json.return_value = jwks
    resp.raise_for_status = MagicMock()
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = resp
    return client


@pytest.mark.asyncio
async def test_valid_token_returns_claims(rsa_key: rsa.RSAPrivateKey) -> None:
    """A well-formed token verifies and yields its claims."""
    token = _id_token(rsa_key)
    claims = await oidc_service.verify_id_token(
        _DISCOVERY, token, _AUD, _NONCE, _client(_jwks(rsa_key))
    )
    assert claims["sub"] == "user-123"
    assert claims["email"] == "sso@example.com"


@pytest.mark.asyncio
async def test_wrong_nonce_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    """A nonce that doesn't match the login request is rejected."""
    token = _id_token(rsa_key, nonce="attacker-nonce")
    with pytest.raises(oidc_service.OIDCError):
        await oidc_service.verify_id_token(_DISCOVERY, token, _AUD, _NONCE, _client(_jwks(rsa_key)))


@pytest.mark.asyncio
async def test_wrong_audience_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    """A token minted for another client is rejected."""
    token = _id_token(rsa_key, aud="some-other-client")
    with pytest.raises(oidc_service.OIDCError):
        await oidc_service.verify_id_token(_DISCOVERY, token, _AUD, _NONCE, _client(_jwks(rsa_key)))


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    """A token from an unexpected issuer is rejected."""
    token = _id_token(rsa_key, iss="https://evil-idp.example")
    with pytest.raises(oidc_service.OIDCError):
        await oidc_service.verify_id_token(_DISCOVERY, token, _AUD, _NONCE, _client(_jwks(rsa_key)))


@pytest.mark.asyncio
async def test_expired_token_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    """An expired token is rejected."""
    past = int(time.time()) - 3600
    token = _id_token(rsa_key, iat=past, exp=past + 60)
    with pytest.raises(oidc_service.OIDCError):
        await oidc_service.verify_id_token(_DISCOVERY, token, _AUD, _NONCE, _client(_jwks(rsa_key)))


@pytest.mark.asyncio
async def test_bad_signature_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    """A token signed by a different key fails signature verification."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _id_token(other)  # signed by `other` but JWKS exposes `rsa_key`
    with pytest.raises(oidc_service.OIDCError):
        await oidc_service.verify_id_token(_DISCOVERY, token, _AUD, _NONCE, _client(_jwks(rsa_key)))


@pytest.mark.asyncio
async def test_symmetric_algorithm_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    """An HS256 token (alg-confusion attempt) is refused outright."""
    now = int(time.time())
    forged = jwt.encode(
        {"iss": _ISSUER, "aud": _AUD, "sub": "x", "nonce": _NONCE, "exp": now + 300},
        "public-key-as-secret",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(oidc_service.OIDCError):
        await oidc_service.verify_id_token(
            _DISCOVERY, forged, _AUD, _NONCE, _client(_jwks(rsa_key))
        )
