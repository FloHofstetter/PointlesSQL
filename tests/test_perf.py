"""The backend query-timing primitive records, and the hot paths use it.

``query_span`` was dead code — defined but never called, so its histogram
``pointlessql_db_query_duration_seconds`` stayed permanently empty. These
tests pin that the span records on both the success and the raising path,
that ``backend_label`` normalises the dialect to the metric's label set,
and that a real instrumented hot path (query-history listing) actually
advances the histogram.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pointlessql.api.main import app
from pointlessql.services import metrics, query_history
from pointlessql.services.perf import backend_label, query_span


def _count(operation: str, backend: str) -> float:
    """Return the histogram's observation count for one label pair.

    Read off the public ``collect()`` exposition (the ``_count`` sample)
    rather than a private child attribute, so it stays valid regardless of
    prometheus_client's internal histogram representation.
    """
    for metric in metrics.db_query_duration_seconds.collect():
        for sample in metric.samples:
            if (
                sample.name.endswith("_count")
                and sample.labels.get("operation") == operation
                and sample.labels.get("backend") == backend
            ):
                return sample.value
    return 0.0


def _fake_session(dialect_name: str) -> Any:
    """A duck-typed session whose bound engine reports *dialect_name*."""
    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
    return SimpleNamespace(get_bind=lambda: bind)


def test_query_span_records_on_success() -> None:
    """A clean block adds one observation to the histogram."""
    before = _count("unit_probe", "sqlite")
    with query_span("unit_probe", "sqlite"):
        pass
    assert _count("unit_probe", "sqlite") == before + 1


def test_query_span_records_on_raise() -> None:
    """A raising block still records — failures must not vanish from latency."""
    before = _count("unit_probe_raise", "sqlite")
    with pytest.raises(RuntimeError):  # noqa: SIM117 — assert the span re-raises
        with query_span("unit_probe_raise", "sqlite"):
            raise RuntimeError("boom")
    assert _count("unit_probe_raise", "sqlite") == before + 1


def test_backend_label_normalises_postgres() -> None:
    """SQLAlchemy's ``postgresql`` dialect maps to the ``postgres`` label."""
    assert backend_label(_fake_session("postgresql")) == "postgres"


def test_backend_label_passes_other_dialects_through() -> None:
    """A real sqlite session reports the ``sqlite`` label unchanged."""
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        assert backend_label(session) == "sqlite"


def test_list_queries_bumps_db_query_histogram() -> None:
    """The query-history listing hot path advances the histogram."""
    factory = app.state.session_factory
    with factory() as session:
        backend = backend_label(session)
    before = _count("query_history_list", backend)
    query_history.list_queries(factory, limit=10)
    assert _count("query_history_list", backend) == before + 1
