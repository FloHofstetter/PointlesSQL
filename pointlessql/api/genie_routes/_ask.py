"""The Genie ask path — NL question → validated SQL → governed result.

One round-trip per ask: persist the question, render the curated
context, generate SQL through the shared Lens provider plumbing,
scope-check it against the space's table list, then execute through
the exact recipe the BI-dashboard widgets use
(:func:`resolve_select_context` + ``PQL.sql`` with table policies on
the app executor).  Failures after the question is persisted land in
the transcript as assistant ``error`` turns so the room shows what
went wrong; the HTTP response carries the matching RFC 9457 envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.api.genie_routes._shared import ensure_can_edit, ensure_space, serialize_asset
from pointlessql.api.sql.editor._helpers import short_sql_hash
from pointlessql.exceptions import (
    PermissionDeniedError,
    PointlessSQLError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.genie import GenieSpace
from pointlessql.services import genie as genie_service
from pointlessql.services._executor import run_sync
from pointlessql.services.genie import generate_sql
from pointlessql.services.notebook._sql_cell import resolve_select_context

router = APIRouter()

_MAX_ROWS = 1_000
_HISTORY_TURNS = 12
_MAX_QUESTION_CHARS = 2_000


def _run_genie_sql(
    sql: str,
    approved: dict[str, str],
    max_rows: int,
    policies: dict[str, Any] | None = None,
) -> Any:
    """Execute *sql* in the sync PQL bridge (dispatched via run_sync)."""
    from pointlessql.pql import PQL

    return PQL.sql(sql, approved_tables=approved, max_rows=max_rows, table_policies=policies)


def _persist_error_turn(request: Request, space: GenieSpace, sql: str | None, detail: str) -> None:
    """Append an assistant ``error`` turn so the room records the failure."""
    genie_service.append_message(
        request.app.state.session_factory,
        space_id=space.id,
        user_id=None,
        role="assistant",
        content="I could not answer that question.",
        sql_text=sql,
        status="error",
        error=detail,
    )


@router.post("/api/genie/spaces/{slug}/ask")
async def api_ask(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Answer one natural-language question inside a space.

    Args:
        request: Incoming FastAPI request.
        slug: Space slug.
        body: ``{"question": str}``.

    Returns:
        ``{"message_id", "sql", "columns", "rows", "row_count",
        "truncated"}`` — the persisted assistant turn plus the
        governed result.

    Raises:
        PermissionDeniedError: When the caller is unauthenticated.
        ValidationError: On an empty question, a non-SELECT model
            reply, or generated SQL referencing tables outside the
            space (the rejection is also persisted as an assistant
            ``error`` turn).
        PointlessSQLError: Propagated from SELECT enforcement or
            execution after the failure is persisted to the
            transcript.  An unconfigured LLM raises the 503
            :class:`pointlessql.services.genie.GenieLLMNotConfiguredError`.
    """
    space = ensure_space(request, slug)
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to ask Genie")
    question = str(body.get("question") or "").strip()
    if not question:
        raise ValidationError("question must be a non-empty string")
    if len(question) > _MAX_QUESTION_CHARS:
        raise ValidationError(f"question must be at most {_MAX_QUESTION_CHARS} characters")

    factory = request.app.state.session_factory
    settings = request.app.state.settings
    workspace_id = current_workspace_id(request)

    # History is captured BEFORE the new question lands so the prompt
    # does not carry it twice; error turns stay out of the prompt.
    history = [
        m
        for m in genie_service.list_messages(factory, space_id=space.id, limit=_HISTORY_TURNS)
        if m.status == "ok"
    ]
    genie_service.append_message(
        factory,
        space_id=space.id,
        user_id=int(user["id"]),
        role="user",
        content=question,
    )

    context = await genie_service.build_context(request.app.state.uc_client, factory, space)
    sql = await generate_sql(
        question,
        context,
        history,
        factory=factory,
        workspace_id=workspace_id,
        settings=settings,
    )

    try:
        genie_service.validate_generated_sql(sql, allowed_tables=genie_service.space_tables(space))
    except ValidationError as exc:
        _persist_error_turn(request, space, sql, str(exc))
        raise

    try:
        approved, policies = await resolve_select_context(
            sql,
            uc_client=request.app.state.uc_client,
            actor_email=user["email"],
            is_admin=bool(user["is_admin"]),
        )
        result = await run_sync(_run_genie_sql, sql, approved, _MAX_ROWS, policies)
    except PointlessSQLError as exc:
        _persist_error_turn(request, space, sql, str(exc))
        raise

    message = genie_service.append_message(
        factory,
        space_id=space.id,
        user_id=None,
        role="assistant",
        content=f"Returned {result.row_count} rows.",
        sql_text=sql,
        status="ok",
    )
    await audit(
        request,
        "genie.asked",
        f"genie_space:{space.slug}",
        {"sql_hash": short_sql_hash(sql), "message_id": message.id},
    )
    return {
        "message_id": message.id,
        "sql": sql,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
    }


