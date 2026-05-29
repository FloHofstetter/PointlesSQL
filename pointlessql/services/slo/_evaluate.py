"""SLO evaluation — verdicts from data the platform already holds.

For each declared objective (plus the implicit freshness objective the
product's ``sla_minutes`` encodes), this module computes a verdict:

* ``pass`` / ``fail`` for the measurable kinds — freshness (lag of the
  latest self-generated statistics snapshot), volume (row count),
  completeness (non-null fraction), statistical_shape (drift sigma), and
  lineage (whether inputs are declared);
* ``unmeasured`` for declaration-only kinds (precision/accuracy,
  availability, performance) and for any objective missing a threshold.

No Delta IO: everything derives from the statistics snapshots + declared
ports, so evaluation is cheap and unit-testable.
"""

from __future__ import annotations

import datetime
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    DataProductInputPort,
)
from pointlessql.services.data_product_stats import read_latest_statistics
from pointlessql.services.slo._crud import list_slos
from pointlessql.services.slo._drift import compute_drift, max_drift_sigma
from pointlessql.services.slo._kinds import KIND_META


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


def _verdict(observed: float | None, target: float | None, comparator: str) -> str:
    """Return ``pass`` / ``fail`` / ``unmeasured`` for one comparison."""
    if observed is None or target is None:
        return "unmeasured"
    if comparator == "lte":
        return "pass" if observed <= target else "fail"
    if comparator == "gte":
        return "pass" if observed >= target else "fail"
    return "pass" if observed == target else "fail"


def _completeness_pct(entry: dict[str, Any]) -> float | None:
    """Return the non-null percentage of a statistics snapshot, or ``None``."""
    row_count = entry.get("row_count")
    shape = entry.get("shape") or {}
    columns = shape.get("columns", {}) if isinstance(shape, dict) else {}
    if not row_count or not columns:
        return None
    total_cells = row_count * len(columns)
    if total_cells == 0:
        return None
    total_nulls = sum(
        c.get("null_count", 0) for c in columns.values() if isinstance(c, dict)
    )
    return max(0.0, (1.0 - total_nulls / total_cells) * 100.0)


def _stats_for(stats: list[dict[str, Any]], table_name: str | None) -> list[dict[str, Any]]:
    """Return the stats entries the objective scopes to."""
    if table_name is None:
        return stats
    return [e for e in stats if e.get("table_name") == table_name]


def _observe_measurable(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    slo_kind: str,
    table_name: str | None,
    stats: list[dict[str, Any]],
    has_inputs: bool,
    sigma: float,
) -> float | None:
    """Return the observed value for a measurable kind, or ``None``.

    ``None`` means "cannot measure yet" (no statistics) → ``unmeasured``.
    """
    scoped = _stats_for(stats, table_name)
    if slo_kind == "freshness":
        lags = [
            e["freshness_lag_minutes"]
            for e in scoped
            if e.get("freshness_lag_minutes") is not None
        ]
        return float(max(lags)) if lags else None
    if slo_kind == "volume":
        counts = [e["row_count"] for e in scoped if e.get("row_count") is not None]
        return float(min(counts)) if counts else None
    if slo_kind == "completeness":
        pcts = [p for e in scoped if (p := _completeness_pct(e)) is not None]
        return min(pcts) if pcts else None
    if slo_kind == "statistical_shape":
        tables = (
            [table_name]
            if table_name is not None
            else [e["table_name"] for e in stats if e.get("table_name")]
        )
        worst = 0.0
        measured = False
        for tbl in tables:
            drift = compute_drift(
                session_factory,
                data_product_id=data_product_id,
                table_name=str(tbl),
                sigma=sigma,
            )
            if drift["measured"]:
                measured = True
                worst = max(worst, max_drift_sigma(drift))
        return worst if measured else None
    if slo_kind == "lineage":
        return 100.0 if has_inputs else 0.0
    return None


def evaluate_product(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    now: datetime.datetime | None = None,
    sigma: float = 2.0,
) -> dict[str, Any]:
    """Evaluate every objective on a product and roll up a pass rate.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product to evaluate.
        now: Reference instant for freshness lag (defaults to UTC now).
        sigma: z-score threshold for the statistical-shape verdict.

    Returns:
        ``{"data_product_id", "results": [...], "passed", "failed",
        "unmeasured", "pass_rate"}`` where each result is
        ``{slo_kind, table, target, comparator, unit, observed, verdict,
        source, measurable}``.
    """
    with session_factory() as session:
        product = session.get(DataProduct, data_product_id)
        sla_minutes = product.sla_minutes if product is not None else None
        has_inputs = (
            session.scalar(
                select(DataProductInputPort.id)
                .where(DataProductInputPort.data_product_id == data_product_id)
                .limit(1)
            )
            is not None
        )

    stats = read_latest_statistics(session_factory, data_product_id=data_product_id, now=now)
    declared = list_slos(session_factory, data_product_id=data_product_id)

    results: list[dict[str, Any]] = []
    has_declared_freshness = any(s.slo_kind == "freshness" for s in declared)

    # Implicit freshness objective from sla_minutes (when not overridden
    # by an explicit declared freshness SLO).
    if sla_minutes is not None and not has_declared_freshness:
        observed = _observe_measurable(
            session_factory,
            data_product_id=data_product_id,
            slo_kind="freshness",
            table_name=None,
            stats=stats,
            has_inputs=has_inputs,
            sigma=sigma,
        )
        results.append(
            {
                "slo_kind": "freshness",
                "table": None,
                "target": float(sla_minutes),
                "comparator": "lte",
                "unit": "minutes",
                "observed": observed,
                "verdict": _verdict(observed, float(sla_minutes), "lte"),
                "source": "implicit_freshness",
                "measurable": True,
            }
        )

    for slo in declared:
        if not slo.enabled:
            continue
        measurable = bool(KIND_META.get(slo.slo_kind, {}).get("measurable"))
        observed = (
            _observe_measurable(
                session_factory,
                data_product_id=data_product_id,
                slo_kind=slo.slo_kind,
                table_name=slo.table_name,
                stats=stats,
                has_inputs=has_inputs,
                sigma=sigma,
            )
            if measurable
            else None
        )
        verdict = (
            _verdict(observed, slo.target_value, slo.comparator)
            if measurable
            else "unmeasured"
        )
        results.append(
            {
                "slo_kind": slo.slo_kind,
                "table": slo.table_name,
                "target": slo.target_value,
                "comparator": slo.comparator,
                "unit": slo.unit,
                "observed": observed,
                "verdict": verdict,
                "source": "declared",
                "measurable": measurable,
            }
        )

    passed = sum(1 for r in results if r["verdict"] == "pass")
    failed = sum(1 for r in results if r["verdict"] == "fail")
    unmeasured = sum(1 for r in results if r["verdict"] == "unmeasured")
    scored = passed + failed
    return {
        "data_product_id": data_product_id,
        "results": results,
        "passed": passed,
        "failed": failed,
        "unmeasured": unmeasured,
        "pass_rate": (passed / scored) if scored else None,
    }
