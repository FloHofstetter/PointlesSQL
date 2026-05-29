"""Control-Port + governance endpoints for a data product.

The control-port hangs off the existing
``/api/data-products/{catalog}/{schema}`` surface and carries the
policy configuration + privileged operations the Data-Mesh control-port
calls for:

* ``GET    .../policy`` — the effective policy (product ⇐ workspace).
* ``PUT    .../policy`` — set the product's policy overrides.
* ``GET    .../classifications`` — declared column classifications.
* ``POST   .../classifications`` — classify a column.
* ``DELETE .../classifications/{id}`` — remove a classification.
* ``POST   .../control/forget`` — right-to-be-forgotten (deletes rows).
* ``GET    .../forget-requests`` — the forget ledger.
* ``GET    .../governance`` — the aggregate the Governance tab renders.

GET endpoints are open to any authenticated user; every mutation +
the forget op gate on ``_require_steward_or_admin``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.proposals import (
    _require_steward_or_admin,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    effective_principal,
    get_user,
    require_user,
)
from pointlessql.config import Settings
from pointlessql.exceptions import BadRequestError
from pointlessql.models import AuditLog
from pointlessql.services import governance as governance_service
from pointlessql.services.governance._compliance import COMPLIANCE_VIOLATION_ACTION
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_FORGOTTEN,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])


def _serialise_classification(row: Any) -> dict[str, Any]:
    """Render a classification row as JSON with its effective strategy."""
    return {
        "id": row.id,
        "table": row.table_name,
        "column": row.column_name,
        "classification": row.classification,
        "masking_strategy": governance_service.effective_strategy(
            row.classification, row.masking_strategy
        ),
        "strategy_override": row.masking_strategy,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialise_forget_request(row: Any) -> dict[str, Any]:
    """Render a forget-request ledger row as JSON (no raw subject value)."""
    return {
        "id": row.id,
        "subject_column": row.subject_column,
        "status": row.status,
        "tables_affected": json.loads(row.tables_affected_json or "[]"),
        "rows_deleted": row.rows_deleted,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
    }


@router.get("/api/data-products/{catalog}/{schema}/policy")
async def get_policy(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the product's effective policy + raw override + workspace default."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    return {
        "effective": governance_service.get_effective_policy(
            factory, data_product_id=dp_row.id, workspace_id=workspace_id
        ),
        "product": governance_service.get_product_policy(factory, data_product_id=dp_row.id),
        "workspace_default": governance_service.get_workspace_policy(
            factory, workspace_id=workspace_id
        ),
    }


@router.put("/api/data-products/{catalog}/{schema}/policy")
async def set_policy(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Set the product's policy overrides.

    Body keys (all optional): ``retention_days``, ``encryption_class``,
    ``residency_region``, ``consent_required``, ``consent_basis``.  Pass
    an explicit ``null`` to clear a field back to "inherit".
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    fields = {k: body[k] for k in governance_service.POLICY_FIELDS if k in body}
    updater = int(user["id"]) if user["id"] > 0 else None
    try:
        governance_service.set_product_policy(
            factory, data_product_id=dp_row.id, fields=fields, updated_by_user_id=updater
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        "data_product.policy_set",
        f"data_product:{catalog}.{schema}",
        {"fields": list(fields.keys())},
    )
    return {
        "effective": governance_service.get_effective_policy(
            factory, data_product_id=dp_row.id, workspace_id=workspace_id
        )
    }


@router.get("/api/data-products/{catalog}/{schema}/classifications")
async def list_classifications(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """List the column classifications declared on this product."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    rows = governance_service.list_classifications(factory, data_product_id=dp_row.id)
    return {"classifications": [_serialise_classification(r) for r in rows]}


