"""``/api/data-products/{cat}/{sch}/proposals`` — schema-change proposals.

Four endpoints:

* ``GET /proposals`` — list open + historical.
* ``POST /proposals`` — open a new proposal.  Agents pass
  ``X-Agent-Run-Id``; humans rely on the session cookie.
* ``POST /proposals/{id}/approve`` — apply yaml in-place (safe
  deltas only) or write a draft yaml; gate steward + admin.
* ``POST /proposals/{id}/reject`` — stamp resolution; same
  gate.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._proposals_diff import (
    apply_diff_to_yaml,
    find_yaml_for_dp,
    is_safe_for_inplace,
    validate_diff,
)
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.data_products import load_contract
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.catalog._data_product_proposal import (
    DataProductSchemaProposal,
)
from pointlessql.models.catalog._data_product_yaml_draft import (
    DataProductYamlDraft,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services import audit as audit_service
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_PROPOSAL_OPENED,
    EVENT_TYPE_DATA_PRODUCT_PROPOSAL_RESOLVED,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])


def _serialise_proposal(row: DataProductSchemaProposal) -> dict[str, Any]:
    """Render one proposal row as JSON.

    Args:
        row: The proposal ORM row.

    Returns:
        JSON-friendly dict.
    """
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "data_product_id": row.data_product_id,
        "proposer_user_id": row.proposer_user_id,
        "proposer_agent_run_id": row.proposer_agent_run_id,
        "diff": json.loads(row.diff_json or "{}"),
        "summary_md": row.summary_md or "",
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "resolved_at": (row.resolved_at.isoformat() if row.resolved_at else None),
        "resolved_by_user_id": row.resolved_by_user_id,
        "resolution_note_md": row.resolution_note_md,
    }


def _require_steward_or_admin(user: Any, row: Any) -> None:
    """Raise unless the caller is the DP's steward or an install-admin.

    Args:
        user: Current user dict.
        row: The DataProduct row.

    Raises:
        AuthorizationError: When neither steward nor admin.
    """
    is_steward = row.steward_user_id is not None and row.steward_user_id == user["id"]
    is_admin = bool(user.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="proposal-resolve",
            securable_type="data_product",
            full_name=f"{row.catalog_name}.{row.schema_name}",
        )


@router.get("/api/data-products/{catalog}/{schema}/proposals")
async def list_proposals(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the proposal list for one DP.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "proposals": [...]}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductSchemaProposal)
                .where(
                    DataProductSchemaProposal.workspace_id == workspace_id,
                    DataProductSchemaProposal.data_product_id == row.id,
                )
                .order_by(DataProductSchemaProposal.created_at.desc())
            )
            .scalars()
            .all()
        )

    return {
        "data_product_id": row.id,
        "proposals": [_serialise_proposal(r) for r in rows],
    }


@router.post("/api/data-products/{catalog}/{schema}/proposals")
async def open_proposal(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Open a new schema-change proposal.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        Serialised proposal row.

    Raises:
        HTTPException: 400 when the diff is malformed.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    body = await request.json()
    diff = validate_diff(body.get("diff") or {})
    summary_md = str(body.get("summary_md") or "").strip()
    agent_run_id = request.headers.get("X-Agent-Run-Id")

    now = datetime.datetime.now(datetime.UTC)
    proposer_user_id: int | None = user["id"] if user.get("id") else None
    if agent_run_id and not summary_md:
        summary_md = "agent-proposed schema change"
    if not proposer_user_id and not agent_run_id:
        raise BadRequestError("proposer_user_id or X-Agent-Run-Id header required")

    with factory() as session:
        new_row = DataProductSchemaProposal(
            workspace_id=workspace_id,
            data_product_id=row.id,
            proposer_user_id=proposer_user_id,
            proposer_agent_run_id=agent_run_id,
            diff_json=json.dumps(diff, sort_keys=True),
            summary_md=summary_md,
            status="open",
            created_at=now,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)
        proposal_id = new_row.id
        payload = _serialise_proposal(new_row)

    audit_service.log_action(
        factory,
        user_id=proposer_user_id or 0,
        user_email=user.get("email", ""),
        action="data_product.proposal_opened",
        target=f"data_product:{catalog}.{schema}",
        detail={"proposal_id": proposal_id, "diff": diff},
        workspace_id=workspace_id,
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_PROPOSAL_OPENED,
        {
            "data_product_id": row.id,
            "data_product_ref": f"{catalog}.{schema}",
            "proposal_id": proposal_id,
            "proposer_user_id": proposer_user_id,
            "proposer_agent_run_id": agent_run_id,
            "diff": diff,
        },
        settings=settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    return payload


def _load_proposal_for_resolve(
    session: Any,
    *,
    workspace_id: int,
    proposal_id: int,
) -> DataProductSchemaProposal:
    """Fetch an open proposal or raise 404 / 400.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        proposal_id: PK of the row.

    Returns:
        The :class:`DataProductSchemaProposal` row.

    Raises:
        HTTPException: 404 when missing, 400 when already resolved.
    """
    proposal = session.execute(
        select(DataProductSchemaProposal).where(
            DataProductSchemaProposal.id == proposal_id,
            DataProductSchemaProposal.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise ResourceNotFoundError.not_found(what=f"proposal id={proposal_id}")
    if proposal.status != "open":
        raise BadRequestError(f"proposal already resolved (status={proposal.status})")
    return proposal


@router.post("/api/data-products/{catalog}/{schema}/proposals/{proposal_id}/approve")
async def approve_proposal(
    catalog: str,
    schema: str,
    proposal_id: int,
    request: Request,
) -> dict[str, Any]:
    """Approve a proposal (in-place yaml rewrite or draft export).

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        proposal_id: PK of the proposal row.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "status": "approved_inplace" |
        "approved_draft", "applied_path": str | None,
        "draft_id": int | None}``.

    Raises:
        HTTPException: 400 on unsafe inplace diff or missing
            target yaml; 404 when the proposal doesn't exist.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    raw_body: Any = await request.json() if await request.body() else {}
    body: dict[str, Any] = raw_body if isinstance(raw_body, dict) else {}
    kind = str(body.get("kind", "inplace"))
    if kind not in ("inplace", "draft"):
        raise BadRequestError("kind must be 'inplace' or 'draft'")
    resolution_note = body.get("resolution_note_md")
    now = datetime.datetime.now(datetime.UTC)

    with factory() as session:
        proposal = _load_proposal_for_resolve(
            session, workspace_id=workspace_id, proposal_id=proposal_id
        )
        diff = json.loads(proposal.diff_json or "{}")
        proposal_payload = _serialise_proposal(proposal)

    applied_path: str | None = None
    draft_id: int | None = None

    diff_dict: dict[str, Any] = diff if isinstance(diff, dict) else {}
    if kind == "inplace":
        if not is_safe_for_inplace(diff_dict):
            raise BadRequestError(
                "diff contains unsafe ops; only "
                "add_columns + change_descriptions are allowed "
                "in-place — re-run with kind='draft'"
            )
        yaml_path = find_yaml_for_dp(settings, workspace_id, catalog, schema)
        if yaml_path is None:
            raise BadRequestError(
                "no yaml file resolved for this DP; configure yaml_search_paths or use kind='draft'"
            )
        new_text = apply_diff_to_yaml(yaml_path.read_text(encoding="utf-8"), diff_dict)
        yaml_path.write_text(new_text, encoding="utf-8")
        load_contract(yaml_path, factory=factory, workspace_id=workspace_id)
        applied_path = str(yaml_path)
        new_status = "approved_inplace"
    else:
        draft_dir_base = Path(settings.data_products.draft_dir) / str(workspace_id)
        draft_dir_base.mkdir(parents=True, exist_ok=True)
        target = draft_dir_base / f"{catalog}__{schema}.yaml"
        base_text: str
        existing_path = find_yaml_for_dp(settings, workspace_id, catalog, schema)
        if existing_path is not None:
            base_text = existing_path.read_text(encoding="utf-8")
        else:
            with factory() as session:
                dp = session.execute(
                    select(DataProduct).where(DataProduct.id == dp_row.id)
                ).scalar_one()
                base_block = json.loads(dp.contract_json)
            base_text = yaml.safe_dump({"data_product": base_block}, sort_keys=False)
        new_text = apply_diff_to_yaml(base_text, diff_dict)
        target.write_text(new_text, encoding="utf-8")
        yaml_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
        with factory() as session:
            existing_draft = session.execute(
                select(DataProductYamlDraft).where(
                    DataProductYamlDraft.workspace_id == workspace_id,
                    DataProductYamlDraft.catalog_name == catalog,
                    DataProductYamlDraft.schema_name == schema,
                    DataProductYamlDraft.yaml_hash == yaml_hash,
                )
            ).scalar_one_or_none()
            if existing_draft is None:
                new_draft = DataProductYamlDraft(
                    workspace_id=workspace_id,
                    catalog_name=catalog,
                    schema_name=schema,
                    draft_path=str(target),
                    source_kind="agent_proposal",
                    created_by_user_id=user["id"],
                    created_at=now,
                    yaml_hash=yaml_hash,
                )
                session.add(new_draft)
                session.flush()
                draft_id = new_draft.id
            else:
                existing_draft.draft_path = str(target)
                existing_draft.source_kind = "agent_proposal"
                session.add(existing_draft)
                draft_id = existing_draft.id
            session.commit()
        new_status = "approved_draft"

    with factory() as session:
        proposal = session.get(DataProductSchemaProposal, proposal_id)
        if proposal is None:
            raise ResourceNotFoundError.not_found(what=f"proposal id={proposal_id}")
        proposal.status = new_status
        proposal.resolved_at = now
        proposal.resolved_by_user_id = user["id"]
        if resolution_note is not None:
            proposal.resolution_note_md = str(resolution_note)
        session.add(proposal)
        session.commit()

    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="data_product.proposal_resolved",
        target=f"data_product:{catalog}.{schema}",
        detail={
            "proposal_id": proposal_id,
            "status": new_status,
            "draft_id": draft_id,
            "applied_path": applied_path,
        },
        workspace_id=workspace_id,
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_PROPOSAL_RESOLVED,
        {
            "data_product_id": dp_row.id,
            "data_product_ref": f"{catalog}.{schema}",
            "proposal_id": proposal_id,
            "status": new_status,
            "applied_path": applied_path,
            "draft_id": draft_id,
            "resolved_by_user_id": user["id"],
        },
        settings=settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    del proposal_payload
    return {
        "id": proposal_id,
        "status": new_status,
        "applied_path": applied_path,
        "draft_id": draft_id,
    }


