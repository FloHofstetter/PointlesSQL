"""Backend query timing primitive.

A single drop-in context manager, :func:`query_span`, that times a backend
query section and records it into the shared Prometheus registry as
``pointlessql_db_query_duration_seconds`` (labelled by logical operation and
backend engine).  Hot paths — audit FTS search, the lineage graph build, the
table-stats GROUP BY, query-history listing — wrap their DB calls in it so a
single dashboard shows where backend time is spent, independent of the HTTP
route that triggered the work.

The span is deliberately minimal: a ``perf_counter`` delta around a ``with``
block.  Instrumentation overhead is a couple of function calls plus one
histogram observation, well under a percent of any query worth measuring, so
it is always on (no feature flag) — matching the always-on philosophy of the
scheduler metrics in :mod:`pointlessql.services.metrics`.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from pointlessql.services import metrics


@contextmanager
def query_span(operation: str, backend: str) -> Iterator[None]:
    """Time the wrapped block and record it as a backend query observation.

    The duration is recorded even when the block raises, so a failing or
    timing-out query still shows up in the latency histogram rather than
    vanishing from the data.

    Args:
        operation: A stable logical name for the query
            (``audit_fts_search``, ``lineage_graph_build``, …).  Keep it
            low-cardinality — it becomes a Prometheus label.
        backend: The engine running the query (``sqlite`` / ``postgres`` /
            ``duckdb``).

    Yields:
        ``None`` — the context manager exposes no handle; it only times.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        metrics.record_db_query(operation, backend, time.perf_counter() - start)
