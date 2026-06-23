"""Cascade detection + rollback-preview API.

Two layers under test:

* :func:`pointlessql.services.workspace._cascade.find_downstream_tables` —
  reads ``lineage_row_edges`` + ``lineage_column_map`` and reports
  distinct downstream targets.  Pure SQLAlchemy unit tests; no
  HTTP.
* ``GET /api/runs/{run_id}/rollback-preview?target=…`` — admin-
  gated route on top of cascade + ``agent_run_operations``.
  Exercised through ``httpx.AsyncClient`` against the FastAPI
  app (the conftest's autouse ``_auth_db`` already wires up the
  admin cookie).
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
    LineageColumnMap,
    LineageRowEdge,
)
from pointlessql.services.workspace import find_downstream_tables


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory with the audit + lineage schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    target: str,
    delta_version_before: int | None = 0,
    delta_version_after: int | None = 1,
    op_name: str = "merge",
) -> tuple[str, int]:
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-16-test",
                notebook_path="rollback_preview.py",
                status="running",
                started_at=now,
            )
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name=op_name,
            params_json=json.dumps({"target": target}),
            target_table=target,
            delta_version_before=delta_version_before,
            delta_version_after=delta_version_after,
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return run_id, op.id


def _seed_row_edge(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    target_table: str,
) -> None:
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op_id,
                source_table=source_table,
                source_row_id="src-1",
                target_table=target_table,
                target_row_id="tgt-1",
                created_at=now,
            )
        )
        session.commit()


def _seed_col_edge(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    target_table: str,
) -> None:
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=op_id,
                source_table=source_table,
                source_column="x",
                target_table=target_table,
                target_column="x",
                transform_kind="identity",
                created_at=now,
            )
        )
        session.commit()


class TestFindDownstreamTables:
    """The cascade helper drives both the API and the future agent tool."""

    def test_no_edges_returns_empty(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        assert find_downstream_tables(factory, source_table="main.silver.x") == []

    def test_row_only_edge_via_row(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory, target="main.silver.orders")
        _seed_row_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.silver.orders",
            target_table="main.gold.daily_revenue",
        )
        specs = find_downstream_tables(factory, source_table="main.silver.orders")
        assert len(specs) == 1
        assert specs[0].target_table == "main.gold.daily_revenue"
        assert specs[0].via == "row"
        assert specs[0].edge_count == 1
        assert specs[0].most_recent_run_id == run_id

    def test_column_only_edge_via_column(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory, target="main.silver.orders")
        _seed_col_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.silver.orders",
            target_table="main.gold.daily_revenue",
        )
        specs = find_downstream_tables(factory, source_table="main.silver.orders")
        assert len(specs) == 1
        assert specs[0].via == "column"

    def test_both_axes_marks_via_both(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory, target="main.silver.orders")
        _seed_row_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.silver.orders",
            target_table="main.gold.daily_revenue",
        )
        _seed_col_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.silver.orders",
            target_table="main.gold.daily_revenue",
        )
        specs = find_downstream_tables(factory, source_table="main.silver.orders")
        assert len(specs) == 1
        assert specs[0].via == "both"
        assert specs[0].edge_count == 2

    def test_self_edges_skipped(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory, target="main.silver.orders")
        _seed_row_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.silver.orders",
            target_table="main.silver.orders",
        )
        # Self-edge filtered.
        assert find_downstream_tables(factory, source_table="main.silver.orders") == []

    def test_sorted_by_edge_count_desc(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory, target="main.silver.orders")
        # Two edges into "loud" target, one into "quiet" target.
        for _ in range(2):
            _seed_row_edge(
                factory,
                run_id=run_id,
                op_id=op_id,
                source_table="main.silver.orders",
                target_table="main.gold.loud",
            )
        _seed_row_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.silver.orders",
            target_table="main.gold.quiet",
        )
        specs = find_downstream_tables(factory, source_table="main.silver.orders")
        assert [s.target_table for s in specs] == ["main.gold.loud", "main.gold.quiet"]


class TestRollbackPreviewRoute:
    """End-to-end: HTTP shape, admin gating, multi-op ambiguity."""

    @pytest.mark.asyncio
    async def test_admin_required(self, non_admin_client: httpx.AsyncClient) -> None:
        run_id, _op = _seed_run_op_via_app(target="main.silver.orders")
        resp = await non_admin_client.get(
            f"/api/runs/{run_id}/rollback-preview",
            params={"target": "main.silver.orders"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_run_target_returns_404(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        resp = await admin_client.get(
            f"/api/runs/{uuid.uuid4()}/rollback-preview",
            params={"target": "main.silver.nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_single_op_payload_shape(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        run_id, op_id = _seed_run_op_via_app(
            target="main.silver.orders",
            delta_version_before=0,
            delta_version_after=1,
        )
        resp = await admin_client.get(
            f"/api/runs/{run_id}/rollback-preview",
            params={"target": "main.silver.orders"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["target_table"] == "main.silver.orders"
        assert body["op_id"] == op_id
        assert body["delta_version_before"] == 0
        assert body["delta_version_after"] == 1
        assert body["op_candidates"] != []
        # current_version is None when soyuz/Delta isn't reachable in tests.
        assert "current_version" in body
        assert "is_stale" in body
        assert body["intervening_writes"] == []  # no other run touched silver
        # Not stale (Delta unreachable → current_version None), so the
        # verification flag defaults to True.
        assert body["intervening_writes_verified"] is True
        assert body["downstream_warnings"] == []  # no lineage seeded

    @pytest.mark.asyncio
    async def test_invalid_creation_op_returns_422(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        run_id, _op = _seed_run_op_via_app(
            target="main.silver.orders",
            op_name="write_table",
            delta_version_before=None,
            delta_version_after=0,
        )
        resp = await admin_client.get(
            f"/api/runs/{run_id}/rollback-preview",
            params={"target": "main.silver.orders"},
        )
        assert resp.status_code == 422
        assert "rollback would mean dropping" in resp.text

    @pytest.mark.asyncio
    async def test_multi_op_returns_candidates(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        run_id = _seed_multi_op_via_app(
            target="main.silver.orders",
            ops=[
                (1, 0, 1, "merge"),
                (2, 1, 2, "merge"),
            ],
        )
        resp = await admin_client.get(
            f"/api/runs/{run_id}/rollback-preview",
            params={"target": "main.silver.orders"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["op_id"] is None
        assert len(body["op_candidates"]) == 2
        ordinals = [c["ordinal"] for c in body["op_candidates"]]
        assert ordinals == [1, 2]


def _fake_request(factory: Any) -> Any:
    """Minimal stand-in exposing ``request.app.state.session_factory``."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=factory)))


