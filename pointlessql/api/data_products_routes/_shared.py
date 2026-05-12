"""Shared helpers used across the data_products_routes sub-modules.

The listing / detail / diff / lineage / reload sub-modules — and
the upcoming Phase-71 comment / review / follow / readme handlers —
all need a way to serialise a :class:`DataProduct` ORM row and to
look up one product (plus its parsed pydantic contract + steward)
by ``(workspace_id, catalog, schema)``.  Centralising those tiny
helpers here keeps the import graph one-way: every sub-module
depends on ``_shared``, and ``_shared`` depends on nothing else
inside the package.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from pointlessql.data_products import DataProductContract
from pointlessql.data_products._diff import ContractDiffResult
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct


def serialise_product(
    row: DataProduct,
    *,
    steward_email: str | None,
    steward_display_name: str | None,
) -> dict[str, Any]:
    """Render one ``DataProduct`` cache row as a JSON-friendly dict.

    Used by both the listing and detail handlers so the wire format
    stays consistent.

    Args:
        row: The persisted data-product row.
        steward_email: Pre-resolved steward email, or ``None`` when
            the row's ``steward_user_id`` is NULL.
        steward_display_name: Pre-resolved steward display name.

    Returns:
        Dict ready for ``jsonable_encoder`` / FastAPI response.
    """
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "catalog": row.catalog_name,
        "schema": row.schema_name,
        "ref": f"{row.catalog_name}.{row.schema_name}",
        "version": row.version,
        "description": row.description,
        "sla_minutes": row.sla_minutes,
        "steward": {
            "user_id": row.steward_user_id,
            "email": steward_email,
            "display_name": steward_display_name,
        },
        "contract_yaml_hash": row.contract_yaml_hash,
        "last_loaded_at": row.last_loaded_at.isoformat(),
        "last_alerted_at": (
            row.last_alerted_at.isoformat() if row.last_alerted_at else None
        ),
    }


def load_one(
    session_factory: Any,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> tuple[DataProduct, DataProductContract, str | None, str | None]:
    """Look up the product + parsed contract; raise 404 when missing.

    Args:
        session_factory: SQLAlchemy session factory from app state.
        workspace_id: Active workspace id resolved from the request.
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Tuple of ``(row, contract, steward_email, steward_display)``.

    Raises:
        ResourceNotFoundError: When no product matches the
            ``(workspace_id, catalog, schema)`` tuple.
    """
    with session_factory() as session:
        row = session.execute(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFoundError(
                f"data product {catalog}.{schema!r} not found"
            )
        contract = DataProductContract.model_validate(json.loads(row.contract_json))
        if row.steward_user_id is not None:
            user = session.get(User, row.steward_user_id)
            steward_email = user.email if user else None
            steward_display = user.display_name if user else None
        else:
            steward_email = None
            steward_display = None
        return row, contract, steward_email, steward_display


def diff_to_payload(
    table_name: str, diff: ContractDiffResult | str
) -> dict[str, Any]:
    """Render a diff result (or error string) as a JSON-friendly dict."""
    if isinstance(diff, str):
        return {"name": table_name, "error": diff}
    return {"name": table_name, **diff.as_dict()}