@router.post("/api/genie/spaces/{slug}/assets/{asset_id}/run")
async def api_run_trusted_asset(request: Request, slug: str, asset_id: int) -> dict[str, Any]:
    """Re-run a trusted asset's stored SQL through the governed path.

    Turns a saved question -> SQL asset into a deterministic, re-runnable
    skill: it executes the vetted SQL directly (no LLM round-trip) under
    the caller's own SELECT privileges, after re-checking the SQL still
    falls within the space's curated tables (which may have changed since
    the asset was saved).

    Args:
        request: Incoming FastAPI request.
        slug: Space slug.
        asset_id: Trusted-asset primary key.

    Returns:
        ``{"asset_id", "question", "sql", "columns", "rows",
        "row_count", "truncated"}``.  A :class:`ValidationError`
        (stored SQL now outside the space's tables) or a
        :class:`PointlessSQLError` (SELECT enforcement / execution)
        propagates from the callees.

    Raises:
        PermissionDeniedError: When the caller is unauthenticated.
        ResourceNotFoundError: When the asset is absent or cross-space.
    """
    space = ensure_space(request, slug)
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to run a Genie skill")
    factory = request.app.state.session_factory
    asset = genie_service.get_trusted_asset(factory, space_id=space.id, asset_id=asset_id)
    if asset is None:
        raise ResourceNotFoundError(f"Genie trusted asset {asset_id} not found.")
    genie_service.validate_generated_sql(
        asset.sql_text, allowed_tables=genie_service.space_tables(space)
    )
    approved, policies = await resolve_select_context(
        asset.sql_text,
        uc_client=request.app.state.uc_client,
        actor_email=user["email"],
        is_admin=bool(user["is_admin"]),
    )
    result = await run_sync(_run_genie_sql, asset.sql_text, approved, _MAX_ROWS, policies)
    await audit(
        request,
        "genie.skill_run",
        f"genie_space:{space.slug}",
        {"asset_id": asset_id, "sql_hash": short_sql_hash(asset.sql_text)},
    )
    return {
        "asset_id": asset_id,
        "question": asset.question,
        "sql": asset.sql_text,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
    }


def _space_for_message(request: Request, message_id: int) -> tuple[Any, GenieSpace]:
    """Resolve a message + its space, enforcing workspace isolation.

    Args:
        request: Incoming FastAPI request.
        message_id: Message primary key from the URL.

    Returns:
        ``(message, space)`` detached rows.

    Raises:
        ResourceNotFoundError: When the message does not exist or its
            space lives in another workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    message = genie_service.get_message(factory, message_id=message_id)
    if message is None:
        raise ResourceNotFoundError(f"Genie message {message_id} not found.")
    with factory() as session:
        space = session.get(GenieSpace, message.space_id)
        if space is None or space.workspace_id != workspace_id:
            raise ResourceNotFoundError(f"Genie message {message_id} not found.")
        session.expunge(space)
    return message, space


@router.post("/api/genie/messages/{message_id}/feedback")
async def api_message_feedback(
    request: Request,
    message_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Record a thumbs reaction on an assistant answer.

    Args:
        request: Incoming FastAPI request.
        message_id: Assistant message primary key.
        body: ``{"feedback": "up" | "down"}``.

    Returns:
        ``{"id", "feedback"}`` after the update.

    Raises:
        PermissionDeniedError: When the caller is unauthenticated.
        ValidationError: On an unknown feedback value or a
            non-assistant target.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to leave feedback")
    _message, space = _space_for_message(request, message_id)
    factory = request.app.state.session_factory
    try:
        updated = genie_service.set_feedback(
            factory, message_id=message_id, feedback=str(body.get("feedback") or "")
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    assert updated is not None  # ensured by _space_for_message  # noqa: S101
    await audit(
        request,
        "genie.feedback",
        f"genie_space:{space.slug}",
        {"message_id": message_id, "feedback": updated.feedback},
    )
    return {"id": updated.id, "feedback": updated.feedback}


@router.post("/api/genie/messages/{message_id}/promote")
async def api_promote_message(request: Request, message_id: int) -> dict[str, Any]:
    """Promote an assistant answer into the trusted assets (owner/admin).

    Args:
        request: Incoming FastAPI request.
        message_id: Assistant message primary key.

    Returns:
        The serialized trusted asset created from the answer.

    Raises:
        ValidationError: When the message is not a promotable
            assistant answer.
    """
    _message, space = _space_for_message(request, message_id)
    user = ensure_can_edit(request, space)
    factory = request.app.state.session_factory
    try:
        asset = genie_service.promote_message(
            factory, message_id=message_id, created_by=int(user["id"])
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "genie.message_promoted",
        f"genie_space:{space.slug}",
        {"message_id": message_id, "asset_id": asset.id},
    )
    return serialize_asset(asset)
