r"""Champion/Challenger promotion service.

A registered model carries at most one *champion* version at a time.
Operators (or supervisor-scoped agents) promote a challenger version
to champion through :func:`promote_version`, which:

1. Validates the challenger is ``READY`` and not already champion.
2. Patches the registered-model's ``comment`` field with a
   ``_pql_promotion`` JSON marker (analog to ``_pql_link`` from
   see
   :mod:`pointlessql.services.agent_runs.mlflow_soyuz_link`).
3. Inserts an :class:`AgentReview` row with
   ``kind="model_promotion"`` so the  cockpit fan-out can
   notify subscribed webhooks.
4. Returns a CloudEvents 1.0 envelope (``pointlessql.model.promoted``)
   the caller is free to dispatch.

The marker convention deliberately spiegelt ``_pql_link`` — both
JSON blobs coexist in the same ``comment`` field, separated by
``\n\n`` chunks, so the read-side parsers stay independent. A
future migration to first-class soyuz aliases (out of scope for
) re-emits markers as real catalog tags via a one-shot
script.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from pointlessql.exceptions import PointlessSQLError
from pointlessql.models import AgentReview

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.services.unitycatalog import UnityCatalogClient

_logger = logging.getLogger(__name__)

_MARKER_KEY = "_pql_promotion"

EVENT_TYPE_MODEL_PROMOTED = "pointlessql.model.promoted"


class PromotionError(PointlessSQLError):
    """Raised when a champion/challenger swap cannot be applied."""


def parse_promotion_marker(comment: str | None) -> dict[str, Any] | None:
    """Extract the ``_pql_promotion`` marker from a comment, if present.

    Counterpart to :func:`serialize_promotion_marker`.  Returns the
    most recent marker chunk so a later promotion overwrites the
    earlier one cleanly.

    Args:
        comment: Registered-model ``comment`` value, possibly
            ``None``.

    Returns:
        The marker payload dict, or ``None`` when no marker is
        present.
    """
    if not comment:
        return None
    found: dict[str, Any] | None = None
    for chunk in comment.split("\n\n"):
        chunk = chunk.strip()
        if _MARKER_KEY not in chunk:
            continue
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        marker = parsed.get(_MARKER_KEY)
        if isinstance(marker, dict):
            found = marker
    return found


def serialize_promotion_marker(
    *,
    champion_version: int,
    promoted_by: str,
    promoted_at: datetime.datetime,
    reason: str,
    previous_champion: int | None,
    existing_comment: str | None,
) -> str:
    """Build the new ``comment`` payload, preserving any user prose.

    Replaces a prior ``_pql_promotion`` marker — promotion is
    idempotent: re-promoting a version simply rewrites the marker
    with a new ``promoted_at`` timestamp.  Other markers (including
    ``_pql_link``) survive untouched.

    Args:
        champion_version: New champion version.
        promoted_by: Email or identity of the actor.
        promoted_at: UTC promotion timestamp.
        reason: Free-text justification (mandatory at the API
            boundary).
        previous_champion: The version this swap dethroned, or
            ``None`` on the first promotion.
        existing_comment: Whatever currently lives in
            ``registered_model.comment``, possibly ``None``.

    Returns:
        The new ``comment`` value to PATCH back.
    """
    blob: dict[str, Any] = {
        "champion_version": champion_version,
        "promoted_by": promoted_by,
        "promoted_at": promoted_at.isoformat(),
        "reason": reason,
    }
    if previous_champion is not None:
        blob["previous_champion"] = previous_champion
    marker = json.dumps({_MARKER_KEY: blob}, sort_keys=True)
    if not existing_comment:
        return marker
    parts = existing_comment.split("\n\n")
    cleaned = [p for p in parts if _MARKER_KEY not in p]
    cleaned.append(marker)
    return "\n\n".join(cleaned)


async def get_current_champion(
    uc_client: UnityCatalogClient,
    full_name: str,
) -> int | None:
    """Return the currently-promoted champion version, or a sensible default.

    Reads the registered-model's ``_pql_promotion`` marker. If no
    marker exists yet, falls back to the highest-numbered ``READY``
    version (so a never-promoted model still has an obvious answer).

    Args:
        uc_client: A configured ``UnityCatalogClient``.
        full_name: Three-level FQN ``catalog.schema.model``.

    Returns:
        The champion version number, or ``None`` if the model has
        no READY versions yet.
    """
    model = await uc_client.get_registered_model(full_name)
    if not model:
        return None
    marker = parse_promotion_marker(model.get("comment"))
    if marker is not None:
        ver = marker.get("champion_version")
        if isinstance(ver, int):
            return ver
    versions = await uc_client.list_model_versions(full_name=full_name)
    versions_int: list[int] = []
    for v in versions:
        if v.get("status") != "READY":
            continue
        ver = v.get("version")
        if isinstance(ver, int):
            versions_int.append(ver)
    if not versions_int:
        return None
    return max(versions_int)


def build_model_promoted_event(
    *,
    model_full_name: str,
    champion_version: int,
    previous_champion: int | None,
    promoted_by: str,
    reason: str,
    promoted_at: datetime.datetime,
    review_id: int | None,
) -> dict[str, Any]:
    """Build the CloudEvents 1.0 envelope for ``pointlessql.model.promoted``.

    Args:
        model_full_name: Three-level FQN ``catalog.schema.model``.
        champion_version: New champion version number.
        previous_champion: Version that lost champion status, or
            ``None`` on the first promotion.
        promoted_by: Email/identity of the actor.
        reason: Free-text justification.
        promoted_at: UTC promotion timestamp.
        review_id: Primary key of the matching ``AgentReview`` row.

    Returns:
        A CloudEvents 1.0 envelope dict ready for webhook dispatch.
    """
    data: dict[str, Any] = {
        "model_full_name": model_full_name,
        "champion_version": champion_version,
        "promoted_by": promoted_by,
        "reason": reason,
        "promoted_at": promoted_at.isoformat(),
    }
    if previous_champion is not None:
        data["previous_champion"] = previous_champion
    if review_id is not None:
        data["review_id"] = review_id

    source = (
        f"/pointlessql/agent_reviews/{review_id}"
        if review_id is not None
        else "/pointlessql/model_promotion"
    )
    return {
        "specversion": "1.0",
        "id": uuid.uuid4().hex,
        "source": source,
        "type": EVENT_TYPE_MODEL_PROMOTED,
        "time": promoted_at.isoformat(),
        "datacontenttype": "application/json",
        "subject": f"{model_full_name}@v{champion_version}",
        "data": data,
    }


def _record_promotion_review(
    session: Session,
    *,
    model_full_name: str,
    champion_version: int,
    previous_champion: int | None,
    promoted_by: str,
    reason: str,
    promoted_at: datetime.datetime,
) -> int:
    """Insert one ``agent_reviews`` row for the promotion.

    Uses a 1-microsecond span around ``promoted_at`` to satisfy the
    ``period_end > period_start`` CHECK without leaking arbitrary
    review-window semantics.

    Args:
        session: Active SQLAlchemy session (caller commits).
        model_full_name: Three-level FQN.
        champion_version: New champion version.
        previous_champion: Dethroned version or ``None``.
        promoted_by: Actor identity.
        reason: Free-text justification.
        promoted_at: UTC promotion timestamp.

    Returns:
        Primary key of the new review row.
    """
    period_end = promoted_at + datetime.timedelta(microseconds=1)
    payload = {
        "model_full_name": model_full_name,
        "champion_version": champion_version,
        "previous_champion": previous_champion,
        "promoted_by": promoted_by,
        "reason": reason,
    }
    summary = (
        f"Promoted **{model_full_name}** to champion v{champion_version}"
        + (f" (was v{previous_champion})" if previous_champion is not None else "")
        + f" by `{promoted_by}`.\n\nReason: {reason}"
    )
    review = AgentReview(
        run_id=None,
        kind="model_promotion",
        period_start=promoted_at,
        period_end=period_end,
        severity="ok",
        summary_md=summary,
        payload_json=json.dumps(payload, sort_keys=True),
        delivered_to_json=None,
        created_at=promoted_at,
    )
    session.add(review)
    session.flush()
    return review.id


async def promote_version(
    factory: sessionmaker[Session],
    uc_client: UnityCatalogClient,
    full_name: str,
    *,
    target_version: int,
    promoted_by: str,
    reason: str,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Promote ``target_version`` of ``full_name`` to champion.

    The promotion writes a ``_pql_promotion`` marker into the
    registered-model's ``comment``, inserts a ``model_promotion``
    review row, and returns the matching CloudEvent envelope so the
    caller (typically the API route) can dispatch it through the
    webhook fan-out.

    Args:
        factory: SQLAlchemy session factory for the audit DB.
        uc_client: Per-request ``UnityCatalogClient`` (the caller is
            responsible for forwarding ``X-Principal``).
        full_name: Three-level FQN ``catalog.schema.model``.
        target_version: The version to crown.
        promoted_by: Email/identity of the actor (typically the
            cookie user's email or an API-key principal).
        reason: Free-text justification.  Empty/whitespace strings
            are rejected.
        now: Optional override for the promotion timestamp; defaults
            to ``datetime.now(UTC)``.

    Returns:
        ``{"champion_version", "previous_champion", "promoted_at",
        "review_id", "event"}`` — the event is the unsent CloudEvents
        envelope.

    Raises:
        PromotionError: When ``target_version`` is missing, not
            READY, already champion, or when soyuz rejects the
            comment PATCH.
    """
    if not reason or not reason.strip():
        raise PromotionError("reason is required for promotion")

    target_info = await uc_client.get_model_version(full_name, target_version)
    if not target_info:
        raise PromotionError(
            f"version {target_version} of {full_name!r} not found"
        )
    if target_info.get("status") != "READY":
        raise PromotionError(
            f"version {target_version} is not READY (status={target_info.get('status')!r})"
        )

    previous_champion = await get_current_champion(uc_client, full_name)
    if previous_champion == target_version:
        raise PromotionError(
            f"version {target_version} is already champion"
        )

    model = await uc_client.get_registered_model(full_name)
    if not model:
        raise PromotionError(f"registered model {full_name!r} not found")

    promoted_at = now or datetime.datetime.now(datetime.UTC)
    new_comment = serialize_promotion_marker(
        champion_version=target_version,
        promoted_by=promoted_by,
        promoted_at=promoted_at,
        reason=reason.strip(),
        previous_champion=previous_champion,
        existing_comment=model.get("comment"),
    )

    try:
        await uc_client.update_registered_model(full_name, comment=new_comment)
    except Exception as exc:  # noqa: BLE001 — re-raise as PromotionError
        raise PromotionError(
            f"soyuz comment PATCH failed for {full_name!r}: {exc}"
        ) from exc

    with factory() as session:
        review_id = _record_promotion_review(
            session,
            model_full_name=full_name,
            champion_version=target_version,
            previous_champion=previous_champion,
            promoted_by=promoted_by,
            reason=reason.strip(),
            promoted_at=promoted_at,
        )
        session.commit()

    event = build_model_promoted_event(
        model_full_name=full_name,
        champion_version=target_version,
        previous_champion=previous_champion,
        promoted_by=promoted_by,
        reason=reason.strip(),
        promoted_at=promoted_at,
        review_id=review_id,
    )
    _logger.info(
        "Promoted %s/v%d (was v%s) by %s",
        full_name,
        target_version,
        previous_champion,
        promoted_by,
    )
    return {
        "champion_version": target_version,
        "previous_champion": previous_champion,
        "promoted_at": promoted_at.isoformat(),
        "review_id": review_id,
        "event": event,
    }


