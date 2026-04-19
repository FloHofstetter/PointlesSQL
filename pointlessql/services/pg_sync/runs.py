"""End-to-end sync orchestration + ``SyncRun`` bookkeeping."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import SyncRun
from pointlessql.services.pg_sync.diff import (
    apply_diff,
    collect_uc_tables,
    diff_snapshots,
)
from pointlessql.services.pg_sync.dsn import build_dsn, effective_options
from pointlessql.services.pg_sync.types import PostgresIntrospector
from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)


def _start_run(session: Session, catalog_name: str) -> SyncRun:
    """Insert the initial ``running`` :class:`SyncRun` row."""
    run = SyncRun(
        catalog_name=catalog_name,
        started_at=datetime.datetime.now(datetime.UTC),
        status="running",
        added_count=0,
        changed_count=0,
        dropped_count=0,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _finish_run(
    session: Session,
    run_id: int,
    status: str,
    added: int,
    changed: int,
    dropped: int,
    error: str | None,
) -> None:
    """Flip a :class:`SyncRun` from ``running`` to its terminal status."""
    run = session.get(SyncRun, run_id)
    if run is None:  # pragma: no cover — row was just inserted
        return
    run.status = status
    run.finished_at = datetime.datetime.now(datetime.UTC)
    run.added_count = added
    run.changed_count = changed
    run.dropped_count = dropped
    run.error = error
    session.commit()


async def run_sync(
    uc: UnityCatalogClient,
    factory: sessionmaker[Session],
    catalog_name: str,
    introspector: PostgresIntrospector,
    connection: dict[str, Any],
    credential: dict[str, Any] | None,
    schema_filter: Sequence[str] | None = None,
) -> SyncRun:
    """End-to-end: introspect Postgres, diff, apply, record.

    The high-level orchestration glue: wire the passed introspector
    into the same ``SyncRun`` bookkeeping the API route and the
    future scheduler both depend on. Always writes exactly one row
    — the ``running`` placeholder is updated in place so the history
    card never shows half-formed entries.

    Args:
        uc: UnityCatalog facade to drive.
        factory: SQLAlchemy session factory (our own metadata DB).
        catalog_name: Foreign catalog to sync.
        introspector: Source of the Postgres snapshot.
        connection: ``ConnectionInfo.to_dict()`` payload for the
            catalog's bound connection.
        credential: Optional ``CredentialInfo.to_dict()`` payload that
            supplies secrets the connection options do not carry.
        schema_filter: Optional list of Postgres schema names to sync;
            ``None`` means every non-system schema.

    Returns:
        The final :class:`SyncRun` row (post-commit).
    """
    with factory() as session:
        run = _start_run(session, catalog_name)
        run_id = run.id

    added = 0
    changed = 0
    dropped = 0
    error: str | None = None

    try:
        options = effective_options(connection, credential)
        dsn = build_dsn(options)
        snapshot = introspector.snapshot(dsn, schema_filter)
        uc_tables = await collect_uc_tables(uc, catalog_name)
        diff = diff_snapshots(snapshot, uc_tables)
        logger.info(
            "pg_sync: catalog=%s add_schemas=%d add_tables=%d change_tables=%d drop_tables=%d",
            catalog_name,
            len(diff.add_schemas),
            len(diff.add_tables),
            len(diff.change_tables),
            len(diff.drop_tables),
        )
        added, changed, dropped = await apply_diff(uc, catalog_name, diff)
        status = "succeeded"
    except Exception as exc:  # noqa: BLE001 — pg_sync records every failure type onto the run row
        error = str(exc)
        status = "failed"
        logger.exception("pg_sync: sync failed for catalog=%s", catalog_name)

    with factory() as session:
        _finish_run(session, run_id, status, added, changed, dropped, error)
        final = session.get(SyncRun, run_id)
        assert final is not None  # just written
        # Detach so the caller can read attributes after the session closes.
        session.expunge(final)
        return final


def list_recent_runs(
    factory: sessionmaker[Session], catalog_name: str, limit: int = 20
) -> list[SyncRun]:
    """Return the last *limit* :class:`SyncRun` rows for *catalog_name*.

    Ordered newest-first. Powers the sync-history card on the
    foreign-catalog detail page.

    Args:
        factory: SQLAlchemy session factory.
        catalog_name: Target catalog.
        limit: Maximum number of rows to return.

    Returns:
        A list of :class:`SyncRun` objects, most recent first.
    """
    from sqlalchemy import select

    with factory() as session:
        rows = session.scalars(
            select(SyncRun)
            .where(SyncRun.catalog_name == catalog_name)
            .order_by(SyncRun.started_at.desc())
            .limit(limit)
        ).all()
        # Detach so the caller renders attributes outside the session.
        for r in rows:
            session.expunge(r)
        return list(rows)
