"""Tests for the audit log service.

Sprint 48 extended the surface:

* Append-only ORM guards (UPDATE always blocked, DELETE only
  inside :func:`_allow_audit_mutation`).
* JSON-encodable ``detail`` (dict → JSON-string round trip).
* New ``actor_role`` + ``client_ip`` columns.
* :func:`cleanup_old_entries` with a configurable retention window.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import AuditLog, Base
from pointlessql.services.audit import (
    AuditIntegrityError,
    cleanup_old_entries,
    log_action,
)
from pointlessql.services.audit._core import (
    _allow_audit_mutation,  # noqa: PLC2701  # test reaches private contextmanager
)


def _make_factory() -> sessionmaker[Session]:
    """Create an in-memory DB with the audit_log table.

    StaticPool keeps the schema visible across any
    ``asyncio.to_thread``-style fan-out that a caller might do.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class TestLogAction:
    def test_inserts_row(self) -> None:
        factory = _make_factory()
        log_action(factory, 1, "user@test.com", "update_catalog", "catalog:my_cat")

        with factory() as session:
            rows = session.execute(select(AuditLog)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == 1
        assert row.user_email == "user@test.com"
        assert row.action == "update_catalog"
        assert row.target == "catalog:my_cat"
        assert row.detail is None
        # Sprint 48 defaults.
        assert row.actor_role == "user"
        assert row.client_ip is None
        assert isinstance(row.created_at, datetime.datetime)

    def test_with_string_detail_legacy(self) -> None:
        """Pre-Sprint-48 string detail still round-trips verbatim."""
        factory = _make_factory()
        log_action(
            factory,
            2,
            "admin@test.com",
            "grant_permission",
            "catalog:my_cat",
            detail='{"privilege": "USE CATALOG"}',
        )

        with factory() as session:
            rows = session.execute(select(AuditLog)).scalars().all()
        assert rows[0].detail == '{"privilege": "USE CATALOG"}'

    def test_dict_detail_is_json_encoded(self) -> None:
        """Sprint 48: dict detail is JSON-encoded before insert."""
        factory = _make_factory()
        log_action(
            factory,
            2,
            "admin@test.com",
            "update_catalog",
            "catalog:my_cat",
            detail={"comment": "new", "owner": "alice"},
        )

        with factory() as session:
            row = session.execute(select(AuditLog)).scalars().one()
        assert row.detail is not None
        parsed = json.loads(row.detail)
        assert parsed == {"comment": "new", "owner": "alice"}

    def test_actor_role_and_client_ip_persisted(self) -> None:
        factory = _make_factory()
        log_action(
            factory,
            3,
            "admin@test.com",
            "delete_connection",
            "connection:prod",
            actor_role="admin",
            client_ip="203.0.113.42",
        )

        with factory() as session:
            row = session.execute(select(AuditLog)).scalars().one()
        assert row.actor_role == "admin"
        assert row.client_ip == "203.0.113.42"

    def test_multiple_entries(self) -> None:
        factory = _make_factory()
        log_action(factory, 1, "a@test.com", "view_catalog", "catalog:cat1")
        log_action(factory, 2, "b@test.com", "update_schema", "schema:cat1.sch1")
        log_action(factory, 1, "a@test.com", "delete_connection", "connection:pg1")

        with factory() as session:
            rows = session.execute(select(AuditLog)).scalars().all()
        assert len(rows) == 3
        assert {r.action for r in rows} == {
            "view_catalog",
            "update_schema",
            "delete_connection",
        }


class TestAppendOnlyGuards:
    """Sprint 48: AuditLog rows cannot be mutated after insert."""

    def test_update_is_blocked(self) -> None:
        factory = _make_factory()
        log_action(factory, 1, "user@test.com", "update_catalog", "catalog:my_cat")

        with factory() as session:  # noqa: SIM117
            row = session.execute(select(AuditLog)).scalars().one()
            row.user_email = "tampered@evil.com"
            with pytest.raises(AuditIntegrityError, match="UPDATE"):
                session.commit()

    def test_delete_outside_cleanup_is_blocked(self) -> None:
        factory = _make_factory()
        log_action(factory, 1, "user@test.com", "update_catalog", "catalog:my_cat")

        with factory() as session:  # noqa: SIM117
            row = session.execute(select(AuditLog)).scalars().one()
            session.delete(row)
            with pytest.raises(AuditIntegrityError, match="DELETE"):
                session.commit()

    def test_delete_inside_allow_scope_succeeds(self) -> None:
        factory = _make_factory()
        log_action(factory, 1, "user@test.com", "update_catalog", "catalog:my_cat")

        with factory() as session, _allow_audit_mutation():
            row = session.execute(select(AuditLog)).scalars().one()
            session.delete(row)
            session.commit()
        with factory() as session:
            assert session.execute(select(AuditLog)).scalars().all() == []


class TestCleanup:
    """Sprint 48: retention sweep deletes rows older than the cutoff."""

    def _insert_with_timestamp(
        self,
        factory: sessionmaker[Session],
        *,
        created_at: datetime.datetime,
        action: str,
    ) -> None:
        """Insert a row bypassing ``log_action`` so we can backdate ``created_at``."""
        with factory() as session:
            entry = AuditLog(
                user_id=1,
                user_email="u@test.com",
                actor_role="user",
                action=action,
                target="catalog:x",
                client_ip=None,
                detail=None,
                created_at=created_at,
            )
            session.add(entry)
            session.commit()

    def test_retention_zero_keeps_everything(self) -> None:
        """retention_days=0 disables cleanup (pre-Sprint-48 behaviour)."""
        factory = _make_factory()
        old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1000)
        self._insert_with_timestamp(factory, created_at=old, action="ancient")

        assert cleanup_old_entries(factory, 0) == 0
        with factory() as session:
            assert len(session.execute(select(AuditLog)).scalars().all()) == 1

    def test_old_rows_deleted_fresh_kept(self) -> None:
        factory = _make_factory()
        now = datetime.datetime.now(datetime.UTC)
        self._insert_with_timestamp(
            factory, created_at=now - datetime.timedelta(days=400), action="ancient"
        )
        self._insert_with_timestamp(
            factory, created_at=now - datetime.timedelta(days=10), action="recent"
        )

        deleted = cleanup_old_entries(factory, retention_days=365)

        assert deleted == 1
        with factory() as session:
            remaining = session.execute(select(AuditLog)).scalars().all()
        assert [r.action for r in remaining] == ["recent"]

    def test_cleanup_survives_db_error(self) -> None:
        """Broken factory → cleanup swallows and returns 0 (never crashes)."""

        def broken_factory() -> Session:
            raise RuntimeError("db offline")

        deleted = cleanup_old_entries(broken_factory, retention_days=90)  # type: ignore[arg-type]
        assert deleted == 0
