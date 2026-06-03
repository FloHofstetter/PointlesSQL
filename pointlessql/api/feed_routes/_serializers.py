"""Shared row-builders + lookup caches for the feed sub-routers.

Every feed endpoint (``/api/feed``, ``/api/feed/trending``,
``/api/feed/people``) and every mute endpoint reaches for one of
these helpers to:

* Build the ``{dp_id: 'cat.sch'}`` cache fed into the URL builder so
  one SELECT per request covers all rows.
* Resolve a batch of ``actor_user_id`` / ``author_user_id`` values
  to display names in a single round-trip.
* Compute the active mute set so the feed handler can drop muted
  rows after the merge.
* Normalise inbox notifications, comments, and reviews into the
  single feed-row shape consumed by the Alpine renderer.

Centralising these here keeps the sub-routers thin and lets the
``muting.py`` endpoints reuse ``_active_mute_keys`` for consistency
checks without re-implementing the predicate.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, cast

from sqlalchemy import or_, select

from pointlessql.models.actionable_signals import ActionableSignal
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._feed_mute import FeedMute
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.notifications.categories import (
    ATTENTION_ACT,
    ATTENTION_AMBIENT,
    attention_for_event,
    classify_category,
    classify_signal,
)
from pointlessql.services.social import entity_registry

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def dp_url_from_id(fqn_map: dict[int, str], dp_id: int | None) -> str:
    """Build the DP detail URL from an id via the entity registry.

    the URL is built through
    :func:`entity_registry.url_for` so the same lookup table
    powers every future kind (table / model / branch / …).
    ``fqn_map`` is the per-request ``{dp_id: 'cat.sch'}`` cache
    pre-fetched by the feed handler.  Falls back to the legacy
    fragment-anchor format when the id is unknown (e.g.
    historic row whose DP was deleted) so the link is at least
    parseable.

    Args:
        fqn_map: ``{dp_id: 'cat.sch'}`` cache.
        dp_id: Data-product id or ``None``.

    Returns:
        URL string; falls back to ``/data-products/#<id>`` when the
        FQN cannot be resolved.
    """
    fqn = fqn_map.get(int(dp_id)) if dp_id is not None else None
    if fqn is None:
        return f"/data-products/#{dp_id}"
    return entity_registry.url_for("dp", fqn)


def classify_notification(event_type: str) -> str:
    """Map a ``user_notifications.event_type`` to a feed render kind.

    the renderer wants a coarser bucket than the dotted
    event-type string so per-kind Alpine branches stay readable.
    ``mentioned`` substrings light up the mention treatment, the rest
    map by prefix.  Unknown event types fall through to the generic
    notification card.

    Args:
        event_type: ``pointlessql.<scope>.<verb>`` event identifier.

    Returns:
        One of ``mention``, ``agent_run``, ``badge_award``, ``issue``,
        ``branch``, ``fact``, ``notification``.
    """
    if not event_type:
        return "notification"
    if "mentioned" in event_type or ".mention" in event_type:
        return "mention"
    if event_type.startswith("pointlessql.agent_run."):
        return "agent_run"
    if event_type.startswith("pointlessql.user.badge_"):
        return "badge_award"
    if event_type.startswith("pointlessql.issue."):
        return "issue"
    if event_type.startswith("pointlessql.branch."):
        return "branch"
    if event_type == "notebook_revision_pinned":
        return "fact"
    return "notification"


def row_from_notification(
    row: UserNotification,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
) -> dict[str, Any]:
    """Normalise a ``UserNotification`` to the feed row shape.

    adds the coarse ``render_kind`` discriminator + actor
    display-name resolution so the Alpine renderer can branch on a
    single field instead of substring-matching ``event_type``.

    Args:
        row: The notification row.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for DP-URL fallback.
        actor_names: ``{user_id: display_name}`` cache built once
            per feed request.

    Returns:
        Feed-row dict ready for JSON serialisation.
    """
    source_url = row.source_url or dp_url_from_id(fqn_map, row.source_data_product_id)
    render_kind = classify_notification(row.event_type or "")
    category, severity = classify_category(row.event_type or "")
    return {
        "id": row.id,
        "kind": "notification",
        "render_kind": render_kind,
        "category": category,
        "severity": severity,
        "attention": row.attention or attention_for_event(row.event_type),
        "event_type": row.event_type,
        "summary_md": row.summary_md,
        "body_md": row.summary_md,
        "source_url": source_url,
        "data_product_id": row.source_data_product_id,
        "entity_kind": row.source_entity_kind,
        "entity_ref": row.source_entity_ref,
        "actor_user_id": row.actor_user_id,
        "actor_display_name": (
            actor_names.get(int(row.actor_user_id)) if row.actor_user_id is not None else None
        ),
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def row_from_comment(
    comment: DataProductComment,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
    target: SocialTarget | None = None,
    reply_count: int = 0,
) -> dict[str, Any]:
    """Normalise a comment to the feed row shape.

    The serialised dict carries the full ``body_md`` (Alpine
    truncates + "Show more"), ``actor_display_name``,
    ``comment_id``, and a ``render_kind`` of ``comment`` for the
    per-kind renderer.

    Args:
        comment: The comment row to normalise.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for the DP fallback.
        actor_names: ``{user_id: display_name}`` cache.
        target: Optional joined ``social_targets`` row.
        reply_count: Number of threaded replies under this comment, so
            the card can offer "View N replies" without a per-row query.

    Returns:
        Feed-row dict (kind / event_type / summary / source_url /
        entity_kind / entity_ref / actor / timestamps).
    """
    dp_id = comment.data_product_id
    if target is not None:
        entity_kind = str(target.entity_kind)
        entity_ref = str(target.entity_ref)
        source_url = entity_registry.url_for(entity_kind, entity_ref)
    else:
        entity_kind = "dp"
        entity_ref = fqn_map.get(int(dp_id)) if dp_id is not None else None
        source_url = dp_url_from_id(fqn_map, dp_id)
    return {
        "kind": "comment",
        "render_kind": "comment",
        "category": "social",
        "severity": "info",
        "attention": ATTENTION_AMBIENT,
        "event_type": "pointlessql.data_product.commented",
        "summary_md": comment.body_md[:160],
        "body_md": comment.body_md,
        "comment_id": comment.id,
        "reply_count": int(reply_count),
        "source_url": source_url,
        "data_product_id": dp_id,
        "entity_kind": entity_kind,
        "entity_ref": entity_ref,
        "actor_user_id": comment.author_user_id,
        "actor_display_name": actor_names.get(int(comment.author_user_id)),
        "created_at": comment.created_at.isoformat(),
        "read_at": None,
    }


def row_from_review(
    review: DataProductReview,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
    target: SocialTarget | None = None,
) -> dict[str, Any]:
    """Normalise a review to the feed row shape.

    The serialised dict carries ``stars`` as a separate integer
    field (Alpine renders the actual stars row), full ``body_md``,
    and ``actor_display_name`` for the per-kind renderer.

    Args:
        review: The review row to normalise.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for the DP fallback.
        actor_names: ``{user_id: display_name}`` cache.
        target: Optional joined ``social_targets`` row.

    Returns:
        Feed-row dict with the same shape as the comment row, plus
        a top-level ``stars`` integer.
    """
    dp_id = review.data_product_id
    if target is not None:
        entity_kind = str(target.entity_kind)
        entity_ref = str(target.entity_ref)
        source_url = entity_registry.url_for(entity_kind, entity_ref)
    else:
        entity_kind = "dp"
        entity_ref = fqn_map.get(int(dp_id)) if dp_id is not None else None
        source_url = dp_url_from_id(fqn_map, dp_id)
    return {
        "kind": "review",
        "render_kind": "review",
        "category": "social",
        "severity": "info",
        "attention": ATTENTION_AMBIENT,
        "event_type": "pointlessql.data_product.reviewed",
        "summary_md": f"{'★' * review.stars} — {review.body_md[:120]}",
        "body_md": review.body_md,
        "stars": int(review.stars),
        "review_id": int(review.id),
        "source_url": source_url,
        "data_product_id": dp_id,
        "entity_kind": entity_kind,
        "entity_ref": entity_ref,
        "actor_user_id": review.author_user_id,
        "actor_display_name": actor_names.get(int(review.author_user_id)),
        "created_at": review.created_at.isoformat(),
        "read_at": None,
    }


def row_from_pending_run(
    run: AgentRun,
    principals: dict[str, tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Normalise an approval-pending agent run to the feed row shape.

    This is a *live* row — it is read straight from ``agent_runs``
    where ``status = 'needs_approval'`` at query time, never stored as
    a notification.  Acting on it (or any other admin / the runtime
    resolving the run) drops it from the next fetch, so the card can
    never go stale.  The row carries the ``run_id`` + ``principal``
    the inline Approve / Deny buttons need.

    The principal is resolved to a human display name (+ user id, so the
    avatar picks a stable colour) when the run acted on behalf of a known
    user, so the card reads "Mara Lindqvist needs your approval" rather
    than leading with a raw email.

    Args:
        run: The agent-run row in ``needs_approval``.
        principals: Optional ``{email: (user_id, display_name)}`` map the
            feed handler pre-resolves for every pending run's principal.

    Returns:
        Feed-row dict with ``render_kind = 'approval'``.
    """
    short = run.id[:8]
    resolved = (principals or {}).get(run.principal or "")
    if resolved is not None:
        actor_user_id, actor_display_name = resolved[0], resolved[1]
    else:
        actor_user_id, actor_display_name = None, (run.principal or run.agent_id or "an agent")
    return {
        "kind": "approval",
        "render_kind": "approval",
        "category": "approval",
        "severity": "warn",
        "attention": ATTENTION_ACT,
        "event_type": "pointlessql.agent_run.needs_approval",
        "run_id": run.id,
        "principal": run.principal,
        "notebook_path": run.notebook_path,
        "summary_md": f"Agent run {short} is awaiting approval",
        "body_md": run.notebook_path or "",
        "source_url": f"/runs/{run.id}",
        "data_product_id": None,
        "entity_kind": "run",
        "entity_ref": run.id,
        "actor_user_id": actor_user_id,
        "actor_display_name": actor_display_name,
        "created_at": run.started_at.isoformat() if run.started_at else "",
        "read_at": None,
    }


