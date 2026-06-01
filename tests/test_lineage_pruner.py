"""Unit tests for the lineage retention pruner.

``prune_once`` deletes lineage rows older than per-axis day thresholds and
returns ``{axis: deleted_count}`` for the axes that ran. The settings
object is a light stand-in exposing only ``audit.lineage_retention`` — the
pruner reads four day-count attributes off it — so the tests can drive
each threshold (a positive cutoff, ``None`` = never, ``0`` = skip) without
mutating real configuration.
"""

from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select

from pointlessql.api.main import app
from pointlessql.models import LineageRowEdge
from pointlessql.services.lineage.pruner import prune_once

_NOW = _dt.datetime(2026, 6, 1, tzinfo=_dt.UTC)


def _settings(
    *,
    row_edges_days: int | None = None,
    row_rejects_days: int | None = None,
    column_map_days: int | None = None,
    value_changes_days: int | None = None,
) -> Any:
    """Build a stand-in settings object with only the retention sub-tree."""
    return SimpleNamespace(
        audit=SimpleNamespace(
            lineage_retention=SimpleNamespace(
                row_edges_days=row_edges_days,
                row_rejects_days=row_rejects_days,
                column_map_days=column_map_days,
                value_changes_days=value_changes_days,
            )
        )
    )


def _add_row_edge(run_id: str, age_days: int) -> None:
    """Insert one row edge whose ``created_at`` is *age_days* before ``_NOW``."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=1,
                source_table="cat.sch.src",
                source_row_id="r1",
                target_table="cat.sch.tgt",
                target_row_id="r1",
                created_at=_NOW - _dt.timedelta(days=age_days),
            )
        )
        session.commit()


def _count_edges(run_id: str) -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(LineageRowEdge).where(
                    LineageRowEdge.run_id == run_id
                )
            )
            or 0
        )


def test_prune_deletes_only_rows_older_than_threshold() -> None:
    run_id = "prune-mixed"
    _add_row_edge(run_id, age_days=400)  # older than 365 → deleted
    _add_row_edge(run_id, age_days=10)  # newer → kept
    deleted = prune_once(
        app.state.session_factory,
        _settings(row_edges_days=365),
        now=_NOW,
    )
    assert deleted == {"row_edges": 1}
    assert _count_edges(run_id) == 1


def test_threshold_none_skips_axis_entirely() -> None:
    run_id = "prune-none"
    _add_row_edge(run_id, age_days=1000)
    deleted = prune_once(
        app.state.session_factory,
        _settings(row_edges_days=None),
        now=_NOW,
    )
    assert "row_edges" not in deleted
    assert _count_edges(run_id) == 1


def test_threshold_zero_or_negative_skips_axis() -> None:
    run_id = "prune-zero"
    _add_row_edge(run_id, age_days=1000)
    deleted = prune_once(
        app.state.session_factory,
        _settings(row_edges_days=0),
        now=_NOW,
    )
    assert "row_edges" not in deleted
    assert _count_edges(run_id) == 1


def test_prune_reports_zero_when_nothing_old_enough() -> None:
    run_id = "prune-fresh"
    _add_row_edge(run_id, age_days=5)
    deleted = prune_once(
        app.state.session_factory,
        _settings(row_edges_days=365),
        now=_NOW,
    )
    assert deleted == {"row_edges": 0}
    assert _count_edges(run_id) == 1
