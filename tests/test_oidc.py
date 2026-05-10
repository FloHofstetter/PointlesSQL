"""Tests for OIDC / OAuth2 service and routes."""

from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.models import Base
from pointlessql.services import auth
from pointlessql.services import oidc as oidc_service
from tests.conftest import seed_csrf

SECRET = "test-secret-key-for-unit-tests!!"

# A minimal OIDC discovery document for testing.
FAKE_DISCOVERY = {
    "issuer": "https://fake-idp.example",
    "authorization_endpoint": "https://fake-idp.example/authorize",
    "token_endpoint": "https://fake-idp.example/token",
    "userinfo_endpoint": "https://fake-idp.example/userinfo",
}

FAKE_DISCOVERY_URL = "https://fake-idp.example/.well-known/openid-configuration"


@pytest.fixture
def db_factory():
    """Create an in-memory SQLite database with the users table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


# ---------------------------------------------------------------------------
# Unit tests — PKCE
# ---------------------------------------------------------------------------


class TestGeneratePKCE:
    """PKCE code_verifier / code_challenge generation."""

    def test_verifier_length(self):
        verifier, _ = oidc_service.generate_pkce()
        assert 43 <= len(verifier) <= 128

    def test_challenge_is_sha256_of_verifier(self):
        verifier, challenge = oidc_service.generate_pkce()
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode()
        )
        assert challenge == expected

    def test_different_each_call(self):
        v1, _ = oidc_service.generate_pkce()
        v2, _ = oidc_service.generate_pkce()
        assert v1 != v2


# ---------------------------------------------------------------------------
# Unit tests — signed state cookie
# ---------------------------------------------------------------------------


class TestStateCookie:
    """HMAC-signed state cookie round-trip."""

    def test_sign_and_verify(self):
        payload = {"state": "abc123", "code_verifier": "xyz", "nonce": "n"}
        cookie = oidc_service.sign_state_cookie(payload, SECRET)
        result = oidc_service.verify_state_cookie(cookie, SECRET)
        assert result == payload

    def test_tampered_cookie_rejected(self):
        payload = {"state": "abc"}
        cookie = oidc_service.sign_state_cookie(payload, SECRET)
        # Flip a character in the signature.
        parts = cookie.split(".")
        parts[1] = parts[1][:-1] + ("a" if parts[1][-1] != "a" else "b")
        tampered = ".".join(parts)
        assert oidc_service.verify_state_cookie(tampered, SECRET) is None

    def test_wrong_secret_rejected(self):
        cookie = oidc_service.sign_state_cookie({"x": 1}, SECRET)
        assert oidc_service.verify_state_cookie(cookie, "wrong-secret") is None

    def test_malformed_cookie(self):
        assert oidc_service.verify_state_cookie("no-dot-here", SECRET) is None
        assert oidc_service.verify_state_cookie("", SECRET) is None


# ---------------------------------------------------------------------------
# Unit tests — build_authorize_url
# ---------------------------------------------------------------------------


class TestBuildAuthorizeURL:
    """Authorization URL construction."""

    def test_contains_all_params(self):
        url = oidc_service.build_authorize_url(
            FAKE_DISCOVERY,
            "my-client",
            "http://localhost/cb",
            "state123",
            "nonce456",
            "challenge789",
        )
        assert url.startswith("https://fake-idp.example/authorize?")
        assert "response_type=code" in url
        assert "client_id=my-client" in url
        assert "redirect_uri=http" in url
        assert "state=state123" in url
        assert "nonce=nonce456" in url
        assert "code_challenge=challenge789" in url
        assert "code_challenge_method=S256" in url
        assert "scope=openid+email+profile" in url


# ---------------------------------------------------------------------------
# Unit tests — fetch_discovery (cached)
# ---------------------------------------------------------------------------


class TestFetchDiscovery:
    """Discovery document fetching and caching."""

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        # Clear cache.
        oidc_service._discovery_cache.clear()

        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_DISCOVERY
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        result = await oidc_service.fetch_discovery(FAKE_DISCOVERY_URL, mock_client)
        assert result == FAKE_DISCOVERY
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_caches_result(self):
        oidc_service._discovery_cache.clear()

        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_DISCOVERY
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        await oidc_service.fetch_discovery(FAKE_DISCOVERY_URL, mock_client)
        await oidc_service.fetch_discovery(FAKE_DISCOVERY_URL, mock_client)

        # Only one HTTP call despite two invocations.
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_failure_raises(self):
        oidc_service._discovery_cache.clear()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(oidc_service.OIDCError, match="Failed to fetch"):
            await oidc_service.fetch_discovery(FAKE_DISCOVERY_URL, mock_client)


# ---------------------------------------------------------------------------
# Unit tests — exchange_code
# ---------------------------------------------------------------------------


class TestExchangeCode:
    """Token exchange via POST to token endpoint."""

    @pytest.mark.asyncio
    async def test_public_client(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "at", "id_token": "it"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        result = await oidc_service.exchange_code(
            FAKE_DISCOVERY,
            "code123",
            "verifier",
            "client-id",
            None,
            "http://localhost/cb",
            mock_client,
        )
        assert result["access_token"] == "at"

        # Verify no client_secret in the POST data.
        call_kwargs = mock_client.post.call_args
        assert "client_secret" not in call_kwargs.kwargs["data"]

    @pytest.mark.asyncio
    async def test_confidential_client(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "at"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        await oidc_service.exchange_code(
            FAKE_DISCOVERY,
            "code123",
            "verifier",
            "client-id",
            "client-secret",
            "http://localhost/cb",
            mock_client,
        )

        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["data"]["client_secret"] == "client-secret"

    @pytest.mark.asyncio
    async def test_exchange_failure_raises(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(oidc_service.OIDCError, match="Token exchange failed"):
            await oidc_service.exchange_code(
                FAKE_DISCOVERY,
                "c",
                "v",
                "cid",
                None,
                "http://x",
                mock_client,
            )


# ---------------------------------------------------------------------------
# Unit tests — fetch_userinfo
# ---------------------------------------------------------------------------


class TestFetchUserinfo:
    """Userinfo endpoint fetch."""

    @pytest.mark.asyncio
    async def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "sub": "user-123",
            "email": "u@x.com",
            "name": "User",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        info = await oidc_service.fetch_userinfo(FAKE_DISCOVERY, "token", mock_client)
        assert info["sub"] == "user-123"
        assert info["email"] == "u@x.com"

    @pytest.mark.asyncio
    async def test_missing_sub_raises(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"email": "u@x.com"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        with pytest.raises(oidc_service.OIDCError, match="missing 'sub'"):
            await oidc_service.fetch_userinfo(FAKE_DISCOVERY, "token", mock_client)


# ---------------------------------------------------------------------------
# Unit tests — find_or_create_oidc_user
# ---------------------------------------------------------------------------


class TestFindOrCreateOIDCUser:
    """User provisioning from OIDC claims."""

    def test_create_new_user(self, db_factory):
        user = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "new@test.com",
            "New User",
        )
        assert user.email == "new@test.com"
        assert user.oidc_provider == FAKE_DISCOVERY_URL
        assert user.oidc_subject == "sub-1"
        assert user.password_hash is None

    def test_first_oidc_user_is_admin(self, db_factory):
        user = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "first@test.com",
            "First",
        )
        assert user.is_admin is True

    def test_second_oidc_user_not_admin(self, db_factory):
        oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "first@test.com",
            "First",
        )
        user = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-2",
            "second@test.com",
            "Second",
        )
        assert user.is_admin is False

    def test_existing_oidc_user_returned(self, db_factory):
        user1 = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "u@test.com",
            "User",
        )
        user2 = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "u@test.com",
            "User",
        )
        assert user1.id == user2.id

    def test_links_existing_email_user(self, db_factory):
        # Create a local user first.
        auth.register(db_factory, "local@test.com", "Local User", "password123")

        # OIDC login with same email should link.
        user = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-oidc",
            "local@test.com",
            "OIDC Name",
        )
        assert user.oidc_provider == FAKE_DISCOVERY_URL
        assert user.oidc_subject == "sub-oidc"
        # Password still set (local account).
        assert user.password_hash is not None

    def test_updates_profile_on_existing(self, db_factory):
        oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "old@test.com",
            "Old Name",
        )
        user = oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "new@test.com",
            "New Name",
        )
        assert user.email == "new@test.com"
        assert user.display_name == "New Name"


# ---------------------------------------------------------------------------
# Route tests — SSO + callback
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_oidc_app():
    """Set up app state for OIDC route tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app.state.session_factory = factory

    from pointlessql.api.main import _TEMPLATES

    app.state.templates = _TEMPLATES

    from pointlessql.config import Settings

    app.state.settings = Settings(
        jupyter={"enabled": False},
        auth={"secret_key": SECRET},
        oidc={
            "discovery_url": FAKE_DISCOVERY_URL,
            "client_id": "test-client",
        },
    )

    mock_uc = AsyncMock()
    mock_uc.list_catalogs.return_value = []
    mock_uc.get_tree.return_value = []
    app.state.uc_client = mock_uc

    yield

    engine.dispose()


