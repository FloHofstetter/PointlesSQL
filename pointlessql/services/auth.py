"""Authentication service — register, login, JWT tokens.

Handles password hashing via pwdlib/bcrypt and JWT session tokens
stored in an HttpOnly cookie. The first user to register becomes
admin automatically (first-run bootstrap).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import User
from pointlessql.models.workspace import WorkspaceMember
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

_hasher = PasswordHash((BcryptHasher(),))

COOKIE_NAME = "pql_session"


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        str: Bcrypt-hashed password string.
    """
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        password: The plaintext password to verify.
        hashed: The bcrypt hash to verify against.

    Returns:
        bool: ``True`` if the password matches.
    """
    try:
        return _hasher.verify(password, hashed)
    except ValueError, TypeError, PwdlibError:
        logger.warning("Password verification error (corrupt hash?)", exc_info=True)
        return False


def create_jwt(
    user_id: int,
    email: str,
    is_admin: bool,
    secret_key: str,
    expiry_hours: int = 168,
) -> str:
    """Create a signed JWT token for the given user.

    Args:
        user_id: Database ID of the user.
        email: User email address.
        is_admin: Whether the user is an administrator.
        secret_key: Secret key for signing the token.
        expiry_hours: Token validity in hours (default 7 days).

    Returns:
        str: Encoded JWT token string.
    """
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + datetime.timedelta(hours=expiry_hours),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def verify_jwt(
    token: str,
    secret_key: str,
    *,
    previous_key: str | None = None,
) -> dict[str, Any] | None:
    """Verify and decode a JWT token.

    Tries the primary ``secret_key`` first.  If that rejects the
    token and ``previous_key`` is set, retries once with the old
    key — this mid-flight grace window lets operators rotate the
    signing key without terminating every live session.  Corrupt,
    expired, or tampered tokens still fail under both keys.

    Args:
        token: The JWT token string to verify.
        secret_key: Primary signing key (all new tokens use this).
        previous_key: Optional prior signing key, honoured only for
            verification so mid-flight tokens from before a
            rotation keep working until they expire naturally.

    Returns:
        dict[str, Any] | None: Decoded payload on success, ``None`` on failure.
    """
    try:
        return jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        if not previous_key:
            return None
    try:
        return jwt.decode(token, previous_key, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def is_first_user(factory: sessionmaker[Session]) -> bool:
    """Check whether the users table is empty (first-run bootstrap).

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        bool: ``True`` if no users exist yet.
    """
    with factory() as session:
        return session.query(User).count() == 0


def register(
    factory: sessionmaker[Session],
    email: str,
    display_name: str,
    password: str,
) -> User | None:
    """Register a new user account.

    The first user to register automatically becomes admin.

    Args:
        factory: SQLAlchemy session factory.
        email: User email address.
        display_name: Human-readable display name.
        password: Plaintext password (will be hashed).

    Returns:
        User | None: The created user, or ``None`` if the email is taken.
    """
    email = email.strip().lower()
    first_user = is_first_user(factory)

    with factory() as session:
        now = datetime.datetime.now(datetime.UTC)
        user = User(
            email=email,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            is_admin=first_user,
            created_at=now,
            default_workspace_id=1,
        )
        try:
            session.add(user)
            session.flush()
            # Workspace membership for the seeded ``default`` workspace
            # (id=1).  The middleware's ``X-Workspace`` enforcement
            # requires an explicit ``workspace_members`` row — the
            # ``users.default_workspace_id`` pointer alone is not
            # membership.  HTMX-boosted clicks send the slug as a header
            # on every nav, so a missing membership row 403s every
            # boosted link.  Role mirrors ``is_admin`` so first-user
            # gets workspace-admin rights too.
            session.add(
                WorkspaceMember(
                    workspace_id=1,
                    user_id=user.id,
                    role="admin" if first_user else "member",
                    created_at=now,
                )
            )
            session.commit()
            session.refresh(user)
            logger.info(
                "User registered (id=%d, email=%s, is_admin=%s)",
                user.id,
                email,
                first_user,
            )
            return user
        except IntegrityError as exc:
            session.rollback()
            logger.warning("Registration failed (email=%s): %s", email, exc.orig)
            return None


# Dummy hash for constant-time comparison when user not found.
_DUMMY_HASH = "$2b$12$LJ3m4ys3Lg2VBe50VdnCJOIBbGMkGLWMFwxL8MKGqUVAyGYQz/mPa"


def login(
    factory: sessionmaker[Session],
    email: str,
    password: str,
    secret_key: str,
    expiry_hours: int = 168,
) -> str | None:
    """Verify credentials and return a JWT token on success.

    Uses constant-time comparison to prevent timing-based email
    enumeration: a dummy bcrypt hash is verified when the user does
    not exist so the response time is indistinguishable.

    Args:
        factory: SQLAlchemy session factory.
        email: User email address.
        password: Plaintext password to verify.
        secret_key: Secret key for JWT signing.
        expiry_hours: JWT validity in hours.

    Returns:
        str | None: JWT token string on success, ``None`` on failure.
    """
    email = email.strip().lower()

    with factory() as session:
        user = session.query(User).filter(User.email == email).first()
        pw_hash = (
            user.password_hash
            if user is not None and user.password_hash is not None
            else _DUMMY_HASH
        )
        password_ok = verify_password(password, pw_hash)

        if user is None or not password_ok:
            logger.warning("Login failed: invalid credentials (email=%s)", email)
            return None

        return create_jwt(user.id, user.email, user.is_admin, secret_key, expiry_hours)


def get_current_user(
    factory: sessionmaker[Session],
    token: str,
    secret_key: str,
    *,
    previous_key: str | None = None,
) -> UserInfo | None:
    """Decode a JWT and look up the corresponding user.

    Args:
        factory: SQLAlchemy session factory.
        token: JWT token string.
        secret_key: Primary signing key for verification.
        previous_key: Optional prior key for the rotation grace
            window (see :func:`verify_jwt`).

    Returns:
        UserInfo | None: User info dict or ``None`` if invalid.
    """
    payload = verify_jwt(token, secret_key, previous_key=previous_key)
    if payload is None:
        return None

    sub = payload.get("sub")
    if sub is None:
        return None

    try:
        user_id = int(sub)
    except ValueError, TypeError:
        return None

    with factory() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user is None:
            return None
        return UserInfo(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            is_supervisor=bool(user.is_supervisor),
            is_auditor=bool(user.is_auditor),
        )
