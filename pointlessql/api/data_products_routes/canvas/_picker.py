"""DP-picker route: the dropdown feed for the DataProduct compound block."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes.canvas._schemas import (
    DataProductPickerEntry,
    DataProductPickerResponse,
)
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.models import DataProduct, DataProductOutputPort

router = APIRouter(prefix="/api/dp", tags=["data-products-canvas"])


@router.get("/_picker", response_model=DataProductPickerResponse)
def list_dp_picker(request: Request) -> DataProductPickerResponse:
    """Return DPs in the active workspace plus their output ports.

    Powers the DataProduct compound-block's config-form dropdown so
    the user can pick which upstream DP + which port to wire in.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        dps = (
            session.execute(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            )
            .scalars()
            .all()
        )
        ports = (
            session.execute(
                select(DataProductOutputPort).where(
                    DataProductOutputPort.data_product_id.in_([dp.id for dp in dps] or [-1])
                )
            )
            .scalars()
            .all()
        )
    ports_by_dp: dict[int, list[dict[str, Any]]] = {}
    for port in ports:
        ports_by_dp.setdefault(port.data_product_id, []).append(
            {
                "name": port.name,
                "kind": port.kind,
                "location": port.location,
            }
        )
    return DataProductPickerResponse(
        data_products=[
            DataProductPickerEntry(
                dp_id=dp.id,
                catalog=dp.catalog_name,
                schema_name=dp.schema_name,
                ref=f"{dp.catalog_name}.{dp.schema_name}",
                output_ports=ports_by_dp.get(dp.id, []),
            )
            for dp in dps
        ]
    )