@router.post("/api/data-products/{catalog}/{schema}/classifications")
async def add_classification(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Classify one column.

    Body: ``{"table": str, "column": str, "classification":
    "public"|"internal"|"confidential"|"pii"|"phi",
    "masking_strategy"?: str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    creator = int(user["id"]) if user["id"] > 0 else None
    strategy = body.get("masking_strategy")
    try:
        row = governance_service.add_classification(
            factory,
            data_product_id=dp_row.id,
            catalog=catalog,
            schema=schema,
            table=str(body.get("table", "")),
            column=str(body.get("column", "")),
            classification=str(body.get("classification", "")),
            masking_strategy=str(strategy) if strategy else None,
            created_by_user_id=creator,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        "data_product.column_classified",
        f"data_product:{catalog}.{schema}",
        {"table": row.table_name, "column": row.column_name, "class": row.classification},
    )
    return _serialise_classification(row)


@router.delete("/api/data-products/{catalog}/{schema}/classifications/{classification_id}")
async def delete_classification(
    catalog: str, schema: str, classification_id: int, request: Request
) -> dict[str, Any]:
    """Remove a column classification from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    deleted = governance_service.delete_classification(
        factory, data_product_id=dp_row.id, classification_id=classification_id
    )
    if deleted:
        await audit(
            request,
            "data_product.classification_removed",
            f"data_product:{catalog}.{schema}",
            {"classification_id": classification_id},
        )
    return {"deleted": deleted}


@router.post("/api/data-products/{catalog}/{schema}/control/forget")
async def right_to_be_forgotten(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Erase a data subject's rows across the product's declared tables.

    Body: ``{"subject_column": str, "subject_value": str}``.  Destructive
    + irreversible — steward/admin only.  The subject value is used for
    the delete predicate and a ledger hash; it is never stored raw.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, contract, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    subject_column = str(body.get("subject_column", "")).strip()
    subject_value = str(body.get("subject_value", ""))
    if not subject_column or not subject_value:
        raise BadRequestError("subject_column and subject_value are required")

    declared_tables = [(t.name, [c.name for c in t.columns]) for t in contract.tables]
    principal = effective_principal(request) or user.get("email", "")
    settings: Settings = request.app.state.settings
    executor = int(user["id"]) if user["id"] > 0 else None
    try:
        summary = await asyncio.to_thread(
            governance_service.execute_forget,
            factory,
            settings,
            data_product_id=dp_row.id,
            catalog=catalog,
            schema=schema,
            subject_column=subject_column,
            subject_value=subject_value,
            declared_tables=declared_tables,
            principal=principal,
            executed_by_user_id=executor,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await audit(
        request,
        "data_product.forget",
        f"data_product:{catalog}.{schema}",
        {
            "subject_column": subject_column,
            "rows_deleted": summary["rows_deleted"],
            "tables_affected": summary["tables_affected"],
        },
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_FORGOTTEN,
        {
            "product": f"{catalog}.{schema}",
            "subject_column": subject_column,
            "rows_deleted": summary["rows_deleted"],
            "tables_affected": [t["table"] for t in summary["tables_affected"]],
        },
        settings=settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    return summary


@router.post("/api/data-products/{catalog}/{schema}/control/forget-requests")
async def propose_forget_request(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Propose a right-to-be-forgotten request without executing it.

    The path a supervised agent takes: it records a ``proposed`` ledger
    row (subject value stored hashed, no deletion) that a steward/admin
    reviews and then executes via ``POST .../control/forget``.  Open to
    any authenticated user.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    subject_column = str(body.get("subject_column", "")).strip()
    subject_value = str(body.get("subject_value", ""))
    if not subject_column or not subject_value:
        raise BadRequestError("subject_column and subject_value are required")
    requester = int(user["id"]) if user["id"] > 0 else None
    try:
        row = governance_service.propose_forget(
            factory,
            data_product_id=dp_row.id,
            subject_column=subject_column,
            subject_value=subject_value,
            requested_by_user_id=requester,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        "data_product.forget_proposed",
        f"data_product:{catalog}.{schema}",
        {"request_id": row.id, "subject_column": subject_column},
    )
    return _serialise_forget_request(row)


@router.get("/api/data-products/{catalog}/{schema}/forget-requests")
async def list_forget_requests(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the right-to-be-forgotten ledger for this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)
    rows = governance_service.list_forget_requests(factory, data_product_id=dp_row.id)
    return {"forget_requests": [_serialise_forget_request(r) for r in rows]}


def _recent_violations(
    factory: Any, *, workspace_id: int, catalog: str, schema: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Return recent compliance-violation audit rows for this product."""
    target = f"data_product:{catalog}.{schema}"
    with factory() as session:
        rows = list(
            session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.action == COMPLIANCE_VIOLATION_ACTION,
                    AuditLog.target == target,
                )
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            ).all()
        )
    violations: list[dict[str, Any]] = []
    for row in rows:
        try:
            detail = json.loads(row.detail) if row.detail else {}
        except (TypeError, ValueError):
            detail = {}
        violations.append(
            {"created_at": row.created_at.isoformat() if row.created_at else None, **detail}
        )
    return violations


@router.get("/api/data-products/{catalog}/{schema}/governance")
async def governance_aggregate(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the aggregate the Governance tab renders.

    Effective policy + classifications + recent compliance violations +
    the forget ledger (steward/admin only) + the A4 ownership
    suggestion + a derived trust flag.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    is_admin = bool(user.get("is_admin"))
    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    can_manage = is_admin or is_steward

    classifications = governance_service.list_classifications(factory, data_product_id=dp_row.id)
    violations = _recent_violations(
        factory, workspace_id=workspace_id, catalog=catalog, schema=schema
    )
    forget_requests = (
        [
            _serialise_forget_request(r)
            for r in governance_service.list_forget_requests(factory, data_product_id=dp_row.id)
        ]
        if can_manage
        else []
    )
    return {
        "can_manage": can_manage,
        "effective_policy": governance_service.get_effective_policy(
            factory, data_product_id=dp_row.id, workspace_id=workspace_id
        ),
        "classifications": [_serialise_classification(r) for r in classifications],
        "violations": violations,
        "trust_downgraded": len(violations) > 0,
        "forget_requests": forget_requests,
        "ownership_suggestion": governance_service.suggest_domain_for_aggregate(
            factory, data_product_id=dp_row.id, workspace_id=workspace_id
        ),
    }
