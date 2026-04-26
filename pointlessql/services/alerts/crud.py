"""Alert CRUD + serialisation + backing-Job lifecycle.

Owns:

* the slug / authorisation / serialisation helpers shared with the
  destinations and events sub-modules;
* the alert ``Job`` lifecycle (`_sync_backing_job`) that drives the
  scheduler when ``is_active`` flips;
* the public CRUD surface (``create_alert``, ``list_visible``,
  ``get_by_slug``, ``update_by_slug``, ``delete_by_slug``).
"""

from __future__ import annotations

import datetime
import json
import re
import secrets
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, desc, select

from pointlessql.exceptions import ValidationError
from pointlessql.models import Alert, AlertDestination, AlertEvent, Job

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_SLUG_SANITIZER = re.compile(r"[^a-z0-9-]+")
VALID_OPS = {"gt", "lt", "eq", "ne"}


def make_slug(title: str) -> str:
    """Derive a URL-safe slug from *title* with a random suffix.

    Args:
        title: The user-entered title.

    Returns:
        A slug matching ``[a-z0-9-]+-[0-9a-f]{6}`` capped at 200 chars.
    """
    base = (title or "alert").strip().lower()
    base = _SLUG_SANITIZER.sub("-", base).strip("-")
    if not base:
        base = "alert"
    max_base = 200 - 7
    if len(base) > max_base:
        base = base[:max_base].rstrip("-")
    return f"{base}-{secrets.token_hex(3)}"


def can_mutate(row: Alert, user_id: int, is_admin: bool) -> bool:
    """Return whether the user may edit or delete *row*.

    Args:
        row: The alert being checked.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.

    Returns:
        ``True`` when the caller owns the alert or is an admin.
    """
    return is_admin or row.owner_id == user_id


def serialize_destination(dest: AlertDestination) -> dict[str, Any]:
    """Convert an :class:`AlertDestination` to a JSON-friendly dict.

    Args:
        dest: The row to serialise.

    Returns:
        Dict with ``has_hmac`` surfaced as a boolean so the frontend
        never sees the raw secret.
    """
    return {
        "id": dest.id,
        "alert_id": dest.alert_id,
        "kind": dest.kind,
        "webhook_url": dest.webhook_url,
        "has_hmac": bool(dest.hmac_secret),
        "is_active": dest.is_active,
        "created_at": dest.created_at.isoformat() if dest.created_at else None,
    }


def serialize(row: Alert, destinations: list[AlertDestination] | None = None) -> dict[str, Any]:
    """Convert an :class:`Alert` and its destinations to a JSON-friendly dict.

    Args:
        row: The alert row.
        destinations: Pre-loaded destinations to embed, or ``None``.

    Returns:
        Dict shape consumed by the API routes and templates.
    """
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "saved_query_id": row.saved_query_id,
        "owner_id": row.owner_id,
        "cron_expr": row.cron_expr,
        "condition_op": row.condition_op,
        "threshold": row.threshold,
        "is_active": row.is_active,
        "backing_job_id": row.backing_job_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "destinations": [serialize_destination(d) for d in destinations or []],
    }


