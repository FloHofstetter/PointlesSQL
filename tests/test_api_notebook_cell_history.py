"""Tests for ``GET /api/notebooks/cell-history`` (Sprint 66.7)."""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.notebook import outputs as notebook_outputs_service


@pytest.fixture
def seed_runs() -> None:
    """Pre-write three NotebookCellRunSource rows for the test cell."""
    factory = app.state.session_factory
    base = datetime.datetime(2026, 5, 10, 12, 0, tzinfo=datetime.UTC)
    for i in range(3):
        notebook_outputs_service.record_cell_run_start(
            factory,
            file_path="demo.py",
            content_hash="abcd1234abcd1234",
            kernel_session_id="ksess",
            source=f"print({i})",
            started_at=base + datetime.timedelta(seconds=i),
        )


async def test_cell_history_happy_path(
    seed_runs: None, admin_client: httpx.AsyncClient
) -> None:
    """Returns up to ``limit`` rows newest-first for the cell."""
    resp = await admin_client.get(
        "/api/notebooks/cell-history?path=demo.py&content_hash=abcd1234abcd1234&limit=5"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cell"]["path"] == "demo.py"
    assert body["cell"]["content_hash"] == "abcd1234abcd1234"
    assert len(body["runs"]) == 3
    # Newest-first ordering
    assert body["runs"][0]["source"] == "print(2)"
    assert body["runs"][2]["source"] == "print(0)"


async def test_cell_history_empty(admin_client: httpx.AsyncClient) -> None:
    """Unknown cell → empty runs list (200, not 404)."""
    resp = await admin_client.get(
        "/api/notebooks/cell-history?path=ghost.py&content_hash=ffffffffffffffff"
    )
    assert resp.status_code == 200
    assert resp.json()["runs"] == []


async def test_cell_history_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Non-admins get 403."""
    resp = await non_admin_client.get(
        "/api/notebooks/cell-history?path=demo.py&content_hash=ff"
    )
    assert resp.status_code == 403


async def test_cell_history_limit_clamp(
    admin_client: httpx.AsyncClient,
) -> None:
    """``limit`` outside [1, 100] → 422."""
    resp = await admin_client.get(
        "/api/notebooks/cell-history?path=demo.py&content_hash=ff&limit=0"
    )
    assert resp.status_code == 422
