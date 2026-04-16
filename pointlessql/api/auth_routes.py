"""Authentication routes — login, register, logout, current user."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from pointlessql.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def _factory(request: Request):
    """Return the DB session factory from app state."""
    return request.app.state.session_factory


def _settings(request: Request):
    """Return the Settings instance from app state."""
    return request.app.state.settings


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    """Render the login page."""
    return _templates(request).TemplateResponse(
        request,
        "pages/login.html",
        {"error": error, "hide_sidebar": True},
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
        settings.secret_key,
        settings.jwt_expiry_hours,
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
        max_age=settings.jwt_expiry_hours * 3600,
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
            request, "pages/register.html", ctx, status_code=status,
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
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


@router.get("/me")
async def current_user(request: Request):
    """Return the current authenticated user as JSON."""
    user = getattr(request.state, "user", None)
    if user is None:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse(user)
