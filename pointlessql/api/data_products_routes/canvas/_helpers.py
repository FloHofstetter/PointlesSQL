"""Shared helpers for the visual data-product canvas routes.

Authorisation, DP resolution, the raw soyuz client accessor, and the two
document pre-passes (resolve ``DataProduct`` block references; seed
``InputPort`` / ``DataProduct`` schemas from UC) the validate, preview,
materialise and save handlers all lean on.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from soyuz_catalog_client import Client as SoyuzClient
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_uc_client
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogUnavailableError,
    ResourceNotFoundError,
)
from pointlessql.models import DataProduct, DataProductOutputPort
from pointlessql.services.dp_canvas import (
    CanvasDoc,
    CompileError,
    PinSchema,
    fetch_table_info,
    table_info_to_pin_schema,
)


def load_dp(request: Request, dp_id: int) -> DataProduct:
    """Resolve *dp_id* in the active workspace; raise 404 otherwise."""
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(DataProduct, dp_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError(f"data product id={dp_id} not found")
        session.expunge(row)
        return row


def require_dp_write(user: Any, row: DataProduct) -> None:
    """Raise :class:`AuthorizationError` unless the caller may edit *row*."""
    is_steward = row.steward_user_id is not None and row.steward_user_id == user["id"]
    is_admin = bool(user.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="canvas-write",
            securable_type="data_product",
            full_name=f"{row.catalog_name}.{row.schema_name}",
        )


def raw_soyuz_client(request: Request) -> SoyuzClient:
    """Return the per-request raw ``soyuz_catalog_client.Client``.

    The visual canvas executor + validator both consume the generated
    client directly because they make sync calls inside DuckDB
    materialise loops where the async facade would force an event-loop
    hop on every base-table lookup.
    """
    uc = get_uc_client(request)
    return uc._client  # pyright: ignore[reportPrivateUsage]


def resolve_dp_refs(request: Request, doc: CanvasDoc) -> CanvasDoc:
    """Walk every ``DataProduct`` block and fill ``materialized_table``.

    The editor stores ``dp_id`` + ``port_name`` on the block; the
    compiler reads the resolved 3-part FQN.  Doing the lookup here on
    save (and re-doing it on validate / materialise) means the
    compile path stays pure and a rename of the upstream port can be
    surfaced at edit-time without rewriting saved docs.
    """
    factory = request.app.state.session_factory
    needs = [
        (n, int(n.config.get("dp_id", 0) or 0), str(n.config.get("port_name") or "").strip())
        for n in doc.nodes
        if n.block_type == "DataProduct"
    ]
    if not needs:
        return doc
    targets: dict[tuple[int, str], str] = {}
    with factory() as session:
        for _node, dp_id, port_name in needs:
            if dp_id <= 0 or not port_name:
                continue
            key = (dp_id, port_name)
            if key in targets:
                continue
            row = session.execute(
                select(DataProductOutputPort).where(
                    DataProductOutputPort.data_product_id == dp_id,
                    DataProductOutputPort.name == port_name,
                )
            ).scalar_one_or_none()
            if row is None or not row.location:
                continue
            targets[key] = row.location
    updated_nodes = []
    for node in doc.nodes:
        if node.block_type != "DataProduct":
            updated_nodes.append(node)
            continue
        dp_id = int(node.config.get("dp_id", 0) or 0)
        port_name = str(node.config.get("port_name") or "").strip()
        resolved = targets.get((dp_id, port_name))
        if resolved:
            new_cfg = {**node.config, "materialized_table": resolved}
            updated_nodes.append(node.model_copy(update={"config": new_cfg}))
        else:
            updated_nodes.append(node)
    return doc.model_copy(update={"nodes": updated_nodes})


def seed_schemas_for_doc(
    doc: CanvasDoc, client: SoyuzClient
) -> tuple[dict[str, PinSchema], list[CompileError]]:
    """Resolve every InputPort + DataProduct source FQN to a ``PinSchema`` via soyuz.

    Returns a ``(seeds, errors)`` tuple; errors carry ``bad_config`` kind
    so the editor surfaces them on the offending node.
    """
    seeds: dict[str, PinSchema] = {}
    errors: list[CompileError] = []
    for node in doc.nodes:
        if node.block_type == "InputPort":
            fqn_key = "table_fqn"
        elif node.block_type == "DataProduct":
            fqn_key = "materialized_table"
        else:
            continue
        fqn = str(node.config.get(fqn_key) or "").strip()
        if not fqn:
            continue
        try:
            info = fetch_table_info(client, fqn)
        except CatalogUnavailableError:
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node.id,
                    pin="out",
                    message=f"soyuz-catalog unreachable while resolving {fqn!r}",
                )
            )
            continue
        if info is None:
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node.id,
                    pin="out",
                    message=f"table {fqn!r} not registered in UC",
                )
            )
            continue
        seeds[node.id] = table_info_to_pin_schema(info)
    return seeds, errors
