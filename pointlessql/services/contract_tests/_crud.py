"""CRUD for contract tests + fixtures + result reads."""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.models import (
    ASSERTION_KINDS,
    CONTRACT_TEST_SEVERITIES,
    DataProductContractTest,
    DataProductContractTestResult,
    DataProductFixture,
)
from pointlessql.types import SessionFactory


def _serialise_test(row: DataProductContractTest) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "data_product_id": int(row.data_product_id),
        "name": row.name,
        "assertion_kind": row.assertion_kind,
        "assertion_spec_json": row.assertion_spec_json,
        "severity": row.severity,
        "enabled": bool(row.enabled),
        "created_at": row.created_at.isoformat(),
    }


def _serialise_fixture(row: DataProductFixture) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "data_product_id": int(row.data_product_id),
        "table_name": row.table_name,
        "generator_spec_json": row.generator_spec_json,
        "row_count": int(row.row_count),
        "created_at": row.created_at.isoformat(),
    }


def _serialise_result(row: DataProductContractTestResult) -> dict[str, Any]:
    obs: dict[str, Any] = {}
    if row.observation_json:
        try:
            decoded = json.loads(row.observation_json)
            if isinstance(decoded, dict):
                obs = decoded
        except (json.JSONDecodeError, ValueError):
            obs = {"raw": row.observation_json}
    return {
        "id": int(row.id),
        "contract_test_id": int(row.contract_test_id),
        "run_at": row.run_at.isoformat(),
        "status": row.status,
        "observation": obs,
        "duration_ms": row.duration_ms,
    }


def declare_contract_test(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    name: str,
    assertion_kind: str,
    assertion_spec_json: str | dict[str, Any],
    severity: str = "warn",
    enabled: bool = True,
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Idempotent create/update of a contract test for a product."""
    if assertion_kind not in ASSERTION_KINDS:
        raise ValueError(f"unknown assertion_kind: {assertion_kind}")
    if severity not in CONTRACT_TEST_SEVERITIES:
        raise ValueError(f"unknown severity: {severity}")
    if not name.strip():
        raise ValueError("name is required")
    spec_text = (
        assertion_spec_json
        if isinstance(assertion_spec_json, str)
        else json.dumps(assertion_spec_json)
    )
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.scalar(
            select(DataProductContractTest)
            .where(DataProductContractTest.data_product_id == data_product_id)
            .where(DataProductContractTest.name == name.strip())
        )
        if row is None:
            row = DataProductContractTest(
                data_product_id=data_product_id,
                name=name.strip(),
                assertion_kind=assertion_kind,
                assertion_spec_json=spec_text,
                severity=severity,
                enabled=enabled,
                created_by_user_id=created_by_user_id,
                created_at=now,
            )
            session.add(row)
        else:
            row.assertion_kind = assertion_kind
            row.assertion_spec_json = spec_text
            row.severity = severity
            row.enabled = enabled
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("contract test name conflict") from exc
        session.refresh(row)
        return _serialise_test(row)


def list_contract_tests(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    include_disabled: bool = True,
) -> list[dict[str, Any]]:
    """Return every contract test for a product, ordered by id."""
    with session_factory() as session:
        stmt = select(DataProductContractTest).where(
            DataProductContractTest.data_product_id == data_product_id
        )
        if not include_disabled:
            stmt = stmt.where(DataProductContractTest.enabled.is_(True))
        return [
            _serialise_test(r)
            for r in session.scalars(stmt.order_by(DataProductContractTest.id))
        ]


def delete_contract_test(
    session_factory: SessionFactory, *, contract_test_id: int
) -> bool:
    """Remove one contract test row; returns True if a row was deleted."""
    with session_factory() as session:
        row = session.get(DataProductContractTest, contract_test_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def declare_fixture(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    table_name: str,
    generator_spec_json: str | list[dict[str, Any]],
    row_count: int = 100,
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Idempotent create/update of a fixture for a product table."""
    if not table_name.strip():
        raise ValueError("table_name is required")
    spec_text = (
        generator_spec_json
        if isinstance(generator_spec_json, str)
        else json.dumps(generator_spec_json)
    )
    rows = max(1, min(int(row_count), 100_000))
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.scalar(
            select(DataProductFixture)
            .where(DataProductFixture.data_product_id == data_product_id)
            .where(DataProductFixture.table_name == table_name.strip())
        )
        if row is None:
            row = DataProductFixture(
                data_product_id=data_product_id,
                table_name=table_name.strip(),
                generator_spec_json=spec_text,
                row_count=rows,
                created_by_user_id=created_by_user_id,
                created_at=now,
            )
            session.add(row)
        else:
            row.generator_spec_json = spec_text
            row.row_count = rows
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("fixture conflict") from exc
        session.refresh(row)
        return _serialise_fixture(row)


def list_fixtures(
    session_factory: SessionFactory, *, data_product_id: int
) -> list[dict[str, Any]]:
    """Return every fixture row for a product."""
    with session_factory() as session:
        rows = session.scalars(
            select(DataProductFixture)
            .where(DataProductFixture.data_product_id == data_product_id)
            .order_by(DataProductFixture.id)
        ).all()
        return [_serialise_fixture(r) for r in rows]


def delete_fixture(
    session_factory: SessionFactory, *, fixture_id: int
) -> bool:
    """Remove one fixture row; returns True if a row was deleted."""
    with session_factory() as session:
        row = session.get(DataProductFixture, fixture_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_results(
    session_factory: SessionFactory,
    *,
    contract_test_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return the most recent result rows for one test, newest-first."""
    with session_factory() as session:
        rows = session.scalars(
            select(DataProductContractTestResult)
            .where(
                DataProductContractTestResult.contract_test_id == contract_test_id
            )
            .order_by(DataProductContractTestResult.run_at.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        ).all()
        return [_serialise_result(r) for r in rows]
