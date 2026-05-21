"""Tests for Phase 98.C — cell-level lineage badges."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
)
from pointlessql.models.notebook import NotebookCellRun
from pointlessql.services.notebook import cell_lineage as cell_lineage_service


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """Build an in-memory SQLite session factory with the schema applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run_with_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    file_path: str,
    content_hash: str,
    op_name: str,
    target_table: str | None,
    rows_affected: int | None = None,
    delta_version_after: int | None = None,
    when: datetime.datetime | None = None,
) -> str:
    """Insert one ``agent_runs`` + ``agent_run_operations`` +
    ``notebook_cell_runs`` triple linked together.

    Returns the agent_run_id so the caller can chain more ops onto
    the same run if needed.
    """
    now = when or datetime.datetime.now(datetime.UTC)
    run_id = str(uuid.uuid4())
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-98c-test",
                notebook_path=file_path,
                status="running",
                started_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name=op_name,
                params_json="{}",
                target_table=target_table,
                rows_affected=rows_affected,
                delta_version_after=delta_version_after,
                started_at=now,
            )
        )
        s.add(
            NotebookCellRun(
                file_path=file_path,
                content_hash=content_hash,
                kernel_session_id=f"sess-{run_id[:8]}",
                workspace_id=1,
                status="ok",
                started_at=now,
                finished_at=now,
                agent_run_id=run_id,
            )
        )
        s.commit()
    return run_id


def test_no_cell_run_returns_empty(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Cells with no run history return an empty badge list."""
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session, file_path="nope.py", content_hash="deadbeef"
        )
    assert badges == []


def test_cell_run_without_agent_run_id_returns_empty(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A cell-run without an agent_run_id is skipped — no badges."""
    with factory() as session:
        session.add(
            NotebookCellRun(
                file_path="n.py",
                content_hash="abc",
                kernel_session_id="s1",
                workspace_id=1,
                status="ok",
                started_at=datetime.datetime.now(datetime.UTC),
                agent_run_id=None,
            )
        )
        session.commit()
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session, file_path="n.py", content_hash="abc"
        )
    assert badges == []


def test_write_op_surfaces_as_badge(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A single write-op cell-run produces one badge."""
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="abc",
        op_name="write_table",
        target_table="main.silver.events",
        rows_affected=42,
        delta_version_after=7,
    )
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session, file_path="n.py", content_hash="abc"
        )
    assert len(badges) == 1
    assert badges[0]["op_name"] == "write_table"
    assert badges[0]["target_table"] == "main.silver.events"
    assert badges[0]["rows_affected"] == 42
    assert badges[0]["delta_version_after"] == 7


def test_read_ops_excluded_from_badges(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Read-only ops (sql, aggregate, sql_explain) do NOT surface."""
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="abc",
        op_name="sql",
        target_table=None,
    )
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session, file_path="n.py", content_hash="abc"
        )
    assert badges == []


def test_duplicate_ops_collapsed_to_most_recent(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Re-runs writing to the same table yield one badge (the latest)."""
    base = datetime.datetime.now(datetime.UTC)
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="abc",
        op_name="write_table",
        target_table="main.silver.events",
        rows_affected=10,
        when=base - datetime.timedelta(hours=2),
    )
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="abc",
        op_name="write_table",
        target_table="main.silver.events",
        rows_affected=99,
        when=base,
    )
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session, file_path="n.py", content_hash="abc"
        )
    assert len(badges) == 1
    assert badges[0]["rows_affected"] == 99  # most-recent wins


def test_multiple_distinct_writes_all_surface(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Distinct (op_name, target_table) pairs produce separate badges."""
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="abc",
        op_name="write_table",
        target_table="main.silver.events",
    )
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="abc",
        op_name="merge",
        target_table="main.silver.summary",
    )
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session, file_path="n.py", content_hash="abc"
        )
    targets = {(b["op_name"], b["target_table"]) for b in badges}
    assert ("write_table", "main.silver.events") in targets
    assert ("merge", "main.silver.summary") in targets


# -- REST surface -------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_cell_lineage_empty_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown notebook path → 422 with the resolver envelope."""
    resp = await admin_client.get(
        "/api/notebooks/cell/lineage",
        params={"path": "nope.py", "content_hash": "abc"},
    )
    assert resp.status_code == 422


async def test_api_cell_lineage_empty_cell(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Existing notebook + cell with no audit history → empty badges."""
    await admin_client.post(
        "/api/notebooks/create", json={"path": "n.py"}
    )
    resp = await admin_client.get(
        "/api/notebooks/cell/lineage",
        params={"path": "n.py", "content_hash": "abc"},
    )
    assert resp.status_code == 200
    assert resp.json()["badges"] == []


# -- bulk REST surface --------------------------------------------------------


async def test_api_cell_lineage_bulk_empty_notebook(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Bulk endpoint returns ``{}`` for a notebook with no write history."""
    await admin_client.post(
        "/api/notebooks/create", json={"path": "n.py"}
    )
    resp = await admin_client.get(
        "/api/notebooks/cell/lineage/bulk",
        params={"path": "n.py"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "n.py"
    assert body["badges"] == {}


def test_list_cell_lineage_badges_bulk_indexes_by_content_hash(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Bulk service maps ``content_hash`` -> badges across all cells."""
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="aaaa",
        op_name="write_table",
        target_table="main.silver.events",
    )
    _seed_run_with_op(
        factory,
        file_path="n.py",
        content_hash="bbbb",
        op_name="merge",
        target_table="main.gold.summary",
    )
    with factory() as session:
        out = cell_lineage_service.list_cell_lineage_badges_bulk(
            session, file_path="n.py"
        )
    assert set(out) == {"aaaa", "bbbb"}
    assert out["aaaa"][0]["target_table"] == "main.silver.events"
    assert out["bbbb"][0]["op_name"] == "merge"
