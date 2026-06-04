"""Infrastructure-declaration upsert + read."""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import (
    INFRASTRUCTURE_STORAGE_CLASSES,
    DataProductInfrastructure,
)
from pointlessql.types import SessionFactory


def _row_to_dict(row: DataProductInfrastructure | None) -> dict[str, Any]:
    if row is None:
        return {
            "storage_class": None,
            "compute_runtime": None,
            "access_methods": [],
            "region": None,
            "notes": None,
            "updated_at": None,
        }
    try:
        methods = json.loads(row.access_methods_json) if row.access_methods_json else []
    except (TypeError, ValueError):
        methods = []
    return {
        "storage_class": row.storage_class,
        "compute_runtime": row.compute_runtime,
        "access_methods": methods,
        "region": row.region,
        "notes": row.notes,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_infrastructure(
    factory: SessionFactory, *, data_product_id: int
) -> dict[str, Any]:
    """Return the product's infrastructure declaration, or all-``None`` row."""
    with factory() as session:
        row = session.scalar(
            select(DataProductInfrastructure).where(
                DataProductInfrastructure.data_product_id == data_product_id
            )
        )
        return _row_to_dict(row)


def set_infrastructure(
    factory: SessionFactory,
    *,
    data_product_id: int,
    fields: dict[str, Any],
    updated_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Upsert the product's infrastructure row.

    Args:
        factory: Sessionmaker callable.
        data_product_id: Product to upsert against.
        fields: Subset of
            ``{"storage_class","compute_runtime","access_methods",
            "region","notes"}``.  ``access_methods`` is a list of
            strings (serialised to JSON in the column).
        updated_by_user_id: Audit trail.

    Returns:
        The fully-populated dict view of the row (same shape as
        :func:`get_infrastructure`).

    Raises:
        ValueError: When ``storage_class`` is set to an invalid value.
    """
    storage_class = fields.get("storage_class")
    if storage_class is not None and storage_class not in INFRASTRUCTURE_STORAGE_CLASSES:
        raise ValueError(
            f"storage_class {storage_class!r} not in {INFRASTRUCTURE_STORAGE_CLASSES}"
        )
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.scalar(
            select(DataProductInfrastructure).where(
                DataProductInfrastructure.data_product_id == data_product_id
            )
        )
        if row is None:
            row = DataProductInfrastructure(
                data_product_id=data_product_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        if "storage_class" in fields:
            row.storage_class = fields["storage_class"]
        if "compute_runtime" in fields:
            value = fields["compute_runtime"]
            row.compute_runtime = (
                value.strip() if isinstance(value, str) and value.strip() else None
            )
        if "access_methods" in fields:
            value = fields["access_methods"]
            if value is None:
                row.access_methods_json = None
            else:
                if not isinstance(value, list):
                    raise ValueError("access_methods must be a list of strings")
                row.access_methods_json = json.dumps(
                    [str(v).strip() for v in value if str(v).strip()]
                )
        if "region" in fields:
            value = fields["region"]
            row.region = (
                value.strip() if isinstance(value, str) and value.strip() else None
            )
        if "notes" in fields:
            value = fields["notes"]
            row.notes = value if isinstance(value, str) and value.strip() else None
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        session.commit()
        session.refresh(row)
        return _row_to_dict(row)
