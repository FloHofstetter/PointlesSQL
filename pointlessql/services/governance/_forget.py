"""Right-to-be-forgotten — the control-port's privileged deletion op.

A forget request names a data subject by ``(column, value)``.  An
agent may *propose* one (a hash-only ledger row, no deletion); a
steward/admin *executes* it, deleting the subject's rows across every
declared table that carries the column.  The subject value is stored
only as an HMAC — the ledger that records the erasure must never itself
become a copy of the PII.

Scope is single-product fan-out: the deletion touches the addressed
product's declared tables only.  Mesh-wide, lineage-driven cascade
deletion across downstream products is a later capability.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import DataProductForgetRequest
from pointlessql.services.pii._redactor import (
    get_or_create_pii_hash_secret,
    hash_value,
)
from pointlessql.types import SessionFactory


def hash_subject(session_factory: Any, value: str) -> str:
    """Return the install-keyed HMAC of a subject value.

    Args:
        session_factory: Sessionmaker callable (for the hash secret).
        value: The raw subject value.

    Returns:
        The hex HMAC digest stored in the ledger.
    """
    secret = get_or_create_pii_hash_secret(session_factory)
    return hash_value(value, secret=secret) or ""


def propose_forget(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    subject_column: str,
    subject_value: str,
    requested_by_user_id: int | None = None,
    agent_run_id: int | None = None,
) -> DataProductForgetRequest:
    """Record a ``proposed`` forget request (no deletion runs).

    Returns:
        The detached ledger row.

    Raises:
        ValueError: When column / value are empty.
    """
    subject_column = subject_column.strip()
    if not subject_column or not subject_value:
        raise ValueError("subject_column and subject_value are required")
    now = datetime.datetime.now(datetime.UTC)
    row = DataProductForgetRequest(
        data_product_id=data_product_id,
        subject_column=subject_column,
        subject_value_hash=hash_subject(session_factory, subject_value),
        status="proposed",
        tables_affected_json="[]",
        requested_by_user_id=requested_by_user_id,
        agent_run_id=agent_run_id,
        created_at=now,
    )
    with session_factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def execute_forget(
    session_factory: SessionFactory,
    settings: Any,
    *,
    data_product_id: int,
    catalog: str,
    schema: str,
    subject_column: str,
    subject_value: str,
    declared_tables: list[tuple[str, list[str]]],
    principal: str | None,
    executed_by_user_id: int | None = None,
    request_id: int | None = None,
) -> dict[str, Any]:
    """Delete the subject's rows across declared tables, then stamp the ledger.

    Args:
        session_factory: Sessionmaker callable.
        settings: App :class:`Settings` (for the PQL client).
        data_product_id: Product whose tables to scrub.
        catalog: UC catalog segment.
        schema: UC schema segment.
        subject_column: Identifying column (must be declared on at
            least one table).
        subject_value: Raw value to erase — used for the delete
            predicate and the ledger hash; never persisted raw.
        declared_tables: ``[(table_name, [column, ...])]`` from the
            product contract; only tables carrying ``subject_column``
            are touched.
        principal: Effective principal email for the UC client, or
            ``None`` for the service client.
        executed_by_user_id: The steward/admin running the op.
        request_id: When executing a prior ``proposed`` row, its id —
            the supplied value's hash must match the stored hash;
            ``None`` creates a fresh ``executed`` row.

    Returns:
        ``{"request_id", "rows_deleted", "tables_affected", "status"}``.

    Raises:
        ValueError: On empty inputs, an undeclared column, or a
            proposal whose stored hash does not match the supplied
            value.
    """
    subject_column = subject_column.strip()
    if not subject_column or not subject_value:
        raise ValueError("subject_column and subject_value are required")

    targets = [name for name, columns in declared_tables if subject_column in columns]
    if not targets:
        raise ValueError(f"column {subject_column!r} is not declared on any table of this product")

    value_hash = hash_subject(session_factory, subject_value)
    if request_id is not None:
        with session_factory() as session:
            existing = session.get(DataProductForgetRequest, request_id)
            if existing is None or existing.data_product_id != data_product_id:
                raise ValueError(f"forget request id={request_id} not found for this product")
            if existing.subject_value_hash != value_hash:
                raise ValueError("supplied subject value does not match the proposed request")

    predicate_value = subject_value.replace("'", "''")
    where = f"{subject_column} = '{predicate_value}'"

    from pointlessql.pql import PQL  # noqa: PLC0415 — avoids an import cycle
    from pointlessql.services.soyuz_client import (  # noqa: PLC0415
        make_principal_client,
        make_soyuz_client,
    )

    client = (
        make_principal_client(settings, principal) if principal else make_soyuz_client(settings)
    )
    pql = PQL(client=client, settings=settings)

    tables_affected: list[dict[str, Any]] = []
    total_deleted = 0
    for table in targets:
        metrics = pql.delete(f"{catalog}.{schema}.{table}", where=where)
        deleted = int(metrics.get("num_deleted_rows", 0) or 0)
        total_deleted += deleted
        tables_affected.append({"table": table, "rows_deleted": deleted})

    now = datetime.datetime.now(datetime.UTC)
    affected_names = [f"{catalog}.{schema}.{t['table']}" for t in tables_affected]
    with session_factory() as session:
        if request_id is not None:
            row = session.get(DataProductForgetRequest, request_id)
        else:
            row = DataProductForgetRequest(
                data_product_id=data_product_id,
                subject_column=subject_column,
                subject_value_hash=value_hash,
                requested_by_user_id=executed_by_user_id,
                created_at=now,
            )
            session.add(row)
        assert row is not None  # noqa: S101 — request_id existence checked above
        row.status = "executed"
        row.tables_affected_json = json.dumps(affected_names)
        row.rows_deleted = total_deleted
        row.executed_by_user_id = executed_by_user_id
        row.executed_at = now
        session.commit()
        request_pk = row.id

    return {
        "request_id": request_pk,
        "rows_deleted": total_deleted,
        "tables_affected": tables_affected,
        "status": "executed",
    }


def list_forget_requests(
    session_factory: SessionFactory, *, data_product_id: int
) -> list[DataProductForgetRequest]:
    """Return a product's forget ledger, newest first."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductForgetRequest)
                .where(DataProductForgetRequest.data_product_id == data_product_id)
                .order_by(DataProductForgetRequest.created_at.desc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows
