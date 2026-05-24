"""``/api/topics/{slug}`` + topic-assignment on DPs.

Two endpoints:

* ``GET /api/topics/{slug}`` — detail with the list of DPs in the
  topic + follower count.
* ``PUT /api/data-products/{c}/{s}/topics`` — replace-all
  assignment.  Steward / install-admin only.  Fans out
  ``pointlessql.topic.dp_added`` per added topic so topic
  followers receive an inbox row.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import delete, func, select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._topic import (
    DataProductTopic,
    Topic,
    UserTopicFollow,
)
from pointlessql.services import audit as audit_service
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_TOPIC_DP_ADDED,
    emit_governance_event,
)

router = APIRouter(tags=["topics"])

_AUDIT_DP_TOPICS_SET = "audit.data_product.topics_set"


@router.get("/api/topics/{slug}")
async def topic_detail(slug: str, request: Request) -> dict[str, Any]:
    """Return a topic + its assigned DPs + follower count.

    Args:
        slug: URL-safe topic identifier.
        request: Incoming FastAPI request.

    Returns:
        ``{"topic": {...}, "data_products": [...],
        "followers": int, "viewer_follows": bool}``.

    Raises:
        HTTPException: 404 when the slug does not resolve.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        topic = session.execute(
            select(Topic).where(
                Topic.workspace_id == workspace_id, Topic.slug == slug
            )
        ).scalar_one_or_none()
        if topic is None:
            raise ResourceNotFoundError(f"topic {slug!r} not found.")

        dps = (
            session.execute(
                select(
                    DataProduct.id,
                    DataProduct.catalog_name,
                    DataProduct.schema_name,
                    DataProduct.description,
                )
                .join(
                    DataProductTopic,
                    DataProductTopic.data_product_id == DataProduct.id,
                )
                .where(DataProductTopic.topic_id == topic.id)
                .order_by(DataProduct.catalog_name, DataProduct.schema_name)
            )
            .all()
        )
        followers = int(
            session.execute(
                select(func.count())
                .select_from(UserTopicFollow)
                .where(UserTopicFollow.topic_id == topic.id)
            ).scalar_one()
        )
        viewer_follows = (
            session.execute(
                select(UserTopicFollow).where(
                    UserTopicFollow.topic_id == topic.id,
                    UserTopicFollow.user_id == caller["id"],
                )
            ).first()
            is not None
        )

    return {
        "topic": {
            "id": topic.id,
            "slug": topic.slug,
            "display_name": topic.display_name,
            "description_md": topic.description_md,
        },
        "data_products": [
            {
                "id": int(d),
                "catalog": c,
                "schema": s,
                "description": n,
            }
            for d, c, s, n in dps
        ],
        "followers": followers,
        "viewer_follows": viewer_follows,
    }