@router.post("/api/data-products/{catalog}/{schema}/proposals/{proposal_id}/reject")
async def reject_proposal(
    catalog: str,
    schema: str,
    proposal_id: int,
    request: Request,
) -> dict[str, Any]:
    """Reject a proposal.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        proposal_id: PK of the proposal row.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "status": "rejected"}``.

        Raises 404 (via :func:`_load_proposal_for_resolve`) when
        the proposal doesn't exist, and 400 when it's already
        resolved.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    raw_body: Any = await request.json() if await request.body() else {}
    body: dict[str, Any] = raw_body if isinstance(raw_body, dict) else {}
    resolution_note = body.get("resolution_note_md")
    now = datetime.datetime.now(datetime.UTC)

    with factory() as session:
        proposal = _load_proposal_for_resolve(
            session, workspace_id=workspace_id, proposal_id=proposal_id
        )
        proposal.status = "rejected"
        proposal.resolved_at = now
        proposal.resolved_by_user_id = user["id"]
        if resolution_note is not None:
            proposal.resolution_note_md = str(resolution_note)
        session.add(proposal)
        session.commit()

    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="data_product.proposal_resolved",
        target=f"data_product:{catalog}.{schema}",
        detail={"proposal_id": proposal_id, "status": "rejected"},
        workspace_id=workspace_id,
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_PROPOSAL_RESOLVED,
        {
            "data_product_id": dp_row.id,
            "data_product_ref": f"{catalog}.{schema}",
            "proposal_id": proposal_id,
            "status": "rejected",
            "resolved_by_user_id": user["id"],
        },
        settings=settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    return {"id": proposal_id, "status": "rejected"}
