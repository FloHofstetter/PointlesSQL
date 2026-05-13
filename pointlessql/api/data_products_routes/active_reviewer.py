"""``/api/data-products/{c}/{s}/active-reviewer`` — Phase 74 config.

Three endpoints:

* ``GET`` — return the per-DP config row + last-run snapshot.
* ``POST`` — UPSERT the config.  Steward + admin gate.  Body:
  ``{enabled, runner, llm_provider?, llm_model?,
  prompt_override_md?}``.
* ``POST /run-now`` — fire one synchronous tick.  Used by:

  - the steward "Test now" button in the DP detail page (74.3);
  - the Hermes-cron runner (74.2) as the per-DP entry point.

Plus a workspace-level helper:

* ``GET /api/data-products/active-reviewer/queue`` — list every DP
  with ``runner='hermes_cron'`` so the Hermes-cron job can
  enumerate work.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_admin,
    require_user,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.catalog._data_product_active_reviewer_config import (
    ACTIVE_REVIEWER_PROVIDERS,
    ACTIVE_REVIEWER_RUNNERS,
    DataProductActiveReviewerConfig,
)
from pointlessql.services.data_products import (
    iter_opted_in_dp_ids,
    run_reviewer_for_dp,
    upsert_config,
)

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(user: Any, dp_row: Any) -> None:
    """Raise unless the caller can manage this DP's reviewer config.

    Args:
        user: Session-cookie user dict.
        dp_row: Hydrated :class:`DataProduct` row.

    Raises:
        AuthorizationError: When the caller is neither admin nor
            the registered steward of *dp_row*.
    """
    is_admin = bool(user.get("is_admin"))
    is_steward = (
        dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    )
    if is_admin or is_steward:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="active-reviewer-config",
        securable_type="data_product",
        full_name=f"{dp_row.catalog_name}.{dp_row.schema_name}",
    )


def _serialise_config(
    row: DataProductActiveReviewerConfig | None,
) -> dict[str, Any] | None:
    """Render one config row as JSON, or return ``None``."""
    if row is None:
        return None
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "enabled": bool(row.enabled),
        "runner": row.runner,
        "llm_provider": row.llm_provider,
        "llm_model": row.llm_model,
        "prompt_override_md": row.prompt_override_md,
        "last_run_at": (
            row.last_run_at.isoformat() if row.last_run_at else None
        ),
        "last_run_comment_id": row.last_run_comment_id,
        "acting_user_id": row.acting_user_id,
        "agent_slug": row.agent_slug,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/api/active-reviewer/queue")
async def list_active_reviewer_queue(request: Request) -> dict[str, Any]:
    """Return the list of DPs the Hermes-cron runner should process.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"queue": [{data_product_id, workspace_id, catalog,
        schema}, ...]}``.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    rows = iter_opted_in_dp_ids(factory, runner="hermes_cron")
    # Workspace-scope filter — admins of one workspace shouldn't see
    # another workspace's queue even though require_admin already
    # gates the surface.
    filtered = [r for r in rows if r[0] == workspace_id]
    return {
        "queue": [
            {
                "workspace_id": ws,
                "data_product_id": dp_id,
                "catalog": catalog,
                "schema": schema,
            }
            for ws, dp_id, catalog, schema in filtered
        ]
    }


@router.get("/api/data-products/{catalog}/{schema}/active-reviewer")
async def get_active_reviewer_config(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the per-DP active-reviewer config (or empty payload).

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "config": <row|None>}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    with factory() as session:
        cfg = session.execute(
            select(DataProductActiveReviewerConfig).where(
                DataProductActiveReviewerConfig.workspace_id == workspace_id,
                DataProductActiveReviewerConfig.data_product_id == row.id,
            )
        ).scalar_one_or_none()
    return {
        "data_product_id": row.id,
        "config": _serialise_config(cfg),
    }


