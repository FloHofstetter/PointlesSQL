"""end-to-end SQLite → Postgres migration tool.

Tests the operator-facing :mod:`pointlessql.cli.migrate_to_postgres`
helper.  All non-validation cases require a live Postgres so they
carry the ``@pytest.mark.postgres`` marker — the SQLite CI lane
selects them out via the ``addopts = "-m 'not integration'"``
pytest rule and the ``postgres`` marker, while the PG
lane runs them with ``TEST_DATABASE_URL`` pointing at the live PG.
"""

from __future__ import annotations

import datetime as dt
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from pointlessql.cli import migrate_to_postgres as mtp
from pointlessql.db import _alembic_config  # pyright: ignore[reportPrivateUsage]
from pointlessql.models import AgentRun, Workspace


def _make_sqlite_source() -> str:
    """Create a fresh SQLite DB, run alembic, seed a few rows.

    Returns:
        SQLAlchemy URL for the seeded SQLite source.
    """
    fd, path = tempfile.mkstemp(prefix="pql_30_3_src_", suffix=".db")
    os.close(fd)
    Path(path).unlink()  # alembic creates the file
    url = f"sqlite:///{path}"

    from alembic import command  # noqa: PLC0415

    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine)
    with factory() as session:
        # Bootstrap default workspace if not already seeded by a
        # migration (the chain currently leaves it to the runtime).
        existing = session.get(Workspace, 1)
        if existing is None:
            session.add(
                Workspace(
                    id=1,
                    slug="default",
                    name="Default workspace",
                    description="Migrate-to-PG fixture seed.",
                    created_at=dt.datetime.now(dt.UTC),
                )
            )
            session.commit()
        for i in range(3):
            session.add(
                AgentRun(
                    id=str(uuid.uuid4()),
                    principal=f"alice-{i}@test",
                    agent_id="searcher",
                    notebook_path=f"alice/job_{i}.py",
                    source_snapshot_sha="0" * 64,
                    status="succeeded",
                    started_at=dt.datetime.now(dt.UTC),
                )
            )
        session.commit()
    engine.dispose()
    return url


# ---------------------------------------------------------------------------
# Validation — runs without a live PG.
# ---------------------------------------------------------------------------


def test_ensure_dialects_rejects_non_sqlite_source() -> None:
    with pytest.raises(mtp.MigrationError, match="must be a sqlite URL"):
        mtp._ensure_dialects("postgresql://x", "postgresql://y")  # pyright: ignore[reportPrivateUsage]


def test_ensure_dialects_rejects_non_pg_target() -> None:
    with pytest.raises(mtp.MigrationError, match="must be a postgresql URL"):
        mtp._ensure_dialects("sqlite:///x", "sqlite:///y")  # pyright: ignore[reportPrivateUsage]


def test_copy_set_covers_every_portable_orm_table() -> None:
    """The copy set is every ORM table minus the explicit non-portable allowlist.

    Guards the silent-data-loss regression: a hand-maintained table tuple
    copied only 38 of 185 tables (two names even stale) yet reported
    success. The runtime ordering must track the model registry exactly.
    """
    from pointlessql.models import Base

    copied = set(mtp._ordered_table_names())  # pyright: ignore[reportPrivateUsage]
    expected = set(Base.metadata.tables) - mtp._NON_PORTABLE_TABLES  # pyright: ignore[reportPrivateUsage]
    assert copied == expected
    # The previously-dropped real table is now covered; the stale names
    # that masked it are gone.
    assert "sync_run" in copied
    assert {"sync_runs", "job_steps"}.isdisjoint(copied)


def test_copy_order_is_fk_safe() -> None:
    """Every table is copied after the tables its foreign keys reference.

    A child copied before its parent would fail the FK insert on Postgres,
    so the parent→child ordering is the contract the bulk copy depends on.
    """
    from pointlessql.models import Base

    names = mtp._ordered_table_names()  # pyright: ignore[reportPrivateUsage]
    position = {name: i for i, name in enumerate(names)}
    for table in Base.metadata.sorted_tables:
        if table.name not in position:
            continue
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            if parent == table.name or parent not in position:
                continue  # self-FK / non-portable parent — not an ordering constraint
            assert position[parent] <= position[table.name], (
                f"{table.name} copied before its FK parent {parent}"
            )


