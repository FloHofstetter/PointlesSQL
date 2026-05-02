"""Focused model-lineage DAG builder ( + 21.7).

The model-detail Lineage tab does not reuse the run-detail
``build_lineage_graph`` because the audience and scope differ:

* Run-detail wants every row-edge + column-map for a run, with
  per-op grain.
* Model-detail wants the *coarse* picture — model-node in the
  middle, source-tables that trained it on the upstream side
  (``trained_from`` edges), prediction-tables it inferred into
  on the downstream side (``inferred_to`` edges, dashed).

added the downstream half:
:func:`aggregate_prediction_tables_for_model` queries
:class:`pointlessql.models.LineageRowEdge` for every row whose
``source_model_uri`` matches the model FQN, returning the distinct
target-tables together with their edge counts.  The new
``inferred_to`` edges share a single bidirectional graph with
the existing ``trained_from`` ones so the cytoscape renderer can
draw both halves in one call.

Implementation highlights:

* The list of agent-run-ids for the upstream half comes from the
  ``_pql_link`` markers on the model's versions (passed in by the
  caller; we don't re-walk soyuz here).
* For the downstream half we filter
  ``lineage_row_edges.source_model_uri LIKE 'models:/{fqn}/%'``,
  which matches every version of the registered model without
  requiring a per-version scan.  No column-pair expansion — this
  is a top-of-funnel summary.
* Result schema mirrors the run-detail builder's ``{nodes, edges}``
  shape so the cytoscape renderer can reuse the same code path.
* ``kind`` is set to ``"model"`` on the centre node, ``"table"`` on
  the upstream predecessors, and ``"prediction"`` on the
  downstream successors so the renderer can branch styling.

The function is sync (consumed by an async route via
``asyncio.to_thread``-friendly call sites) — keeps the SQLAlchemy
session usage straightforward.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from pointlessql.models import LineageRowEdge


def aggregate_source_tables_for_runs(
    factory: Callable[[], Session], agent_run_ids: Iterable[str]
) -> list[str]:
    """Return the distinct source-tables touched by the given runs.

    Args:
        factory: SQLAlchemy session factory bound to PointlesSQL's
            audit DB.
        agent_run_ids: Iterable of agent-run UUIDs.  Empty input
            yields an empty list without opening a session.

    Returns:
        list[str]: Sorted, de-duplicated FQN strings.
    """
    ids = [rid for rid in agent_run_ids if rid]
    if not ids:
        return []
    with factory() as session:
        stmt = select(distinct(LineageRowEdge.source_table)).where(
            LineageRowEdge.run_id.in_(ids),
            LineageRowEdge.source_table.isnot(None),
        )
        rows = session.execute(stmt).all()
    sources = sorted({row[0] for row in rows if row[0]})
    return sources


def aggregate_prediction_tables_for_model(
    factory: Callable[[], Session], model_full_name: str
) -> list[dict[str, Any]]:
    """Return distinct prediction-tables a registered model wrote into.

    Args:
        factory: SQLAlchemy session factory bound to PointlesSQL's
            audit DB.
        model_full_name: Three-level FQN ``catalog.schema.model``.
            Matched against ``source_model_uri`` with the
            ``models:/{fqn}/%`` prefix so any version of the model
            counts.

    Returns:
        A list of ``{"target_table": str, "edge_count": int}``
        dicts sorted by target FQN.  Empty list when no inference
        edges have been recorded yet.
    """
    if not model_full_name:
        return []
    prefix = f"models:/{model_full_name}/%"
    with factory() as session:
        stmt = (
            select(
                LineageRowEdge.target_table,
                func.count(LineageRowEdge.id).label("edge_count"),
            )
            .where(LineageRowEdge.source_model_uri.like(prefix))
            .group_by(LineageRowEdge.target_table)
            .order_by(LineageRowEdge.target_table)
        )
        rows = session.execute(stmt).all()
    return [
        {"target_table": row[0], "edge_count": int(row[1])}
        for row in rows
        if row[0]
    ]


def build_model_lineage_graph(
    factory: Callable[[], Session],
    *,
    model_full_name: str,
    agent_run_ids: list[str],
) -> dict[str, Any]:
    """Build the bidirectional ``{nodes, edges}`` payload for a model.

    Sources upstream (``trained_from`` solid edges) +
    prediction-tables downstream (``inferred_to`` dashed edges).

    Args:
        factory: SQLAlchemy session factory.
        model_full_name: Three-level FQN of the registered model.
        agent_run_ids: Hermes agent-run UUIDs cross-linked to any
            version of the model.

    Returns:
        ``{"model_full_name", "nodes", "edges"}`` — the model
        node's id is the FQN; both predecessor and successor table
        nodes carry the same id-as-fqn convention as the run-detail
        graph.  Each successor node carries an ``edge_count`` field
        so the UI can show "N predictions / 32 rows".
    """
    sources = aggregate_source_tables_for_runs(factory, agent_run_ids)
    predictions = aggregate_prediction_tables_for_model(factory, model_full_name)

    nodes: list[dict[str, Any]] = [
        {
            "id": model_full_name,
            "kind": "model",
            "type": "model",
            "label": model_full_name.split(".")[-1] or model_full_name,
        }
    ]
    edges: list[dict[str, Any]] = []

    for src in sources:
        nodes.append(
            {
                "id": src,
                "kind": "table",
                "type": "table",
                "label": src.split(".")[-1] or src,
            }
        )
        edges.append(
            {
                "id": f"{src}__{model_full_name}",
                "source": src,
                "target": model_full_name,
                "label": "trained_from",
            }
        )

    for entry in predictions:
        target = entry["target_table"]
        # Avoid clobbering a pre-existing source node when a table is
        # both consumed and produced (rare but legal).
        if target == model_full_name or any(n["id"] == target for n in nodes):
            continue
        nodes.append(
            {
                "id": target,
                "kind": "prediction",
                "type": "prediction",
                "label": target.split(".")[-1] or target,
                "edge_count": entry["edge_count"],
            }
        )
        edges.append(
            {
                "id": f"{model_full_name}__{target}",
                "source": model_full_name,
                "target": target,
                "label": "inferred_to",
            }
        )

    return {
        "model_full_name": model_full_name,
        "nodes": nodes,
        "edges": edges,
    }
