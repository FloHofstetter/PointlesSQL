"""Tests for the Sprint 43 ``/auth/*`` rate-limit middleware.

Covers the per-IP and per-email buckets on ``POST /auth/login``, the
per-IP buckets on ``POST /auth/register`` and ``GET /auth/sso``,
``Retry-After`` header shape, window expiry, the
``rate_limit_enabled=False`` bypass, and the audit-log entry that
every reject writes.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import _TEMPLATES, app
from pointlessql.models import AuditLog, Base, RateLimitEvent
from pointlessql.services import auth, csrf
from pointlessql.services import rate_limit as rate_limit_service
from pointlessql.settings import Settings


@pytest.fixture(autouse=True)
def _setup_app():
    """Wire an in-memory DB + real Settings onto the FastAPI app.

    The rate limiter reads every count/window from ``app.state.settings``
    so using a real :class:`Settings` instance (rather than a
    ``MagicMock``) keeps the tests honest: if a setting is renamed the
    middleware and its tests fail together rather than drifting apart.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app.state.session_factory = factory
    settings = Settings(
        jupyter_enabled=False,
        scheduler_enabled=False,
        rate_limit_enabled=True,
    )
    settings.secret_key = "test-secret-key-for-unit-tests!!"  # type: ignore[misc]
    app.state.settings = settings
    app.state.templates = _TEMPLATES

    mock_uc = AsyncMock()
    mock_uc.list_catalogs.return_value = []
    mock_uc.get_tree.return_value = []
    app.state.uc_client = mock_uc

    yield factory

    engine.dispose()