def _sync_backing_job(session: Session, alert: Alert) -> None:
    """Materialise / update / retire the scheduler Job for *alert*.

    Lifecycle:

    - ``is_active=True`` and no backing job → create one.
    - ``is_active=True`` and a backing job exists → sync ``cron_expr``
      and un-pause.
    - ``is_active=False`` and a backing job exists → pause it (so the
      scheduler skips ticks) without deleting so history is preserved.
    - ``is_active=False`` and no backing job → nothing to do.

    Args:
        session: Active SQLAlchemy session (caller commits).
        alert: The alert whose lifecycle just changed.
    """
    now = datetime.datetime.now(datetime.UTC)
    job: Job | None = None
    if alert.backing_job_id is not None:
        job = session.get(Job, alert.backing_job_id)
    if alert.is_active:
        if job is None:
            job = Job(
                name=f"alert:{alert.slug}",
                cron_expr=alert.cron_expr,
                run_as_user_id=alert.owner_id,
                kind="alert_check",
                config=json.dumps({"alert_id": alert.id}, sort_keys=True),
                is_paused=False,
                max_parallel_runs=1,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.flush()
            alert.backing_job_id = job.id
        else:
            job.cron_expr = alert.cron_expr
            job.is_paused = False
            job.updated_at = now
    elif job is not None:
        job.is_paused = True
        job.updated_at = now


def create_alert(
    factory: sessionmaker[Session],
    *,
    owner_id: int,
    title: str,
    saved_query_id: int,
    cron_expr: str,
    condition_op: str,
    threshold: int,
    is_active: bool = True,
) -> dict[str, Any]:
    """Insert a new alert, plus its backing scheduler Job when active.

    Args:
        factory: SQLAlchemy session factory.
        owner_id: User id that will run the check.
        title: Human-readable title.
        saved_query_id: FK to a visible :class:`~pointlessql.models.SavedQuery`.
        cron_expr: 5-field croniter expression.
        condition_op: One of ``gt`` / ``lt`` / ``eq`` / ``ne``.
        threshold: Integer threshold.
        is_active: When ``True`` the backing Job is created right away.

    Returns:
        The serialised alert with an empty ``destinations`` list.

    Raises:
        ValidationError: If *title* is empty or *condition_op* is not
            in the allowed set.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValidationError("Title must not be empty.")
    if condition_op not in VALID_OPS:
        raise ValidationError(
            f"condition_op must be one of {sorted(VALID_OPS)}, got {condition_op!r}."
        )
    clean_cron = (cron_expr or "").strip()
    if not clean_cron:
        raise ValidationError("cron_expr must not be empty.")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        alert = Alert(
            slug=make_slug(clean_title),
            title=clean_title[:200],
            saved_query_id=saved_query_id,
            owner_id=owner_id,
            cron_expr=clean_cron[:120],
            condition_op=condition_op,
            threshold=int(threshold),
            is_active=bool(is_active),
            created_at=now,
            updated_at=now,
        )
        session.add(alert)
        session.flush()
        _sync_backing_job(session, alert)
        session.commit()
        session.refresh(alert)
        return serialize(alert, [])


def list_visible(
    factory: sessionmaker[Session],
    *,
    user_id: int,
    is_admin: bool,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return alerts visible to the caller, newest-updated first.

    Args:
        factory: SQLAlchemy session factory.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.
        limit: Hard row cap.

    Returns:
        List of serialised alert dicts with embedded destinations.
    """
    stmt = select(Alert).order_by(desc(Alert.updated_at)).limit(limit)
    if not is_admin:
        stmt = stmt.where(Alert.owner_id == user_id)
    with factory() as session:
        alerts = list(session.scalars(stmt).all())
        if not alerts:
            return []
        ids = [a.id for a in alerts]
        dests = session.scalars(
            select(AlertDestination).where(AlertDestination.alert_id.in_(ids))
        ).all()
        by_alert: dict[int, list[AlertDestination]] = {i: [] for i in ids}
        for d in dests:
            by_alert.setdefault(d.alert_id, []).append(d)
        return [serialize(a, by_alert.get(a.id, [])) for a in alerts]


def get_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
) -> dict[str, Any] | None:
    """Return the alert with matching *slug* when visible to the caller.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target slug.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.

    Returns:
        Serialised alert dict or ``None``.  Missing / forbidden collapse.
    """
    with factory() as session:
        row = session.scalar(select(Alert).where(Alert.slug == slug))
        if row is None or not can_mutate(row, user_id, is_admin):
            return None
        dests = list(
            session.scalars(
                select(AlertDestination).where(AlertDestination.alert_id == row.id)
            ).all()
        )
        return serialize(row, dests)


def update_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
    title: str | None = None,
    cron_expr: str | None = None,
    condition_op: str | None = None,
    threshold: int | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    """Partially update an alert and re-sync its backing Job.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target slug.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.
        title: New title, or ``None`` to leave unchanged.
        cron_expr: New cron expression, or ``None``.
        condition_op: New condition operator, or ``None``.
        threshold: New threshold, or ``None``.
        is_active: New active flag, or ``None``.

    Returns:
        The updated alert dict, or ``None`` when missing or not mutable.

    Raises:
        ValidationError: If *title* is present but empty, or
            *condition_op* is not in the allowed set.
    """
    with factory() as session:
        row = session.scalar(select(Alert).where(Alert.slug == slug))
        if row is None or not can_mutate(row, user_id, is_admin):
            return None
        if title is not None:
            clean = title.strip()
            if not clean:
                raise ValidationError("Title must not be empty.")
            row.title = clean[:200]
        if cron_expr is not None:
            clean_cron = cron_expr.strip()
            if not clean_cron:
                raise ValidationError("cron_expr must not be empty.")
            row.cron_expr = clean_cron[:120]
        if condition_op is not None:
            if condition_op not in VALID_OPS:
                raise ValidationError(f"condition_op must be one of {sorted(VALID_OPS)}.")
            row.condition_op = condition_op
        if threshold is not None:
            row.threshold = int(threshold)
        if is_active is not None:
            row.is_active = bool(is_active)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        _sync_backing_job(session, row)
        session.commit()
        session.refresh(row)
        dests = list(
            session.scalars(
                select(AlertDestination).where(AlertDestination.alert_id == row.id)
            ).all()
        )
        return serialize(row, dests)


def delete_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
) -> bool:
    """Delete an alert, its destinations, events, and backing Job.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target slug.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.

    Returns:
        ``True`` iff the row existed and the caller could delete it.
    """
    with factory() as session:
        row = session.scalar(select(Alert).where(Alert.slug == slug))
        if row is None or not can_mutate(row, user_id, is_admin):
            return False
        session.execute(delete(AlertDestination).where(AlertDestination.alert_id == row.id))
        session.execute(delete(AlertEvent).where(AlertEvent.alert_id == row.id))
        backing_id = row.backing_job_id
        session.delete(row)
        if backing_id is not None:
            job = session.get(Job, backing_id)
            if job is not None:
                session.delete(job)
        session.commit()
        return True
