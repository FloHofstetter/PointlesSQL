"""Audit log service — append-only record of user actions."""

from __future__ import annotations

import datetime
import logging

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import AuditLog

logger = logging.getLogger(__name__)


def log_action(
    factory: sessionmaker[Session],
    user_id: int,
    user_email: str,
    action: str,
    target: str,
    detail: str | None = None,
) -> None:
    """Write a single audit entry.

    This is a synchronous, quick INSERT. It opens a session, inserts
    one row, and commits. Designed to be called from route handlers
    after a successful write operation.

    Args:
        factory: SQLAlchemy session factory.
        user_id: ID of the acting user.
        user_email: Email of the acting user (snapshot).
        action: Short verb (e.g. ``update_catalog``, ``grant_permission``).
        target: Identifier of the affected resource
            (e.g. ``catalog:my_catalog``).
        detail: Optional JSON string with extra context.
    """
    with factory() as session:
        entry = AuditLog(
            user_id=user_id,
            user_email=user_email,
            action=action,
            target=target,
            detail=detail,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(entry)
        session.commit()
        logger.debug("audit: %s %s %s", user_email, action, target)
