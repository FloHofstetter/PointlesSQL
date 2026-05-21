"""Cross-module constants, helpers, and serialisers.

Extracted from the 2231-LOC ``_polymorphic_handlers.py`` monolith
in Phase 89.1 — each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
)
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.social._entity_readme import EntityReadme
from pointlessql.services.social import (
    get_or_create_target,
)
from pointlessql.services.social.entity_registry import (
    get as registry_get,
)

# ---------------------------------------------------------------------------
# Per-axis constants reused from the DP handlers
# ---------------------------------------------------------------------------

_BODY_PREVIEW_LEN = 140
MAX_THREAD_DEPTH = 5

DISCUSSION_POSTED = "audit.discussion.posted"
DISCUSSION_DELETED = "audit.discussion.deleted"
_MENTION_RE = re.compile(r"@([\w.+-]+@[\w-]+\.[\w.-]+)")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)

ALLOWED_CATEGORIES: tuple[str, ...] = (
    "general",
    "question",
    "announcement",
    "idea",
    # Phase 101 Wave-D — review-decision category.  Surfaces a
    # ``notebook_cell`` comment as an explicit review pass; the
    # cell-thread UI renders the badge and the per-cell social
    # bulk-counts roll up review counts separately.
    "review",
)
ALLOWED_EMOJI: tuple[str, ...] = ("👍", "❤️", "🎉", "😄", "😕", "👀")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def body_preview(body_md: str) -> str:
    """Truncate a comment body for the audit-log detail JSON."""
    snippet = body_md.strip().replace("\n", " ")
    if len(snippet) > _BODY_PREVIEW_LEN:
        return snippet[: _BODY_PREVIEW_LEN - 1] + "…"
    return snippet


def extract_mention_emails(body_md: str) -> list[str]:
    """Return ``@email`` mentions in *body_md* with fenced code stripped."""
    stripped = _FENCED_CODE_RE.sub("", body_md)
    return _MENTION_RE.findall(stripped)


def resolve_mention_ids(session: Any, emails: list[str]) -> list[int]:
    """Map @-mention emails to persisted user ids (case-insensitive)."""
    if not emails:
        return []
    lowered = list({e.lower() for e in emails})
    rows = session.execute(
        select(User.id).where(User.email.in_(lowered))
    ).all()
    return [int(uid) for (uid,) in rows]


def chain_depth(session: Any, parent_id: int) -> int:
    """Return the depth of the existing reply chain ending at *parent_id*."""
    depth = 1
    current_id: int | None = parent_id
    while current_id is not None and depth <= MAX_THREAD_DEPTH + 1:
        parent = session.get(DataProductComment, current_id)
        if parent is None or parent.parent_comment_id is None:
            return depth
        current_id = parent.parent_comment_id
        depth += 1
    return depth


def collect_reactions(
    session: Any, comment_ids: list[int], caller_user_id: int
) -> dict[int, list[dict[str, Any]]]:
    """Return per-comment reaction aggregates keyed by comment id."""
    if not comment_ids:
        return {}
    rows = session.execute(
        select(
            DataProductCommentReaction.comment_id,
            DataProductCommentReaction.emoji,
            DataProductCommentReaction.user_id,
        ).where(DataProductCommentReaction.comment_id.in_(comment_ids))
    ).all()
    counts: dict[int, dict[str, int]] = {}
    mine: dict[int, set[str]] = {}
    for cid, emoji, uid in rows:
        counts.setdefault(cid, {e: 0 for e in ALLOWED_EMOJI})
        if emoji in counts[cid]:
            counts[cid][emoji] += 1
        if uid == caller_user_id:
            mine.setdefault(cid, set()).add(emoji)
    result: dict[int, list[dict[str, Any]]] = {}
    for cid in comment_ids:
        per = counts.get(cid, {e: 0 for e in ALLOWED_EMOJI})
        mine_set = mine.get(cid, set())
        result[cid] = [
            {
                "emoji": e,
                "count": per[e],
                "has_current_user_reacted": e in mine_set,
            }
            for e in ALLOWED_EMOJI
        ]
    return result


def serialise_comment(
    row: DataProductComment,
    *,
    author_email: str | None,
    author_display_name: str | None,
    body_md_resolved: str,
    reactions: list[dict[str, Any]] | None = None,
    agent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render one comment row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "social_target_id": row.social_target_id,
        "parent_comment_id": row.parent_comment_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "agent": agent,
        "body_md": "" if row.deleted_at else row.body_md,
        "body_md_resolved": body_md_resolved,
        "mentioned_user_ids": json.loads(row.mentioned_user_ids_json or "[]"),
        "category": row.category,
        "is_accepted_answer": bool(row.is_accepted_answer),
        "reactions": reactions if reactions is not None else [],
        "created_at": row.created_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


def serialise_endorsement(
    row: DataProductEndorsement,
    *,
    author_email: str | None,
    author_display_name: str | None,
    note_md_resolved: str,
) -> dict[str, Any]:
    """Render one endorsement row as JSON (no agent payload here)."""
    return {
        "id": row.id,
        "social_target_id": row.social_target_id,
        "endorsement_type": row.endorsement_type,
        "applied_by": {
            "user_id": row.applied_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "applied_at": row.applied_at.isoformat(),
        "removed_at": (
            row.removed_at.isoformat() if row.removed_at else None
        ),
        "note_md": row.note_md or "",
        "note_md_resolved": note_md_resolved,
    }


def serialise_readme(
    row: EntityReadme,
    *,
    author_email: str | None,
    author_display_name: str | None,
) -> dict[str, Any]:
    """Render one README version as JSON."""
    return {
        "id": row.id,
        "social_target_id": row.social_target_id,
        "version_int": row.version_int,
        "body_md": row.body_md,
        "updated_by": {
            "user_id": row.updated_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "updated_at": row.updated_at.isoformat(),
    }


def resolve_target_id(
    request: Request, kind: str, ref: str
) -> tuple[int, int]:
    """Resolve ``(workspace_id, social_target_id)`` for the kind+ref.

    For ``kind='dp'`` routes through :func:`resolve_dp_target` so the
    ``data_product_id`` back-pointer gets populated correctly; the
    plain :func:`get_or_create_target` requires the caller to know
    that id upfront, which the polymorphic Star / Follow paths
    don't until they resolve the DP themselves.

    Args:
        request: Active FastAPI request — used for workspace scope.
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.

    Returns:
        Tuple of ``(workspace_id, social_target_id)``.  The anchor
        row is created on demand if it does not yet exist.

    Raises:
        HTTPException: 404 when ``kind='dp'`` and no DataProduct
            exists at the requested ``catalog.schema``.
    """
    from pointlessql.services.social._target_resolver import resolve_dp_target

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        if kind == "dp":
            parts = ref.split(".", 1)
            if len(parts) != 2 or not all(parts):
                # bare-http-ok: ref shape is the API contract.
                raise HTTPException(
                    status_code=400,
                    detail="kind='dp' ref must be 'catalog.schema'",
                )
            try:
                target = resolve_dp_target(
                    session,
                    workspace_id=workspace_id,
                    catalog_name=parts[0],
                    schema_name=parts[1],
                )
            except LookupError as exc:
                # bare-http-ok: DP not found in this workspace.
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        else:
            target = get_or_create_target(
                session,
                workspace_id=workspace_id,
                kind=kind,
                ref=ref,
            )
        session.commit()
        return workspace_id, int(target.id)


def readme_supported(kind: str) -> None:
    """Raise 404 when *kind* has ``supports_readme=False``.

    Branches return ``supports_readme=False`` in the registry —
    the README endpoints would silently succeed otherwise because
    the underlying table has no kind gate.  We surface a clean
    404 so the client knows there's no READMEs for this entity.
    """
    spec = registry_get(kind)
    if not spec.supports_readme:
        # bare-http-ok: READMEs are entity-kind opt-in.
        raise HTTPException(
            status_code=404,
            detail=f"kind={kind!r} does not support READMEs",
        )


def endorsements_supported(kind: str) -> None:
    """Raise 404 when *kind* has ``supports_endorsements=False``."""
    spec = registry_get(kind)
    if not spec.supports_endorsements:
        # bare-http-ok: endorsements are entity-kind opt-in.
        raise HTTPException(
            status_code=404,
            detail=f"kind={kind!r} does not support endorsements",
        )


def reviews_supported(kind: str) -> None:
    """Raise 501 when *kind* has ``supports_reviews=False``."""
    spec = registry_get(kind)
    if not spec.supports_reviews:
        # bare-http-ok: reviews are entity-kind opt-in.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} does not support reviews "
                "(supports_reviews=False in the entity registry)"
            ),
        )


def serialise_review(
    row: DataProductReview,
    *,
    author_email: str | None,
    author_display_name: str | None,
    body_md_resolved: str,
) -> dict[str, Any]:
    """Render one polymorphic review row as JSON.

    Mirrors the DP-route serialiser shape minus the ``agent``
    payload — agent-on-behalf-of authoring stays a DP-only
    affordance.  The ``data_product_id`` field stays in the payload
    for backward JSON-shape compat; it is ``None`` for non-DP kinds.
    """
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "social_target_id": row.social_target_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "agent": None,
        "stars": row.stars,
        "body_md": row.body_md,
        "body_md_resolved": body_md_resolved,
        "dp_version_at_review": row.dp_version_at_review,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


