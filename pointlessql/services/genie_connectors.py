"""Genie bot connectors — registry + shared-secret auth.

CRUD over the ``genie_bot_connectors`` table plus the token plumbing the
inbound chat webhook needs: a connector's shared secret is generated
once, returned in clear exactly once (on create / rotate), and stored
only as a SHA-256 hash.  :func:`authenticate` resolves a connector by its
public id and verifies a presented token in constant time.
"""

from __future__ import annotations

import datetime
import hmac
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import GENIE_CONNECTOR_PLATFORMS, GenieBotConnector
from pointlessql.services.api_keys import hash_secret

#: Plaintext token prefix so admins can eyeball which secret is live.
_TOKEN_PREFIX = "pqlbot_"

#: Sentinel distinguishing "leave unchanged" from "set to None".
_UNSET = object()


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def verify_token(token_hash: str, presented: str) -> bool:
    """Constant-time check of a presented token against a stored hash.

    Args:
        token_hash: The stored SHA-256 hex digest.
        presented: The token offered by the caller.

    Returns:
        ``True`` when *presented* hashes to *token_hash*.
    """
    return hmac.compare_digest(token_hash, hash_secret(presented))


def _new_token() -> str:
    """Mint a fresh connector shared secret."""
    return f"{_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def _serialize(row: GenieBotConnector) -> dict[str, Any]:
    """Render a connector row into a JSON-safe dict (never the hash)."""
    return {
        "id": row.id,
        "name": row.name,
        "platform": row.platform,
        "public_id": row.public_id,
        "genie_space_slug": row.genie_space_slug,
        "token_prefix": row.token_prefix,
        "enabled": bool(row.enabled),
        "created_by": row.created_by,
        "messaging_path": f"/api/genie/teams/{row.public_id}/messages",
    }


def _clean_platform(platform: str | None) -> str:
    """Validate and normalise a connector platform."""
    value = (platform or "teams").strip().lower()
    if value not in GENIE_CONNECTOR_PLATFORMS:
        raise ValidationError(
            f"unknown connector platform {value!r}; "
            f"choose one of {', '.join(GENIE_CONNECTOR_PLATFORMS)}"
        )
    return value


def list_connectors(factory: sessionmaker[Session], *, workspace_id: int) -> list[dict[str, Any]]:
    """List a workspace's bot connectors.

    Args:
        factory: Session factory.
        workspace_id: Active workspace.

    Returns:
        Serialized connector dicts ordered by name.
    """
    with factory() as session:
        rows = session.scalars(
            select(GenieBotConnector)
            .where(GenieBotConnector.workspace_id == workspace_id)
            .order_by(GenieBotConnector.name)
        ).all()
        return [_serialize(row) for row in rows]


def create_connector(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: str,
    platform: str | None = None,
    genie_space_slug: str | None = None,
    created_by: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Register a connector and mint its shared-secret token.

    Args:
        factory: Session factory.
        workspace_id: Active workspace.
        name: Connector name, unique per workspace.
        platform: Target chat platform; defaults to ``teams``.
        genie_space_slug: Optional Genie space the bot answers over.
        created_by: Authoring principal.

    Returns:
        ``(serialized_connector, plaintext_token)`` — the token is shown
        only here and never recoverable afterwards.

    Raises:
        ValidationError: When the name is blank/duplicate or the platform
            is unknown.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("connector name is required")
    clean_platform = _clean_platform(platform)
    slug = (genie_space_slug or "").strip() or None
    token = _new_token()
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(GenieBotConnector).where(
                GenieBotConnector.workspace_id == workspace_id,
                GenieBotConnector.name == clean_name,
            )
        )
        if existing is not None:
            raise ValidationError(f"connector {clean_name!r} already exists")
        row = GenieBotConnector(
            workspace_id=workspace_id,
            name=clean_name,
            platform=clean_platform,
            public_id=uuid.uuid4().hex,
            genie_space_slug=slug,
            token_hash=hash_secret(token),
            token_prefix=token[:12],
            enabled=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            # A concurrent create raced past the existence check above.
            session.rollback()
            raise ValidationError(f"connector {clean_name!r} already exists") from exc
        session.refresh(row)
        return _serialize(row), token


def update_connector(
    factory: sessionmaker[Session],
    *,
    connector_id: int,
    workspace_id: int,
    platform: str | None = None,
    genie_space_slug: object = _UNSET,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Patch a connector's platform, bound space, and/or enabled flag.

    Args:
        factory: Session factory.
        connector_id: Target connector.
        workspace_id: Active workspace (the connector must belong to it).
        platform: New platform, when provided.
        genie_space_slug: New space slug; pass ``None`` to unbind, or omit
            to leave unchanged.
        enabled: New enabled flag, when provided.

    Returns:
        The serialized, updated connector.

    Raises:
        ValidationError: When the connector is unknown or the platform is
            invalid.
    """
    with factory() as session:
        row = session.get(GenieBotConnector, connector_id)
        if row is None or int(row.workspace_id) != workspace_id:
            raise ValidationError(f"connector {connector_id} not found")
        if platform is not None:
            row.platform = _clean_platform(platform)
        if genie_space_slug is not _UNSET:
            slug = genie_space_slug
            row.genie_space_slug = (str(slug).strip() or None) if slug is not None else None
        if enabled is not None:
            row.enabled = bool(enabled)
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        return _serialize(row)


def rotate_token(
    factory: sessionmaker[Session], *, connector_id: int, workspace_id: int
) -> tuple[dict[str, Any], str]:
    """Mint a fresh shared secret for a connector, invalidating the old.

    Args:
        factory: Session factory.
        connector_id: Target connector.
        workspace_id: Active workspace.

    Returns:
        ``(serialized_connector, plaintext_token)``.

    Raises:
        ValidationError: When the connector is unknown.
    """
    token = _new_token()
    with factory() as session:
        row = session.get(GenieBotConnector, connector_id)
        if row is None or int(row.workspace_id) != workspace_id:
            raise ValidationError(f"connector {connector_id} not found")
        row.token_hash = hash_secret(token)
        row.token_prefix = token[:12]
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        return _serialize(row), token


def delete_connector(
    factory: sessionmaker[Session], *, connector_id: int, workspace_id: int
) -> bool:
    """Delete a connector.

    Args:
        factory: Session factory.
        connector_id: Target connector.
        workspace_id: Active workspace.

    Returns:
        ``True`` when a row was removed.
    """
    with factory() as session:
        row = session.get(GenieBotConnector, connector_id)
        if row is None or int(row.workspace_id) != workspace_id:
            return False
        session.delete(row)
        session.commit()
    return True


def authenticate(
    factory: sessionmaker[Session], *, public_id: str, presented_token: str
) -> GenieBotConnector | None:
    """Resolve and authenticate a connector for an inbound message.

    Args:
        factory: Session factory.
        public_id: The connector's public id (from the messaging URL).
        presented_token: The bearer token offered by the caller.

    Returns:
        The detached, enabled connector row when the token matches;
        ``None`` for an unknown / disabled connector or a bad token.
    """
    if not public_id or not presented_token:
        return None
    with factory() as session:
        row = session.scalar(
            select(GenieBotConnector).where(GenieBotConnector.public_id == public_id)
        )
        if row is None or not row.enabled:
            return None
        if not verify_token(row.token_hash, presented_token):
            return None
        session.expunge(row)
        return row
