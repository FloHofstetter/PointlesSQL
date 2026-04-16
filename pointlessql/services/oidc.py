"""OIDC / OAuth2 authorization-code flow with PKCE.

Implements the browser-redirect flow against any OpenID Connect
provider. No external OIDC library — the flow is simple enough to
build on top of httpx + PyJWT + the standard library.

The typical sequence is:

1. ``GET /auth/sso`` → generate PKCE pair, build authorize URL,
   store state in a signed cookie, redirect to provider.
2. Provider authenticates user, redirects to ``/auth/callback``.
3. ``GET /auth/callback`` → verify state cookie, exchange code for
   tokens, fetch userinfo, find-or-create local user, issue JWT.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import User
from pointlessql.services.auth import is_first_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OIDCError(Exception):
    """Human-readable OIDC failure suitable for display on the login page."""


# ---------------------------------------------------------------------------
# PKCE helpers (RFC 7636)
# ---------------------------------------------------------------------------


def generate_pkce() -> tuple[str, str]:
    """Generate a PKCE code-verifier and code-challenge pair.

    Returns:
        tuple[str, str]: ``(code_verifier, code_challenge)`` where
            the challenge is the Base64url-encoded SHA-256 of the verifier.
    """
    verifier_bytes = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


# ---------------------------------------------------------------------------
# Signed state cookie
# ---------------------------------------------------------------------------

_STATE_COOKIE_NAME = "pql_oidc_state"


def sign_state_cookie(payload: dict[str, Any], secret_key: str) -> str:
    """Serialize *payload* as JSON and sign with HMAC-SHA256.

    Args:
        payload: Arbitrary dict (must be JSON-serializable).
        secret_key: Application secret key for signing.

    Returns:
        str: ``<base64url-json>.<base64url-signature>``
    """
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_state_cookie(cookie: str, secret_key: str) -> dict[str, Any] | None:
    """Verify signature and decode a state cookie.

    Args:
        cookie: The cookie value produced by :func:`sign_state_cookie`.
        secret_key: Application secret key.

    Returns:
        dict[str, Any] | None: The original payload, or ``None`` if the
            signature is invalid or the cookie is malformed.
    """
    parts = cookie.split(".", 1)
    if len(parts) != 2:
        return None
    raw, sig = parts
    expected = hmac.new(secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(raw + "=="))
    except (json.JSONDecodeError, Exception):
        return None


# ---------------------------------------------------------------------------
# Discovery document (cached)
# ---------------------------------------------------------------------------

_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 300  # 5 minutes


async def fetch_discovery(
    discovery_url: str,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Fetch and cache the OpenID Connect discovery document.

    Args:
        discovery_url: The provider's ``/.well-known/openid-configuration``
            URL.
        client: An ``httpx.AsyncClient`` to use for the request.

    Returns:
        dict[str, Any]: The parsed discovery document.

    Raises:
        OIDCError: If the fetch fails or the response is not valid JSON.
    """
    now = time.monotonic()
    cached = _discovery_cache.get(discovery_url)
    if cached is not None and now - cached[0] < _CACHE_TTL:
        return cached[1]

    try:
        resp = await client.get(discovery_url, timeout=10)
        resp.raise_for_status()
        doc = resp.json()
    except httpx.HTTPError as exc:
        raise OIDCError(f"Failed to fetch OIDC discovery document: {exc}") from exc

    _discovery_cache[discovery_url] = (now, doc)
    return doc


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------