def row_from_signal(signal: ActionableSignal) -> dict[str, Any]:
    """Normalise an open actionable signal to the feed row shape.

    Like the pending-run row, this is *live* — read straight from
    ``actionable_signals`` where ``status='open'`` at query time, so
    the card disappears the moment the problem is resolved.  The
    ``render_kind`` is ``data_health`` for health lanes and
    ``pipeline`` for failure lanes; ``severity`` drives the stripe.

    Args:
        signal: The open signal row.

    Returns:
        Feed-row dict carrying ``signal_kind`` + ``signal_id`` so the
        inline acknowledge / snooze / retry actions can target it.
    """
    category, severity = classify_signal(signal.signal_kind)
    render_kind = "pipeline" if category == "pipeline" else "data_health"
    payload: dict[str, Any] = {}
    if signal.payload_json:
        try:
            loaded: Any = json.loads(signal.payload_json)
            if isinstance(loaded, dict):
                payload = cast("dict[str, Any]", loaded)
        except ValueError, TypeError:
            payload = {}
    source_url = payload.get("source_url") or entity_registry.url_for(
        signal.entity_kind, signal.entity_ref
    )
    return {
        "kind": "signal",
        "render_kind": render_kind,
        "category": category,
        "severity": signal.severity or severity,
        "attention": ATTENTION_ACT,
        "event_type": f"pointlessql.signal.{signal.signal_kind}",
        "signal_id": signal.id,
        "signal_kind": signal.signal_kind,
        "summary_md": signal.summary_md,
        "body_md": payload.get("detail") or signal.summary_md,
        "source_url": source_url,
        "data_product_id": None,
        "entity_kind": signal.entity_kind,
        "entity_ref": signal.entity_ref,
        "actor_user_id": None,
        "actor_display_name": None,
        "payload": payload,
        "created_at": signal.opened_at.isoformat() if signal.opened_at else "",
        "read_at": None,
    }


