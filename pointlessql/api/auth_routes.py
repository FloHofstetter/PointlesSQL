"""Authentication routes — login, register, logout, current user, OIDC SSO."""

from __future__ import annotations

import secrets
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pointlessql.services import auth, csrf
from pointlessql.services import oidc as oidc_service
from pointlessql.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def _factory(request: Request):
    """Return the DB session factory from app state."""
    return request.app.state.session_factory


def _settings(request: Request) -> Settings:
    """Return the Settings instance from app state."""
    return request.app.state.settings


def _oidc_redirect_uri(request: Request, settings: Settings) -> str:
    """Build the OIDC callback redirect URI.

    Uses ``POINTLESSQL_BASE_URL`` when set so the URI is correct behind
    reverse proxies or inside Docker. Falls back to deriving the URI
    from the incoming request.
    """
    if settings.server.base_url:
        return settings.server.base_url.rstrip("/") + "/auth/callback"
    return str(request.url_for("oidc_callback"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    """Render the login page."""
    settings = _settings(request)
    return _templates(request).TemplateResponse(
        request,
        "pages/login.html",
        {
            "error": error,
            "hide_sidebar": True,
            "oidc_enabled": settings.oidc.enabled,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(),
    password: str = Form(),
):
    """Verify credentials and set session cookie."""
    settings = _settings(request)
    token = auth.login(
        _factory(request),
        email,
        password,
        settings.auth.secret_key,
        settings.auth.jwt_expiry_hours,
    )
    if token is None:
        return _templates(request).TemplateResponse(
            request,
            "pages/login.html",
            {"error": "Invalid email or password.", "hide_sidebar": True},
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.auth.jwt_expiry_hours * 3600,
    )
    # Rotate the CSRF cookie on successful login — standard token
    # fixation prevention, matching the auth cookie's attributes.
    response.set_cookie(
        csrf.COOKIE_NAME,
        csrf.generate_token(),
        httponly=True,
        samesite="lax",
        max_age=settings.auth.jwt_expiry_hours * 3600,
        path="/",
    )
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    """Render the register page."""
    first_user = auth.is_first_user(_factory(request))
    return _templates(request).TemplateResponse(
        request,
        "pages/register.html",
        {"error": error, "first_user": first_user, "hide_sidebar": True},
    )


@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(),
    display_name: str = Form(),
    password: str = Form(),
    password_confirm: str = Form(),
):
    """Create a new user and redirect to login."""
    factory = _factory(request)

    def _reg_error(msg: str, status: int = 400):
        ctx = {
            "error": msg,
            "first_user": auth.is_first_user(factory),
            "hide_sidebar": True,
        }
        return _templates(request).TemplateResponse(
            request,
            "pages/register.html",
            ctx,
            status_code=status,
        )

    if password != password_confirm:
        return _reg_error("Passwords do not match.")

    if len(password) < 8:
        return _reg_error("Password must be at least 8 characters.")

    user = auth.register(factory, email, display_name, password)
    if user is None:
        return _reg_error("An account with that email already exists.", 409)

    return RedirectResponse(url="/auth/login", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    """Clear the session cookie and redirect to login."""
    settings = _settings(request)
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME)
    # Rotate the CSRF cookie alongside the auth cookie. Deleting it
    # would just force the middleware to re-issue a fresh one on the
    # redirect target; rotating in place keeps the token bound to the
    # new anonymous session and makes the state change observable.
    response.set_cookie(
        csrf.COOKIE_NAME,
        csrf.generate_token(),
        httponly=True,
        samesite="lax",
        max_age=settings.auth.jwt_expiry_hours * 3600,
        path="/",
    )
    return response


@router.get("/me")
async def current_user(request: Request):
    """Return the current authenticated user as JSON."""
    user = getattr(request.state, "user", None)
    if user is None:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse(user)


# ---------------------------------------------------------------------------
# OIDC / SSO
# ---------------------------------------------------------------------------


@router.get("/sso")
async def sso_redirect(request: Request):
    """Initiate OIDC authorization-code flow with PKCE."""
    settings = _settings(request)
    if not settings.oidc.enabled:
        return RedirectResponse(url="/auth/login?error=SSO+is+not+configured", status_code=303)

    redirect_uri = _oidc_redirect_uri(request, settings)

    async with httpx.AsyncClient() as client:
        discovery = await oidc_service.fetch_discovery(
            settings.oidc.discovery_url,  # type: ignore[arg-type]
            client,  # type: ignore[arg-type]
        )

    code_verifier, code_challenge = oidc_service.generate_pkce()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    authorize_url = oidc_service.build_authorize_url(
        discovery,
        settings.oidc.client_id,  # type: ignore[arg-type]
        redirect_uri,
        state,
        nonce,
        code_challenge,
    )

    cookie_value = oidc_service.sign_state_cookie(
        {"state": state, "code_verifier": code_verifier, "nonce": nonce},
        settings.auth.secret_key,
    )

    response = RedirectResponse(url=authorize_url, status_code=302)
    response.set_cookie(
        oidc_service.STATE_COOKIE_NAME,
        cookie_value,
        httponly=True,
        samesite="lax",
        max_age=300,
    )
    return response


@router.get("/callback")
async def oidc_callback(request: Request):
    """Handle the OIDC provider redirect after authentication."""
    settings = _settings(request)

    # Provider may return an error directly.
    if error := request.query_params.get("error"):
        desc = request.query_params.get("error_description", error)
        return RedirectResponse(
            url=f"/auth/login?error={quote(desc)}",
            status_code=303,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return RedirectResponse(
            url="/auth/login?error=Missing+code+or+state",
            status_code=303,
        )

    # Verify state cookie.
    cookie_raw = request.cookies.get(oidc_service.STATE_COOKIE_NAME)
    if cookie_raw is None:
        return RedirectResponse(
            url="/auth/login?error=SSO+session+expired",
            status_code=303,
        )

    cookie_payload = oidc_service.verify_state_cookie(cookie_raw, settings.auth.secret_key)
    if cookie_payload is None or cookie_payload.get("state") != state:
        return RedirectResponse(
            url="/auth/login?error=Invalid+SSO+state",
            status_code=303,
        )

    redirect_uri = _oidc_redirect_uri(request, settings)

    try:
        async with httpx.AsyncClient() as client:
            discovery = await oidc_service.fetch_discovery(
                settings.oidc.discovery_url,  # type: ignore[arg-type]
                client,  # type: ignore[arg-type]
            )
            tokens = await oidc_service.exchange_code(
                discovery,
                code,
                cookie_payload["code_verifier"],
                settings.oidc.client_id,  # type: ignore[arg-type]
                settings.oidc.client_secret,
                redirect_uri,
                client,
            )
            userinfo = await oidc_service.fetch_userinfo(
                discovery,
                tokens["access_token"],
                client,
            )
    except oidc_service.OIDCError as exc:
        return RedirectResponse(
            url=f"/auth/login?error={quote(str(exc))}",
            status_code=303,
        )

    # Map claims to local user.
    email = userinfo.get("email") or userinfo.get("preferred_username", "")
    display_name = userinfo.get("name") or userinfo.get("preferred_username") or email

    try:
        user = oidc_service.find_or_create_oidc_user(
            _factory(request),
            settings.oidc.discovery_url,  # type: ignore[arg-type]
            userinfo["sub"],
            email,
            display_name,
        )
    except oidc_service.OIDCError as exc:
        return RedirectResponse(
            url=f"/auth/login?error={quote(str(exc))}",
            status_code=303,
        )

    token = auth.create_jwt(
        user.id,
        user.email,
        user.is_admin,
        settings.auth.secret_key,
        settings.auth.jwt_expiry_hours,
    )

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.auth.jwt_expiry_hours * 3600,
    )
    # Rotate the CSRF cookie on SSO login, matching the local-login
    # path in ``login_submit``.
    response.set_cookie(
        csrf.COOKIE_NAME,
        csrf.generate_token(),
        httponly=True,
        samesite="lax",
        max_age=settings.auth.jwt_expiry_hours * 3600,
        path="/",
    )
    response.delete_cookie(oidc_service.STATE_COOKIE_NAME)
    return response