@router.post("/api/data-products/{catalog}/{schema}/active-reviewer")
async def upsert_active_reviewer_config(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """UPSERT the per-DP active-reviewer config.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        Serialised row.

    Raises:
        HTTPException: 400 on invalid body shape.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, row)

    raw_body = await request.json()
    if not isinstance(raw_body, dict):
        # bare-http-ok: malformed body shape.
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    body: dict[str, Any] = raw_body
    enabled = bool(body.get("enabled", False))
    runner = str(body.get("runner") or "")
    if runner not in ACTIVE_REVIEWER_RUNNERS:
        # bare-http-ok: bad runner enum.
        raise HTTPException(
            status_code=400,
            detail=f"runner must be one of {list(ACTIVE_REVIEWER_RUNNERS)!r}",
        )
    llm_provider_raw = body.get("llm_provider")
    llm_provider: str | None = None
    if llm_provider_raw is not None and llm_provider_raw != "":
        if llm_provider_raw not in ACTIVE_REVIEWER_PROVIDERS:
            # bare-http-ok: bad provider enum.
            raise HTTPException(
                status_code=400,
                detail=(
                    "llm_provider must be one of "
                    f"{list(ACTIVE_REVIEWER_PROVIDERS)!r} or null"
                ),
            )
        llm_provider = str(llm_provider_raw)
    llm_model = body.get("llm_model")
    if llm_model is not None and not isinstance(llm_model, str):
        # bare-http-ok: malformed llm_model type.
        raise HTTPException(
            status_code=400, detail="llm_model must be a string or null"
        )
    prompt_override = body.get("prompt_override_md")
    if prompt_override is not None and not isinstance(prompt_override, str):
        # bare-http-ok: malformed prompt_override_md type.
        raise HTTPException(
            status_code=400,
            detail="prompt_override_md must be a string or null",
        )
    if prompt_override is not None and not prompt_override.strip():
        prompt_override = None
    agent_slug_raw = body.get("agent_slug")
    if agent_slug_raw is not None and not isinstance(agent_slug_raw, str):
        # bare-http-ok: malformed agent_slug type.
        raise HTTPException(
            status_code=400,
            detail="agent_slug must be a string or null",
        )
    agent_slug = (
        agent_slug_raw.strip().lower() if isinstance(agent_slug_raw, str) else None
    )
    if agent_slug == "":
        agent_slug = None

    with factory() as session:
        cfg = upsert_config(
            session,
            workspace_id=workspace_id,
            data_product_id=row.id,
            enabled=enabled,
            runner=runner,
            llm_provider=llm_provider,
            llm_model=str(llm_model) if isinstance(llm_model, str) else None,
            prompt_override_md=prompt_override,
            acting_user_id=user["id"],
            agent_slug=agent_slug,
        )
        session.commit()
        session.refresh(cfg)
        payload = _serialise_config(cfg)

    return {
        "data_product_id": row.id,
        "config": payload,
    }


@router.post("/api/data-products/{catalog}/{schema}/active-reviewer/run-now")
async def run_active_reviewer_now(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Fire one synchronous tick for this DP.

    Used by the steward "Test now" button and by the Hermes-cron
    runner.  Returns the resulting comment_id + endorsement_id +
    verdict severity.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "result": <dict>}``.

    Raises:
        HTTPException: 400 when no config row exists or the LLM
            credential is missing for the configured provider.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, row)

    try:
        result = await run_reviewer_for_dp(
            factory,
            workspace_id=workspace_id,
            data_product_id=row.id,
            trigger="manual",
            provider_default=settings.data_products.active_reviewer_llm_provider,
            model_default=settings.data_products.active_reviewer_model,
        )
    except ValueError as exc:
        # bare-http-ok: service-level invariant fail (missing config / DP).
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except RuntimeError as exc:
        # bare-http-ok: missing LLM credential for configured provider.
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"data_product_id": row.id, "result": result}