async def list_promotion_history(
    factory: sessionmaker[Session],
    full_name: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the chronological promotion history for a model.

    Reads the ``agent_reviews`` table filtered by
    ``kind="model_promotion"`` and the model FQN inside
    ``payload_json``.  Newest entry first, capped at *limit*.

    Args:
        factory: Audit-DB session factory.
        full_name: Three-level FQN ``catalog.schema.model``.
        limit: Maximum number of entries to return.

    Returns:
        A list of ``{review_id, champion_version, previous_champion,
        promoted_by, reason, promoted_at}`` dicts.
    """
    from sqlalchemy import select

    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentReview)
            .where(AgentReview.kind == "model_promotion")
            .order_by(AgentReview.id.desc())
            .limit(limit)
        )
        for review in session.scalars(stmt).all():
            payload: dict[str, Any] = {}
            if review.payload_json:
                try:
                    payload = json.loads(review.payload_json)
                except json.JSONDecodeError:
                    payload = {}
            if payload.get("model_full_name") != full_name:
                continue
            rows.append(
                {
                    "review_id": review.id,
                    "champion_version": payload.get("champion_version"),
                    "previous_champion": payload.get("previous_champion"),
                    "promoted_by": payload.get("promoted_by"),
                    "reason": payload.get("reason"),
                    "promoted_at": review.created_at.isoformat()
                    if review.created_at
                    else None,
                }
            )
    return rows