class TestLoadInterveningWrites:
    """The intervening-writes check must distinguish 'clean' from 'unknown'.

    This gates a destructive forced rollback, so a query failure must
    report ``verified=False`` (an empty list that means "unknown") rather
    than the same empty list a genuinely-clean table returns.
    """

    def test_success_returns_rows_verified_true(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Two later runs are returned, version-ordered, with verified=True."""
        from pointlessql.api.runs_routes.rollback import _load_intervening_writes

        run_b, _ = _seed_run_op(
            factory, target="main.silver.orders", delta_version_before=1, delta_version_after=2
        )
        run_c, _ = _seed_run_op(
            factory, target="main.silver.orders", delta_version_before=2, delta_version_after=3
        )
        rows, verified = _load_intervening_writes(
            _fake_request(factory),
            target="main.silver.orders",
            after_version=1,
            exclude_run="some-unrelated-run",
        )
        assert verified is True
        assert [r["delta_version_after"] for r in rows] == [2, 3]
        assert {r["run_id"] for r in rows} == {run_b, run_c}

    def test_exclude_run_is_filtered(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """The run being rolled back is excluded even if its version is higher."""
        from pointlessql.api.runs_routes.rollback import _load_intervening_writes

        run_b, _ = _seed_run_op(
            factory, target="main.silver.orders", delta_version_before=1, delta_version_after=2
        )
        run_c, _ = _seed_run_op(
            factory, target="main.silver.orders", delta_version_before=2, delta_version_after=3
        )
        rows, verified = _load_intervening_writes(
            _fake_request(factory),
            target="main.silver.orders",
            after_version=1,
            exclude_run=run_b,
        )
        assert verified is True
        assert {r["run_id"] for r in rows} == {run_c}

    def test_query_failure_returns_unverified(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A factory error yields ([], False) and logs — never a silent clean."""
        from pointlessql.api.runs_routes.rollback import _load_intervening_writes

        class _BoomFactory:
            def __call__(self) -> Any:
                raise RuntimeError("db down")

        with caplog.at_level(logging.ERROR, logger="pointlessql.api.runs_routes.rollback"):
            rows, verified = _load_intervening_writes(
                _fake_request(_BoomFactory()),
                target="main.silver.orders",
                after_version=1,
                exclude_run="run-x",
            )
        assert rows == []
        assert verified is False
        assert any("verification failed" in r.getMessage() for r in caplog.records)


def _seed_run_op_via_app(
    *,
    target: str,
    delta_version_before: int | None = 0,
    delta_version_after: int | None = 1,
    op_name: str = "merge",
) -> tuple[str, int]:
    """Seed an agent run + op through the live app's session factory."""
    factory = _app_factory()
    return _seed_run_op(
        factory,
        target=target,
        delta_version_before=delta_version_before,
        delta_version_after=delta_version_after,
        op_name=op_name,
    )


def _seed_multi_op_via_app(
    *,
    target: str,
    ops: list[tuple[int, int | None, int | None, str]],
) -> str:
    """Seed one run with multiple ops on the same target."""
    factory = _app_factory()
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-16-test",
                notebook_path="rollback_preview_multi.py",
                status="running",
                started_at=now,
            )
        )
        session.flush()
        for ordinal, before, after, op_name in ops:
            session.add(
                AgentRunOperation(
                    agent_run_id=run_id,
                    ordinal=ordinal,
                    op_name=op_name,
                    params_json=json.dumps({"target": target}),
                    target_table=target,
                    delta_version_before=before,
                    delta_version_after=after,
                    started_at=now,
                    finished_at=now,
                )
            )
        session.commit()
    return run_id


def _app_factory() -> sessionmaker:  # type: ignore[type-arg]
    """Return the session factory the conftest installed onto the app."""
    factory = getattr(app.state, "session_factory", None)
    assert factory is not None, "conftest._auth_db must run before route tests"
    return factory


# httpx.ASGITransport reuse-friendly app marker; keeps pyright happy on FastAPI typing.
_APP: FastAPI = app
