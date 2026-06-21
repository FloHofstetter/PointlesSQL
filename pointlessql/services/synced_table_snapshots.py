"""CRUD + lifecycle for synced-table snapshots / branches.

The management layer behind Lakebase-style git branching: create a named
snapshot of a synced table (capturing the Delta version + row count the
serving mirror held at that moment), promote one as the serving
baseline, or discard / delete it.  Every operation is metadata-only —
the serving Postgres mirror is never written from here; the
copy-on-write storage that a real branch needs is out of scope.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import SNAPSHOT_STATUSES, SyncedTable, SyncedTableSnapshot


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _serialize(row: SyncedTableSnapshot) -> dict[str, Any]:
    """Render a snapshot row into a JSON-safe dict."""
    return {
        "id": row.id,
        "synced_table_id": row.synced_table_id,
        "name": row.name,
        "source_version": row.source_version,
        "rows_snapshot": row.rows_snapshot,
        "status": row.status,
        "note": row.note,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_snapshot(
    factory: sessionmaker[Session],
    *,
    synced_table_id: int,
    name: str,
    note: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Capture a named snapshot of a synced table's current state.

    Args:
        factory: Session factory.
        synced_table_id: The owning synced table.
        name: Snapshot identifier, unique per synced table.
        note: Optional rationale.
        created_by: Creating principal's e-mail.

    Returns:
        The serialized new snapshot.

    Raises:
        ValidationError: When the synced table is unknown, the name is
            empty, or the name is already taken on that table.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("snapshot name is required")
    now = _utcnow()
    with factory() as session:
        table = session.get(SyncedTable, synced_table_id)
        if table is None:
            raise ValidationError(f"synced table {synced_table_id} not found")
        existing = session.scalar(
            select(SyncedTableSnapshot).where(
                SyncedTableSnapshot.synced_table_id == synced_table_id,
                SyncedTableSnapshot.name == clean_name,
            )
        )
        if existing is not None:
            raise ValidationError(f"snapshot {clean_name!r} already exists on this table")
        row = SyncedTableSnapshot(
            workspace_id=table.workspace_id,
            synced_table_id=synced_table_id,
            name=clean_name,
            source_version=table.last_synced_version,
            rows_snapshot=table.rows_synced,
            status="active",
            note=(note or "").strip() or None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            # A concurrent create raced past the existence check above.
            session.rollback()
            raise ValidationError(f"snapshot {clean_name!r} already exists on this table") from exc
        session.refresh(row)
        return _serialize(row)


def list_snapshots(factory: sessionmaker[Session], *, synced_table_id: int) -> list[dict[str, Any]]:
    """List a synced table's snapshots, newest first.

    Args:
        factory: Session factory.
        synced_table_id: The owning synced table.

    Returns:
        Serialized snapshot dicts.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(SyncedTableSnapshot)
                .where(SyncedTableSnapshot.synced_table_id == synced_table_id)
                .order_by(SyncedTableSnapshot.created_at.desc(), SyncedTableSnapshot.id.desc())
            ).all()
        )
        return [_serialize(row) for row in rows]


def _set_status(
    factory: sessionmaker[Session], *, snapshot_id: int, synced_table_id: int, status: str
) -> dict[str, Any]:
    """Transition a snapshot to *status*, returning the updated row.

    Args:
        factory: Session factory.
        snapshot_id: Target snapshot.
        synced_table_id: The owning synced table; a snapshot belonging to
            any other table is treated as missing so a caller can only
            ever act on snapshots of a table it already resolved.
        status: New status (a member of :data:`SNAPSHOT_STATUSES`).

    Returns:
        The serialized, updated snapshot.

    Raises:
        ValidationError: On an unknown status or missing snapshot.
    """
    if status not in SNAPSHOT_STATUSES:
        raise ValidationError(f"status must be one of {list(SNAPSHOT_STATUSES)}")
    with factory() as session:
        row = session.get(SyncedTableSnapshot, snapshot_id)
        if row is None or row.synced_table_id != synced_table_id:
            raise ValidationError(f"snapshot {snapshot_id} not found")
        # Promoting one snapshot demotes any sibling baseline so a synced
        # table only ever has a single promoted serving branch.
        if status == "promoted":
            siblings = session.scalars(
                select(SyncedTableSnapshot).where(
                    SyncedTableSnapshot.synced_table_id == row.synced_table_id,
                    SyncedTableSnapshot.status == "promoted",
                    SyncedTableSnapshot.id != snapshot_id,
                )
            ).all()
            for sibling in siblings:
                sibling.status = "active"
                sibling.updated_at = _utcnow()
        row.status = status
        row.updated_at = _utcnow()
        session.commit()
        session.refresh(row)
        return _serialize(row)


def promote_snapshot(
    factory: sessionmaker[Session], *, snapshot_id: int, synced_table_id: int
) -> dict[str, Any]:
    """Promote a snapshot to the serving baseline (demotes any sibling).

    Args:
        factory: Session factory.
        snapshot_id: Target snapshot.
        synced_table_id: The owning synced table (ownership guard).

    Returns:
        The serialized, promoted snapshot.
    """
    return _set_status(
        factory, snapshot_id=snapshot_id, synced_table_id=synced_table_id, status="promoted"
    )


def discard_snapshot(
    factory: sessionmaker[Session], *, snapshot_id: int, synced_table_id: int
) -> dict[str, Any]:
    """Soft-discard a snapshot (tombstoned, kept for audit).

    Args:
        factory: Session factory.
        snapshot_id: Target snapshot.
        synced_table_id: The owning synced table (ownership guard).

    Returns:
        The serialized, discarded snapshot.
    """
    return _set_status(
        factory, snapshot_id=snapshot_id, synced_table_id=synced_table_id, status="discarded"
    )


def delete_snapshot(
    factory: sessionmaker[Session], *, snapshot_id: int, synced_table_id: int
) -> bool:
    """Hard-delete a snapshot row.

    Args:
        factory: Session factory.
        snapshot_id: Target snapshot.
        synced_table_id: The owning synced table; a snapshot belonging to
            any other table is treated as missing.

    Returns:
        ``True`` when a row was removed.
    """
    with factory() as session:
        row = session.get(SyncedTableSnapshot, snapshot_id)
        if row is None or row.synced_table_id != synced_table_id:
            return False
        session.delete(row)
        session.commit()
    return True
