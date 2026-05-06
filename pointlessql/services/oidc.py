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

from pointlessql.exceptions import PointlessSQLError
from pointlessql.models import User, Workspace
from pointlessql.services.auth import is_first_user
from pointlessql.settings import GroupMapping, Settings

logger = logging.getLogger(__name__)


def _http_timeout() -> float:
    """Return the configured OIDC HTTP timeout in seconds.

    Instantiated per call so test overrides of
    ``POINTLESSQL_OIDC_HTTP_TIMEOUT_SECONDS`` take effect without
    re-importing the module — matches the per-request settings
    pattern used elsewhere in the codebase.
    """
    return Settings().oidc.http_timeout_seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OIDCError(PointlessSQLError):
    """Human-readable OIDC failure suitable for display on the login page.

    Attributes:
        status_code: Always 401.
        error_code: Always ``"oidc_error"``.
    """

    status_code: int = 401
    error_code: str = "oidc_error"


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

STATE_COOKIE_NAME = "pql_oidc_state"


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
    except json.JSONDecodeError, ValueError, UnicodeDecodeError:
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
        resp = await client.get(discovery_url, timeout=_http_timeout())
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
    *,
    scope: str = "openid email profile",
) -> str:
    """Build the provider's authorization URL for a PKCE flow.

    Args:
        discovery: Parsed OIDC discovery document.
        client_id: OAuth2 client identifier.
        redirect_uri: Callback URL (``/auth/callback``).
        state: Random state parameter for CSRF protection.
        nonce: Random nonce bound into the id_token.
        code_challenge: PKCE S256 code challenge.
        scope: Space-separated OAuth2 scope string.  Defaults to
            ``"openid email profile"``; pass :attr:`OIDCSettings.scope`
            to opt into the configurable value without forcing every
            existing caller to thread it through.

    Returns:
        str: Full authorization URL with query parameters.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
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
            timeout=_http_timeout(),
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
            timeout=_http_timeout(),
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


def _resolve_group_mapping(
    factory: sessionmaker[Session],
    groups: list[str],
    group_map: dict[str, GroupMapping],
) -> tuple[int | None, bool, bool, bool]:
    """Apply :attr:`OIDCSettings.parsed_group_map` to *groups*.

    Args:
        factory: SQLAlchemy session factory — used to verify the
            mapped workspace exists before honouring the override.
        groups: Group claim values from the IdP (already coerced to
            ``list[str]``).  May be empty when the IdP omits the
            claim.
        group_map: Parsed mapping table from
            :attr:`OIDCSettings.parsed_group_map`.

    Returns:
        ``(workspace_id, is_admin, is_supervisor, is_auditor)`` —
        the union of every matching group's grant.
        ``workspace_id is None`` means "leave the user's existing
        ``default_workspace_id`` alone".  A mapped workspace ID that
        doesn't resolve in the DB falls through to ``None`` and logs
        a warning so federation never silently drops a user into a
        ghost tenant.
    """
    if not groups or not group_map:
        return (None, False, False, False)
    matched = [group_map[g] for g in groups if g in group_map]
    if not matched:
        return (None, False, False, False)

    is_admin = any(m.is_admin for m in matched)
    is_supervisor = any(m.is_supervisor for m in matched)
    is_auditor = any(m.is_auditor for m in matched)

    workspace_id: int | None = None
    for m in matched:
        if m.workspace_id is not None:
            workspace_id = m.workspace_id
            break

    if workspace_id is not None:
        with factory() as session:
            ws = session.get(Workspace, workspace_id)
            if ws is None:
                logger.warning(
                    "OIDC group_map references workspace_id=%d which does not exist; "
                    "falling back to default_workspace_id",
                    workspace_id,
                )
                workspace_id = None

    return (workspace_id, is_admin, is_supervisor, is_auditor)


def find_or_create_oidc_user(
    factory: sessionmaker[Session],
    provider: str,
    subject: str,
    email: str,
    display_name: str,
    *,
    groups: list[str] | None = None,
    group_map: dict[str, GroupMapping] | None = None,
) -> User:
    """Find an existing OIDC user or create/link one.

    Lookup order:

    1. Match on ``(oidc_provider, oidc_subject)`` — return existing.
    2. Match on ``email`` — link OIDC identity to the local account.
    3. No match — create a new user (``password_hash=None``).

    The first user ever created becomes admin (same bootstrap rule as
    local registration).

    When *groups* + *group_map* are supplied, the function
    additionally:

    * Persists the groups list to ``oidc_groups_json`` for audit
      visibility (snapshotted on every login so a stale mapping ages
      out naturally).
    * Routes the user to the workspace named in the first matching
      mapping (overrides the default_workspace_id).
    * Unions the ``admin / supervisor / auditor`` scope flags from
      every matching mapping.

    Args:
        factory: SQLAlchemy session factory.
        provider: OIDC discovery URL acting as provider identifier.
        subject: The ``sub`` claim from the provider.
        email: Email from the provider's userinfo.
        display_name: Display name from the provider's userinfo.
        groups: Optional groups-claim values; an empty list or
            ``None`` skips the mapping step.
        group_map: Optional mapping from
            :attr:`OIDCSettings.parsed_group_map`.  ``None`` when the
            install hasn't configured the feature.

    Returns:
        User: The matched or newly created user.

    Raises:
        OIDCError: If a concurrent conflict prevents user creation.
    """
    email = email.strip().lower()
    display_name = display_name.strip() or email
    groups_clean = [str(g).strip() for g in (groups or []) if str(g).strip()]
    groups_json: str | None = json.dumps(groups_clean) if groups_clean else None
    ws_override, group_admin, group_supervisor, group_auditor = _resolve_group_mapping(
        factory, groups_clean, group_map or {}
    )

    with factory() as session:
        # 1. Existing OIDC identity
        user = (
            session.query(User)
            .filter(User.oidc_provider == provider, User.oidc_subject == subject)
            .first()
        )
        if user is not None:
            # Refresh profile + group-derived state from provider.
            user.email = email
            user.display_name = display_name
            user.oidc_groups_json = groups_json
            if ws_override is not None:
                user.default_workspace_id = ws_override
            user.is_supervisor = group_supervisor
            user.is_auditor = group_auditor
            if group_admin:
                user.is_admin = True
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
            user.oidc_groups_json = groups_json
            if ws_override is not None:
                user.default_workspace_id = ws_override
            user.is_supervisor = group_supervisor
            user.is_auditor = group_auditor
            if group_admin:
                user.is_admin = True
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
            is_admin=first_user or group_admin,
            is_supervisor=group_supervisor,
            is_auditor=group_auditor,
            created_at=datetime.datetime.now(datetime.UTC),
            oidc_provider=provider,
            oidc_subject=subject,
            oidc_groups_json=groups_json,
            default_workspace_id=ws_override or 1,
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
