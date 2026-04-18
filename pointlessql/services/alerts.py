"""CRUD + lifecycle helpers for the Sprint-55 query alerts surface.

Visibility + mutation rules mirror :mod:`pointlessql.services.saved_queries`:
owner + admin see every row; anyone else gets 404 via the API layer.
The scheduler drives alert firing through a hidden backing
:class:`~pointlessql.models.Job` row (``kind="alert_check"``) created
when an alert is first activated and deleted when the alert is
removed — see :func:`_sync_backing_job`.
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
_VALID_OPS = {"gt", "lt", "eq", "ne"}
_VALID_KINDS = {"webhook", "feed"}


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


def _can_mutate(row: Alert, user_id: int, is_admin: bool) -> bool:
    """Return whether the user may edit or delete *row*.

    Args:
        row: The alert being checked.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.

    Returns:
        ``True`` when the caller owns the alert or is an admin.
    """
    return is_admin or row.owner_id == user_id


def _serialize_destination(dest: AlertDestination) -> dict[str, Any]:
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


def _serialize(
    row: Alert, destinations: list[AlertDestination] | None = None
) -> dict[str, Any]:
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
        "destinations": [
            _serialize_destination(d) for d in destinations or []
        ],
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
    if condition_op not in _VALID_OPS:
        raise ValidationError(
            f"condition_op must be one of {sorted(_VALID_OPS)}, got {condition_op!r}."
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
        return _serialize(alert, [])


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
        return [_serialize(a, by_alert.get(a.id, [])) for a in alerts]


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
        if row is None or not _can_mutate(row, user_id, is_admin):
            return None
        dests = list(
            session.scalars(
                select(AlertDestination).where(
                    AlertDestination.alert_id == row.id
                )
            ).all()
        )
        return _serialize(row, dests)


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
        if row is None or not _can_mutate(row, user_id, is_admin):
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
            if condition_op not in _VALID_OPS:
                raise ValidationError(
                    f"condition_op must be one of {sorted(_VALID_OPS)}."
                )
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
                select(AlertDestination).where(
                    AlertDestination.alert_id == row.id
                )
            ).all()
        )
        return _serialize(row, dests)


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
        if row is None or not _can_mutate(row, user_id, is_admin):
            return False
        session.execute(
            delete(AlertDestination).where(
                AlertDestination.alert_id == row.id
            )
        )
        session.execute(
            delete(AlertEvent).where(AlertEvent.alert_id == row.id)
        )
        backing_id = row.backing_job_id
        session.delete(row)
        if backing_id is not None:
            job = session.get(Job, backing_id)
            if job is not None:
                session.delete(job)
        session.commit()
        return True


def add_destination(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
    kind: str,
    webhook_url: str | None = None,
    hmac_secret: str | None = None,
) -> dict[str, Any] | None:
    """Attach a new destination to the alert at *slug*.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target alert slug.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.
        kind: ``webhook`` or ``feed``.
        webhook_url: Required when ``kind == "webhook"``.
        hmac_secret: Optional shared secret for webhook signing.

    Returns:
        The new destination dict, or ``None`` if the alert is absent
        or not mutable by the caller.

    Raises:
        ValidationError: On unknown *kind* or webhook without URL.
    """
    if kind not in _VALID_KINDS:
        raise ValidationError(f"kind must be one of {sorted(_VALID_KINDS)}.")
    if kind == "webhook" and not (webhook_url or "").strip():
        raise ValidationError("webhook destinations require webhook_url.")
    with factory() as session:
        alert = session.scalar(select(Alert).where(Alert.slug == slug))
        if alert is None or not _can_mutate(alert, user_id, is_admin):
            return None
        dest = AlertDestination(
            alert_id=alert.id,
            kind=kind,
            webhook_url=(webhook_url or "").strip() or None,
            hmac_secret=(hmac_secret or "").strip() or None,
            is_active=True,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(dest)
        session.commit()
        session.refresh(dest)
        return _serialize_destination(dest)


def delete_destination(
    factory: sessionmaker[Session],
    slug: str,
    destination_id: int,
    *,
    user_id: int,
    is_admin: bool,
) -> bool:
    """Remove a destination from the alert at *slug*.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target alert slug.
        destination_id: Target destination row id.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.

    Returns:
        ``True`` iff a matching row was deleted.
    """
    with factory() as session:
        alert = session.scalar(select(Alert).where(Alert.slug == slug))
        if alert is None or not _can_mutate(alert, user_id, is_admin):
            return False
        dest = session.scalar(
            select(AlertDestination).where(
                AlertDestination.id == destination_id,
                AlertDestination.alert_id == alert.id,
            )
        )
        if dest is None:
            return False
        session.delete(dest)
        session.commit()
        return True


def record_event(
    factory: sessionmaker[Session],
    *,
    alert_id: int,
    event_id: str,
    fired_at: datetime.datetime,
    row_count: int | None,
    outcome: str,
    payload_json: str,
) -> int:
    """Insert one :class:`AlertEvent` row, returning its PK.

    Args:
        factory: SQLAlchemy session factory.
        alert_id: Parent alert id.
        event_id: CloudEvents ``id`` (uuid4 hex).
        fired_at: Timestamp the check decided to fire.
        row_count: Query row count at firing time, or ``None``.
        outcome: ``fired`` / ``suppressed`` / ``delivery_failed``.
        payload_json: Serialised CloudEvents envelope.

    Returns:
        The new ``alert_events.id``.
    """
    with factory() as session:
        ev = AlertEvent(
            alert_id=alert_id,
            event_id=event_id,
            fired_at=fired_at,
            row_count=row_count,
            outcome=outcome,
            payload_json=payload_json,
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)
        return ev.id


def set_event_outcome(
    factory: sessionmaker[Session], event_id: str, outcome: str
) -> None:
    """Patch the ``outcome`` of a previously-recorded event.

    Args:
        factory: SQLAlchemy session factory.
        event_id: The CloudEvents ``id`` (``AlertEvent.event_id``).
        outcome: New outcome value.
    """
    with factory() as session:
        ev = session.scalar(
            select(AlertEvent).where(AlertEvent.event_id == event_id)
        )
        if ev is not None:
            ev.outcome = outcome
            session.commit()


def list_events_for_alert(
    factory: sessionmaker[Session],
    alert_id: int,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent events for *alert_id* as dicts.

    Args:
        factory: SQLAlchemy session factory.
        alert_id: Parent alert id.
        limit: Hard row cap.

    Returns:
        List of dicts in newest-first order.
    """
    stmt = (
        select(AlertEvent)
        .where(AlertEvent.alert_id == alert_id)
        .order_by(desc(AlertEvent.fired_at))
        .limit(limit)
    )
    with factory() as session:
        rows = session.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "alert_id": r.alert_id,
                "event_id": r.event_id,
                "fired_at": r.fired_at.isoformat() if r.fired_at else None,
                "row_count": r.row_count,
                "outcome": r.outcome,
                "payload_json": r.payload_json,
            }
            for r in rows
        ]


