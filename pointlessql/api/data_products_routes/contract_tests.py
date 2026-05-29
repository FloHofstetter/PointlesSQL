"""Per-product contract-tests + fixtures + run-results routes.

Steward / admin can declare and run contract tests on their product;
any-user can read the listings + result history.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError
from pointlessql.services import contract_tests as contract_tests_service

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request, catalog: str, schema: str) -> None:
    """Raise 403 unless the caller is admin or the product's steward."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    if user.get("is_admin"):
        return
    if dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="steward",
        securable_type="data_product",
        full_name=f"{catalog}.{schema}",
    )


@router.get("/api/data-products/{catalog}/{schema}/contract-tests")
async def list_contract_tests(
    catalog: str, schema: str, request: Request
) -> dict[str, Any]:
    """Return every contract test on the product."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    return {
        "contract_tests": contract_tests_service.list_contract_tests(
            factory, data_product_id=int(dp_row.id)
        )
    }


@router.post("/api/data-products/{catalog}/{schema}/contract-tests")
async def declare_contract_test(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Declare / update one contract test (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        test = contract_tests_service.declare_contract_test(
            factory,
            data_product_id=int(dp_row.id),
            name=str(body.get("name", "")),
            assertion_kind=str(body.get("assertion_kind", "")),
            assertion_spec_json=body.get("assertion_spec", {}),
            severity=str(body.get("severity", "warn")),
            enabled=bool(body.get("enabled", True)),
            created_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"contract_test": test}


@router.delete(
    "/api/data-products/{catalog}/{schema}/contract-tests/{contract_test_id}"
)
async def delete_contract_test(
    catalog: str, schema: str, contract_test_id: int, request: Request
) -> dict[str, Any]:
    """Delete one contract test (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    removed = contract_tests_service.delete_contract_test(
        factory, contract_test_id=contract_test_id
    )
    if not removed:
        # bare-http-ok: 404 for unknown contract-test PK; no domain exception.
        raise HTTPException(
            status_code=404, detail="contract test not found"
        )
    return {"deleted": True}


@router.get("/api/data-products/{catalog}/{schema}/fixtures")
async def list_fixtures(
    catalog: str, schema: str, request: Request
) -> dict[str, Any]:
    """Return every fixture declared on the product."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    return {
        "fixtures": contract_tests_service.list_fixtures(
            factory, data_product_id=int(dp_row.id)
        )
    }


@router.post("/api/data-products/{catalog}/{schema}/fixtures")
async def declare_fixture(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Declare / update one synthetic fixture (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        fixture = contract_tests_service.declare_fixture(
            factory,
            data_product_id=int(dp_row.id),
            table_name=str(body.get("table_name", "")),
            generator_spec_json=body.get("generator_spec", []),
            row_count=int(body.get("row_count", 100) or 100),
            created_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"fixture": fixture}


@router.delete(
    "/api/data-products/{catalog}/{schema}/fixtures/{fixture_id}"
)
async def delete_fixture(
    catalog: str, schema: str, fixture_id: int, request: Request
) -> dict[str, Any]:
    """Delete one fixture row (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    removed = contract_tests_service.delete_fixture(
        factory, fixture_id=fixture_id
    )
    if not removed:
        # bare-http-ok: 404 for unknown fixture PK; no domain exception.
        raise HTTPException(status_code=404, detail="fixture not found")
    return {"deleted": True}


@router.post("/api/data-products/{catalog}/{schema}/contract-tests/run")
async def run_contract_tests_now(
    catalog: str,
    schema: str,
    request: Request,
    mode: str = "synthetic",
) -> dict[str, Any]:
    """Kick a contract-test run synchronously (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        outcome = contract_tests_service.run_contract_tests(
            factory,
            data_product_id=int(dp_row.id),
            mode=mode,
            user_id=int(user.get("id", 0) or 0),
            user_email=str(user.get("email", "system")),
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {
        "mode": outcome.mode,
        "total": outcome.total,
        "passed": outcome.passed,
        "failed": outcome.failed,
        "errored": outcome.errored,
        "results": outcome.results,
    }


@router.get(
    "/api/data-products/{catalog}/{schema}/contract-tests/{contract_test_id}/results"
)
async def list_contract_test_results(
    catalog: str,
    schema: str,
    contract_test_id: int,
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return the most recent result rows for one test."""
    require_user(request)
    factory = request.app.state.session_factory
    return {
        "results": contract_tests_service.list_results(
            factory,
            contract_test_id=contract_test_id,
            limit=limit,
            offset=offset,
        )
    }
