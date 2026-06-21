"""Genie App Builder — natural-language authoring endpoint for apps.

One POST route that turns a plain-language prompt into a runnable hosted
app: it drafts the source via the Genie/Lens LLM plumbing (falling back
to a deterministic scaffold when no workspace credential is configured)
and creates the app through the existing app-hosting service.  The
created app is then managed on the regular ``/apps`` surface — start,
edit, proxy — so this module adds only the authoring step, no new
metadata surface.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api.apps_routes import serialize_app
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_workspace_admin,
)
from pointlessql.config import get_settings
from pointlessql.exceptions import ValidationError
from pointlessql.services import app_hosting, genie_app_builder

router = APIRouter(tags=["genie-app-builder"])


@router.post("/api/apps/genie-build")
async def genie_build_app(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Build a hosted app from a natural-language prompt and create it.

    Args:
        request: Incoming FastAPI request.
        body: ``{"prompt", "kind", "title"?}`` — *kind* is one of the
            buildable app kinds; *title* defaults to the prompt's first
            words.

    Returns:
        ``{"app": <serialized app>, "used_llm": bool}`` — the created
        app and whether an LLM drafted the body (vs. a scaffold).

    Raises:
        ValidationError: When the prompt is blank or *kind* is not
            buildable.
    """
    require_workspace_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)

    prompt = str(body.get("prompt") or "").strip()
    kind = str(body.get("kind") or "fastapi").strip()
    title = str(body.get("title") or "").strip()
    if not prompt:
        raise ValidationError("A prompt is required to build an app.")
    if kind not in genie_app_builder.APP_BUILDER_KINDS:
        raise ValidationError(
            f"Cannot build a {kind!r} app from a prompt; "
            f"choose one of {', '.join(genie_app_builder.APP_BUILDER_KINDS)}."
        )

    source_code, used_llm = await genie_app_builder.generate_app_source(
        prompt,
        kind,
        factory=factory,
        workspace_id=workspace_id,
        settings=get_settings(),
    )
    row = app_hosting.create_app(
        factory,
        workspace_id=workspace_id,
        title=title or genie_app_builder.default_title(prompt),
        description=prompt,
        kind=kind,
        source_code=source_code,
        command_override=None,
        env=None,
        created_by_user_id=user["id"],
    )
    return {"app": serialize_app(row), "used_llm": used_llm}