def list_events_for_owner(
    factory: sessionmaker[Session],
    owner_id: int,
    *,
    since: datetime.datetime | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return events for every alert owned by *owner_id*.

    Used by the pull-feed endpoints.  Implicitly scopes to the caller
    because the feed token itself authenticates ownership.

    Args:
        factory: SQLAlchemy session factory.
        owner_id: Owner id whose alerts' events we surface.
        since: Floor on ``fired_at``.  ``None`` returns the full window.
        limit: Hard row cap.

    Returns:
        List of dicts sorted newest-first; each entry embeds the
        parent alert's slug + title for feed-renderer convenience.
    """
    stmt = (
        select(AlertEvent, Alert)
        .join(Alert, Alert.id == AlertEvent.alert_id)
        .where(Alert.owner_id == owner_id)
        .order_by(desc(AlertEvent.fired_at))
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(AlertEvent.fired_at >= since)
    with factory() as session:
        rows = session.execute(stmt).all()
        return [
            {
                "id": ev.id,
                "alert_id": ev.alert_id,
                "alert_slug": al.slug,
                "alert_title": al.title,
                "event_id": ev.event_id,
                "fired_at": ev.fired_at.isoformat() if ev.fired_at else None,
                "row_count": ev.row_count,
                "outcome": ev.outcome,
                "payload_json": ev.payload_json,
            }
            for ev, al in rows
        ]


def prune_events_older_than(
    factory: sessionmaker[Session], cutoff: datetime.datetime
) -> int:
    """Delete ``alert_events`` rows with ``fired_at`` older than *cutoff*.

    Args:
        factory: SQLAlchemy session factory.
        cutoff: Timestamp threshold.

    Returns:
        The number of deleted rows.
    """
    with factory() as session:
        result = session.execute(
            delete(AlertEvent).where(AlertEvent.fired_at < cutoff)
        )
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0)


# ---------------------------------------------------------------------------
# CloudEvents envelope + condition helpers


def evaluate_condition(row_count: int, op: str, threshold: int) -> bool:
    """Return whether *row_count* satisfies *op* against *threshold*.

    Args:
        row_count: Observed row count.
        op: One of ``gt`` / ``lt`` / ``eq`` / ``ne``.
        threshold: Compared value.

    Returns:
        ``True`` when the condition is met.

    Raises:
        ValidationError: On unknown operator.
    """
    if op == "gt":
        return row_count > threshold
    if op == "lt":
        return row_count < threshold
    if op == "eq":
        return row_count == threshold
    if op == "ne":
        return row_count != threshold
    raise ValidationError(f"Unknown condition_op {op!r}.")


def build_cloudevent(
    *,
    event_id: str,
    alert_slug: str,
    saved_query_slug: str,
    condition_op: str,
    threshold: int,
    row_count: int,
    duration_ms: int,
    referenced_tables: list[str],
    fired_at: datetime.datetime,
) -> dict[str, Any]:
    """Build a CloudEvents 1.0 envelope for a fired alert.

    Args:
        event_id: Unique event id (uuid4 hex).
        alert_slug: The firing alert's slug.
        saved_query_slug: The saved-query slug the alert watches.
        condition_op: The condition operator that fired.
        threshold: The threshold the condition was compared against.
        row_count: The observed row count.
        duration_ms: DuckDB wall-clock time for the query.
        referenced_tables: UC tables touched by the query.
        fired_at: UTC timestamp the check fired.

    Returns:
        A dict ready to ``json.dumps``-serialise onto the wire with
        ``Content-Type: application/cloudevents+json``.
    """
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": f"/pointlessql/alerts/{alert_slug}",
        "type": "sql.pointlessql.alert.fired.v1",
        "time": fired_at.astimezone(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": saved_query_slug,
        "data": {
            "alert_slug": alert_slug,
            "saved_query_slug": saved_query_slug,
            "condition": {"op": condition_op, "threshold": threshold},
            "row_count": row_count,
            "duration_ms": duration_ms,
            "referenced_tables": list(referenced_tables),
            "fired_at": fired_at.astimezone(datetime.UTC).isoformat(),
        },
    }
