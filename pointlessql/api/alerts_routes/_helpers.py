"""Shared helpers across the alerts sub-routers.

* :func:`base_url` is used by the public feed routes to build feed-
  entry permalinks.
* :func:`rotate_or_fetch_feed_token` is used by both the feed-token
  endpoints and is exported through the package facade.
* :func:`user_for_feed_token` resolves the opaque ``?token=...``
  query param back to a user row for the unauthenticated feed
  endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


def base_url(request: Request) -> str:
    """Return the absolute base URL for the running deployment.

    Args:
        request: Incoming request used to build the URL.

    Returns:
        ``<scheme>://<host>`` without trailing slash.
    """
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def rotate_or_fetch_feed_token(
    factory: Any,
    user_id: int,
    rotate: bool = False,
) -> str:
    """Return the caller's feed token, materialising one on first access.

    Args:
        factory: SQLAlchemy session factory.
        user_id: Authenticated user id.
        rotate: When ``True`` force a fresh token even if one exists.

    Returns:
        URL-safe opaque token.

    Raises:
        RuntimeError: When the authenticated user id no longer
            resolves to a row (shouldn't happen since the request
            already authenticated, but kept explicit).
    """
    import secrets as _secrets

    from pointlessql.models import User

    with factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        if not user.feed_token or rotate:
            user.feed_token = _secrets.token_urlsafe(32)
            session.commit()
            session.refresh(user)
        return user.feed_token or ""


def user_for_feed_token(factory: Any, token: str) -> Any:
    """Return the :class:`User` matching *token*, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        token: Opaque token from the query string.

    Returns:
        The user row or ``None`` when the token does not resolve.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import User

    if not token:
        return None
    with factory() as session:
        return session.scalar(
            _select(User).where(User.feed_token == token),
        )
