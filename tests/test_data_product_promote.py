"""Tests for the Phase-73.1 promote-to-DP scanner + draft yaml flow.

Covers:

* ``scan_candidates`` ignores ops without ``target_table``.
* Threshold gates: < min_runs / < min_ops → no candidate.
* Existing ``DataProduct`` row covers schema → no candidate.
* Re-scan with same data is idempotent (UPSERT updates counts).
* Dismissed candidate stays dismissed on re-scan.
* Cross-workspace iso.
* ``build_draft_yaml`` round-trips through DataProductContract.
* POST ``/api/data-products/candidates/{id}/dismiss`` flips status.
* POST ``/api/data-products/candidates/{id}/generate-draft`` writes
  the file + inserts ``DataProductYamlDraft`` row.
* HTML page renders.
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import httpx
import pytest
import yaml
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products._schema import DataProductContract
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.catalog._data_product_candidate import (
    DataProductPromotionCandidate,
)
from pointlessql.models.catalog._data_product_yaml_draft import (
    DataProductYamlDraft,
)
from pointlessql.models.workspace import Workspace, WorkspaceMember
from pointlessql.services.data_products import build_draft_yaml, scan_candidates


def _seed_run_op(
    *,
    target_table: str | None,
    workspace_id: int = 1,
    age_seconds: int = 0,
    run_id: str | None = None,
) -> str:
    """Seed one AgentRun + AgentRunOperation; return the run id."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    run_id = run_id or str(uuid.uuid4())
    with factory() as session:
        existing_run = session.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        ).scalar_one_or_none()
        if existing_run is None:
            run = AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal="t@t.com",
                agent_id="a",
                notebook_path="/x",
                status="finished",
                started_at=when,
                finished_at=when,
            )
            session.add(run)
            session.flush()
        ordinal = (
            session.execute(
                select(AgentRunOperation).where(
                    AgentRunOperation.agent_run_id == run_id
                )
            )
            .scalars()
            .all()
        )
        op = AgentRunOperation(
            workspace_id=workspace_id,
            agent_run_id=run_id,
            ordinal=len(ordinal) + 1,
            op_name="write_table",
            params_json="{}",
            target_table=target_table,
            started_at=when,
            finished_at=when,
        )
        session.add(op)
        session.commit()
    return run_id


def _seed_workspace_two(user_id: int) -> None:
    """Seed workspace id=2 + add the test user as a member."""
    factory = app.state.session_factory
    with factory() as session:
        existing = session.execute(
            select(Workspace).where(Workspace.id == 2)
        ).scalar_one_or_none()
        if existing is None:
            ws = Workspace(
                id=2,
                slug="ws2",
                name="Workspace Two",
                created_at=datetime.datetime.now(datetime.UTC),
            )
            session.add(ws)
            session.flush()
            session.add(
                WorkspaceMember(
                    workspace_id=2,
                    user_id=user_id,
                    role="member",
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()


# ---------------------------------------------------------------------------
# scan_candidates
# ---------------------------------------------------------------------------


def test_scan_ignores_ops_with_no_target_table() -> None:
    """SQL-read ops (target_table NULL) don't yield candidates."""
    for _ in range(15):
        _seed_run_op(target_table=None)
    inserted = scan_candidates(app.state.session_factory)
    assert inserted == 0


def test_scan_threshold_min_runs() -> None:
    """One run, many ops → fails min_runs gate."""
    run = str(uuid.uuid4())
    for _ in range(15):
        _seed_run_op(target_table="catA.schemA.tbl", run_id=run)
    inserted = scan_candidates(
        app.state.session_factory, min_runs=3, min_ops=5
    )
    assert inserted == 0


def test_scan_threshold_min_ops() -> None:
    """Three runs, one op each → fails min_ops gate."""
    for _ in range(3):
        _seed_run_op(target_table="catB.schemB.tbl")
    inserted = scan_candidates(
        app.state.session_factory, min_runs=3, min_ops=10
    )
    assert inserted == 0


def test_scan_creates_candidate_above_thresholds() -> None:
    """3 distinct runs × 5 ops each = open candidate."""
    for _ in range(3):
        run = str(uuid.uuid4())
        for _ in range(5):
            _seed_run_op(target_table="catC.schemC.tbl", run_id=run)
    inserted = scan_candidates(
        app.state.session_factory, min_runs=3, min_ops=10
    )
    assert inserted == 1
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(select(DataProductPromotionCandidate)).scalar_one()
        assert row.catalog_name == "catC"
        assert row.schema_name == "schemC"
        assert row.status == "open"
        assert row.distinct_run_count == 3
        assert row.write_op_count == 15


def test_scan_skips_schema_already_a_data_product(tmp_path: Path) -> None:
    """If a DataProduct row already covers (catalog, schema), skip."""
    from pointlessql.data_products import load_contract

    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text(
        """\
data_product:
  name: D
  version: "1.0.0"
  description: d
  catalog: catD
  schema: schemD
  tables: []
""",
        encoding="utf-8",
    )
    load_contract(yaml_path, factory=app.state.session_factory)
    for _ in range(3):
        run = str(uuid.uuid4())
        for _ in range(5):
            _seed_run_op(target_table="catD.schemD.tbl", run_id=run)
    inserted = scan_candidates(
        app.state.session_factory, min_runs=3, min_ops=10
    )
    assert inserted == 0


def test_scan_is_idempotent() -> None:
    """Two consecutive scans against the same data don't duplicate rows."""
    for _ in range(3):
        run = str(uuid.uuid4())
        for _ in range(5):
            _seed_run_op(target_table="catE.schemE.tbl", run_id=run)
    scan_candidates(app.state.session_factory, min_runs=3, min_ops=10)
    scan_candidates(app.state.session_factory, min_runs=3, min_ops=10)
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductPromotionCandidate)).scalars().all()
        assert len(rows) == 1


