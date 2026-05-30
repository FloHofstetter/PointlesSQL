"""CRUD for the output-port schema-version history."""

from __future__ import annotations

import datetime
import json
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import DataProductOutputPort, OutputPortSchemaVersion
from pointlessql.services.schema_versioning._bumper import propose_bump
from pointlessql.services.schema_versioning._diff import (
    SchemaDiff,
    compute_diff,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


def list_versions(
    session_factory: _SessionFactory, *, output_port_id: int
) -> list[dict[str, Any]]:
    """Return every history row for one port, newest first."""
    with session_factory() as session:
        rows = session.scalars(
            select(OutputPortSchemaVersion)
            .where(OutputPortSchemaVersion.output_port_id == output_port_id)
            .order_by(OutputPortSchemaVersion.bumped_at.desc())
        ).all()
        return [_serialise(r) for r in rows]


def get_version_history(
    session_factory: _SessionFactory, *, output_port_id: int
) -> list[dict[str, Any]]:
    """Alias for :func:`list_versions` (matches plan vocabulary)."""
    return list_versions(session_factory, output_port_id=output_port_id)


def current_schema(
    session_factory: _SessionFactory, *, output_port_id: int
) -> dict[str, Any] | None:
    """Return the most recent ``schema_json`` decoded as a dict."""
    with session_factory() as session:
        row = session.scalar(
            select(OutputPortSchemaVersion)
            .where(OutputPortSchemaVersion.output_port_id == output_port_id)
            .order_by(OutputPortSchemaVersion.bumped_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        try:
            decoded = json.loads(row.schema_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return decoded if isinstance(decoded, dict) else None


def bump_port_version(
    session_factory: _SessionFactory,
    *,
    output_port_id: int,
    new_schema: dict[str, Any],
    change_summary: str | None = None,
    bumped_by_user_id: int | None = None,
) -> tuple[dict[str, Any], SchemaDiff]:
    """Compute + persist the next semver for *output_port_id*.

    Returns:
        ``(history_row_dict, diff)`` — the persisted row and the diff
        between previous and presented schema.  When the diff is a
        no-op the persistence step is skipped and the current row is
        returned.

    Raises:
        LookupError: When *output_port_id* does not exist.
    """
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        port = session.get(DataProductOutputPort, output_port_id)
        if port is None:
            raise LookupError(f"output port {output_port_id} not found")
        current_row = session.scalar(
            select(OutputPortSchemaVersion)
            .where(OutputPortSchemaVersion.output_port_id == output_port_id)
            .order_by(OutputPortSchemaVersion.bumped_at.desc())
            .limit(1)
        )
        prior: dict[str, Any] | None = None
        if current_row is not None:
            try:
                decoded = json.loads(current_row.schema_json)
                if isinstance(decoded, dict):
                    prior = decoded
            except (json.JSONDecodeError, TypeError, ValueError):
                prior = None
        diff = compute_diff(prior, new_schema)
        next_semver, kind = propose_bump(
            port.version_semver or "0.1.0", diff
        )
        if kind == "none" and current_row is not None:
            return _serialise(current_row), diff
        new_row = OutputPortSchemaVersion(
            output_port_id=output_port_id,
            version_semver=next_semver,
            schema_json=json.dumps(new_schema, sort_keys=True),
            change_kind=kind if kind != "none" else "patch",
            change_summary=change_summary,
            bumped_at=now,
            bumped_by_user_id=bumped_by_user_id,
        )
        session.add(new_row)
        port.version_semver = next_semver
        session.commit()
        session.refresh(new_row)
        return _serialise(new_row), diff


def _serialise(row: OutputPortSchemaVersion) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "output_port_id": int(row.output_port_id),
        "version_semver": row.version_semver,
        "change_kind": row.change_kind,
        "change_summary": row.change_summary,
        "bumped_at": row.bumped_at.isoformat(),
        "bumped_by_user_id": row.bumped_by_user_id,
        "schema": json.loads(row.schema_json) if row.schema_json else None,
    }