class TestSSORedirect:
    """GET /auth/sso initiates the OIDC flow."""

    @pytest.mark.asyncio
    async def test_redirects_to_provider(self):
        with patch(
            "pointlessql.api.auth_routes.oidc_service.fetch_discovery",
            new_callable=AsyncMock,
            return_value=FAKE_DISCOVERY,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get("/auth/sso")

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert location.startswith("https://fake-idp.example/authorize?")
            assert "code_challenge_method=S256" in location
            assert oidc_service.STATE_COOKIE_NAME in resp.cookies

    @pytest.mark.asyncio
    async def test_sso_disabled(self):
        app.state.settings.oidc.discovery_url = None

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/auth/sso")

        assert resp.status_code == 303
        assert "not+configured" in resp.headers["location"]

        # Restore.
        app.state.settings.oidc.discovery_url = FAKE_DISCOVERY_URL


class TestOIDCCallback:
    """GET /auth/callback handles the provider redirect."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        # Prepare a valid state cookie.
        state = "test-state-value"
        verifier = "test-verifier"
        cookie = oidc_service.sign_state_cookie(
            {"state": state, "code_verifier": verifier, "nonce": "n"},
            SECRET,
        )

        with (
            patch(
                "pointlessql.api.auth_routes.oidc_service.fetch_discovery",
                new_callable=AsyncMock,
                return_value=FAKE_DISCOVERY,
            ),
            patch(
                "pointlessql.api.auth_routes.oidc_service.exchange_code",
                new_callable=AsyncMock,
                return_value={"access_token": "at123"},
            ),
            patch(
                "pointlessql.api.auth_routes.oidc_service.fetch_userinfo",
                new_callable=AsyncMock,
                return_value={"sub": "oidc-sub", "email": "sso@test.com", "name": "SSO User"},
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
                cookies={oidc_service.STATE_COOKIE_NAME: cookie},
            ) as client:
                resp = await client.get(f"/auth/callback?code=authcode&state={state}")

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert auth.COOKIE_NAME in resp.cookies

    @pytest.mark.asyncio
    async def test_state_mismatch(self):
        cookie = oidc_service.sign_state_cookie(
            {"state": "expected", "code_verifier": "v", "nonce": "n"},
            SECRET,
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
            cookies={oidc_service.STATE_COOKIE_NAME: cookie},
        ) as client:
            resp = await client.get("/auth/callback?code=c&state=wrong")

        assert resp.status_code == 303
        assert "Invalid" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_missing_state_cookie(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/auth/callback?code=c&state=s")

        assert resp.status_code == 303
        assert "expired" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_provider_error(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                "/auth/callback?error=access_denied&error_description=User+cancelled"
            )

        assert resp.status_code == 303
        assert "cancelled" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_missing_code(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/auth/callback?state=s")

        assert resp.status_code == 303
        assert "Missing" in resp.headers["location"]


class TestLoginPageSSO:
    """Login page conditionally shows the SSO button."""

    @pytest.mark.asyncio
    async def test_shows_sso_button_when_enabled(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/login")

        assert resp.status_code == 200
        assert "Sign in with SSO" in resp.text

    @pytest.mark.asyncio
    async def test_hides_sso_button_when_disabled(self):
        app.state.settings.oidc.discovery_url = None

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/auth/login")

        assert resp.status_code == 200
        assert "Sign in with SSO" not in resp.text

        # Restore.
        app.state.settings.oidc.discovery_url = FAKE_DISCOVERY_URL


class TestOIDCUserCannotLocalLogin:
    """OIDC-only user (no password) cannot log in via email/password."""

    @pytest.mark.asyncio
    async def test_oidc_user_password_login_fails(self, db_factory):
        oidc_service.find_or_create_oidc_user(
            db_factory,
            FAKE_DISCOVERY_URL,
            "sub-1",
            "oidc@test.com",
            "OIDC User",
        )
        result = auth.login(db_factory, "oidc@test.com", "anypassword", SECRET)
        assert result is None


class TestLocalLoginWithOIDCEnabled:
    """Local email/password login still works when OIDC is enabled."""

    @pytest.mark.asyncio
    async def test_local_login_works(self):
        factory = app.state.session_factory
        auth.register(factory, "local@test.com", "Local", "password123")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            csrf_token = await seed_csrf(client)
            resp = await client.post(
                "/auth/login",
                data={
                    "email": "local@test.com",
                    "password": "password123",
                    "csrf_token": csrf_token,
                },
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert auth.COOKIE_NAME in resp.cookies
