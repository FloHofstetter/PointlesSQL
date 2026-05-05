"""Agent-review API routes.

Three endpoints, all auditor-gated:

- ``POST /api/agent-reviews`` — the Audit-Reviewer-Agent posts a
  Markdown review here.  The handler persists, then synchronously
  fans the CloudEvents envelope out via
  :func:`pointlessql.services.review_dispatcher.dispatch_review`.
- ``GET /api/agent-reviews/latest`` — the cockpit "Latest review"
  card reads this.  Returns ``404`` when the table is empty.
- ``GET /api/agent-reviews/{review_id}`` — full detail (markdown +
  payload + dispatcher fan-out log) for the detail page.

Validation bounds match the plan: ``period_end > period_start``,
``severity ∈ {ok, warn, critical}``, ``summary_md ≤ 50 KiB``,
``payload_json ≤ 1 MiB``.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_admin,
    require_auditor,
)
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models.agent_reviews import REVIEW_SEVERITIES, AgentReview
from pointlessql.services import output_rendering as output_rendering_service
from pointlessql.services.review_dispatcher import dispatch_review

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-reviews"])

_MAX_SUMMARY_BYTES = 50 * 1024
_MAX_PAYLOAD_BYTES = 1024 * 1024


def _row_to_dict(row: AgentReview) -> dict[str, Any]:
    """Project an :class:`AgentReview` ORM row to a JSON-safe dict.

    Args:
        row: Detached or session-attached review row.

    Returns:
        Plain dict, ready to ``json.dumps``-serialise.
    """
    return {
        "id": row.id,
        "run_id": row.run_id,
        "workspace_id": int(row.workspace_id),
        "period_start": row.period_start.astimezone(datetime.UTC).isoformat(),
        "period_end": row.period_end.astimezone(datetime.UTC).isoformat(),
        "severity": row.severity,
        "summary_md": row.summary_md,
        "payload_json": json.loads(row.payload_json) if row.payload_json else None,
        "delivered_to": json.loads(row.delivered_to_json) if row.delivered_to_json else [],
        "created_at": row.created_at.astimezone(datetime.UTC).isoformat(),
    }


def _parse_iso8601(name: str, value: str) -> datetime.datetime:
    """Parse a strict ISO-8601 timestamp from the request body.

    Args:
        name: Field name for the error message.
        value: Raw string from the request body.

    Returns:
        Timezone-aware UTC datetime.

    Raises:
        ValidationError: When *value* is not parseable.
    """
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


@router.post("/api/agent-reviews")
async def api_post_agent_review(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Persist a freshly-drafted review and fan it out to subscribers.

    The auditor scope passes here; supervisor and bare API keys do
    not.  The fan-out happens synchronously (small N — one webhook
    per admin-configured destination, retries already bounded inside
    :func:`dispatch_review`) so the response carries the
    delivery-attempted log and callers can surface delivery failures
    without a follow-up read.

    Args:
        request: FastAPI request, carrying auth state.
        body: Validated dict with ``period_start``, ``period_end``,
            ``severity``, ``summary_md``; optional ``run_id`` and
            ``payload_json``.

    Returns:
        ``{"id", "run_id", "period_start", "period_end", "severity",
        "summary_md", "payload_json", "delivered_to", "created_at"}``.

    Raises:
        CatalogNotFoundError: When the row vanishes between insert
            and re-fetch (race only, kept for shape symmetry).
        ValidationError: On bound or shape violations.
    """
    require_auditor(request)
    period_start = _parse_iso8601("period_start", str(body.get("period_start", "")))
    period_end = _parse_iso8601("period_end", str(body.get("period_end", "")))
    if period_end <= period_start:
        raise ValidationError("period_end must be > period_start")
    severity = str(body.get("severity", "")).strip()
    if severity not in REVIEW_SEVERITIES:
        raise ValidationError(
            f"severity must be one of {sorted(REVIEW_SEVERITIES)}; got {severity!r}"
        )
    summary_md = str(body.get("summary_md", ""))
    if not summary_md.strip():
        raise ValidationError("summary_md must be non-empty")
    if len(summary_md.encode("utf-8")) > _MAX_SUMMARY_BYTES:
        raise ValidationError(f"summary_md exceeds {_MAX_SUMMARY_BYTES} bytes (UTF-8)")
    raw_payload = body.get("payload_json")
    payload_serialised: str | None = None
    if raw_payload is not None:
        payload_serialised = json.dumps(raw_payload, sort_keys=True)
        if len(payload_serialised.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValidationError(
                f"payload_json exceeds {_MAX_PAYLOAD_BYTES} bytes once serialised"
            )
    run_id = body.get("run_id")
    run_id_clean: str | None = str(run_id).strip() if run_id else None

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    workspace_id = current_workspace_id(request)
    with factory() as session:
        row = AgentReview(
            run_id=run_id_clean,
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=period_end,
            severity=severity,
            summary_md=summary_md,
            payload_json=payload_serialised,
            delivered_to_json=None,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        review_id = row.id

    delivered_to = await dispatch_review(factory, review_id)
    await audit(
        request,
        "agent_review.posted",
        f"agent_review:{review_id}",
        {"severity": severity, "destinations": len(delivered_to)},
    )
    with factory() as session:
        row = session.get(AgentReview, review_id)
        if row is None:  # pragma: no cover — race only
            raise CatalogNotFoundError(f"agent_review id={review_id} not found post-insert")
        session.expunge(row)
    return _row_to_dict(row)


@router.get("/api/agent-reviews/latest")
async def api_get_latest_review(request: Request) -> dict[str, Any]:
    """Return the most recently created review, or 404 when empty.

    Used by the cockpit "Latest review" card and by the
    ``pql_get_latest_review`` plugin tool so the Compliance-Bot /
    Incident-Responder personas can reference yesterday's review
    without enumerating the table.
    """
    require_auditor(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalars(
            select(AgentReview).order_by(desc(AgentReview.created_at)).limit(1)
        ).first()
        if row is None:
            raise CatalogNotFoundError("no agent reviews recorded yet")
        session.expunge(row)
    return _row_to_dict(row)


@router.get("/api/agent-reviews/{review_id}")
async def api_get_agent_review(request: Request, review_id: int) -> dict[str, Any]:
    """Return one review by id (markdown + payload + fan-out log)."""
    require_auditor(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(AgentReview, review_id)
        if row is None:
            raise CatalogNotFoundError(f"agent_review id={review_id} not found")
        session.expunge(row)
    return _row_to_dict(row)


@router.get("/agent-reviews/{review_id}", response_class=HTMLResponse)
async def html_agent_review_detail(request: Request, review_id: int) -> HTMLResponse:
    """Render the full review detail page (admin-only).

    The cockpit "Latest review" card on ``/`` links here.  Admin gate
    is stricter than ``require_auditor`` because the rendered page
    surfaces the full Markdown digest + raw payload transcript +
    dispatcher fan-out log; auditor keys are HTTP-API-only by
    convention.
    """
    require_admin(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(AgentReview, review_id)
        if row is None:
            raise CatalogNotFoundError(f"agent_review id={review_id} not found")
        session.expunge(row)
    payload = _row_to_dict(row)
    return request.app.state.templates.TemplateResponse(
        request,
        "pages/agent_review_detail.html",
        {
            "review": payload,
            "render_markdown": output_rendering_service.render_markdown_source,
            "is_admin": user.get("is_admin", False),
            "active_page": "audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