def active_mute_keys(session: Any, user_id: int) -> set[tuple[str, str]]:
    """Return ``{(entity_kind, entity_ref)}`` the caller has muted.

    the feed handler calls this once per request and
    drops rows whose ``(entity_kind, entity_ref)`` is in the set
    before serialising.  Rows with ``muted_until`` in the past are
    ignored (the rows persist so the user's history of mute picks
    survives, but they don't filter live data).

    Args:
        session: SQLAlchemy session.
        user_id: The caller's user id.

    Returns:
        Set of ``(entity_kind, entity_ref)`` tuples currently muted.
    """
    now = datetime.datetime.now(datetime.UTC)
    rows = session.execute(
        select(FeedMute.entity_kind, FeedMute.entity_ref).where(
            FeedMute.user_id == user_id,
            or_(
                FeedMute.muted_until.is_(None),
                FeedMute.muted_until > now,
            ),
        )
    ).all()
    return {(str(k), str(r)) for k, r in rows}


def build_actor_names(session: Any, rows_iter: Any) -> dict[int, str]:
    """Resolve ``{user_id: display_name}`` for actors in a row batch.

    the renderer needs actor display names to attribute
    feed items.  Building the map once per request avoids one query
    per row.  Pass any iterable of ``actor_user_id``-bearing objects
    (UserNotification, DataProductComment, DataProductReview); the
    function de-duplicates and returns only the ids it found.

    Args:
        session: SQLAlchemy session.
        rows_iter: Iterable of ORM rows carrying ``actor_user_id`` or
            ``author_user_id``.

    Returns:
        Dict mapping user-id to display-name.  Missing ids are simply
        absent; callers ``.get`` with a fallback.
    """
    ids: set[int] = set()
    for r in rows_iter:
        for attr in ("actor_user_id", "author_user_id"):
            v = getattr(r, attr, None)
            if v is not None:
                ids.add(int(v))
    if not ids:
        return {}
    pairs = session.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()
    return {int(uid): str(name) for uid, name in pairs}


