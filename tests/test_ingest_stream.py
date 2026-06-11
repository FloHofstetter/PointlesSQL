"""Stream-buffer + direct-write stream API tests.

The router under test is exported but not yet registered on the app,
so a module fixture mounts it for the duration of this file.  Buffer
tests write real local Delta tables under ``tmp_path``; route tests
stub the UC facade so no soyuz-catalog server is needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import deltalake
import httpx
import pytest

import pointlessql.models.autoloader  # noqa: F401  # pyright: ignore[reportUnusedImport]
from pointlessql.api.main import app
from pointlessql.models import AuditLog
from pointlessql.services.ingest import stream_buffer as stream_buffer_module
from pointlessql.services.ingest.stream_buffer import StreamBuffer, get_stream_buffer


@pytest.fixture(scope="module", autouse=True)
def _mount_stream_routes() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Mount the unregistered stream router on the app for this module."""
    from pointlessql.api.ingest_stream_routes import router

    before = list(app.router.routes)
    app.include_router(router)
    yield
    app.router.routes[:] = before


@pytest.fixture(autouse=True)
def _fresh_buffer() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Give every test a fresh lazily-created buffer instance."""
    app.state.ingest_stream_buffer = None
    yield
    app.state.ingest_stream_buffer = None


# ---------------------------------------------------------------------------
# StreamBuffer unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buffer_flushes_on_size_cap(tmp_path: Path) -> None:
    """Reaching max_rows writes one Delta append and empties the key."""
    target = str(tmp_path / "events")
    buf = StreamBuffer(max_rows=3, max_age_seconds=999.0)
    try:
        assert await buf.append("main.s.t", target, [{"a": 1}, {"a": 2}]) == 2
        assert buf.buffered_rows("main.s.t") == 2
        # Third row trips the size flush.
        assert await buf.append("main.s.t", target, [{"a": 3}]) == 0
        assert buf.buffered_rows("main.s.t") == 0
        frame = deltalake.DeltaTable(target).to_pandas()
        assert len(frame) == 3
    finally:
        await buf.shutdown()


@pytest.mark.asyncio
async def test_buffer_force_flush_and_schema_merge(tmp_path: Path) -> None:
    """Force-flush writes pending rows; new fields evolve the schema."""
    target = str(tmp_path / "events")
    buf = StreamBuffer(max_rows=100, max_age_seconds=999.0)
    try:
        await buf.append("main.s.t", target, [{"a": 1}])
        assert await buf.flush("main.s.t") == 1
        assert await buf.flush("main.s.t") == 0  # nothing pending

        # A second batch growing a column appends via schema merge.
        await buf.append("main.s.t", target, [{"a": 2, "b": "x"}])
        assert await buf.flush("main.s.t") == 1
        frame = deltalake.DeltaTable(target).to_pandas()
        assert len(frame) == 2
        assert "b" in frame.columns
    finally:
        await buf.shutdown()


@pytest.mark.asyncio
async def test_buffer_flushes_aged_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ticker flushes keys whose oldest row exceeds max_age."""
    import asyncio

    monkeypatch.setattr(stream_buffer_module, "_TICK_SECONDS", 0.05)
    target = str(tmp_path / "events")
    buf = StreamBuffer(max_rows=100, max_age_seconds=0.05)
    try:
        await buf.append("main.s.t", target, [{"a": 1}])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if buf.buffered_rows("main.s.t") == 0:
                break
        assert buf.buffered_rows("main.s.t") == 0
        assert len(deltalake.DeltaTable(target).to_pandas()) == 1
    finally:
        await buf.shutdown()


@pytest.mark.asyncio
async def test_buffer_shutdown_drains_pending_rows(tmp_path: Path) -> None:
    """shutdown() flushes whatever is still buffered."""
    target = str(tmp_path / "events")
    buf = StreamBuffer(max_rows=100, max_age_seconds=999.0)
    await buf.append("main.s.t", target, [{"a": 1}, {"a": 2}])
    await buf.shutdown()
    assert len(deltalake.DeltaTable(target).to_pandas()) == 2


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def _stub_table(uc_client_stub: MagicMock, storage_location: str | None) -> None:
    """Point the UC stub's get_table at one storage location (or 404)."""
    info: dict[str, Any] = (
        {"storage_location": storage_location, "owner": "someone@else.test"}
        if storage_location
        else {}
    )
    uc_client_stub.get_table.return_value = info


