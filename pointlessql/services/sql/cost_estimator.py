"""Heuristic cost estimator for DuckDB ``EXPLAIN (FORMAT JSON)`` plans.

The estimator is intentionally simple — its job is to say "this
query will scan a lot of rows, ask a human" before an agent fires
off a multi-hour join.  A precise cost model is the wrong
investment; a defensible cardinality × join-depth heuristic is
enough to gate the obvious blow-ups while staying explainable to
the agent (which can read the same plan and decide whether to
rewrite).

The walker is defensive: DuckDB's plan JSON shape has shifted
across releases (``estimated_cardinality`` vs ``cardinality``,
nested ``children`` vs ``__children__``).  We look up multiple
candidate keys and tolerate missing ones rather than hard-coding
a single schema version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

_CARDINALITY_KEYS: tuple[str, ...] = (
    "estimated_cardinality",
    "cardinality",
    "rows",
)

# DuckDB 1.x stores cardinality in nested ``extra_info`` under a
# space-and-capitalised key.  The walker checks both spellings —
# the synthetic-plan unit test uses ``estimated_cardinality`` at
# the node root, but real DuckDB EXPLAIN output uses
# ``extra_info["Estimated Cardinality"]`` as a string.
_CARDINALITY_EXTRA_INFO_KEYS: tuple[str, ...] = (
    "Estimated Cardinality",
    "Cardinality",
)
_CHILDREN_KEYS: tuple[str, ...] = (
    "children",
    "__children__",
)
_JOIN_NODE_HINT = "JOIN"


@dataclass(frozen=True)
class CostEstimate:
    """Output of :func:`estimate_cost` for one EXPLAIN plan.

    ``max_cardinality`` is the largest single-node estimated row
    count anywhere in the plan tree — usually a leaf scan or a
    cartesian-cross intermediate.  ``join_depth`` is the count of
    join nodes encountered (any plan node whose ``name`` contains
    ``JOIN``).  ``cost`` is the headline number callers gate on:
    ``max_cardinality × (1 + join_depth)``.

    The dataclass is frozen so callers can stash it on a request
    object without worrying about mutation later in the pipeline.
    """

    max_cardinality: int
    join_depth: int
    cost: int

    @property
    def explanation(self) -> str:
        """Render a one-line, agent-readable explanation of the cost.

        Returns:
            str: A short sentence the EXPLAIN endpoint can echo into
                its JSON response so the agent can paraphrase it
                back to the human reviewer.
        """
        return (
            f"max_cardinality={self.max_cardinality:,} × "
            f"(1 + join_depth={self.join_depth}) = cost={self.cost:,}"
        )


def estimate_cost(plan_json: Any) -> CostEstimate:
    """Walk a DuckDB EXPLAIN plan and compute the heuristic cost.

    Accepts either the parsed JSON object DuckDB returns from
    ``EXPLAIN (FORMAT JSON)`` (a dict with at least a ``name`` and
    optionally ``children``) or a list of such dicts (DuckDB
    sometimes wraps the root in a single-element array).

    Walks the tree once, tracking:

    * the maximum ``estimated_cardinality`` (or ``cardinality`` /
      ``rows``) seen on any node,
    * the count of nodes whose ``name`` contains the substring
      ``JOIN``.

    Returns the :class:`CostEstimate` with ``cost = max_cardinality
    × (1 + join_depth)``.  An empty / missing plan produces
    ``CostEstimate(0, 0, 0)`` so callers always have a defined
    contract.

    Args:
        plan_json: The parsed plan, as a dict or list of dicts.
            ``None`` and other types collapse to a zero estimate.

    Returns:
        CostEstimate: Heuristic cardinality, join depth, and cost.
    """
    max_cardinality = 0
    join_depth = 0

    stack: list[Any] = []
    if isinstance(plan_json, list):
        stack.extend(cast(list[Any], plan_json))
    elif isinstance(plan_json, dict):
        stack.append(plan_json)

    while stack:
        node_any = stack.pop()
        if not isinstance(node_any, dict):
            continue
        node = cast(dict[str, Any], node_any)

        name = node.get("name", "")
        if isinstance(name, str) and _JOIN_NODE_HINT in name.upper():
            join_depth += 1

        node_cardinality: int | None = None
        for key in _CARDINALITY_KEYS:
            raw = node.get(key)
            if raw is None:
                continue
            try:
                node_cardinality = int(raw)
            except (TypeError, ValueError):
                continue
            break

        if node_cardinality is None:
            extra = node.get("extra_info")
            if isinstance(extra, dict):
                extra_dict = cast(dict[str, Any], extra)
                for key in _CARDINALITY_EXTRA_INFO_KEYS:
                    raw_extra = extra_dict.get(key)
                    if raw_extra is None:
                        continue
                    try:
                        node_cardinality = int(str(raw_extra).strip())
                    except (TypeError, ValueError):
                        continue
                    break

        if node_cardinality is not None and node_cardinality > max_cardinality:
            max_cardinality = node_cardinality

        for key in _CHILDREN_KEYS:
            children = node.get(key)
            if isinstance(children, list):
                stack.extend(cast(list[Any], children))
                break

    cost = max_cardinality * (1 + join_depth)
    return CostEstimate(
        max_cardinality=max_cardinality,
        join_depth=join_depth,
        cost=cost,
    )