def build_authorize_url(
    discovery: dict[str, Any],
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    """Build the provider's authorization URL for a PKCE flow.

    Args:
        discovery: Parsed OIDC discovery document.
        client_id: OAuth2 client identifier.
        redirect_uri: Callback URL (``/auth/callback``).
        state: Random state parameter for CSRF protection.
        nonce: Random nonce bound into the id_token.
        code_challenge: PKCE S256 code challenge.

    Returns:
        str: Full authorization URL with query parameters.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


async def exchange_code(
    discovery: dict[str, Any],
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str | None,
    redirect_uri: str,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Exchange an authorization code for tokens.

    Args:
        discovery: Parsed OIDC discovery document.
        code: The authorization code from the callback.
        code_verifier: PKCE code verifier.
        client_id: OAuth2 client identifier.
        client_secret: Client secret (``None`` for public clients).
        redirect_uri: The same redirect URI used in the authorize request.
        client: An ``httpx.AsyncClient`` for the request.

    Returns:
        dict[str, Any]: Token response containing ``access_token``,
            ``id_token``, etc.

    Raises:
        OIDCError: If the token exchange fails.
    """
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret is not None:
        data["client_secret"] = client_secret

    try:
        resp = await client.post(
            discovery["token_endpoint"],
            data=data,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise OIDCError(f"Token exchange failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Userinfo
# ---------------------------------------------------------------------------


async def fetch_userinfo(
    discovery: dict[str, Any],
    access_token: str,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Fetch user claims from the provider's userinfo endpoint.

    Args:
        discovery: Parsed OIDC discovery document.
        access_token: Bearer token from the token exchange.
        client: An ``httpx.AsyncClient`` for the request.

    Returns:
        dict[str, Any]: Userinfo claims (at least ``sub``).

    Raises:
        OIDCError: If the request fails or ``sub`` is missing.
    """
    try:
        resp = await client.get(
            discovery["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        info = resp.json()
    except httpx.HTTPError as exc:
        raise OIDCError(f"Userinfo fetch failed: {exc}") from exc

    if "sub" not in info:
        raise OIDCError("Userinfo response missing 'sub' claim")

    return info


# ---------------------------------------------------------------------------
# User provisioning
# ---------------------------------------------------------------------------


def find_or_create_oidc_user(
    factory: sessionmaker[Session],
    provider: str,
    subject: str,
    email: str,
    display_name: str,
) -> User:
    """Find an existing OIDC user or create/link one.

    Lookup order:

    1. Match on ``(oidc_provider, oidc_subject)`` — return existing.
    2. Match on ``email`` — link OIDC identity to the local account.
    3. No match — create a new user (``password_hash=None``).

    The first user ever created becomes admin (same bootstrap rule as
    local registration).

    Args:
        factory: SQLAlchemy session factory.
        provider: OIDC discovery URL acting as provider identifier.
        subject: The ``sub`` claim from the provider.
        email: Email from the provider's userinfo.
        display_name: Display name from the provider's userinfo.

    Returns:
        User: The matched or newly created user.
    """
    email = email.strip().lower()
    display_name = display_name.strip() or email

    with factory() as session:
        # 1. Existing OIDC identity
        user = (
            session.query(User)
            .filter(User.oidc_provider == provider, User.oidc_subject == subject)
            .first()
        )
        if user is not None:
            # Refresh profile from provider
            user.email = email
            user.display_name = display_name
            session.commit()
            session.refresh(user)
            logger.info("OIDC login: existing user id=%d", user.id)
            return user

        # 2. Local user with same email — link OIDC identity
        user = session.query(User).filter(User.email == email).first()
        if user is not None:
            user.oidc_provider = provider
            user.oidc_subject = subject
            user.display_name = display_name
            session.commit()
            session.refresh(user)
            logger.info("OIDC login: linked to existing user id=%d", user.id)
            return user

        # 3. Brand-new user
        first_user = is_first_user(factory)
        new_user = User(
            email=email,
            display_name=display_name,
            password_hash=None,
            is_admin=first_user,
            created_at=datetime.datetime.now(datetime.UTC),
            oidc_provider=provider,
            oidc_subject=subject,
        )
        try:
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            logger.info(
                "OIDC login: created user id=%d (is_admin=%s)",
                new_user.id,
                first_user,
            )
            return new_user
        except IntegrityError:
            session.rollback()
            # Race condition — another request created the user first.
            user = (
                session.query(User)
                .filter(
                    User.oidc_provider == provider,
                    User.oidc_subject == subject,
                )
                .first()
            )
            if user is not None:
                return user
            raise OIDCError("Failed to create OIDC user (concurrent conflict)")