def composer_target_refs(session: Any, workspace_id: int) -> list[str]:
    """Return every ``catalog.schema`` data-product ref in the workspace.

    Powers the feed composer's "post to" picker.  The pills are rendered
    server-side from this list (a ``<template x-for>`` inside the composer's
    toggled editor loses its DOM anchor in Alpine 3.14), so the route hands
    the template a plain ordered list of FQNs.

    Args:
        session: SQLAlchemy session.
        workspace_id: Workspace scope.

    Returns:
        Sorted list of ``catalog.schema`` strings.
    """
    rows = session.execute(
        select(DataProduct.catalog_name, DataProduct.schema_name)
        .where(DataProduct.workspace_id == workspace_id)
        .order_by(DataProduct.catalog_name, DataProduct.schema_name)
    ).all()
    return [f"{cat}.{sch}" for cat, sch in rows]


def build_fqn_map(session: Any, workspace_id: int) -> dict[int, str]:
    """Cache ``{dp_id: 'cat.sch'}`` for every DP in the workspace.

    The feed handler pre-fetches this once per request so the row
    builders can synthesise URLs via the entity registry without
    re-issuing one SELECT per row.

    Args:
        session: SQLAlchemy session.
        workspace_id: Workspace scope.

    Returns:
        Dict mapping data-product id to ``catalog.schema`` FQN.
    """
    rows = session.execute(
        select(DataProduct.id, DataProduct.catalog_name, DataProduct.schema_name).where(
            DataProduct.workspace_id == workspace_id
        )
    ).all()
    return {int(dp_id): f"{cat}.{sch}" for dp_id, cat, sch in rows}
