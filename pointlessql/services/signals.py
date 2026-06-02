"""Open-ledger service for actionable data-health / pipeline signals.

A *signal* is one ongoing problem.  :func:`emit_signal` opens (or
keeps open) a ledger row; :func:`resolve_signal` closes it.  Both are
best-effort — a failure here never breaks the scheduler / executor
that called them.

The contract that makes the feed trustworthy:

* **At most one open card per problem.** ``emit_signal`` keys on a
  ``dedupe_key``; if an open row already exists it just bumps
  ``last_seen_at`` and returns ``False`` (no new card, no SSE ping).
  A check that re-fires every tick therefore produces exactly one
  card, not one per tick.
* **Cards self-heal.** When the condition clears the caller invokes
  ``resolve_signal``; the feed's live union stops returning the row
  on the next fetch, so the card disappears without any per-recipient
  bookkeeping.

Live SSE pings are best-effort to the workspace admins (the people
who triage data health); correctness lives in the DB recompute, not
the ping.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from sqlalchemy import select

from pointlessql.models.actionable_signals import (
    STATUS_OPEN,
    STATUS_RESOLVED,
    ActionableSignal,
)
from pointlessql.services.notifications.categories import classify_signal

logger = logging.getLogger(__name__)


def default_dedupe_key(
    signal_kind: str, workspace_id: int, entity_kind: str, entity_ref: str
) -> str:
    """Build the natural dedupe key for a signal.

    One open row per ``(signal_kind, workspace, entity)`` unless the
    caller supplies a finer key (e.g. one alert evaluation window).
    """
    return f"{signal_kind}:{workspace_id}:{entity_kind}:{entity_ref}"


def _render_kind_for(signal_kind: str) -> str:
    """Map a signal kind to the feed card's ``render_kind``."""
    category, _ = classify_signal(signal_kind)
    return "pipeline" if category == "pipeline" else "data_health"


def _publish_to_admins(session_factory: Any, payload: dict[str, Any]) -> None:
    """Best-effort SSE nudge to every admin so feeds live-update."""
    try:
        from pointlessql.api.notifications_stream import publish_notification
        from pointlessql.services.notifications.fanout import (
            resolve_workspace_admin_ids,
        )

        with session_factory() as session:
            admin_ids = resolve_workspace_admin_ids(session)
        for rid in admin_ids:
            publish_notification(rid, payload)
    except Exception:  # noqa: BLE001 — SSE delivery is best-effort
        logger.exception("signal SSE publish failed")


def emit_signal(
    session_factory: Any,
    *,
    signal_kind: str,
    workspace_id: int,
    entity_kind: str,
    entity_ref: str,
    summary_md: str,
    severity: str | None = None,
    source_url: str | None = None,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    """Open (or keep open) a data-health / pipeline signal.

    Args:
        session_factory: SQLAlchemy session factory.
        signal_kind: One of the ledger kinds (``alert_firing``,
            ``slo_breach``, ``job_failed``, …).
        workspace_id: Tenant scope.
        entity_kind: What the problem is about (``table`` / ``job`` /
            ``alert`` / …).
        entity_ref: Reference within *entity_kind*.
        summary_md: One-line card text.
        severity: ``warn`` / ``error``; defaults from the signal kind.
        source_url: Click-through URL stored in the payload so the
            card links to the right surface.
        payload: Optional extra card data (metric, threshold, error
            snippet, action hints).
        dedupe_key: Override the natural key when a finer grain is
            needed.

    Returns:
        ``True`` when a new open card was created; ``False`` when an
        open card already existed (steady-state re-fire) or the write
        failed.
    """
    sev = severity or classify_signal(signal_kind)[1]
    key = dedupe_key or default_dedupe_key(signal_kind, workspace_id, entity_kind, entity_ref)
    blob = dict(payload or {})
    if source_url:
        blob["source_url"] = source_url
    payload_json = json.dumps(blob) if blob else None
    try:
        now = datetime.datetime.now(datetime.UTC)
        with session_factory() as session:
            existing = session.scalar(
                select(ActionableSignal).where(
                    ActionableSignal.dedupe_key == key,
                    ActionableSignal.status == STATUS_OPEN,
                )
            )
            if existing is not None:
                existing.last_seen_at = now
                if payload_json is not None:
                    existing.payload_json = payload_json
                existing.summary_md = summary_md
                existing.severity = sev
                session.commit()
                return False
            session.add(
                ActionableSignal(
                    workspace_id=workspace_id,
                    signal_kind=signal_kind,
                    severity=sev,
                    entity_kind=entity_kind,
                    entity_ref=entity_ref,
                    dedupe_key=key,
                    status=STATUS_OPEN,
                    summary_md=summary_md,
                    payload_json=payload_json,
                    opened_at=now,
                    last_seen_at=now,
                )
            )
            session.commit()
    except Exception:  # noqa: BLE001 — signal emission must never break the caller
        logger.exception("emit_signal failed for kind=%s ref=%s", signal_kind, entity_ref)
        return False

    category, _ = classify_signal(signal_kind)
    _publish_to_admins(
        session_factory,
        {
            "render_kind": _render_kind_for(signal_kind),
            "category": category,
            "severity": sev,
            "signal_kind": signal_kind,
            "summary_md": summary_md,
            "source_url": blob.get("source_url"),
            "source_entity_kind": entity_kind,
            "source_entity_ref": entity_ref,
            "created_at": now.isoformat(),
        },
    )
    return True


def resolve_signal(
    session_factory: Any,
    *,
    signal_kind: str,
    workspace_id: int,
    entity_kind: str,
    entity_ref: str,
    dedupe_key: str | None = None,
) -> bool:
    """Close any open signal matching the key.

    Args:
        session_factory: SQLAlchemy session factory.
        signal_kind: The kind used when the signal was opened.
        workspace_id: Tenant scope.
        entity_kind: Entity discriminator used when opened.
        entity_ref: Entity reference used when opened.
        dedupe_key: Override the natural key (must match the one used
            at emit time).

    Returns:
        ``True`` when an open row was closed; ``False`` otherwise.
    """
    key = dedupe_key or default_dedupe_key(signal_kind, workspace_id, entity_kind, entity_ref)
    try:
        now = datetime.datetime.now(datetime.UTC)
        with session_factory() as session:
            existing = session.scalar(
                select(ActionableSignal).where(
                    ActionableSignal.dedupe_key == key,
                    ActionableSignal.status == STATUS_OPEN,
                )
            )
            if existing is None:
                return False
            existing.status = STATUS_RESOLVED
            existing.resolved_at = now
            session.commit()
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("resolve_signal failed for key=%s", key)
        return False
    # Nudge admins so the resolved card drops from open feeds.
    _publish_to_admins(
        session_factory,
        {
            "signal_resolved": True,
            "source_entity_kind": entity_kind,
            "source_entity_ref": entity_ref,
            "created_at": now.isoformat(),
        },
    )
    return True