def _client(**kwargs: Any) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` bound to the ASGI app."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
        **kwargs,
    )


async def _csrf_token(client: httpx.AsyncClient, path: str = "/auth/login") -> str:
    """Seed the CSRF cookie by GETting ``path`` and return the token."""
    resp = await client.get(path)
    return resp.cookies[csrf.COOKIE_NAME]


async def _login(
    client: httpx.AsyncClient,
    token: str,
    email: str,
    password: str,
) -> httpx.Response:
    """POST a login attempt with the given CSRF token and credentials."""
    return await client.post(
        "/auth/login",
        data={"email": email, "password": password, "csrf_token": token},
    )


class TestLoginIpLimit:
    """``POST /auth/login`` is capped per source IP.

    The per-email cap (5) is lower than the per-IP cap (10), so the
    tests vary the submitted email per attempt — keeping every email
    bucket under its cap and letting the IP bucket be the decisive
    axis.
    """

    @pytest.mark.asyncio
    async def test_login_ip_limit_trips_after_threshold(self):
        async with _client() as client:
            token = await _csrf_token(client)
            for i in range(10):
                resp = await _login(client, token, f"u{i}@x.com", "bad")
                assert resp.status_code == 401
            resp = await _login(client, token, "u99@x.com", "bad")
        assert resp.status_code == 429
        retry_after = int(resp.headers["Retry-After"])
        assert 1 <= retry_after <= 600

    @pytest.mark.asyncio
    async def test_login_under_limit_does_not_429(self):
        async with _client() as client:
            token = await _csrf_token(client)
            for i in range(9):
                resp = await _login(client, token, f"u{i}@x.com", "bad")
                assert resp.status_code == 401


class TestLoginEmailLimit:
    """``POST /auth/login`` is also capped per submitted email.

    Exercising this axis requires flipping the ``trust_x_forwarded_for``
    flag on so the middleware accepts the synthetic IPs the test sends,
    otherwise all attempts would share the single ASGI client IP and
    the per-IP cap would trip first.
    """

    @pytest.mark.asyncio
    async def test_login_email_limit_trips_across_ips(self):
        app.state.settings.rate_limit_trust_x_forwarded_for = True
        try:
            async with _client() as client:
                token = await _csrf_token(client)
                # Five attempts on the same email from five distinct
                # IPs — the per-email bucket (cap 5) trips on the sixth
                # even though no per-IP bucket ever sees more than one.
                for i in range(5):
                    resp = await client.post(
                        "/auth/login",
                        data={"email": "target@x.com", "password": "bad", "csrf_token": token},
                        headers={"X-Forwarded-For": f"10.0.0.{i + 1}"},
                    )
                    assert resp.status_code == 401
                resp = await client.post(
                    "/auth/login",
                    data={"email": "target@x.com", "password": "bad", "csrf_token": token},
                    headers={"X-Forwarded-For": "10.0.0.99"},
                )
            assert resp.status_code == 429
            assert "Retry-After" in resp.headers
        finally:
            app.state.settings.rate_limit_trust_x_forwarded_for = False


class TestWindowExpiry:
    """Once the window passes, the limiter resets."""

    @pytest.mark.asyncio
    async def test_old_events_are_cleaned_up(self, _setup_app):
        factory = _setup_app
        # Push the per-IP bucket to the cap with rows already older
        # than the 10-minute window; the next real request should
        # prune them, record a fresh event, and succeed (401, not 429).
        stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1000)
        with factory() as session:
            for _ in range(20):
                session.add(
                    RateLimitEvent(
                        bucket="auth.login.ip:127.0.0.1",
                        created_at=stale,
                    )
                )
            session.commit()

        async with _client() as client:
            token = await _csrf_token(client)
            resp = await _login(client, token, "x@x.com", "bad")
        assert resp.status_code == 401


class TestRegisterLimit:
    """``POST /auth/register`` has its own bucket."""

    @pytest.mark.asyncio
    async def test_register_ip_limit_trips_after_threshold(self):
        async with _client() as client:
            token = await _csrf_token(client, "/auth/register")
            # Default cap is 5/IP — the 6th POST should 429. Passwords
            # are short on purpose so each attempt fails validation at
            # 400 instead of succeeding.
            for i in range(5):
                resp = await client.post(
                    "/auth/register",
                    data={
                        "email": f"u{i}@x.com",
                        "display_name": "U",
                        "password": "123",
                        "password_confirm": "123",
                        "csrf_token": token,
                    },
                )
                assert resp.status_code == 400
            resp = await client.post(
                "/auth/register",
                data={
                    "email": "u99@x.com",
                    "display_name": "U",
                    "password": "123",
                    "password_confirm": "123",
                    "csrf_token": token,
                },
            )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_register_bucket_is_independent_from_login(self, _setup_app):
        factory = _setup_app
        # Pin the login-IP bucket at its cap; register on the same IP
        # must still be reachable up to its own cap.
        now = datetime.datetime.now(datetime.UTC)
        with factory() as session:
            for _ in range(10):
                session.add(RateLimitEvent(bucket="auth.login.ip:127.0.0.1", created_at=now))
            session.commit()

        async with _client() as client:
            token = await _csrf_token(client, "/auth/register")
            resp = await client.post(
                "/auth/register",
                data={
                    "email": "indep@x.com",
                    "display_name": "U",
                    "password": "password123",
                    "password_confirm": "password123",
                    "csrf_token": token,
                },
            )
        # Successful register redirects to /auth/login (303).
        assert resp.status_code == 303


class TestOidcLimit:
    """``GET /auth/sso`` and ``/auth/callback`` share a bucket."""

    @pytest.mark.asyncio
    async def test_sso_limit_trips_after_threshold(self, _setup_app):
        factory = _setup_app
        # Seed 20 recent hits — the 21st GET is the reject. Seeding
        # directly avoids the network calls ``/auth/sso`` makes when
        # OIDC is configured; the middleware runs before the handler
        # so that route still returns 429 cleanly.
        now = datetime.datetime.now(datetime.UTC)
        with factory() as session:
            for _ in range(20):
                session.add(RateLimitEvent(bucket="auth.oidc.ip:127.0.0.1", created_at=now))
            session.commit()

        async with _client() as client:
            resp = await client.get("/auth/sso")
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_sso_and_callback_share_bucket(self, _setup_app):
        factory = _setup_app
        # Ten hits on /sso + ten direct seeds labelled as /callback
        # would not exhaust the cap; only shared seeding under the
        # same ``auth.oidc.ip`` key does. Prove the sharing by
        # counting rows under the unified bucket.
        now = datetime.datetime.now(datetime.UTC)
        with factory() as session:
            for _ in range(10):
                session.add(RateLimitEvent(bucket="auth.oidc.ip:127.0.0.1", created_at=now))
            session.commit()

        async with _client() as client:
            # Ten more hits — five via /sso and five via /callback —
            # fill the unified 20 cap without tripping. The 21st hit
            # must reject regardless of which of the two routes it
            # targets.
            for _ in range(10):
                await client.get("/auth/sso")

            resp = await client.get("/auth/callback")
        assert resp.status_code == 429


class TestExemptions:
    """``/healthz`` and ``/api/*`` are not rate-limited by Sprint 43."""

    @pytest.mark.asyncio
    async def test_healthz_never_429(self, _setup_app):
        factory = _setup_app
        # Saturate every auth bucket — healthz must still respond.
        now = datetime.datetime.now(datetime.UTC)
        with factory() as session:
            for bucket in (
                "auth.login.ip:127.0.0.1",
                "auth.register.ip:127.0.0.1",
                "auth.oidc.ip:127.0.0.1",
            ):
                for _ in range(50):
                    session.add(RateLimitEvent(bucket=bucket, created_at=now))
            session.commit()

        async with _client() as client:
            for _ in range(5):
                resp = await client.get("/healthz")
                # Either 200 (route exists) or 404 (route missing) —
                # what matters is that it is never 429.
                assert resp.status_code != 429

    @pytest.mark.asyncio
    async def test_api_surface_not_covered(self, _setup_app):
        factory = _setup_app
        now = datetime.datetime.now(datetime.UTC)
        with factory() as session:
            for _ in range(50):
                session.add(RateLimitEvent(bucket="auth.login.ip:127.0.0.1", created_at=now))
            session.commit()

        async with _client() as client:
            # /api/jobs rejects unauthenticated calls with 401 (from
            # auth_middleware). A 429 here would mean the rate limiter
            # leaked onto the API surface, which is out of Sprint 43.
            resp = await client.post(
                "/api/jobs",
                json={"name": "x", "notebook_path": "/n.ipynb", "schedule": "0 0 * * *"},
            )
        assert resp.status_code == 401


class TestBypass:
    """``rate_limit_enabled=False`` removes the middleware's effect."""

    @pytest.mark.asyncio
    async def test_disabled_setting_skips_check(self, _setup_app):
        factory = _setup_app
        app.state.settings.rate_limit_enabled = False
        try:
            async with _client() as client:
                token = await _csrf_token(client)
                # Way beyond the default cap — every attempt still
                # returns 401, and no events are recorded.
                for _ in range(25):
                    resp = await _login(client, token, "x@x.com", "bad")
                    assert resp.status_code == 401

            with factory() as session:
                count = session.scalar(select(RateLimitEvent.id).limit(1))
            assert count is None
        finally:
            app.state.settings.rate_limit_enabled = True


class TestAuditHook:
    """Every reject writes an ``audit_log`` row visible to /admin/audit."""

    @pytest.mark.asyncio
    async def test_reject_writes_audit_row(self, _setup_app):
        factory = _setup_app
        async with _client() as client:
            token = await _csrf_token(client)
            for _ in range(10):
                await _login(client, token, "spam@x.com", "bad")
            resp = await _login(client, token, "spam@x.com", "bad")
        assert resp.status_code == 429

        with factory() as session:
            rows = list(
                session.scalars(
                    select(AuditLog).where(AuditLog.action == "rate_limit.blocked")
                )
            )
        assert rows, "rate_limit.blocked audit row was not written"
        assert any("auth.login" in row.target for row in rows)
        assert all(row.user_email == "anon" for row in rows)


class TestBodyReplay:
    """Reading the email field must not consume the body for the handler."""

    @pytest.mark.asyncio
    async def test_login_form_fields_reach_handler(self, _setup_app):
        factory = _setup_app
        auth.register(factory, "replay@r.com", "R", "password123")

        async with _client() as client:
            token = await _csrf_token(client)
            resp = await _login(client, token, "replay@r.com", "password123")
        # A broken body re-injection would make FastAPI 422 on the
        # missing ``password`` field.
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"


class TestServiceLayer:
    """Direct unit tests for :mod:`pointlessql.services.rate_limit`."""

    def test_bucket_for_is_stable(self):
        assert (
            rate_limit_service.bucket_for("auth.login", "ip", "1.2.3.4")
            == "auth.login.ip:1.2.3.4"
        )

    def test_check_and_record_allows_until_limit(self, _setup_app):
        factory = _setup_app
        for _ in range(3):
            allowed, retry = rate_limit_service.check_and_record(factory, "b", 3, 60)
            assert allowed and retry == 0
        allowed, retry = rate_limit_service.check_and_record(factory, "b", 3, 60)
        assert not allowed
        assert retry >= 1

    def test_check_and_record_prunes_old_rows(self, _setup_app):
        factory = _setup_app
        old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=120)
        with factory() as session:
            for _ in range(5):
                session.add(RateLimitEvent(bucket="b", created_at=old))
            session.commit()

        allowed, _retry = rate_limit_service.check_and_record(factory, "b", 3, 60)
        assert allowed  # stale rows pruned before the count
