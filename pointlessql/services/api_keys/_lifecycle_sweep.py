"""periodic API-key lifecycle maintenance.

Single sync function exposed for the lifespan async loop.  Per-tick
work:

1. **Auto-quarantine on expiry.**  Keys with ``expires_at <= now`` and
   no quarantine yet are flipped to
   ``quarantined_at=now`` / ``quarantine_reason="auto:expired"`` so the
   verify path returns the same explanatory audit event admins see for
   manual quarantines.  An ``api_key.expired`` audit row is emitted
   exactly once.  ``quarantine_on_expiry`` config flag controls this
   path; when ``False`` the key still authoritatively fails at the
   verify gate, but the row is left untouched (operator preference).

2. **TTL warning.**  Keys with
   ``expires_at - now < expiry_warning_days`` AND
   (``expiry_warned_at`` IS NULL OR ``expiry_warned_at`` predates the
   warning window) get a single ``api_key.expiry_warning`` audit row.
   ``expiry_warned_at`` is then set to ``now`` so the sweep doesn't
   spam the audit log every tick.

The sweep is idempotent — re-running it within a tick is a no-op
because every state change clears the trigger that re-armed it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import ApiKey
from pointlessql.services.audit import _core as audit_core

logger = logging.getLogger(__name__)


def run_lifecycle_sweep(
    session_factory: sessionmaker[Session],
    *,
    expiry_warning_days: int = 14,
    quarantine_on_expiry: bool = True,
) -> dict[str, int]:
    """Sweep ``api_keys`` once for expiry + warning state changes.

    Args:
        session_factory: SQLAlchemy session factory.
        expiry_warning_days: How many days before ``expires_at`` to
            emit the first warning.  Defaults to 14.
        quarantine_on_expiry: When ``True`` (default), expired keys
            also get auto-quarantined so the audit reason carries
            ``"auto:expired"`` for forensic clarity.  When ``False``,
            only the audit row is emitted; the verify path still
            blocks the key via the ``expires_at`` check.

    Returns:
        ``{"expired": int, "warned": int}`` counts of state changes
        applied this tick.
    """
    now = datetime.now(UTC)
    expired_count = 0
    warned_count = 0
    with session_factory() as session:
        # 1. expired + not-quarantined.
        expired_stmt = select(ApiKey).where(
            ApiKey.revoked_at.is_(None),
            ApiKey.expires_at.is_not(None),
            ApiKey.expires_at <= now,
            ApiKey.quarantined_at.is_(None),
        )
        for row in session.scalars(expired_stmt).all():
            if quarantine_on_expiry:
                session.execute(
                    update(ApiKey)
                    .where(ApiKey.id == row.id)
                    .values(quarantined_at=now, quarantine_reason="auto:expired")
                )
            _safe_audit(
                session_factory,
                row,
                "api_key.expired",
                {
                    "expires_at": (row.expires_at.isoformat() if row.expires_at else None),
                    "auto_quarantined": quarantine_on_expiry,
                },
            )
            expired_count += 1

        # 2. soon-to-expire warning.
        warning_cutoff = now + timedelta(days=expiry_warning_days)
        warning_stmt = select(ApiKey).where(
            ApiKey.revoked_at.is_(None),
            ApiKey.quarantined_at.is_(None),
            ApiKey.expires_at.is_not(None),
            ApiKey.expires_at > now,
            ApiKey.expires_at <= warning_cutoff,
        )
        for row in session.scalars(warning_stmt).all():
            # Dedup: emit at most once per (key, current TTL).
            # ``update_api_key_ttl`` clears ``expiry_warned_at`` when
            # an admin extends the deadline, so a TTL bump re-arms the
            # warning naturally.  Without that hook the warning would
            # spam the audit log every tick.
            if row.expiry_warned_at is not None:
                continue
            session.execute(update(ApiKey).where(ApiKey.id == row.id).values(expiry_warned_at=now))
            assert row.expires_at is not None  # query guarantees this
            expires_aware = (
                row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            )
            days_remaining = max(0, (expires_aware - now).days)
            _safe_audit(
                session_factory,
                row,
                "api_key.expiry_warning",
                {
                    "expires_at": expires_aware.isoformat(),
                    "days_remaining": days_remaining,
                },
            )
            warned_count += 1

        session.commit()

    # Cache invalidation: auto-quarantined keys must stop authorising
    # immediately, not after the next 60s TTL.
    if expired_count and quarantine_on_expiry:
        from pointlessql.services.api_keys import invalidate_cache

        invalidate_cache()

    if expired_count or warned_count:
        logger.info(
            "api-key lifecycle sweep: expired=%d warned=%d",
            expired_count,
            warned_count,
        )
    return {"expired": expired_count, "warned": warned_count}


def _safe_audit(
    session_factory: Any,
    row: ApiKey,
    action: str,
    detail: dict[str, Any],
) -> None:
    """Best-effort audit emission; swallows failures."""
    try:
        audit_core.log_action(
            cast(sessionmaker[Session], session_factory),
            user_id=0,
            user_email=f"api_key:{row.name}",
            action=action,
            target=f"api_key:{row.name}",
            detail=detail,
            actor_role="system",
            workspace_id=int(row.workspace_id),
        )
    except Exception:  # noqa: BLE001 — sweep must never break on audit
        logger.debug("Failed to emit %s audit for api_key %s", action, row.name, exc_info=True)
