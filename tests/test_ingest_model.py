"""Phase 82.0 — IngestSource model round-trip + index uniqueness.

Smoke-tests that the ORM model maps cleanly to its alembic-managed
table.  The route layer in Phase 82.1 is what enforces JSON validity
on ``config`` / ``secrets`` / ``table_mappings`` — these tests only
make sure the column types and unique constraint behave.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.models import IngestSource


def _make_source(
    *,
    workspace_id: int,
    owner_user_id: int,
    name: str,
    kind: str = "postgres",
    config: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    mappings: list[dict[str, str]] | None = None,
) -> IngestSource:
    now = datetime.datetime.now(datetime.UTC)
    return IngestSource(
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        name=name,
        kind=kind,
        config=json.dumps(config or {}),
        secrets=json.dumps(secrets or {}),
        table_mappings=json.dumps(mappings or []),
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_ingest_source_persists_round_trip() -> None:
    """Insert + read recovers every column verbatim."""
    factory = app.state.session_factory
    with factory() as session:
        source = _make_source(
            workspace_id=1,
            owner_user_id=1,
            name="pg-prod-replica",
            config={"host": "db.internal", "db": "orders"},
            secrets={"password": "s3cr3t"},
            mappings=[
                {
                    "source_table": "public.orders",
                    "target_fqn": "main.sales.orders",
                    "mode": "full",
                }
            ],
        )
        session.add(source)
        session.commit()
        source_id = source.id

    with factory() as session:
        loaded = session.get(IngestSource, source_id)
        assert loaded is not None
        assert loaded.workspace_id == 1
        assert loaded.kind == "postgres"
        config = json.loads(loaded.config)
        assert config["host"] == "db.internal"
        secrets = json.loads(loaded.secrets)
        assert secrets["password"] == "s3cr3t"
        mappings = json.loads(loaded.table_mappings)
        assert len(mappings) == 1
        assert mappings[0]["target_fqn"] == "main.sales.orders"
        assert loaded.is_active is True
        # Clean up so subsequent tests start fresh.
        session.delete(loaded)
        session.commit()


def test_ingest_source_name_unique_per_workspace() -> None:
    """Two sources with the same ``(workspace_id, name)`` violate UNIQUE."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            _make_source(workspace_id=1, owner_user_id=1, name="duplicate-name")
        )
        session.commit()

    with factory() as session:
        session.add(
            _make_source(workspace_id=1, owner_user_id=1, name="duplicate-name")
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Cleanup
    with factory() as session:
        for src in session.query(IngestSource).all():
            session.delete(src)
        session.commit()
