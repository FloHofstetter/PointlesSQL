"""Audit-hook wrapper around tool execution.

Every Lens tool dispatch goes through :func:`execute_tool_with_audit`
so the chat transcript carries an inline forensic record (one
``lens_messages`` row with role='tool', the args/result/cost/duration
of the call).  Direct executor calls bypass this audit; callers
should never do that in production paths — they exist for unit tests.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from pointlessql.services.lens._messages import append_message
from pointlessql.services.lens.tools._base import (
    LensToolError,
    SessionContext,
    ToolDef,
    UnknownLensToolError,
)
from pointlessql.services.lens.tools._registry import get_tool

logger = logging.getLogger(__name__)


def _serialize_for_audit(payload: object) -> object:
    """Coerce *payload* into a JSON-serialisable structure.

    Pydantic models go through ``model_dump``; everything else is
    passed straight through.  The caller is expected to hand in
    Pydantic-compatible shapes so ``json.dumps`` succeeds in the DB
    layer.
    """
    if isinstance(payload, BaseModel):
        return payload.model_dump()
    return payload


async def execute_tool_with_audit(
    *,
    tool_name: str,
    ctx: SessionContext,
    raw_args: dict[str, Any],
) -> dict[str, Any]:
    """Validate args, dispatch the tool, persist a ``lens_messages`` row.

    The wrapper:

    1. Looks up *tool_name* in the registry.
    2. Validates *raw_args* against the tool's ``input_model``.
    3. Calls the executor and times it.
    4. Writes one ``lens_messages`` row (role='tool') with the
       audit payload.
    5. Returns the serialised output dict to the caller.

    On any failure (unknown tool, validation error, executor raise)
    the audit row is still written with ``tool_status='error'`` so
    the transcript stays complete.

    Args:
        tool_name: Registered tool name.
        ctx: :class:`SessionContext` with workspace + factory + user.
        raw_args: Free-form input dict from the LLM tool call.

    Returns:
        The tool's output as a JSON-serialisable dict.

    Raises:
        UnknownLensToolError: When *tool_name* is not in the registry.
        LensToolError: When validation or execution fails.
    """  # noqa: DOC502,DOC503 — UnknownLensToolError raised by helper
    tool = _resolve_tool_or_audit(tool_name, ctx, raw_args)
    args_obj = _validate_or_audit(tool, ctx, raw_args)
    start = time.monotonic()
    try:
        result = await tool.executor(ctx, args_obj)
    except LensToolError:
        raise
    except Exception as exc:  # noqa: BLE001 — wrap+rethrow as LensToolError below
        logger.exception(
            "Lens tool %s raised unexpectedly", tool_name
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        if ctx.lens_session_id is not None:
            append_message(
                ctx.factory,
                session_id=ctx.lens_session_id,
                role="tool",
                content=f"{tool_name} failed: {exc}",
                tool_name=tool_name,
                tool_args=_serialize_for_audit(args_obj),
                tool_status="error",
                duration_ms=duration_ms,
            )
        raise LensToolError(
            tool_name=tool_name,
            message=f"executor raised: {exc}",
            status="error",
            tool_args=_serialize_for_audit(args_obj),
        ) from exc

    duration_ms = int((time.monotonic() - start) * 1000)
    serialised = _serialize_for_audit(result)
    if ctx.lens_session_id is not None:
        append_message(
            ctx.factory,
            session_id=ctx.lens_session_id,
            role="tool",
            content=f"{tool_name} ok",
            tool_name=tool_name,
            tool_args=_serialize_for_audit(args_obj),
            tool_result=serialised,
            tool_status="ok",
            duration_ms=duration_ms,
        )
    if isinstance(serialised, dict):
        return serialised
    return {"result": serialised}


def _resolve_tool_or_audit(
    tool_name: str, ctx: SessionContext, raw_args: dict[str, Any]
) -> ToolDef:
    """Look up the tool; on miss, write an error audit row + raise."""
    tool = get_tool(tool_name)
    if tool is not None:
        return tool
    if ctx.lens_session_id is not None:
        append_message(
            ctx.factory,
            session_id=ctx.lens_session_id,
            role="tool",
            content=f"unknown tool {tool_name!r}",
            tool_name=tool_name,
            tool_args=raw_args,
            tool_status="error",
        )
    raise UnknownLensToolError(tool_name)


def _validate_or_audit(
    tool: ToolDef, ctx: SessionContext, raw_args: dict[str, Any]
) -> object:
    """Validate *raw_args* against the tool's input model; audit on fail."""
    try:
        return tool.input_model.model_validate(raw_args)
    except ValidationError as exc:
        if ctx.lens_session_id is not None:
            append_message(
                ctx.factory,
                session_id=ctx.lens_session_id,
                role="tool",
                content=f"{tool.name} bad args",
                tool_name=tool.name,
                tool_args=raw_args,
                tool_status="error",
            )
        raise LensToolError(
            tool_name=tool.name,
            message=f"input validation failed: {json.dumps(exc.errors())}",
            status="error",
            tool_args=raw_args,
        ) from exc
