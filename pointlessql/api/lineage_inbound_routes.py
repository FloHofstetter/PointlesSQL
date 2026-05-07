"""Inbound OpenLineage event ingestion route.

Phase 40 Sprint 40.1: external producers (Kafka-Connect, Airflow,
dbt-cloud, peer PointlesSQL installs) POST OpenLineage 1.x
``RunEvent`` envelopes here, and the route normalises them into
``lineage_row_edges`` and ``lineage_column_map`` rows tagged with
``producer = event.job.namespace`` and ``external_event_id =
event.run.runId``.

The route is the only outward-facing surface of the federation
read story.  Auth is a single dedicated scope
(``api_keys.lineage_inbound``) so a federation key can land lineage
events without seeing run audits or tenant aggregates.  Workspace
scoping is sourced from the API key — external producers cannot
cross-post into another workspace.

Idempotency is handled with pre-INSERT EXISTS checks on
``(producer, external_event_id, ...)`` composite keys.  A retry from
a flaky network never produces duplicate edges.

A CloudEvents envelope of type
``pointlessql.lineage.inbound.received`` is fanned out to active
audit sinks so dashboards / Grafana panels see inbound traffic
right next to outbound emission events.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_lineage_inbound
from pointlessql.exceptions import ValidationError
from pointlessql.models import LineageColumnMap, LineageRowEdge
from pointlessql.services.audit_sinks import dispatch_to_sinks
from pointlessql.services.lineage.inbound_parser import (
    OpenLineageInboundEvent,
    parse_to_column_maps,
    parse_to_row_edges,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lineage-inbound"])


def _existing_column_keys(
    session: Any,
    *,
    producer: str,
    external_event_id: str,
    candidates: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """Return the ``(target_table, target_column)`` pairs already on disk.

    Idempotency helper for column-map inserts.  The full key is
    ``(producer, external_event_id, target_table, target_column)``
    but ``producer`` and ``external_event_id`` are constant for one
    POST so we only need the variable suffix back from the SELECT.
    """
    if not candidates:
        return set()
    target_pairs = {(c["target_table"], c["target_column"]) for c in candidates}
    rows = session.execute(
        select(
            LineageColumnMap.target_table,
            LineageColumnMap.target_column,
        ).where(
            LineageColumnMap.producer == producer,
            LineageColumnMap.external_event_id == external_event_id,
        )
    ).all()
    existing = {(t, c) for (t, c) in rows}
    return existing & target_pairs


def _existing_row_keys(
    session: Any,
    *,
    producer: str,
    external_event_id: str,
    candidates: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """Return the ``(source_row_id, target_row_id)`` pairs already on disk."""
    if not candidates:
        return set()
    target_pairs = {(c["source_row_id"], c["target_row_id"]) for c in candidates}
    rows = session.execute(
        select(
            LineageRowEdge.source_row_id,
            LineageRowEdge.target_row_id,
        ).where(
            LineageRowEdge.producer == producer,
            LineageRowEdge.external_event_id == external_event_id,
        )
    ).all()
    existing = {(s, t) for (s, t) in rows}
    return existing & target_pairs


@router.post("/api/lineage/openlineage", status_code=status.HTTP_202_ACCEPTED)
async def api_lineage_openlineage_inbound(
    request: Request,
) -> dict[str, Any]:
    """Accept one OpenLineage RunEvent and land its edges.

    The body is parsed manually rather than via FastAPI's automatic
    Pydantic body validation so we can return a stable
    :class:`ValidationError` (matching the rest of the API) and so
    the parser keeps full control over OL spec drift handling.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"event_id": <runId>, "row_edges": N, "column_maps": M,
        "duplicate_row_edges": X, "duplicate_column_maps": Y}`` —
        ``duplicate_*`` counts attempted-but-deduped rows so a
        replay caller sees its retry was idempotent.

    Raises:
        AuthorizationError: When the caller lacks the
            ``lineage_inbound`` scope.
        ValidationError: When the event body fails OL 1.x parsing
            (missing ``eventTime`` / ``run.runId`` / ``job.namespace``).
    """
    require_lineage_inbound(request)
    workspace_id = current_workspace_id(request)
    raw_body = await request.json()
    if not isinstance(raw_body, dict):
        raise ValidationError("body must be a JSON object")
    try:
        event = OpenLineageInboundEvent.model_validate(raw_body)
    except PydanticValidationError as exc:
        msg = exc.errors()[0].get("msg", "parse error")
        raise ValidationError(f"invalid OpenLineage event: {msg}") from exc

    now = datetime.datetime.now(datetime.UTC)
    column_candidates = parse_to_column_maps(
        event, workspace_id=workspace_id, created_at=now
    )
    row_candidates = parse_to_row_edges(
        event, workspace_id=workspace_id, created_at=now
    )

    factory = request.app.state.session_factory
    inserted_columns = 0
    duplicate_columns = 0
    inserted_rows = 0
    duplicate_rows = 0
    target_tables: set[str] = set()
    with factory() as session:
        if column_candidates:
            existing = _existing_column_keys(
                session,
                producer=event.job.namespace,
                external_event_id=event.run.runId,
                candidates=column_candidates,
            )
            fresh_columns: list[dict[str, Any]] = []
            for cand in column_candidates:
                key = (cand["target_table"], cand["target_column"])
                if key in existing:
                    duplicate_columns += 1
                else:
                    fresh_columns.append(cand)
                    target_tables.add(cand["target_table"])
            if fresh_columns:
                session.bulk_insert_mappings(LineageColumnMap, fresh_columns)
                inserted_columns = len(fresh_columns)

        if row_candidates:
            existing_rows = _existing_row_keys(
                session,
                producer=event.job.namespace,
                external_event_id=event.run.runId,
                candidates=row_candidates,
            )
            fresh_rows: list[dict[str, Any]] = []
            for cand in row_candidates:
                key = (cand["source_row_id"], cand["target_row_id"])
                if key in existing_rows:
                    duplicate_rows += 1
                else:
                    fresh_rows.append(cand)
                    target_tables.add(cand["target_table"])
            if fresh_rows:
                session.bulk_insert_mappings(LineageRowEdge, fresh_rows)
                inserted_rows = len(fresh_rows)

        if inserted_columns or inserted_rows:
            session.commit()

    logger.info(
        "lineage inbound accepted: producer=%s event=%s row_edges=%d column_maps=%d "
        "(duplicates row=%d column=%d) target_tables=%d workspace=%d",
        event.job.namespace,
        event.run.runId,
        inserted_rows,
        inserted_columns,
        duplicate_rows,
        duplicate_columns,
        len(target_tables),
        workspace_id,
    )

    if inserted_columns or inserted_rows:
        envelope = {
            "specversion": "1.0",
            "id": uuid.uuid4().hex,
            "source": "/pointlessql/lineage/inbound",
            "type": "pointlessql.lineage.inbound.received",
            "time": now.isoformat(),
            "datacontenttype": "application/json",
            "subject": event.job.namespace,
            "data": {
                "producer": event.job.namespace,
                "external_event_id": event.run.runId,
                "target_tables": sorted(target_tables),
                "row_edges": inserted_rows,
                "column_maps": inserted_columns,
                "workspace_id": workspace_id,
            },
        }
        try:
            await dispatch_to_sinks(factory, envelope, workspace_id=workspace_id)
        except Exception:  # noqa: BLE001 — sink fan-out must never fail the route
            logger.exception("lineage inbound: dispatch_to_sinks raised; envelope dropped")

    return {
        "event_id": event.run.runId,
        "row_edges": inserted_rows,
        "column_maps": inserted_columns,
        "duplicate_row_edges": duplicate_rows,
        "duplicate_column_maps": duplicate_columns,
    }


__all__ = ["router"]
