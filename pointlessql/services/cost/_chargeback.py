"""Chargeback reporting — pure pivots over cost records.

Aggregates per-query / per-bucket cost records into chargeback reports
pivoted by consumer, product, or workspace, with a CSV export helper.  The
functions are pure: they take an iterable of :class:`CostRecord` and return
the rollup, so the pivot logic is testable in isolation.  Reading the hourly
cost buckets out of the DB and exposing the reports over a route are the
caller's job (deferred — see the phase notes).

``estimated_cost`` is the project's EXPLAIN-derived cost *estimate* (a
unit-less heuristic, not currency); reports label it as cost units, never
dollars.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CostRecord:
    """One unit of attributed cost.

    Attributes:
        product_ref: The data product the cost is attributed to.
        consumer: The consumer (user email / principal) that incurred it.
        estimated_cost: The cost estimate (unit-less), as a Decimal.
        query_count: Number of queries this record rolls up.
    """

    product_ref: str
    consumer: str
    estimated_cost: Decimal
    query_count: int = 1


@dataclass(frozen=True)
class ChargebackRow:
    """One row of a chargeback pivot.

    Attributes:
        key: The pivot key (a consumer, product, or workspace label).
        estimated_cost: Total estimated cost for the key.
        query_count: Total query count for the key.
        breakdown: Secondary rollup (e.g. per-product within a consumer).
    """

    key: str
    estimated_cost: Decimal
    query_count: int
    breakdown: dict[str, Decimal]


def _pivot(
    records: Iterable[CostRecord],
    key: Callable[[CostRecord], str],
    sub: Callable[[CostRecord], str],
) -> list[ChargebackRow]:
    """Roll *records* up by ``key(record)`` with a ``sub(record)`` breakdown."""
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    counts: dict[str, int] = defaultdict(int)
    breakdowns: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    for record in records:
        k = key(record)
        totals[k] += record.estimated_cost
        counts[k] += record.query_count
        breakdowns[k][sub(record)] += record.estimated_cost
    rows = [
        ChargebackRow(
            key=k,
            estimated_cost=totals[k],
            query_count=counts[k],
            breakdown=dict(breakdowns[k]),
        )
        for k in totals
    ]
    rows.sort(key=lambda r: r.estimated_cost, reverse=True)
    return rows


def pivot_by_consumer(records: Iterable[CostRecord]) -> list[ChargebackRow]:
    """Chargeback pivoted by consumer, broken down by product."""
    return _pivot(records, key=lambda r: r.consumer, sub=lambda r: r.product_ref)


def pivot_by_product(records: Iterable[CostRecord]) -> list[ChargebackRow]:
    """Chargeback pivoted by product, broken down by consumer."""
    return _pivot(records, key=lambda r: r.product_ref, sub=lambda r: r.consumer)


def pivot_by_workspace(records: Iterable[CostRecord], workspace_ref: str) -> ChargebackRow:
    """Total chargeback for the whole workspace, broken down by product."""
    materialised = list(records)
    total = sum((r.estimated_cost for r in materialised), Decimal(0))
    count = sum(r.query_count for r in materialised)
    breakdown: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for record in materialised:
        breakdown[record.product_ref] += record.estimated_cost
    return ChargebackRow(
        key=workspace_ref,
        estimated_cost=total,
        query_count=count,
        breakdown=dict(breakdown),
    )


def to_csv(rows: list[ChargebackRow]) -> str:
    """Render chargeback rows as CSV (key, estimated_cost, query_count)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["key", "estimated_cost", "query_count"])
    for row in rows:
        writer.writerow([row.key, str(row.estimated_cost), row.query_count])
    return buffer.getvalue()
