"""Quality monitoring: monitor CRUD + backing-job sync + the scan engine rules."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import deltalake
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Job, JobLog, JobRun, User, Workspace
from pointlessql.models.quality_monitoring import (
    QualityAnomaly,
    QualityMonitor,
    TableProfileSnapshot,
)
from pointlessql.services.quality_monitoring import (
    create_monitor,
    delete_monitor,
    ensure_backing_job,
    get_monitor,
    list_anomalies,
    list_monitors,
    list_snapshots,
    scan_monitor_sync,
    update_monitor,
    validate_target,
)

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)
_FQN = "main.sales.orders"


@pytest.fixture
def factory() -> Any:
    """In-memory session factory seeded with the default workspace + owner."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(Workspace(id=1, slug="default", name="Default workspace", created_at=_NOW))
        session.add(
            User(
                email="owner@test.com",
                display_name="Owner",
                password_hash="x",
                is_admin=True,
                created_at=_NOW,
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _owner_id(factory: Any) -> int:
    with factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        return user.id


def _make_monitor(factory: Any, *, target: str = _FQN, is_active: bool = True) -> dict[str, Any]:
    return create_monitor(
        factory,
        workspace_id=1,
        target=target,
        cron_expr="0 6 * * *",
        created_by_user_id=_owner_id(factory),
        is_active=is_active,
    )


def _write_orders(loc: str, df: pd.DataFrame, *, schema_change: bool = False) -> None:
    mode_kwargs: dict[str, Any] = {"mode": "overwrite"}
    if schema_change:
        mode_kwargs["schema_mode"] = "overwrite"
    if not Path(loc).exists():
        mode_kwargs = {}
    deltalake.write_deltalake(loc, df, **mode_kwargs)


def _scan(factory: Any, monitor_id: int, loc: str) -> dict[str, Any]:
    return scan_monitor_sync(factory, monitor_id=monitor_id, tables={_FQN: loc})


def _open_anomalies(factory: Any, monitor_id: int) -> list[QualityAnomaly]:
    with factory() as session:
        rows = session.scalars(
            select(QualityAnomaly).where(
                QualityAnomaly.monitor_id == monitor_id,
                QualityAnomaly.resolved_at.is_(None),
            )
        ).all()
        session.expunge_all()
        return list(rows)


# ---------------------------------------------------------------------------
# target validation
# ---------------------------------------------------------------------------


def test_validate_target_accepts_schema_and_table() -> None:
    """Two-part schema prefixes and three-part FQNs both validate."""
    assert validate_target("main.sales") == "main.sales"
    assert validate_target("  main.sales.orders  ") == "main.sales.orders"


@pytest.mark.parametrize(
    "bad",
    ["", "main", "a.b.c.d", "main.sales orders", "main..orders", "cat.sch.tbl;drop"],
)
def test_validate_target_rejects_malformed(bad: str) -> None:
    """Anything that is not 2 or 3 dot-joined identifiers is rejected."""
    with pytest.raises(ValidationError):
        validate_target(bad)


# ---------------------------------------------------------------------------
# CRUD + backing-job lifecycle
# ---------------------------------------------------------------------------


def test_create_active_monitor_materialises_backing_job(factory: Any) -> None:
    """An active monitor immediately owns an unpaused quality_monitor Job."""
    monitor = _make_monitor(factory)
    assert monitor["is_active"] is True
    assert monitor["backing_job_id"] is not None
    with factory() as session:
        job = session.get(Job, monitor["backing_job_id"])
        assert job is not None
        assert job.kind == "quality_monitor"
        assert job.is_paused is False
        assert job.cron_expr == "0 6 * * *"
        assert f'"monitor_id": {monitor["id"]}' in job.config


def test_create_inactive_monitor_has_no_job(factory: Any) -> None:
    """An inactive monitor defers the Job until activation or a manual run."""
    monitor = _make_monitor(factory, is_active=False)
    assert monitor["backing_job_id"] is None
    with factory() as session:
        assert session.scalars(select(Job)).first() is None


def test_create_duplicate_target_rejected(factory: Any) -> None:
    """A workspace cannot monitor the same target twice."""
    _make_monitor(factory)
    with pytest.raises(ValidationError, match="already exists"):
        _make_monitor(factory)


def test_update_pause_and_resume_syncs_backing_job(factory: Any) -> None:
    """is_active=False pauses the Job; reactivating un-pauses + syncs cron."""
    monitor = _make_monitor(factory)
    paused = update_monitor(factory, monitor["id"], workspace_id=1, is_active=False)
    assert paused is not None and paused["is_active"] is False
    with factory() as session:
        job = session.get(Job, monitor["backing_job_id"])
        assert job is not None and job.is_paused is True

    resumed = update_monitor(
        factory, monitor["id"], workspace_id=1, is_active=True, cron_expr="*/30 * * * *"
    )
    assert resumed is not None and resumed["is_active"] is True
    with factory() as session:
        job = session.get(Job, monitor["backing_job_id"])
        assert job is not None
        assert job.is_paused is False
        assert job.cron_expr == "*/30 * * * *"


def test_ensure_backing_job_materialises_paused_job(factory: Any) -> None:
    """A manual run on an inactive monitor creates the Job paused."""
    monitor = _make_monitor(factory, is_active=False)
    job_id = ensure_backing_job(factory, monitor["id"], workspace_id=1)
    assert job_id is not None
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None and job.is_paused is True
    # Idempotent — a second call returns the same job.
    assert ensure_backing_job(factory, monitor["id"], workspace_id=1) == job_id


def test_get_and_list_count_open_anomalies(factory: Any) -> None:
    """The serialised monitor carries the unresolved-anomaly count."""
    monitor = _make_monitor(factory)
    with factory() as session:
        session.add(
            QualityAnomaly(
                monitor_id=monitor["id"],
                table_fqn=_FQN,
                kind="freshness",
                severity="warn",
                observed="o",
                expected="e",
                detected_at=_NOW,
            )
        )
        session.add(
            QualityAnomaly(
                monitor_id=monitor["id"],
                table_fqn=_FQN,
                kind="schema_change",
                severity="warn",
                observed="o",
                expected="e",
                detected_at=_NOW,
                resolved_at=_NOW,
            )
        )
        session.commit()
    fetched = get_monitor(factory, monitor["id"], workspace_id=1)
    assert fetched is not None and fetched["open_anomalies"] == 1
    listed = list_monitors(factory, workspace_id=1)
    assert [m["open_anomalies"] for m in listed] == [1]
    assert len(list_anomalies(factory, workspace_id=1, status="open")) == 1
    assert len(list_anomalies(factory, workspace_id=1, status="resolved")) == 1
    assert len(list_anomalies(factory, workspace_id=1)) == 2


def test_delete_monitor_removes_children_and_job(factory: Any) -> None:
    """Delete sweeps snapshots, anomalies, the backing Job, and its runs."""
    monitor = _make_monitor(factory)
    job_id = monitor["backing_job_id"]
    with factory() as session:
        session.add(
            TableProfileSnapshot(
                monitor_id=monitor["id"], table_fqn=_FQN, row_count=1, captured_at=_NOW
            )
        )
        session.add(
            QualityAnomaly(
                monitor_id=monitor["id"],
                table_fqn=_FQN,
                kind="freshness",
                severity="warn",
                observed="o",
                expected="e",
                detected_at=_NOW,
            )
        )
        run = JobRun(
            job_id=job_id,
            status="succeeded",
            trigger="manual",
            started_at=_NOW,
        )
        session.add(run)
        session.flush()
        session.add(JobLog(job_run_id=run.id, ts=_NOW, level="info", message="m"))
        session.commit()

    assert delete_monitor(factory, monitor["id"], workspace_id=1) is True
    with factory() as session:
        assert session.get(QualityMonitor, monitor["id"]) is None
        assert session.scalars(select(TableProfileSnapshot)).first() is None
        assert session.scalars(select(QualityAnomaly)).first() is None
        assert session.get(Job, job_id) is None
        assert session.scalars(select(JobRun)).first() is None
        assert session.scalars(select(JobLog)).first() is None
    # Gone monitors report a clean miss.
    assert delete_monitor(factory, monitor["id"], workspace_id=1) is False


# ---------------------------------------------------------------------------
# scan engine rules
# ---------------------------------------------------------------------------


def test_scan_persists_snapshot_with_column_metrics(factory: Any, tmp_path: Path) -> None:
    """One scan stores rows, Delta version, and per-column metrics."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": [1, 2, 3], "amount": [10.0, 20.0, None]}))
    monitor = _make_monitor(factory, is_active=False)

    result = _scan(factory, monitor["id"], loc)
    assert result["tables_scanned"] == 1
    assert result["tables_skipped"] == []
    assert result["new_anomalies"] == []

    snapshots = list_snapshots(factory, monitor_id=monitor["id"])
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap["table_fqn"] == _FQN
    assert snap["row_count"] == 3
    assert snap["delta_version"] == 0
    assert snap["column_metrics"]["amount"]["null_count"] == 1


def test_volume_drop_critical_below_half(factory: Any, tmp_path: Path) -> None:
    """Falling under 50% of a >=100-row predecessor is critical."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(200)}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(80)}))
    result = _scan(factory, monitor["id"], loc)
    kinds = {(a["kind"], a["severity"]) for a in result["new_anomalies"]}
    assert ("volume_drop", "critical") in kinds


def test_volume_drop_warn_below_eighty_percent(factory: Any, tmp_path: Path) -> None:
    """Falling under 80% (but staying above 50%) warns."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(200)}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(140)}))
    result = _scan(factory, monitor["id"], loc)
    kinds = {(a["kind"], a["severity"]) for a in result["new_anomalies"]}
    assert ("volume_drop", "warn") in kinds


def test_volume_drop_skips_small_predecessors(factory: Any, tmp_path: Path) -> None:
    """Tables under 100 rows never fire the volume rule."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(50)}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(10)}))
    result = _scan(factory, monitor["id"], loc)
    assert all(a["kind"] != "volume_drop" for a in result["new_anomalies"])


def test_null_spike_warn(factory: Any, tmp_path: Path) -> None:
    """A null-fraction rise over 0.2 absolute warns on that column."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(10), "v": ["x"] * 10}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(10), "v": [None] * 4 + ["x"] * 6}))
    result = _scan(factory, monitor["id"], loc)
    spikes = [a for a in result["new_anomalies"] if a["kind"] == "null_spike"]
    assert len(spikes) == 1
    assert spikes[0]["severity"] == "warn"
    assert spikes[0]["column_name"] == "v"


def test_null_spike_critical(factory: Any, tmp_path: Path) -> None:
    """A null-fraction rise over 0.5 absolute is critical."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(10), "v": ["x"] * 10}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(10), "v": [None] * 8 + ["x"] * 2}))
    result = _scan(factory, monitor["id"], loc)
    spikes = [a for a in result["new_anomalies"] if a["kind"] == "null_spike"]
    assert len(spikes) == 1
    assert spikes[0]["severity"] == "critical"


def test_schema_change_detected_then_resolved(factory: Any, tmp_path: Path) -> None:
    """Added columns warn once and auto-resolve when the shape stabilises."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(5)}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(5), "extra": ["x"] * 5}), schema_change=True)
    result = _scan(factory, monitor["id"], loc)
    changes = [a for a in result["new_anomalies"] if a["kind"] == "schema_change"]
    assert len(changes) == 1
    assert changes[0]["severity"] == "warn"
    assert "added: extra" in (changes[0]["detail"] or "")

    # Same shape on the next scan — the open anomaly resolves.
    result = _scan(factory, monitor["id"], loc)
    assert result["new_anomalies"] == []
    assert result["resolved_count"] == 1
    assert _open_anomalies(factory, monitor["id"]) == []


def test_open_anomaly_not_duplicated_while_firing(factory: Any, tmp_path: Path) -> None:
    """A rule that keeps firing leaves exactly one open anomaly row."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(10), "v": ["x"] * 10}))
    monitor = _make_monitor(factory, is_active=False)
    _scan(factory, monitor["id"], loc)

    _write_orders(loc, pd.DataFrame({"id": range(10), "v": [None] * 5 + ["x"] * 5}))
    first = _scan(factory, monitor["id"], loc)
    assert [a["kind"] for a in first["new_anomalies"]] == ["null_spike"]

    # Null fraction climbs again (0.5 → 0.9, another +0.4) — the rule
    # fires but the open (table, column, kind) identity already exists.
    _write_orders(loc, pd.DataFrame({"id": range(10), "v": [None] * 9 + ["x"]}))
    second = _scan(factory, monitor["id"], loc)
    assert second["new_anomalies"] == []
    open_rows = _open_anomalies(factory, monitor["id"])
    assert [(a.kind, a.column_name) for a in open_rows] == [("null_spike", "v")]


def test_freshness_warns_on_stale_tables(
    factory: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A table whose last commit is older than 24h warns on the first scan."""
    loc = str(tmp_path / "orders")
    _write_orders(loc, pd.DataFrame({"id": range(5)}))
    monitor = _make_monitor(factory, is_active=False)

    stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=48)
    monkeypatch.setattr(
        "pointlessql.services.quality_monitoring._engine._last_write_at",
        lambda _loc: stale,
    )
    result = _scan(factory, monitor["id"], loc)
    kinds = {(a["kind"], a["severity"]) for a in result["new_anomalies"]}
    assert ("freshness", "warn") in kinds


def test_unreadable_table_is_skipped(factory: Any, tmp_path: Path) -> None:
    """A missing storage location is recorded as skipped, not raised."""
    monitor = _make_monitor(factory, is_active=False)
    result = _scan(factory, monitor["id"], str(tmp_path / "missing"))
    assert result["tables_scanned"] == 0
    assert result["tables_skipped"] == [_FQN]
