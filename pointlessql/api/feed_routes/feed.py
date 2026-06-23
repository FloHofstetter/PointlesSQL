"""Read-only feed endpoints: merged inbox, trending, people-to-follow.

* ``GET /api/feed`` — the canonical merged feed used by the activity
  pane.  Combines ``user_notifications`` rows (the fan-out target for
  every reactive social event) with comments + reviews authored by
  users the caller follows, dedupes, mute-filters, and returns the
  Alpine-renderable shape.
* ``GET /api/feed/trending`` — top-N entities by 24 h activity count.
* ``GET /api/feed/people`` — top contributors the caller does not
  already follow, 7 d window.

The per-request ``session.execute(...)`` data-fetch blocks live in
:mod:`pointlessql.api.feed_routes._queries`; row→dict shaping lives in
:mod:`pointlessql.api.feed_routes._serializers`.  These route bodies only
orchestrate.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.api.feed_routes._queries import (
    fetch_display_names,
    fetch_followed_overlay,
    fetch_followed_user_ids,
    fetch_inbox,
    fetch_mention_rows,
    fetch_my_rows,
    fetch_needs_action_count,
    fetch_open_signals,
    fetch_pending_runs,
    fetch_people_activity_counts,
    fetch_reply_counts,
    fetch_run_principals,
    fetch_seen_at,
    fetch_trending_counts,
    fetch_unread_for_you_count,
)
from pointlessql.api.feed_routes._serializers import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    active_mute_keys,
    build_actor_names,
    build_fqn_map,
    row_from_comment,
    row_from_notification,
    row_from_pending_run,
    row_from_review,
    row_from_signal,
)
from pointlessql.services.notifications.categories import (
    ATTENTION_ACT,
    ATTENTION_FOR_YOU,
    count_by_category,
)
from pointlessql.services.social import entity_registry

router = APIRouter(tags=["feed"])

_TRENDING_WINDOW = datetime.timedelta(hours=24)
_PEOPLE_WINDOW = datetime.timedelta(days=7)


def _parse_row_dt(value: object) -> datetime.datetime | None:
    """Parse a serialized row's ``created_at`` back to a datetime.

    Row timestamps are ISO-8601 strings produced by ``.isoformat()`` on
    timezone-aware UTC datetimes.  Returns ``None`` for empty / malformed
    values (e.g. a pending run with no ``started_at``) so the caller can
    treat the row as not-new rather than crash on the seen-cursor
    comparison.

    Args:
        value: The row's ``created_at`` field.

    Returns:
        A timezone-aware datetime, or ``None`` when unparseable.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed


# Entity kinds whose ``entity_ref`` is an internal id with no standalone
# display value — excluded from the Trending rail.
_TRENDING_SKIP_KINDS = frozenset({"user", "review", "badge"})