@router.put("/api/data-products/{catalog}/{schema}/topics")
async def set_dp_topics(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Replace the DP's topic assignment with the supplied list.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "topic_slugs": [...]}``.

    Raises:
        AuthorizationError: When the caller is not steward / admin.
        HTTPException: 400 if an unknown slug is supplied;
            404 if the DP is missing.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    is_steward = row.steward_user_id is not None and row.steward_user_id == caller["id"]
    is_admin = bool(caller.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=caller.get("email", ""),
            privilege="set_topics",
            securable_type="data_product",
            full_name=f"{catalog}.{schema}",
        )

    body = await request.json()
    raw_value: Any = body.get("topics") or []
    if not isinstance(raw_value, list):
        raise BadRequestError("topics must be a list")
    slugs: list[str] = [
        str(s).strip().lower() for s in raw_value if str(s).strip()  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
    ]
    slugs = list(dict.fromkeys(slugs))  # de-dup, preserve order

    now = datetime.datetime.now(datetime.UTC)
    added_topics: list[Topic] = []
    with factory() as session:
        if slugs:
            found = (
                session.execute(
                    select(Topic).where(
                        Topic.workspace_id == workspace_id,
                        Topic.slug.in_(slugs),
                    )
                )
                .scalars()
                .all()
            )
            found_slugs = {t.slug for t in found}
            missing = [s for s in slugs if s not in found_slugs]
            if missing:
                raise BadRequestError(f"unknown topic slug(s): {missing}")
            topics_by_slug: dict[str, Topic] = {t.slug: t for t in found}
        else:
            topics_by_slug = {}

        previously = {
            int(tid)
            for (tid,) in session.execute(
                select(DataProductTopic.topic_id).where(
                    DataProductTopic.data_product_id == row.id
                )
            ).all()
        }
        target_ids = {topics_by_slug[s].id for s in slugs}

        # Delete dropped + insert added — replace-all semantics.
        if previously - target_ids:
            session.execute(
                delete(DataProductTopic).where(
                    DataProductTopic.data_product_id == row.id,
                    DataProductTopic.topic_id.in_(previously - target_ids),
                )
            )
        for slug in slugs:
            topic = topics_by_slug[slug]
            if topic.id in previously:
                continue
            session.add(
                DataProductTopic(
                    data_product_id=row.id,
                    topic_id=topic.id,
                    added_by_user_id=caller["id"],
                    added_at=now,
                )
            )
            added_topics.append(topic)
        session.commit()

        # Fanout to followers of newly-added topics.
        fanout_pairs: list[tuple[Topic, list[int]]] = []
        for t in added_topics:
            follower_ids = (
                session.execute(
                    select(UserTopicFollow.user_id).where(
                        UserTopicFollow.topic_id == t.id
                    )
                )
                .scalars()
                .all()
            )
            recipients = [int(uid) for uid in follower_ids if uid != caller["id"]]
            fanout_pairs.append((t, recipients))

    audit_service.log_action(
        factory,
        user_id=caller["id"],
        user_email=caller.get("email", ""),
        action=_AUDIT_DP_TOPICS_SET,
        target=f"data_product:{catalog}.{schema}",
        detail={"topic_slugs": slugs},
        workspace_id=workspace_id,
    )

    for topic, recipients in fanout_pairs:
        if recipients:
            try:
                with factory() as session:
                    session.add_all(
                        [
                            UserNotification(
                                workspace_id=workspace_id,
                                recipient_user_id=rid,
                                event_type=EVENT_TYPE_TOPIC_DP_ADDED,
                                source_data_product_id=row.id,
                                source_url=f"/topics/{topic.slug}",
                                summary_md=(
                                    f"New data product **{catalog}.{schema}**"
                                    f" joined topic **{topic.display_name}**"
                                ),
                                actor_user_id=caller["id"],
                                created_at=now,
                            )
                            for rid in recipients
                        ]
                    )
                    session.commit()
            # bare-broad-ok: inbox fan-out is best-effort — a
            # transient DB error must not abort the surrounding
            # POST handler that already committed the topic-link.
            except Exception:  # noqa: BLE001 — fan-out is best-effort.
                pass
        await emit_governance_event(
            EVENT_TYPE_TOPIC_DP_ADDED,
            {
                "topic_id": topic.id,
                "topic_slug": topic.slug,
                "data_product_id": row.id,
                "data_product_ref": f"{catalog}.{schema}",
                "actor_user_id": caller["id"],
            },
            settings=request.app.state.settings,
            session_factory=factory,
            workspace_id=workspace_id,
        )

    return {
        "data_product_id": row.id,
        "topic_slugs": slugs,
    }


@router.get("/api/data-products/{catalog}/{schema}/topics")
async def get_dp_topics(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the topics currently assigned to a DP.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "topics": [{slug,
        display_name}, ...]}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)
    with factory() as session:
        rows = (
            session.execute(
                select(Topic.slug, Topic.display_name)
                .join(DataProductTopic, DataProductTopic.topic_id == Topic.id)
                .where(DataProductTopic.data_product_id == row.id)
                .order_by(Topic.display_name)
            )
            .all()
        )
    return {
        "data_product_id": row.id,
        "topics": [{"slug": s, "display_name": d} for s, d in rows],
    }
