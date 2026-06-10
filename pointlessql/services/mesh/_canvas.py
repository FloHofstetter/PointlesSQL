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

from pointlessql.models import DataProduct, DataProductInputPort, Workspace
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
    workspace_slug: str | None = None


class MeshCanvasEdge(BaseModel):
    """One ``upstream_product`` binding rendered as a wire on the canvas."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=80)
    source_dp_id: int
    target_dp_id: int
    source_workspace_slug: str | None = None


class MeshCanvasDoc(BaseModel):
    """Editable mesh-canvas envelope persisted via diff against DB rows."""

    model_config = ConfigDict(extra="ignore")

    nodes: list[MeshCanvasNode] = Field(default_factory=lambda: [])
    edges: list[MeshCanvasEdge] = Field(default_factory=lambda: [])


def _dp_ref(dp: DataProduct) -> str:
    return f"{dp.catalog_name}.{dp.schema_name}"


def build_mesh_canvas_doc(factory: sessionmaker[Session], *, workspace_id: int) -> MeshCanvasDoc:
    """Snapshot the workspace's DPs + their upstream bindings as a canvas doc.

    Edge IDs are deterministic (``mesh_edge_<port_id>``) so the
    save-side diff can match round-tripped client docs against the
    DB rows they were derived from.

    Cross-workspace upstreams (``source_workspace_id`` non-null on
    the port) appear as additional ghost nodes carrying the foreign
    workspace's slug so the renderer can distinguish them.
    """
    with factory() as session:
        dps = list(
            session.scalars(select(DataProduct).where(DataProduct.workspace_id == workspace_id))
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
        nodes: list[MeshCanvasNode] = [MeshCanvasNode(dp_id=dp.id, ref=_dp_ref(dp)) for dp in dps]
        cross_ws_ports = [p for p in ports if p.source_workspace_id is not None]
        cross_ws_ids = {p.source_workspace_id for p in cross_ws_ports}
        ws_by_id: dict[int, Workspace] = {}
        if cross_ws_ids:
            for ws in session.scalars(select(Workspace).where(Workspace.id.in_(cross_ws_ids))):
                ws_by_id[ws.id] = ws
        cross_ws_refs: dict[tuple[int, str], int] = {}
        next_ghost_id = -1
        for port in cross_ws_ports:
            if port.source_ref is None or port.source_workspace_id is None:
                continue
            ws = ws_by_id.get(port.source_workspace_id)
            if ws is None:
                continue
            key = (port.source_workspace_id, port.source_ref)
            if key in cross_ws_refs:
                continue
            cross_ws_refs[key] = next_ghost_id
            nodes.append(
                MeshCanvasNode(
                    dp_id=next_ghost_id,
                    ref=port.source_ref,
                    workspace_slug=ws.slug,
                )
            )
            next_ghost_id -= 1
        edges: list[MeshCanvasEdge] = []
        for port in ports:
            if port.source_ref is None:
                continue
            if port.source_workspace_id is not None:
                ws = ws_by_id.get(port.source_workspace_id)
                if ws is None:
                    continue
                ghost_id = cross_ws_refs.get((port.source_workspace_id, port.source_ref))
                if ghost_id is None:
                    continue
                edges.append(
                    MeshCanvasEdge(
                        id=f"{_EDGE_PORT_PREFIX}{port.id}",
                        source_dp_id=ghost_id,
                        target_dp_id=port.data_product_id,
                        source_workspace_slug=ws.slug,
                    )
                )
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
        port_id_str = edge.id[len(_EDGE_PORT_PREFIX) :]
        try:
            port_id = int(port_id_str)
        except ValueError:
            summary.skipped.append(f"malformed edge id {edge.id!r}")
            continue
        to_remove_port_ids.append((edge.target_dp_id, port_id))

    for target_dp_id, port_id in to_remove_port_ids:
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
        if edge.target_dp_id not in valid_dp_ids:
            summary.skipped.append(f"edge {edge.id!r} target dp_id outside workspace")
            continue
        if edge.source_workspace_slug:
            cross_added = _apply_cross_workspace_edge(
                factory,
                edge=edge,
                actor_user_id=actor_user_id,
                next_seq=next_seq,
                summary=summary,
            )
            if cross_added:
                next_seq += 1
            continue
        if edge.source_dp_id not in valid_dp_ids:
            summary.skipped.append(f"edge {edge.id!r} source dp_id outside workspace")
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


def _apply_cross_workspace_edge(
    factory: sessionmaker[Session],
    *,
    edge: MeshCanvasEdge,
    actor_user_id: int | None,
    next_seq: int,
    summary: MeshDiffSummary,
) -> bool:
    """Look up the foreign workspace + create a cross-workspace input-port row.

    Returns True when a port was created, False on any validation
    failure (the per-edge skip is appended to *summary.skipped*).
    """
    with factory() as session:
        ws_row = session.scalar(
            select(Workspace).where(Workspace.slug == edge.source_workspace_slug)
        )
        if ws_row is None:
            summary.skipped.append(
                f"edge {edge.id!r} unknown source workspace {edge.source_workspace_slug!r}"
            )
            return False
        upstream = session.get(DataProduct, edge.source_dp_id)
        if upstream is None or upstream.workspace_id != ws_row.id:
            summary.skipped.append(
                f"edge {edge.id!r} upstream dp not in workspace {edge.source_workspace_slug!r}"
            )
            return False
        ref = _dp_ref(upstream)
        source_workspace_id = ws_row.id
    name = f"mesh_xws_{edge.source_dp_id}_{next_seq}"
    try:
        create_input_port(
            factory,
            data_product_id=edge.target_dp_id,
            name=name,
            kind=_UPSTREAM_KIND,
            source_ref=ref,
            source_workspace_id=source_workspace_id,
            description=(
                f"Mesh-canvas cross-workspace binding from {edge.source_workspace_slug}:{ref}"
            ),
            created_by_user_id=actor_user_id,
        )
        summary.added += 1
        return True
    except ValueError as exc:
        summary.skipped.append(f"edge {edge.id!r}: {exc}")
        return False


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