@router.get("/api/feed")
async def get_feed(
    request: Request,
    filter: str = "all",  # noqa: A002 — query param shadows builtin intentionally
    limit: int = DEFAULT_LIMIT,
    q: str = "",
    kind: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Return the caller's merged feed.

    the feed now lists comments + reviews across every
    polymorphic entity kind (table / model / branch / run / etc.),
    not just data products.  The new optional ``kind`` query
    parameter narrows the result set to one ``entity_kind`` value;
    legacy ``kind=dp`` keeps the historical DP-only view available.
    Each row's ``source_url`` is built through
    :func:`entity_registry.url_for` so the link lands on the right
    detail page regardless of kind.

    Args:
        request: Incoming FastAPI request.
        filter: One of ``all`` (default), ``mentions``,
            ``followed_users``, ``followed_dps``, ``my``.
            Unknown values fall back to ``all``.
        limit: Result cap; clamped to ``[1, 200]``.
        q: Optional substring match on the row summary.  Case-
            insensitive; an empty value disables filtering.
        kind: Optional ``entity_kind`` narrow — e.g. ``table`` keeps
            only table comments/reviews/notifications.  ``None``
            disables the filter.
        category: Optional coarse-lane narrow — one of ``approval``,
            ``health``, ``social``, ``pipeline``, ``governance``.
            ``None`` or ``all`` returns every lane.  The
            ``category_counts`` in the response are computed *before*
            this slice so the chip badges stay stable when a lane is
            selected.

    Returns:
        ``{"filter", "kind", "category", "rows", "category_counts"}``
        with rows sorted by ``created_at`` descending.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    limit = max(1, min(MAX_LIMIT, int(limit)))
    needle = q.strip().lower()
    is_admin = bool(caller.get("is_admin"))

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        # per-request DP-FQN cache feeds the registry-driven URL builder so
        # every feed row carries the same shape ``social_target.entity_ref``
        # rows use.
        fqn_map = build_fqn_map(session, workspace_id)

        # Inbox rows + the followed-users overlay (comments + reviews).  The
        # filter trims after merge, so both are always pulled here.
        inbox = fetch_inbox(session, caller_id=caller["id"], workspace_id=workspace_id, limit=limit)
        followed_user_ids = fetch_followed_user_ids(session, caller_id=caller["id"])
        comments_rows, reviews_rows = fetch_followed_overlay(
            session,
            followed_user_ids=followed_user_ids,
            workspace_id=workspace_id,
            limit=limit,
        )

        # bulk-resolve actor display names so every feed row carries an
        # attribution line — one SELECT for all surfaced user-ids.
        actor_names = build_actor_names(
            session,
            list(inbox) + [c for c, _ in comments_rows] + [r for r, _ in reviews_rows],
        )
        # One grouped SELECT for the reply count under every surfaced
        # comment, so each card can show "View N replies" without a per-row
        # query.
        comment_ids = [int(c.id) for c, _ in comments_rows]
        reply_counts = fetch_reply_counts(
            session, comment_ids=comment_ids, workspace_id=workspace_id
        )

        rows.extend(row_from_notification(n, fqn_map, actor_names) for n in inbox)
        rows.extend(
            row_from_comment(c, fqn_map, actor_names, t, reply_counts.get(int(c.id), 0))
            for c, t in comments_rows
        )
        rows.extend(row_from_review(r, fqn_map, actor_names, t) for r, t in reviews_rows)

        # Action-required lane (live): agent runs in ``needs_approval`` and
        # open actionable signals are read straight from their source
        # tables — never stored as notifications — so the inline cards
        # always reflect current state.  Admin-gated: triage is admin-only.
        if is_admin:
            pending_runs = fetch_pending_runs(session, workspace_id=workspace_id, limit=limit)
            principals = fetch_run_principals(session, pending_runs=pending_runs)
            rows.extend(row_from_pending_run(r, principals) for r in pending_runs)
            open_signals = fetch_open_signals(session, workspace_id=workspace_id, limit=limit)
            rows.extend(row_from_signal(s) for s in open_signals)

        # Attention-tier counts power the "needs you" badge + zone header.
        # They are counted independently of the row slice so a capped fetch
        # never under-reports what is waiting.  The ``act`` work is
        # admin-gated like the cards; the ``for_you`` count covers everyone.
        needs_action_count = (
            fetch_needs_action_count(session, workspace_id=workspace_id) if is_admin else 0
        )
        seen_at = fetch_seen_at(session, caller_id=caller["id"], workspace_id=workspace_id)
        unread_for_you_count = fetch_unread_for_you_count(
            session, caller_id=caller["id"], workspace_id=workspace_id
        )

        # Filter overlays — ``mentions`` / ``my`` replace the merged set
        # with their own query; ``followed_*`` narrow the merged rows.
        if filter == "mentions":
            rows = fetch_mention_rows(
                session, caller_id=caller["id"], workspace_id=workspace_id, fqn_map=fqn_map
            )
        elif filter == "my":
            rows = fetch_my_rows(session, caller_id=caller["id"], fqn_map=fqn_map, limit=limit)
        elif filter == "followed_users":
            rows = [r for r in rows if r["kind"] in ("comment", "review")]
        elif filter == "followed_dps":
            # Inbox events for the followed-DPs case already arrive
            # via the fanout, so keep notification rows only.
            rows = [r for r in rows if r["kind"] == "notification"]

    if needle:
        rows = [r for r in rows if needle in (r.get("summary_md") or "").lower()]

    # kind-filter accepts a comma-separated list of
    # entity-kind values; rows pass when any selected kind matches.
    # A single value keeps the single-kind behaviour.
    if kind:
        wanted_kinds = {k.strip() for k in kind.split(",") if k.strip()}
        if wanted_kinds:
            rows = [r for r in rows if r.get("entity_kind") in wanted_kinds]

    # drop rows muted by the caller.  Muted threads
    # are identified by ``(entity_kind, entity_ref)``; muted authors
    # are stored as ``(entity_kind='user', entity_ref=<user_id>)``
    # so the same set covers both axes in one membership test.
    with factory() as session:
        mute_keys = active_mute_keys(session, caller["id"])
    if mute_keys:
        rows = [
            r
            for r in rows
            if (str(r.get("entity_kind")), str(r.get("entity_ref"))) not in mute_keys
            and ("user", str(r.get("actor_user_id"))) not in mute_keys
        ]

    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

    # De-duplicate by (kind, event_type, summary_md, created_at) to
    # collapse cases where an inbox row + a direct author-overlay row
    # describe the same event (rare but possible).
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("kind")),
            str(row.get("event_type")),
            str(row.get("summary_md")),
            str(row.get("created_at")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    # Chip counts are tallied across every lane *before* the category
    # slice so the badges don't collapse to the selected lane.
    category_counts = count_by_category(unique)

    # Category slice — coarse lane narrow over the stamped ``category``
    # field.  ``all`` / unset returns every lane.
    if category and category != "all":
        unique = [r for r in unique if r.get("category") == category]

    result_rows = unique[:limit]

    # Stamp each row "new" relative to the seen-cursor, and tally how
    # many *stream* rows are still unseen — i.e. rows that flow below the
    # caught-up divider, not the act / unread-for-you rows the client
    # pins into the "needs you" zone.  ``caught_up`` is the composite
    # "nothing waiting + nothing unseen" state that drives the
    # celebratory end-of-feed marker.
    unseen_count = 0
    for row in result_rows:
        row_dt = _parse_row_dt(row.get("created_at"))
        is_new = seen_at is None or (row_dt is not None and row_dt > seen_at)
        row["is_new"] = is_new
        in_zone = row.get("attention") == ATTENTION_ACT or (
            row.get("attention") == ATTENTION_FOR_YOU and not row.get("read_at")
        )
        if is_new and not in_zone:
            unseen_count += 1
    caught_up = needs_action_count == 0 and unread_for_you_count == 0 and unseen_count == 0

    return {
        "filter": filter,
        "kind": kind,
        "category": category,
        "rows": result_rows,
        "category_counts": category_counts,
        "needs_action_count": needs_action_count,
        "unread_for_you_count": unread_for_you_count,
        "unseen_count": unseen_count,
        "caught_up": caught_up,
        "seen_at": seen_at.isoformat() if seen_at else None,
    }


# ---------------------------------------------------------------
# right-column endpoints.
#
# Two read-only feeds drive the discovery panel:
# ``GET /api/feed/trending`` and ``GET /api/feed/people``.  Both
# scope to the caller's workspace; both surface only entities /
# users that have actually been active in the relevant window.
# ---------------------------------------------------------------


@router.get("/api/feed/trending")
async def get_trending(request: Request, limit: int = 5) -> dict[str, Any]:
    """Top-N entities by activity-count in the caller's workspace.

    drives the "Trending today" card on the feed's
    right column.  Aggregates ``user_notifications`` group-by
    ``(source_entity_kind, source_entity_ref)`` over the last 24 h,
    count desc.

    Args:
        request: Incoming FastAPI request.
        limit: Result cap; clamped to ``[1, 20]``.  Defaults to 5
            (one card-row each).

    Returns:
        ``{"rows": [{"entity_kind", "entity_ref", "label",
        "source_url", "count"}, ...]}`` sorted count desc.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    cap = max(1, min(20, int(limit)))
    factory = request.app.state.session_factory
    cutoff = datetime.datetime.now(datetime.UTC) - _TRENDING_WINDOW
    with factory() as session:
        rows = fetch_trending_counts(session, workspace_id=workspace_id, cutoff=cutoff, limit=cap)
    out: list[dict[str, Any]] = []
    for kind, ref, count in rows:
        if not kind or not ref:
            continue
        # Internal-id kinds (a user PK, an agent-review id) carry no
        # human-readable label on their own and don't belong in a
        # "trending entities" list — skip them rather than surface a bare
        # "1" / "w23" to the rail.
        if str(kind) in _TRENDING_SKIP_KINDS:
            continue
        # Run refs are opaque UUIDs — show a short handle instead of the
        # full 36-char id; every other kind's ref already reads as an FQN.
        label = f"run {str(ref)[:8]}" if str(kind) == "run" else str(ref)
        out.append(
            {
                "entity_kind": str(kind),
                "entity_ref": str(ref),
                "label": label,
                "source_url": entity_registry.url_for(str(kind), str(ref)),
                "count": int(count),
            }
        )
    return {"rows": out}


@router.get("/api/feed/people")
async def get_people_to_follow(request: Request, limit: int = 5) -> dict[str, Any]:
    """Top contributors the caller doesn't follow yet.

    drives the "People to follow" card.  Looks at
    the last 7 days of comments + reviews, picks the most active
    authors that aren't already in the caller's ``user_follows``
    set, and returns ``{id, display_name, recent_event_count}``.

    Args:
        request: Incoming FastAPI request.
        limit: Result cap; clamped to ``[1, 20]``.  Defaults to 5.

    Returns:
        ``{"rows": [...]}`` sorted by recent-event count desc.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    cap = max(1, min(20, int(limit)))
    factory = request.app.state.session_factory
    cutoff = datetime.datetime.now(datetime.UTC) - _PEOPLE_WINDOW
    with factory() as session:
        # Already-followed user ids.
        followed: set[int] = set(fetch_followed_user_ids(session, caller_id=caller["id"]))
        # Comment + review activity authored in window.  Counts both
        # tables and sums client-side to keep the SQL portable across
        # SQLite + Postgres.
        comment_counts, review_counts = fetch_people_activity_counts(
            session, workspace_id=workspace_id, cutoff=cutoff
        )
        totals: dict[int, int] = {}
        for uid, c in comment_counts:
            totals[int(uid)] = totals.get(int(uid), 0) + int(c)
        for uid, c in review_counts:
            totals[int(uid)] = totals.get(int(uid), 0) + int(c)
        # Drop caller + already-followed.
        candidates = sorted(
            (
                (uid, total)
                for uid, total in totals.items()
                if uid != caller["id"] and uid not in followed
            ),
            key=lambda x: x[1],
            reverse=True,
        )[:cap]
        if not candidates:
            return {"rows": []}
        ids = [uid for uid, _ in candidates]
        names = fetch_display_names(session, user_ids=ids)
    return {
        "rows": [
            {
                "id": int(uid),
                "display_name": str(names.get(uid, f"user-{uid}")),
                "recent_event_count": int(total),
            }
            for uid, total in candidates
        ]
    }