@pytest.mark.asyncio
async def test_stream_append_then_flush_writes_delta(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """Happy path: rows buffer, force-flush lands them in Delta."""
    target = str(tmp_path / "events")
    _stub_table(uc_client_stub, target)

    res = await admin_client.post(
        "/api/ingest/streams/main/bronze/events",
        json={"rows": [{"id": 1, "kind": "click"}, {"id": 2, "kind": "view"}]},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"accepted": 2, "buffered": 2}

    res2 = await admin_client.post("/api/ingest/streams/main/bronze/events/flush")
    assert res2.status_code == 200, res2.text
    assert res2.json() == {"flushed": 2}
    frame = deltalake.DeltaTable(target).to_pandas()
    assert sorted(frame["id"].tolist()) == [1, 2]

    # Audit rows carry counts only — never payload fields.
    with app.state.session_factory() as session:
        actions = [
            (row.action, row.detail)
            for row in session.query(AuditLog).filter(AuditLog.action.like("ingest_stream.%")).all()
        ]
    assert ("ingest_stream.appended" in dict(actions)) and (
        "ingest_stream.flushed" in dict(actions)
    )
    for _action, detail in actions:
        assert "click" not in (detail or "")

    await get_stream_buffer(app).shutdown()


@pytest.mark.asyncio
async def test_stream_append_size_flush_reports_zero_buffered(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """A request that trips max_rows flushes inline (buffered == 0)."""
    target = str(tmp_path / "events")
    _stub_table(uc_client_stub, target)
    app.state.ingest_stream_buffer = StreamBuffer(max_rows=2, max_age_seconds=999.0)

    res = await admin_client.post(
        "/api/ingest/streams/main/bronze/events",
        json={"rows": [{"id": 1}, {"id": 2}]},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"accepted": 2, "buffered": 0}
    assert len(deltalake.DeltaTable(target).to_pandas()) == 2

    await get_stream_buffer(app).shutdown()


@pytest.mark.asyncio
async def test_stream_rejects_oversized_batch(
    admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """More than 1000 rows per request answers 422."""
    _stub_table(uc_client_stub, "/nowhere")
    res = await admin_client.post(
        "/api/ingest/streams/main/bronze/events",
        json={"rows": [{"id": i} for i in range(1001)]},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_stream_rejects_malformed_rows(
    admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """Empty / non-list / non-object rows answer 422."""
    _stub_table(uc_client_stub, "/nowhere")
    for body in ({}, {"rows": []}, {"rows": "nope"}, {"rows": [{"a": 1}, 7]}):
        res = await admin_client.post("/api/ingest/streams/main/bronze/events", json=body)
        assert res.status_code == 422, body


@pytest.mark.asyncio
async def test_stream_unknown_table_404(
    admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """A target missing from the catalog answers 404."""
    _stub_table(uc_client_stub, None)
    res = await admin_client.post(
        "/api/ingest/streams/main/bronze/missing",
        json={"rows": [{"id": 1}]},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_stream_without_modify_privilege_403(
    tmp_path: Path,
    non_admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """A non-admin without MODIFY on the table is denied."""
    _stub_table(uc_client_stub, str(tmp_path / "events"))
    uc_client_stub.get_effective_permissions.return_value = []
    res = await non_admin_client.post(
        "/api/ingest/streams/main/bronze/events",
        json={"rows": [{"id": 1}]},
    )
    assert res.status_code == 403
    # Nothing reached the buffer.
    assert get_stream_buffer(app).buffered_rows("main.bronze.events") == 0


@pytest.mark.asyncio
async def test_stream_anonymous_rejected(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Unauthenticated callers never reach the buffer."""
    res = await anonymous_client.post(
        "/api/ingest/streams/main/bronze/events",
        json={"rows": [{"id": 1}]},
    )
    assert res.status_code in (401, 403)
