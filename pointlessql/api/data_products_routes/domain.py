"""Product↔domain assignment + transformation-binding endpoints.

These hang off the existing ``/api/data-products/{catalog}/{schema}``
surface so a product's domain + bound transformations are managed in
the same place as its contract.  Both surfaces gate on
``_require_steward_or_admin`` — the product's steward or an
install-admin may (re)assign the domain and bind/unbind code, which
is also the path a supervised agent takes via the
``pql_assign_data_product_domain`` plugin tool.

* ``PATCH  /api/data-products/{catalog}/{schema}/domain`` — set or
  clear the owning domain (``{"domain_id": int | null}``).
* ``GET    /api/data-products/{catalog}/{schema}/transformations``
* ``POST   /api/data-products/{catalog}/{schema}/transformations``
* ``DELETE /api/data-products/{catalog}/{schema}/transformations/{id}``
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.proposals import (
    _require_steward_or_admin,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.models import Notebook
from pointlessql.services import domains as domains_service

router = APIRouter(tags=["data-products"])


def _serialise_transformation(row: Any, *, notebook_path: str | None = None) -> dict[str, Any]:
    """Render a :class:`DataProductTransformation` row as JSON."""
    return {
        "id": row.id,
        "kind": row.kind,
        "notebook_id": row.notebook_id,
        "notebook_path": notebook_path,
        "dbt_model_name": row.dbt_model_name,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.patch("/api/data-products/{catalog}/{schema}/domain")
async def assign_domain(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Set or clear the product's owning domain.

    Body ``{"domain_id": int}`` assigns; ``{"domain_id": null}``
    unassigns.  The domain must live in the same workspace.

    Returns:
        ``{"data_product_id": int, "domain_id": int | None}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    if "domain_id" not in body:
        raise BadRequestError("domain_id is required (use null to unassign)")
    domain_id_raw = body.get("domain_id")
    domain_id: int | None
    if domain_id_raw is None:
        domain_id = None
    elif isinstance(domain_id_raw, int) and not isinstance(domain_id_raw, bool):
        domain_id = domain_id_raw
    else:
        raise BadRequestError("domain_id must be an integer or null")

    try:
        product = domains_service.assign_product_domain(
            factory,
            workspace_id=workspace_id,
            data_product_id=dp_row.id,
            domain_id=domain_id,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await audit(
        request,
        "data_product.domain_assigned",
        f"data_product:{catalog}.{schema}",
        {"data_product_id": product.id, "domain_id": domain_id},
    )
    return {"data_product_id": product.id, "domain_id": product.domain_id}


@router.get("/api/data-products/{catalog}/{schema}/transformations")
async def list_transformations(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """List the transformations bound to this product."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    rows = domains_service.list_transformations(factory, data_product_id=dp_row.id)

    nb_paths: dict[str, str] = {}
    nb_ids = [r.notebook_id for r in rows if r.notebook_id]
    if nb_ids:
        with factory() as session:
            for nb_id in nb_ids:
                nb = session.get(Notebook, nb_id)
                if nb is not None:
                    nb_paths[nb_id] = nb.file_path
    return {
        "transformations": [
            _serialise_transformation(r, notebook_path=nb_paths.get(r.notebook_id or ""))
            for r in rows
        ]
    }


@router.post("/api/data-products/{catalog}/{schema}/transformations")
async def bind_transformation(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Bind a notebook or dbt model to this product.

    Body: ``{"kind": "notebook", "notebook_id": str}`` or
    ``{"kind": "dbt_model", "dbt_model_name": str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    kind = str(body.get("kind", "")).strip()
    notebook_id = body.get("notebook_id")
    dbt_model_name = body.get("dbt_model_name")
    creator_id = int(user["id"]) if user["id"] > 0 else None

    try:
        row = domains_service.bind_transformation(
            factory,
            data_product_id=dp_row.id,
            kind=kind,
            notebook_id=str(notebook_id) if isinstance(notebook_id, str) else None,
            dbt_model_name=str(dbt_model_name) if isinstance(dbt_model_name, str) else None,
            created_by_user_id=creator_id,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await audit(
        request,
        "data_product.transformation_bound",
        f"data_product:{catalog}.{schema}",
        {"transformation_id": row.id, "kind": row.kind},
    )
    return _serialise_transformation(row)


@router.delete("/api/data-products/{catalog}/{schema}/transformations/{transformation_id}")
async def unbind_transformation(
    catalog: str, schema: str, transformation_id: int, request: Request
) -> dict[str, Any]:
    """Remove a transformation binding from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    deleted = domains_service.unbind_transformation(
        factory, data_product_id=dp_row.id, transformation_id=transformation_id
    )
    if deleted:
        await audit(
            request,
            "data_product.transformation_unbound",
            f"data_product:{catalog}.{schema}",
            {"transformation_id": transformation_id},
        )
    return {"deleted": deleted}
