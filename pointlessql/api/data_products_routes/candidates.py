"""``/data-products/candidates`` + JSON endpoints (Phase 73.1).

Three routes:

* ``GET /api/data-products/candidates`` — list open + recent
  dismissed candidates.
* ``POST /api/data-products/candidates/{id}/dismiss`` — flip
  status to ``'dismissed'`` and stamp the dismissor.
* ``POST /api/data-products/candidates/{id}/generate-draft``
  — build a draft yaml from the live schemas and persist a
  ``DataProductYamlDraft`` row + file on disk.
* ``GET /data-products/candidates`` — HTML page.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.models.catalog._data_product_candidate import (
    DataProductPromotionCandidate,
)
from pointlessql.models.catalog._data_product_yaml_draft import (
    DataProductYamlDraft,
)
from pointlessql.services import audit as audit_service
from pointlessql.services.data_products import build_draft_yaml

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request) -> Any:
    """Gate: install-admin OR session-cookie steward.

    Candidate-level actions are not row-scoped (no DP exists
    yet), so we fall back to install-admin.  Any future
    workspace-scoped steward grants can be wired in here.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The current user dict.

    Raises:
        AuthorizationError: When the caller is neither admin
            nor a steward.
    """
    require_user(request)
    user = get_user(request)
    if user.get("is_admin"):
        return user
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="candidate-dismiss",
        securable_type="data_product_candidate",
        full_name="candidates",
    )


def _serialise_candidate(candidate: DataProductPromotionCandidate) -> dict[str, Any]:
    """Render one candidate row as JSON.

    Args:
        candidate: The row.

    Returns:
        JSON-friendly dict.
    """
    return {
        "id": candidate.id,
        "workspace_id": candidate.workspace_id,
        "catalog_name": candidate.catalog_name,
        "schema_name": candidate.schema_name,
        "table_signature_hash": candidate.table_signature_hash,
        "first_seen_at": candidate.first_seen_at.isoformat(),
        "last_seen_at": candidate.last_seen_at.isoformat(),
        "distinct_run_count": candidate.distinct_run_count,
        "write_op_count": candidate.write_op_count,
        "distinct_table_count": candidate.distinct_table_count,
        "sample_target_table": candidate.sample_target_table,
        "status": candidate.status,
        "dismissed_by_user_id": candidate.dismissed_by_user_id,
        "dismissed_at": (
            candidate.dismissed_at.isoformat()
            if candidate.dismissed_at is not None
            else None
        ),
        "promoted_to_data_product_id": candidate.promoted_to_data_product_id,
        "refreshed_at": candidate.refreshed_at.isoformat(),
    }


@router.get("/api/data-products/candidates")
async def list_candidates(request: Request) -> dict[str, Any]:
    """Return the candidate list for the active workspace.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"candidates": [...]}`` ordered by ``status`` then
        ``last_seen_at`` desc.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductPromotionCandidate)
                .where(DataProductPromotionCandidate.workspace_id == workspace_id)
                .order_by(
                    DataProductPromotionCandidate.status.asc(),
                    DataProductPromotionCandidate.last_seen_at.desc(),
                )
            )
            .scalars()
            .all()
        )

    return {"candidates": [_serialise_candidate(c) for c in rows]}


