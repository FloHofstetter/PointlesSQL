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
from typing import Any

from sqlalchemy import or_, select

from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._feed_mute import FeedMute
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social import entity_registry

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def dp_url_from_id(fqn_map: dict[int, str], dp_id: int | None) -> str:
    """Build the DP detail URL from an id via the entity registry.

    Phase 77.0.I — the URL is built through
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

    Phase 81.K.2 — the renderer wants a coarser bucket than the dotted
    event-type string so per-kind Alpine branches stay readable.
    ``mentioned`` substrings light up the mention treatment, the rest
    map by prefix.  Unknown event types fall through to the generic
    notification card.

    Args:
        event_type: ``pointlessql.<scope>.<verb>`` event identifier.

    Returns:
        One of ``mention``, ``agent_run``, ``badge_award``, ``issue``,
        ``branch``, ``notification``.
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
    return "notification"


def row_from_notification(
    row: UserNotification,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
) -> dict[str, Any]:
    """Normalise a ``UserNotification`` to the feed row shape.

    Phase 81.K.2 adds the coarse ``render_kind`` discriminator + actor
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
    source_url = row.source_url or dp_url_from_id(
        fqn_map, row.source_data_product_id
    )
    render_kind = classify_notification(row.event_type or "")
    return {
        "id": row.id,
        "kind": "notification",
        "render_kind": render_kind,
        "event_type": row.event_type,
        "summary_md": row.summary_md,
        "body_md": row.summary_md,
        "source_url": source_url,
        "data_product_id": row.source_data_product_id,
        "entity_kind": row.source_entity_kind,
        "entity_ref": row.source_entity_ref,
        "actor_user_id": row.actor_user_id,
        "actor_display_name": (
            actor_names.get(int(row.actor_user_id))
            if row.actor_user_id is not None
            else None
        ),
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def row_from_comment(
    comment: DataProductComment,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
    target: SocialTarget | None = None,
) -> dict[str, Any]:
    """Normalise a comment to the feed row shape.

    Phase 81.K.2 carries the full ``body_md`` (Alpine truncates +
    "Show more"), ``actor_display_name``, ``comment_id``, and a
    ``render_kind`` of ``comment`` for the per-kind renderer.

    Args:
        comment: The comment row to normalise.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for the DP fallback.
        actor_names: ``{user_id: display_name}`` cache.
        target: Optional joined ``social_targets`` row.

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
        entity_ref = (
            fqn_map.get(int(dp_id)) if dp_id is not None else None
        )
        source_url = dp_url_from_id(fqn_map, dp_id)
    return {
        "kind": "comment",
        "render_kind": "comment",
        "event_type": "pointlessql.data_product.commented",
        "summary_md": comment.body_md[:160],
        "body_md": comment.body_md,
        "comment_id": comment.id,
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

    Phase 81.K.2 carries ``stars`` as a separate integer field
    (Alpine renders the actual stars row), full ``body_md``, and
    ``actor_display_name`` for the per-kind renderer.

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
        entity_ref = (
            fqn_map.get(int(dp_id)) if dp_id is not None else None
        )
        source_url = dp_url_from_id(fqn_map, dp_id)
    return {
        "kind": "review",
        "render_kind": "review",
        "event_type": "pointlessql.data_product.reviewed",
        "summary_md": f"{'★' * review.stars} — {review.body_md[:120]}",
        "body_md": review.body_md,
        "stars": int(review.stars),
        "source_url": source_url,
        "data_product_id": dp_id,
        "entity_kind": entity_kind,
        "entity_ref": entity_ref,
        "actor_user_id": review.author_user_id,
        "actor_display_name": actor_names.get(int(review.author_user_id)),
        "created_at": review.created_at.isoformat(),
        "read_at": None,
    }


def active_mute_keys(
    session: Any, user_id: int
) -> set[tuple[str, str]]:
    """Return ``{(entity_kind, entity_ref)}`` the caller has muted.

    Phase 81.K.4 — the feed handler calls this once per request and
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


def build_actor_names(
    session: Any, rows_iter: Any
) -> dict[int, str]:
    """Resolve ``{user_id: display_name}`` for actors in a row batch.

    Phase 81.K.2 — the renderer needs actor display names to attribute
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
    pairs = session.execute(
        select(User.id, User.display_name).where(User.id.in_(ids))
    ).all()
    return {int(uid): str(name) for uid, name in pairs}


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
        select(
            DataProduct.id, DataProduct.catalog_name, DataProduct.schema_name
        ).where(DataProduct.workspace_id == workspace_id)
    ).all()
    return {int(dp_id): f"{cat}.{sch}" for dp_id, cat, sch in rows}
