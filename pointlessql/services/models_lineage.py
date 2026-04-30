"""Focused model-lineage DAG builder (Phase 21.5.5).

The model-detail Lineage tab does not reuse the run-detail
``build_lineage_graph`` because the audience and scope differ:

* Run-detail wants every row-edge + column-map for a run, with
  per-op grain.
* Model-detail wants the *coarse* picture — model-node in the
  middle, source-tables consumed by the linked Hermes-runs as
  predecessors, edges labelled ``trained_from``.

Implementation highlights:

* The list of agent-run-ids comes from the ``_pql_link`` markers on
  the model's versions (passed in by the caller; we don't re-walk
  soyuz here).
* For each run-id we read the distinct ``source_table`` values from
  :class:`pointlessql.models.LineageRowEdge`.  No column-pair
  expansion — this is a top-of-funnel summary.
* Result schema mirrors the run-detail builder's ``{nodes, edges}``
  shape so the cytoscape renderer can reuse the same code path.
* ``type`` is set to ``"model"`` on the centre node and ``"table"``
  on the predecessors so the renderer can branch styling.

The function is sync (consumed by an async route via
``asyncio.to_thread``-friendly call sites) — keeps the SQLAlchemy
session usage straightforward.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import distinct, select
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


def build_model_lineage_graph(
    factory: Callable[[], Session],
    *,
    model_full_name: str,
    agent_run_ids: list[str],
) -> dict[str, Any]:
    """Build the focused ``{nodes, edges}`` payload for a model.

    Args:
        factory: SQLAlchemy session factory.
        model_full_name: Three-level FQN of the registered model.
        agent_run_ids: Hermes agent-run UUIDs cross-linked to any
            version of the model.

    Returns:
        ``{"model_full_name", "nodes", "edges"}`` — the model
        node's id is the FQN; predecessor table nodes carry the
        same id-as-fqn convention as the run-detail graph.
    """
    sources = aggregate_source_tables_for_runs(factory, agent_run_ids)

    nodes: list[dict[str, Any]] = [
        {
            "id": model_full_name,
            "type": "model",
            "label": model_full_name.split(".")[-1] or model_full_name,
        }
    ]
    for src in sources:
        nodes.append(
            {
                "id": src,
                "type": "table",
                "label": src.split(".")[-1] or src,
            }
        )

    edges: list[dict[str, Any]] = [
        {
            "id": f"{src}__{model_full_name}",
            "source": src,
            "target": model_full_name,
            "label": "trained_from",
        }
        for src in sources
    ]

    return {
        "model_full_name": model_full_name,
        "nodes": nodes,
        "edges": edges,
    }