def test_scan_does_not_resurrect_dismissed() -> None:
    """Dismissed candidate stays dismissed across scans."""
    for _ in range(3):
        run = str(uuid.uuid4())
        for _ in range(5):
            _seed_run_op(target_table="catF.schemF.tbl", run_id=run)
    scan_candidates(app.state.session_factory, min_runs=3, min_ops=10)
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(select(DataProductPromotionCandidate)).scalar_one()
        row.status = "dismissed"
        session.add(row)
        session.commit()
    # New activity arrives.
    _seed_run_op(target_table="catF.schemF.tbl")
    scan_candidates(app.state.session_factory, min_runs=3, min_ops=10)
    with factory() as session:
        row = session.execute(select(DataProductPromotionCandidate)).scalar_one()
        assert row.status == "dismissed"


def test_scan_cross_workspace_isolation() -> None:
    """Workspace-2 ops don't leak into workspace-1 candidates."""
    _seed_workspace_two(user_id=1)
    for _ in range(3):
        run = str(uuid.uuid4())
        for _ in range(5):
            _seed_run_op(
                target_table="catG.schemG.tbl",
                workspace_id=2,
                run_id=run,
            )
    inserted = scan_candidates(
        app.state.session_factory, min_runs=3, min_ops=10
    )
    assert inserted == 1
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(select(DataProductPromotionCandidate)).scalar_one()
        assert row.workspace_id == 2


# ---------------------------------------------------------------------------
# build_draft_yaml
# ---------------------------------------------------------------------------


def _seed_candidate_basic() -> DataProductPromotionCandidate:
    """Insert one open candidate matching seeded ops; return the row."""
    for _ in range(3):
        run = str(uuid.uuid4())
        for _ in range(5):
            _seed_run_op(target_table="catH.schemH.orders", run_id=run)
    scan_candidates(app.state.session_factory, min_runs=3, min_ops=10)
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(select(DataProductPromotionCandidate)).scalar_one()
        # Detach so caller can reuse the snapshot freely.
        session.expunge(row)
        return row


def _stub_schema_reader(target: str) -> list[tuple[str, str, bool]]:
    """Return a deterministic 2-column shape for any target."""
    return [("id", "long", False), ("amount", "double", True)]


def test_build_draft_yaml_round_trips_through_contract() -> None:
    """The generated yaml passes pydantic re-validation."""
    candidate = _seed_candidate_basic()
    factory = app.state.session_factory
    with factory() as session:
        text = build_draft_yaml(
            session,
            workspace_id=1,
            candidate=candidate,
            schema_reader=_stub_schema_reader,
        )
    payload = yaml.safe_load(text)
    contract = DataProductContract.model_validate(payload)
    assert contract.catalog == "catH"
    assert contract.schema_name == "schemH"
    assert any(t.name == "orders" for t in contract.tables)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_route_flips_status(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST .../dismiss flips status to 'dismissed'."""
    candidate = _seed_candidate_basic()
    res = await admin_client.post(
        f"/api/data-products/candidates/{candidate.id}/dismiss"
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(DataProductPromotionCandidate, candidate.id)
        assert row is not None
        assert row.status == "dismissed"
        assert row.dismissed_by_user_id is not None


@pytest.mark.asyncio
async def test_generate_draft_writes_file_and_row(
    admin_client: httpx.AsyncClient, tmp_path: Path
) -> None:
    """POST .../generate-draft writes file + inserts YamlDraft row."""
    app.state.settings.data_products.draft_dir = tmp_path
    app.state.dp_draft_schema_reader = _stub_schema_reader
    try:
        candidate = _seed_candidate_basic()
        res = await admin_client.post(
            f"/api/data-products/candidates/{candidate.id}/generate-draft"
        )
        assert res.status_code == 200, res.text
        body = res.json()
        draft_path = Path(body["draft_path"])
        assert draft_path.exists()
        assert "catalog: catH" in draft_path.read_text(encoding="utf-8")
        factory = app.state.session_factory
        with factory() as session:
            draft = session.execute(select(DataProductYamlDraft)).scalar_one()
            assert draft.source_kind == "candidate_generate"
            assert draft.workspace_id == 1
    finally:
        app.state.dp_draft_schema_reader = None


@pytest.mark.asyncio
async def test_html_page_renders(admin_client: httpx.AsyncClient) -> None:
    """GET /data-products/candidates renders the table fingerprint."""
    _seed_candidate_basic()
    res = await admin_client.get("/data-products/candidates")
    assert res.status_code == 200
    assert "pql-dp-candidates-table" in res.text


@pytest.mark.asyncio
async def test_dismiss_unknown_candidate_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Dismissing a row that doesn't exist returns 404."""
    res = await admin_client.post("/api/data-products/candidates/99999/dismiss")
    assert res.status_code == 404
