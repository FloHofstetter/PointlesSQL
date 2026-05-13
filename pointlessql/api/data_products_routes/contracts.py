"""``/api/contracts`` — yaml-draft authoring (Phase 73.2).

Five endpoints backing the agent + admin flow for the inline
:func:`pql.contract` DSL:

* ``POST /api/contracts/draft`` — preview-only.  Validates the
  payload against :class:`DataProductContract` and returns the
  yaml without writing to disk.
* ``POST /api/contracts/save`` — persists.  Writes the yaml
  file under ``settings.data_products.draft_dir`` and
  inserts a :class:`DataProductYamlDraft` row.
* ``GET /api/contracts/drafts`` — list drafts (admin /
  steward gate).
* ``POST /api/contracts/drafts/{id}/promote`` — copies the
  draft into the first writable
  ``yaml_search_paths`` entry, runs the loader, and stamps
  the row.
* ``POST /api/contracts/drafts/{id}/discard`` — soft-delete
  the draft (stamps ``discarded_at``).
"""

from __future__ import annotations

import datetime
import hashlib
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.data_products import load_contract
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.catalog._data_product_yaml_draft import (
    DataProductYamlDraft,
)
from pointlessql.pql._contracts import DraftContract
from pointlessql.pql._contracts import contract as build_contract

router = APIRouter(tags=["data-products"])


def _draft_filename(catalog: str, schema: str) -> str:
    """Return the on-disk draft filename for a ``(catalog, schema)``."""
    return f"{catalog}__{schema}.yaml"


def _draft_dir(settings: Any, workspace_id: int) -> Path:
    """Return the workspace-scoped draft directory; create on demand.

    Args:
        settings: Live :class:`Settings`.
        workspace_id: Tenant scope.

    Returns:
        Absolute path; created on demand.
    """
    base = Path(settings.data_products.draft_dir)
    parent = base / str(workspace_id)
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def _build_payload(body: dict[str, Any]) -> DraftContract:
    """Validate the body via :func:`build_contract`.

    Args:
        body: Incoming JSON body.

    Returns:
        The validated :class:`DraftContract`.

    Raises:
        HTTPException: 400 on validation failure (catalog,
            schema, or tables missing).
    """
    catalog = body.get("catalog")
    schema = body.get("schema") or body.get("schema_name")
    tables = body.get("tables")
    if not catalog or not schema or tables is None:
        # bare-http-ok: required fields missing.
        raise HTTPException(
            status_code=400,
            detail="catalog, schema, and tables are required",
        )
    try:
        return build_contract(
            str(catalog),
            str(schema),
            tables=list(tables),
            name=body.get("name"),
            description=str(body.get("description") or ""),
            version=str(body.get("version") or "0.1.0-draft"),
            sla_minutes=body.get("sla_minutes"),
            steward_email=body.get("steward_email"),
        )
    except ValidationError as exc:
        # bare-http-ok: pydantic ValidationError surfaced as 400.
        raise HTTPException(status_code=400, detail=str(exc)) from None


def _require_steward_or_admin(request: Request) -> Any:
    """Gate: install-admin or session-cookie steward.

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
        privilege="contract-promote",
        securable_type="data_product_yaml_draft",
        full_name="drafts",
    )


@router.post("/api/contracts/draft")
async def preview_contract_draft(
    request: Request,
) -> dict[str, Any]:
    """Validate the payload and return the rendered yaml + target path.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"yaml_preview": str, "would_write_path": str,
        "validated": dict}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    settings = request.app.state.settings
    body = await request.json()
    draft = _build_payload(body)
    parent = _draft_dir(settings, workspace_id)
    target = parent / _draft_filename(draft.contract.catalog, draft.contract.schema_name)
    return {
        "yaml_preview": draft.yaml(),
        "would_write_path": str(target),
        "validated": draft.as_dict(),
    }