@router.post("/api/data-products/candidates/{candidate_id}/dismiss")
async def dismiss_candidate(
    candidate_id: int,
    request: Request,
) -> dict[str, Any]:
    """Soft-dismiss a candidate so the scanner skips it next tick.

    Args:
        candidate_id: PK of the candidate row.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "status": "dismissed"}``.

    Raises:
        HTTPException: 404 when the row does not exist for the
            active workspace.
    """
    user = _require_steward_or_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    with factory() as session:
        candidate = session.execute(
            select(DataProductPromotionCandidate).where(
                DataProductPromotionCandidate.id == candidate_id,
                DataProductPromotionCandidate.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise ResourceNotFoundError.not_found(what=f"candidate id={candidate_id}")
        catalog_name = candidate.catalog_name
        schema_name = candidate.schema_name
        if candidate.status == "open":
            candidate.status = "dismissed"
            candidate.dismissed_by_user_id = user["id"]
            candidate.dismissed_at = datetime.datetime.now(datetime.UTC)
            session.add(candidate)
            session.commit()

    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="data_product.candidate_dismissed",
        target=f"data_product_candidate:{catalog_name}.{schema_name}",
        detail={"candidate_id": candidate_id},
        workspace_id=workspace_id,
    )
    return {"id": candidate_id, "status": "dismissed"}


def _draft_path(draft_dir: Path, workspace_id: int, catalog: str, schema: str) -> Path:
    """Return the on-disk destination for the workspace's draft yaml.

    Args:
        draft_dir: Configured draft root directory.
        workspace_id: Tenant scope.
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Absolute path; the parent directory is created on the
        fly when missing.
    """
    parent = draft_dir / str(workspace_id)
    parent.mkdir(parents=True, exist_ok=True)
    safe = f"{catalog}__{schema}.yaml"
    return parent / safe


@router.post("/api/data-products/candidates/{candidate_id}/generate-draft")
async def generate_candidate_draft(
    candidate_id: int,
    request: Request,
) -> dict[str, Any]:
    """Build a draft yaml from a candidate's live schema and persist it.

    Args:
        candidate_id: PK of the candidate row.
        request: Incoming FastAPI request.

    Returns:
        ``{"draft_id": int, "draft_path": str, "yaml_preview": str}``.

    Raises:
        HTTPException: 404 when the row does not exist for the
            active workspace.
    """
    user = _require_steward_or_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    schema_reader = getattr(request.app.state, "dp_draft_schema_reader", None)

    with factory() as session:
        candidate = session.execute(
            select(DataProductPromotionCandidate).where(
                DataProductPromotionCandidate.id == candidate_id,
                DataProductPromotionCandidate.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise ResourceNotFoundError.not_found(what=f"candidate id={candidate_id}")
        candidate_catalog = candidate.catalog_name
        candidate_schema = candidate.schema_name

        yaml_text = build_draft_yaml(
            session,
            workspace_id=workspace_id,
            candidate=candidate,
            schema_reader=schema_reader,
        )
        yaml_hash = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()

        draft_path = _draft_path(
            settings.data_products.draft_dir,
            workspace_id,
            candidate.catalog_name,
            candidate.schema_name,
        )
        draft_path.write_text(yaml_text, encoding="utf-8")

        existing = session.execute(
            select(DataProductYamlDraft).where(
                DataProductYamlDraft.workspace_id == workspace_id,
                DataProductYamlDraft.catalog_name == candidate.catalog_name,
                DataProductYamlDraft.schema_name == candidate.schema_name,
                DataProductYamlDraft.yaml_hash == yaml_hash,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.draft_path = str(draft_path)
            existing.created_at = datetime.datetime.now(datetime.UTC)
            existing.created_by_user_id = user["id"]
            existing.source_kind = "candidate_generate"
            session.add(existing)
            draft_id = existing.id
        else:
            new_row = DataProductYamlDraft(
                workspace_id=workspace_id,
                catalog_name=candidate.catalog_name,
                schema_name=candidate.schema_name,
                draft_path=str(draft_path),
                source_kind="candidate_generate",
                created_by_user_id=user["id"],
                created_at=datetime.datetime.now(datetime.UTC),
                yaml_hash=yaml_hash,
            )
            session.add(new_row)
            session.flush()
            draft_id = new_row.id
        session.commit()

    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="data_product.draft_generated",
        target=f"data_product_candidate:{candidate_catalog}.{candidate_schema}",
        detail={
            "candidate_id": candidate_id,
            "draft_id": draft_id,
        },
        workspace_id=workspace_id,
    )
    return {
        "draft_id": draft_id,
        "draft_path": str(draft_path),
        "yaml_preview": yaml_text,
    }


@router.get(
    "/data-products/candidates",
    response_class=HTMLResponse,
    response_model=None,
)
async def data_products_candidates_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the candidates HTML page.

    Args:
        request: Incoming FastAPI request.

    Returns:
        HTML response for authenticated users, redirect to login
        otherwise.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/data-products/candidates",
            status_code=303,
        )
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(DataProductPromotionCandidate)
                .where(
                    DataProductPromotionCandidate.workspace_id == workspace_id
                )
                .order_by(
                    DataProductPromotionCandidate.status.asc(),
                    DataProductPromotionCandidate.last_seen_at.desc(),
                )
            )
            .scalars()
            .all()
        )
    serialised = [_serialise_candidate(c) for c in rows]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/data_products_candidates.html",
        {
            "active_page": "data_products",
            "candidates": serialised,
            "is_admin": bool(user.get("is_admin")),
        },
    )
