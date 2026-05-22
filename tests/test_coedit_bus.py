"""Phase 109.1 — PG LISTEN/NOTIFY-backed co-edit bus.

Two-engine integration test: two ``CoeditBus`` instances against the
same Postgres exchange a frame end-to-end.  Skipped automatically
when ``TEST_DATABASE_URL`` is not Postgres, so the SQLite CI lane
walks past these without effort.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from pointlessql.services.notebook.coedit_bus import CoeditBus

pytestmark = pytest.mark.postgres


def _pg_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url or "postgresql" not in url:
        pytest.skip("TEST_DATABASE_URL must point at PG for coedit_bus tests")
    return url


def _create_subdb_engine(parent_url: str) -> tuple[Engine, str]:
    """Create a fresh PG sub-DB and return an engine bound to it."""
    base = create_engine(parent_url, isolation_level="AUTOCOMMIT")
    sub = f"pql_109_bus_{uuid.uuid4().hex[:8]}"
    with base.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{sub}"'))
    base.dispose()
    sub_url = parent_url.rsplit("/", 1)[0] + "/" + sub
    engine = create_engine(sub_url)
    # Run alembic to create the outbox table.
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        "pointlessql/alembic",
    )
    cfg.set_main_option("sqlalchemy.url", sub_url)
    command.upgrade(cfg, "head")
    return engine, sub


def _drop_subdb(parent_url: str, sub: str) -> None:
    base = create_engine(parent_url, isolation_level="AUTOCOMMIT")
    with base.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{sub}"'))
    base.dispose()


@pytest.fixture
async def two_bus_engines() -> AsyncIterator[tuple[Engine, str]]:
    """Yield (engine, sub_db_name) for a fresh test DB; tear down on exit."""
    parent = _pg_url()
    engine, sub = _create_subdb_engine(parent)
    try:
        yield engine, sub
    finally:
        engine.dispose()
        _drop_subdb(parent, sub)


async def test_publish_dispatches_to_remote_bus(
    two_bus_engines: tuple[Engine, str],
) -> None:
    """Frame published on bus_a fires the dispatch callback on bus_b."""
    engine, _ = two_bus_engines
    bus_a = CoeditBus(engine, ttl_seconds=60, cleanup_interval_seconds=30)
    bus_b = CoeditBus(engine, ttl_seconds=60, cleanup_interval_seconds=30)
    # Force distinct source pids — both buses live in the same OS
    # process so ``own_pid`` would collide.  Spoofing it lets the
    # self-loop suppression behave like in multi-worker reality.
    bus_a.own_pid = 9001
    bus_b.own_pid = 9002

    received: list[tuple[str, bytes, int]] = []
    arrived = asyncio.Event()

    async def cb_b(nb: str, payload: bytes, src: int) -> None:
        received.append((nb, payload, src))
        arrived.set()

    bus_b.set_dispatch_callback(cb_b)
    await bus_a.start()
    await bus_b.start()
    try:
        # Wait for both listeners to attach to PG before publishing —
        # NOTIFY does not buffer for sessions that subscribe later.
        await asyncio.wait_for(bus_a._listener_ready.wait(), timeout=5.0)  # pyright: ignore[reportPrivateUsage]
        await asyncio.wait_for(bus_b._listener_ready.wait(), timeout=5.0)  # pyright: ignore[reportPrivateUsage]

        nb_uuid = uuid.uuid4().hex
        frame = bytes([0x02]) + b"phase-109-multi-worker-payload"
        await bus_a.publish(nb_uuid, frame)
        await asyncio.wait_for(arrived.wait(), timeout=5.0)

        assert len(received) == 1
        nb, payload, src = received[0]
        assert nb == nb_uuid
        assert payload == frame
        assert src == 9001
    finally:
        await bus_a.stop()
        await bus_b.stop()


async def test_publisher_does_not_dispatch_self_loop(
    two_bus_engines: tuple[Engine, str],
) -> None:
    """A bus skips its own NOTIFY via source_pid suppression."""
    engine, _ = two_bus_engines
    bus = CoeditBus(engine, ttl_seconds=60, cleanup_interval_seconds=30)

    received: list[Any] = []

    async def cb(nb: str, payload: bytes, src: int) -> None:
        received.append((nb, payload, src))

    bus.set_dispatch_callback(cb)
    await bus.start()
    try:
        await asyncio.wait_for(bus._listener_ready.wait(), timeout=5.0)  # pyright: ignore[reportPrivateUsage]
        nb_uuid = uuid.uuid4().hex
        await bus.publish(nb_uuid, bytes([0x02]) + b"self-loop")
        # Give the listener time to (not) fire.
        await asyncio.sleep(0.5)
        assert received == []
    finally:
        await bus.stop()


async def test_cleanup_removes_expired_rows(
    two_bus_engines: tuple[Engine, str],
) -> None:
    """TTL cleanup drops rows older than ``ttl_seconds``."""
    engine, _ = two_bus_engines
    bus = CoeditBus(engine, ttl_seconds=1, cleanup_interval_seconds=30)
    bus.own_pid = 9001
    await bus.start()
    try:
        await asyncio.wait_for(bus._listener_ready.wait(), timeout=5.0)  # pyright: ignore[reportPrivateUsage]
        nb_uuid = uuid.uuid4().hex
        await bus.publish(nb_uuid, bytes([0x02]) + b"will-expire")
        snapshot_before = bus.status_snapshot()
        assert snapshot_before["inflight_outbox_rows"] >= 1
        await asyncio.sleep(1.5)
        deleted = await asyncio.to_thread(
            bus._cleanup_once  # pyright: ignore[reportPrivateUsage]
        )
        assert deleted >= 1
        snapshot_after = bus.status_snapshot()
        assert snapshot_after["inflight_outbox_rows"] == 0
    finally:
        await bus.stop()


async def test_malformed_notify_payload_is_ignored(
    two_bus_engines: tuple[Engine, str],
) -> None:
    """Bus tolerates notify payloads it didn't author (e.g. operator pg_notify)."""
    engine, _ = two_bus_engines
    bus = CoeditBus(engine, ttl_seconds=60, cleanup_interval_seconds=30)

    received: list[Any] = []

    async def cb(*args: Any) -> None:
        received.append(args)

    bus.set_dispatch_callback(cb)
    await bus.start()
    try:
        await asyncio.wait_for(bus._listener_ready.wait(), timeout=5.0)  # pyright: ignore[reportPrivateUsage]
        with engine.begin() as conn:
            conn.execute(
                text("SELECT pg_notify(:ch, :pl)"),
                {"ch": "coedit_bus", "pl": "not-a-valid-payload"},
            )
        await asyncio.sleep(0.5)
        assert received == []
    finally:
        await bus.stop()
