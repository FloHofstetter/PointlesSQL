"""Tests for the audit log service."""

from __future__ import annotations

import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import AuditLog, Base
from pointlessql.services.audit import log_action


def _make_factory() -> sessionmaker[Session]:
    """Create an in-memory DB with the audit_log table."""
    engine = create_engine("sqlite:///:memory:")
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
        assert isinstance(row.created_at, datetime.datetime)

    def test_with_detail(self) -> None:
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
        assert len(rows) == 1
        assert rows[0].detail == '{"privilege": "USE CATALOG"}'

    def test_multiple_entries(self) -> None:
        factory = _make_factory()
        log_action(factory, 1, "a@test.com", "view_catalog", "catalog:cat1")
        log_action(factory, 2, "b@test.com", "update_schema", "schema:cat1.sch1")
        log_action(factory, 1, "a@test.com", "delete_connection", "connection:pg1")

        with factory() as session:
            rows = session.execute(select(AuditLog)).scalars().all()
        assert len(rows) == 3
        assert {r.action for r in rows} == {"view_catalog", "update_schema", "delete_connection"}