def test_pinned_roots_lead_the_copy_order() -> None:
    """The pinned FK-root tables head the order so children never race them."""
    names = mtp._ordered_table_names()  # pyright: ignore[reportPrivateUsage]
    assert names[: len(mtp._PIN_FIRST)] == list(mtp._PIN_FIRST)  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# End-to-end — requires PG.
# ---------------------------------------------------------------------------


@pytest.mark.postgres
def test_migrate_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite → PG bulk-copy preserves agent_runs row count and ids."""
    target_url = os.environ.get("TEST_DATABASE_URL")
    if not target_url or "postgresql" not in target_url:
        pytest.skip("TEST_DATABASE_URL must point at PG for migrate tests")

    # Use a dedicated DB so we don't collide with the autouse fixture.
    base_engine = create_engine(target_url, isolation_level="AUTOCOMMIT")
    sub_db = f"pql_30_3_e2e_{uuid.uuid4().hex[:8]}"
    with base_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{sub_db}"'))
    base_engine.dispose()

    sub_target = target_url.rsplit("/", 1)[0] + "/" + sub_db
    source_url = _make_sqlite_source()
    try:
        summary = mtp.migrate(
            source_url=source_url,
            target_url=sub_target,
            batch_size=10,
            dry_run=False,
        )
        assert summary["sequence_sync"] is True
        assert summary["tables"]["agent_runs"] == 3
        verify = summary["verify"]
        assert verify["agent_runs"]["source"] == verify["agent_runs"]["target"] == 3
    finally:
        # Tear the sub-DB down even when the test fails.
        base_engine = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with base_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{sub_db}"'))
        base_engine.dispose()
        Path(source_url.replace("sqlite:///", "")).unlink(missing_ok=True)


@pytest.mark.postgres
def test_migrate_refuses_non_empty_target() -> None:
    """Refuse to copy into a PG with rows already in non-workspace tables."""
    target_url = os.environ.get("TEST_DATABASE_URL")
    if not target_url or "postgresql" not in target_url:
        pytest.skip("TEST_DATABASE_URL must point at PG for migrate tests")

    base_engine = create_engine(target_url, isolation_level="AUTOCOMMIT")
    sub_db = f"pql_30_3_refuse_{uuid.uuid4().hex[:8]}"
    with base_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{sub_db}"'))
    base_engine.dispose()

    sub_target = target_url.rsplit("/", 1)[0] + "/" + sub_db

    # Run alembic + seed an agent_run on the target so the refuse-check trips.
    from alembic import command  # noqa: PLC0415

    cfg = _alembic_config(sub_target)
    command.upgrade(cfg, "head")
    engine = create_engine(sub_target)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        # Need a workspace seed for the FK.
        if session.get(Workspace, 1) is None:
            session.add(
                Workspace(
                    id=1,
                    slug="default",
                    name="Default",
                    created_at=dt.datetime.now(dt.UTC),
                )
            )
            session.commit()
        session.add(
            AgentRun(
                id=str(uuid.uuid4()),
                principal="prior@test",
                agent_id="x",
                notebook_path="x.py",
                source_snapshot_sha="0" * 64,
                status="succeeded",
                started_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()
    engine.dispose()

    source_url = _make_sqlite_source()
    try:
        with pytest.raises(mtp.MigrationError, match="refuse to overwrite"):
            mtp.migrate(
                source_url=source_url,
                target_url=sub_target,
                batch_size=10,
                dry_run=False,
            )
    finally:
        base_engine = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with base_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{sub_db}"'))
        base_engine.dispose()
        Path(source_url.replace("sqlite:///", "")).unlink(missing_ok=True)


def test_migrate_dry_run_writes_nothing(tmp_path: Path) -> None:
    """``--dry-run`` returns counts without touching the target."""
    source_url = _make_sqlite_source()
    # Use a non-PG target URL that would normally be valid; dry-run
    # should NOT actually touch it (no connection is opened beyond
    # SQLAlchemy's lazy ``create_engine``).
    target_url = "postgresql+psycopg://nobody:nopass@unreachable.invalid:5432/none"
    try:
        summary = mtp.migrate(
            source_url=source_url,
            target_url=target_url,
            batch_size=10,
            dry_run=True,
        )
    finally:
        Path(source_url.replace("sqlite:///", "")).unlink(missing_ok=True)
    assert summary["dry_run"] is True
    assert summary["tables"]["agent_runs"] == 3
    assert summary["sequence_sync"] is False
    assert summary["fts_rebuild"] is False
