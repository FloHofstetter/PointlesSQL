"""Convert between the editable mesh-level canvas doc and DP input-port rows.

The mesh-canvas surface is a workspace-wide view: each node is a
data product in the workspace, each edge is one ``upstream_product``
:class:`DataProductInputPort` row (``source_ref`` carries the
upstream DP's ``catalog.schema`` ref).

Service goal: a side-effect-free *diff* between a desired
:class:`MeshCanvasDoc` and the current ``upstream_product`` rows in
the DB, then apply that diff via the existing port-CRUD helpers so
the route layer never touches ``DataProductInputPort`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from pointlessql.models import DataProduct, DataProductInputPort
from pointlessql.services.data_product_ports import (
    create_input_port,
    delete_input_port,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_EDGE_PORT_PREFIX = "mesh_edge_"
_UPSTREAM_KIND = "upstream_product"


class MeshCanvasNode(BaseModel):
    """One DP node on the mesh canvas.  Read-only at the route layer for now."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    dp_id: int
    ref: str
    position: dict[str, float] | None = None


class MeshCanvasEdge(BaseModel):
    """One ``upstream_product`` binding rendered as a wire on the canvas."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=80)
    source_dp_id: int
    target_dp_id: int


class MeshCanvasDoc(BaseModel):
    """Editable mesh-canvas envelope persisted via diff against DB rows."""

    model_config = ConfigDict(extra="ignore")

    nodes: list[MeshCanvasNode] = Field(default_factory=lambda: [])
    edges: list[MeshCanvasEdge] = Field(default_factory=lambda: [])


def _dp_ref(dp: DataProduct) -> str:
    return f"{dp.catalog_name}.{dp.schema_name}"


def build_mesh_canvas_doc(
    factory: sessionmaker[Session], *, workspace_id: int
) -> MeshCanvasDoc:
    """Snapshot the workspace's DPs + their upstream bindings as a canvas doc.

    Edge IDs are deterministic (``mesh_edge_<port_id>``) so the
    save-side diff can match round-tripped client docs against the
    DB rows they were derived from.
    """
    with factory() as session:
        dps = list(
            session.scalars(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            )
        )
        dp_ids = [dp.id for dp in dps] or [-1]
        ports = list(
            session.scalars(
                select(DataProductInputPort).where(
                    DataProductInputPort.kind == _UPSTREAM_KIND,
                    DataProductInputPort.data_product_id.in_(dp_ids),
                )
            )
        )
        ref_to_dp = {_dp_ref(dp): dp.id for dp in dps}
        nodes = [
            MeshCanvasNode(dp_id=dp.id, ref=_dp_ref(dp))
            for dp in dps
        ]
        edges: list[MeshCanvasEdge] = []
        for port in ports:
            if port.source_ref is None:
                continue
            upstream_id = ref_to_dp.get(port.source_ref)
            if upstream_id is None:
                continue
            edges.append(
                MeshCanvasEdge(
                    id=f"{_EDGE_PORT_PREFIX}{port.id}",
                    source_dp_id=upstream_id,
                    target_dp_id=port.data_product_id,
                )
            )
        return MeshCanvasDoc(nodes=nodes, edges=edges)


class MeshDiffSummary(BaseModel):
    """Counts the canvas-save route returns after applying the diff."""

    model_config = ConfigDict(extra="ignore")

    added: int = 0
    removed: int = 0
    skipped: list[str] = Field(default_factory=lambda: [])


def apply_mesh_canvas_doc(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    doc: MeshCanvasDoc,
    actor_user_id: int | None,
) -> MeshDiffSummary:
    """Apply *doc*'s edge set to the upstream-product port rows.

    Edges with deterministic ids matching the current DB rows are
    treated as no-ops; new edges create one ``upstream_product`` port
    on the target DP; missing edges trigger ``delete_input_port``.
    """
    current = build_mesh_canvas_doc(factory, workspace_id=workspace_id)
    current_ids = {edge.id for edge in current.edges}
    desired_ids = {edge.id for edge in doc.edges if edge.id.startswith(_EDGE_PORT_PREFIX)}

    summary = MeshDiffSummary()

    # Removed edges: any edge in current that's not in desired.
    to_remove_port_ids: list[tuple[int, int]] = []  # (data_product_id, port_id)
    for edge in current.edges:
        if edge.id in desired_ids:
            continue
        port_id_str = edge.id[len(_EDGE_PORT_PREFIX):]
        try:
            port_id = int(port_id_str)
        except ValueError:
            summary.skipped.append(f"malformed edge id {edge.id!r}")
            continue
        to_remove_port_ids.append((edge.target_dp_id, port_id))

    for (target_dp_id, port_id) in to_remove_port_ids:
        if delete_input_port(factory, data_product_id=target_dp_id, port_id=port_id):
            summary.removed += 1

    # Added edges: any new edge id (without _EDGE_PORT_PREFIX); ignored
    # if the source/target DP doesn't exist or the source-DP ref is
    # missing.
    with factory() as session:
        valid_dp_ids = {
            dp.id
            for dp in session.scalars(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            )
        }
        dps_by_id = {
            dp.id: dp
            for dp in session.scalars(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            )
        }

    next_seq = 1
    for edge in doc.edges:
        if edge.id in current_ids:
            continue
        if (
            edge.source_dp_id not in valid_dp_ids
            or edge.target_dp_id not in valid_dp_ids
        ):
            summary.skipped.append(
                f"edge {edge.id!r} references dp_id outside workspace"
            )
            continue
        upstream = dps_by_id.get(edge.source_dp_id)
        if upstream is None:
            summary.skipped.append(f"edge {edge.id!r} upstream dp missing")
            continue
        # Mint a unique-enough port name on the target DP.  Mesh
        # canvas treats all generated ports as anonymous wires, so the
        # name is purely a uniqueness handle.
        name = f"mesh_upstream_{edge.source_dp_id}_{next_seq}"
        next_seq += 1
        try:
            create_input_port(
                factory,
                data_product_id=edge.target_dp_id,
                name=name,
                kind=_UPSTREAM_KIND,
                source_ref=_dp_ref(upstream),
                description=f"Mesh-canvas binding from {_dp_ref(upstream)}",
                created_by_user_id=actor_user_id,
            )
            summary.added += 1
        except ValueError as exc:
            summary.skipped.append(f"edge {edge.id!r}: {exc}")

    return summary


def validate_mesh_canvas_doc(doc: MeshCanvasDoc) -> list[str]:
    """Return a list of human-readable issues with *doc* without DB access.

    Surfaces obvious shape problems — self-loops and duplicate edges
    — so the editor can highlight them before the save round-trip.
    """
    issues: list[str] = []
    seen: set[tuple[int, int]] = set()
    for edge in doc.edges:
        pair = (edge.source_dp_id, edge.target_dp_id)
        if edge.source_dp_id == edge.target_dp_id:
            issues.append(f"edge {edge.id!r} forms a self-loop on dp_id={edge.source_dp_id}")
        if pair in seen:
            issues.append(f"edge {edge.id!r} duplicates existing wire {pair}")
        seen.add(pair)
    return issues


__all__: list[str] = [
    "MeshCanvasDoc",
    "MeshCanvasEdge",
    "MeshCanvasNode",
    "MeshDiffSummary",
    "apply_mesh_canvas_doc",
    "build_mesh_canvas_doc",
    "validate_mesh_canvas_doc",
]


# Allow ``Any`` re-export for symmetry with sibling service modules.
_ = Any
