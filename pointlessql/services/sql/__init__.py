"""SQL planner helpers — Sprint 13.1 EXPLAIN gate + cost estimator.

The Phase-12 SQL editor owns query *execution* (in
:mod:`pointlessql.api.sql_routes`); this package owns the
*ahead-of-execution* analysis the Sprint-13 agent loop needs:
parse + EXPLAIN + cost gate.

The seam is small on purpose.  Sprint 13.1 ships only the cost
estimator and the EXPLAIN runner — no UI, no enforcement.
Consumers are the Sprint 13.7 Hermes plugin (decides whether to
self-rewrite a costly query) and the Sprint 13.4 run-detail view
(surfaces ``cost_est`` in the filter bar).
"""

from __future__ import annotations

from pointlessql.services.sql.cost_estimator import (
    CostEstimate,
    estimate_cost,
)
from pointlessql.services.sql.explain import (
    ExplainResult,
    run_explain,
)

__all__ = [
    "CostEstimate",
    "ExplainResult",
    "estimate_cost",
    "run_explain",
]
