"""Cost telemetry + quota enforcement + dashboard aggregator.

Public surface:

* :mod:`_meter` — per-query insert into ``data_product_query_cost``.
* :mod:`_quota` — current-day + current-hour aggregator that raises
  :class:`QuotaExceededError` in ``strict`` mode.
* :mod:`_rollup` — hourly scheduler executor that buckets the raw
  ledger into ``data_product_cost_buckets_hourly``.
* :mod:`_dashboard` — read-only aggregator for the mesh-dashboard
  routes (cost trends, per-domain, top consumers).
"""

from __future__ import annotations

from pointlessql.services.cost._bootstrap import (
    register_cost_hooks,
)
from pointlessql.services.cost._budget import (
    BudgetEvaluation,
    evaluate_budget,
)
from pointlessql.services.cost._chargeback import (
    ChargebackRow,
    CostRecord,
    pivot_by_consumer,
    pivot_by_product,
    pivot_by_workspace,
    to_csv,
)
from pointlessql.services.cost._dashboard import (
    cost_by_consumer,
    cost_by_product,
    mesh_health_full,
)
from pointlessql.services.cost._forecast import (
    CostForecast,
    forecast_breach,
)
from pointlessql.services.cost._meter import (
    MeterContext,
    record_query_cost,
)
from pointlessql.services.cost._quota import (
    QuotaCheck,
    check_quota,
    resolve_quota_mode,
)
from pointlessql.services.cost._rollup import (
    roll_up_hourly_buckets,
)

__all__ = [
    "BudgetEvaluation",
    "ChargebackRow",
    "CostForecast",
    "CostRecord",
    "MeterContext",
    "QuotaCheck",
    "check_quota",
    "cost_by_consumer",
    "cost_by_product",
    "evaluate_budget",
    "forecast_breach",
    "mesh_health_full",
    "pivot_by_consumer",
    "pivot_by_product",
    "pivot_by_workspace",
    "record_query_cost",
    "register_cost_hooks",
    "resolve_quota_mode",
    "roll_up_hourly_buckets",
    "to_csv",
]