@router.post("/api/contracts/save")
async def save_contract_draft(
    request: Request,
) -> dict[str, Any]:
    """Persist the validated yaml to disk + the tracking row.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"draft_id": int, "draft_path": str, "yaml_hash": str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    body = await request.json()
    draft = _build_payload(body)
    parent = _draft_dir(settings, workspace_id)
    target = parent / _draft_filename(draft.contract.catalog, draft.contract.schema_name)
    yaml_text = draft.yaml()
    yaml_hash = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
    target.write_text(yaml_text, encoding="utf-8")

    with factory() as session:
        existing = session.execute(
            select(DataProductYamlDraft).where(
                DataProductYamlDraft.workspace_id == workspace_id,
                DataProductYamlDraft.catalog_name == draft.contract.catalog,
                DataProductYamlDraft.schema_name == draft.contract.schema_name,
                DataProductYamlDraft.yaml_hash == yaml_hash,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.draft_path = str(target)
            existing.created_at = datetime.datetime.now(datetime.UTC)
            existing.created_by_user_id = user["id"]
            existing.source_kind = "pql_contract"
            session.add(existing)
            draft_id = existing.id
        else:
            new_row = DataProductYamlDraft(
                workspace_id=workspace_id,
                catalog_name=draft.contract.catalog,
                schema_name=draft.contract.schema_name,
                draft_path=str(target),
                source_kind="pql_contract",
                created_by_user_id=user["id"],
                created_at=datetime.datetime.now(datetime.UTC),
                yaml_hash=yaml_hash,
            )
            session.add(new_row)
            session.flush()
            draft_id = new_row.id
        session.commit()
    return {
        "draft_id": draft_id,
        "draft_path": str(target),
        "yaml_hash": yaml_hash,
    }


@router.get("/api/contracts/drafts")
async def list_drafts(request: Request) -> dict[str, Any]:
    """Return active + discarded drafts for the workspace.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"drafts": [...]}``.
    """
    _require_steward_or_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(DataProductYamlDraft)
                .where(DataProductYamlDraft.workspace_id == workspace_id)
                .order_by(DataProductYamlDraft.created_at.desc())
            )
            .scalars()
            .all()
        )
        payload = [
            {
                "id": row.id,
                "catalog_name": row.catalog_name,
                "schema_name": row.schema_name,
                "draft_path": row.draft_path,
                "source_kind": row.source_kind,
                "created_at": row.created_at.isoformat(),
                "created_by_user_id": row.created_by_user_id,
                "created_by_agent_run_id": row.created_by_agent_run_id,
                "promoted_at": (
                    row.promoted_at.isoformat() if row.promoted_at else None
                ),
                "promoted_to_data_product_id": row.promoted_to_data_product_id,
                "discarded_at": (
                    row.discarded_at.isoformat() if row.discarded_at else None
                ),
                "yaml_hash": row.yaml_hash,
            }
            for row in rows
        ]
    return {"drafts": payload}


@router.post("/api/contracts/drafts/{draft_id}/promote")
async def promote_draft(
    draft_id: int,
    request: Request,
) -> dict[str, Any]:
    """Copy a draft into the active search path and run the loader.

    Args:
        draft_id: PK of the :class:`DataProductYamlDraft` row.
        request: Incoming FastAPI request.

    Returns:
        ``{"promoted_to_data_product_id": int | None,
        "destination_path": str}``.

    Raises:
        HTTPException: 404 when the draft doesn't exist, 400
            when no writable ``yaml_search_paths`` entry is
            configured or the draft was already promoted.
    """
    _require_steward_or_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings

    yaml_search_paths: list[Path] = list(settings.data_products.yaml_search_paths)
    writable_dir: Path | None = None
    for p in yaml_search_paths:
        candidate = Path(p)
        if candidate.exists() and candidate.is_dir():
            writable_dir = candidate
            break
    if writable_dir is None:
        # bare-http-ok: cannot promote without a target directory.
        raise HTTPException(
            status_code=400,
            detail=(
                "no writable yaml_search_paths directory found; "
                "configure POINTLESSQL_DATA_PRODUCTS_YAML_SEARCH_PATHS "
                "to point at an existing directory before promoting"
            ),
        )

    with factory() as session:
        row = session.execute(
            select(DataProductYamlDraft).where(
                DataProductYamlDraft.id == draft_id,
                DataProductYamlDraft.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            # bare-http-ok: draft not present.
            raise HTTPException(status_code=404, detail="draft not found")
        if row.promoted_at is not None:
            # bare-http-ok: already promoted.
            raise HTTPException(
                status_code=400, detail="draft already promoted"
            )
        if row.discarded_at is not None:
            # bare-http-ok: cannot promote a discarded draft.
            raise HTTPException(
                status_code=400, detail="draft was discarded; cannot promote"
            )
        draft_path = Path(row.draft_path)
        target = writable_dir / _draft_filename(row.catalog_name, row.schema_name)
        catalog_name = row.catalog_name
        schema_name = row.schema_name

    if not draft_path.exists():
        # bare-http-ok: draft yaml missing on disk.
        raise HTTPException(status_code=400, detail="draft file missing")
    shutil.copyfile(draft_path, target)

    load_contract(target, factory=factory, workspace_id=workspace_id)

    with factory() as session:
        from pointlessql.models.catalog._data_products import DataProduct

        dp = session.execute(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog_name,
                DataProduct.schema_name == schema_name,
            )
        ).scalar_one_or_none()
        dp_id = dp.id if dp is not None else None

        row = session.execute(
            select(DataProductYamlDraft).where(DataProductYamlDraft.id == draft_id)
        ).scalar_one()
        row.promoted_at = datetime.datetime.now(datetime.UTC)
        row.promoted_to_data_product_id = dp_id
        session.add(row)
        session.commit()

    return {
        "promoted_to_data_product_id": dp_id,
        "destination_path": str(target),
    }


@router.post("/api/contracts/drafts/{draft_id}/discard")
async def discard_draft(
    draft_id: int,
    request: Request,
) -> dict[str, Any]:
    """Soft-delete a draft (stamps ``discarded_at``).

    Args:
        draft_id: PK of the row.
        request: Incoming FastAPI request.

    Returns:
        ``{"discarded": bool}``.

    Raises:
        HTTPException: 404 when the draft doesn't exist.
    """
    _require_steward_or_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductYamlDraft).where(
                DataProductYamlDraft.id == draft_id,
                DataProductYamlDraft.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            # bare-http-ok: draft not present.
            raise HTTPException(status_code=404, detail="draft not found")
        if row.discarded_at is None:
            row.discarded_at = datetime.datetime.now(datetime.UTC)
            session.add(row)
            session.commit()
    return {"discarded": True}
