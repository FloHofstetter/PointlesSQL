"""Run a :class:`Plan` against the live DB, idempotently.

Each op is dispatched to the matching existing CRUD helper so the
applier never reaches into the ORM directly.  The applier records
per-op outcomes so the route surface can render exactly what landed
and what failed.

Idempotency claim — applying the same spec twice should produce a
plan with zero op count on the second call.  Tests verify this for
the round-trip case ``export → apply → export``.
"""

from __future__ import annotations

import dataclasses
import datetime
import json

from sqlalchemy import select

from pointlessql.models import DataProduct
from pointlessql.services import entities as entities_service
from pointlessql.services.contract_tests import (
    declare_contract_test,
    declare_fixture,
    delete_contract_test,
    delete_fixture,
)
from pointlessql.services.data_product_as_code._planner import Op, Plan
from pointlessql.services.data_product_as_code._spec import DataProductSpec
from pointlessql.services.data_product_ports._crud import (
    create_input_port,
    create_output_port,
    delete_input_port,
    delete_output_port,
)
from pointlessql.services.governance._policy import set_product_policy
from pointlessql.services.slo._crud import declare_slo, delete_slo
from pointlessql.types import SessionFactory


@dataclasses.dataclass(slots=True, frozen=True)
class ApplyOutcome:
    """Summary of one :func:`apply_plan` call.

    Attributes:
        dry_run: True when no write happened.
        total: Total ops considered.
        applied: Count of ops that wrote successfully.
        skipped: Count of ops the applier could not run (unknown kind).
        errors: Per-op error tuples ``(op_target, message)``.
    """

    dry_run: bool
    total: int
    applied: int
    skipped: int
    errors: list[tuple[str, str]]


def apply_plan(
    session_factory: SessionFactory,
    *,
    spec: DataProductSpec,
    plan: Plan,
    dry_run: bool = False,
    workspace_id: int = 1,
    user_id: int | None = None,
) -> ApplyOutcome:
    """Execute *plan* against the DB; idempotent on repeat application."""
    if dry_run:
        return ApplyOutcome(
            dry_run=True,
            total=plan.op_count(),
            applied=0,
            skipped=0,
            errors=[],
        )

    applied = 0
    skipped = 0
    errors: list[tuple[str, str]] = []

    product_id = _ensure_product(session_factory, spec=spec, workspace_id=workspace_id)

    for op in plan.additions + plan.modifications + plan.removals:
        if op.kind == "product":
            applied += 1
            continue
        try:
            _dispatch_op(
                session_factory,
                op=op,
                product_id=product_id,
                user_id=user_id,
            )
            applied += 1
        except (ValueError, LookupError) as exc:
            errors.append((f"{op.kind}:{op.target}", str(exc)))
        except NotImplementedError:
            skipped += 1
    return ApplyOutcome(
        dry_run=False,
        total=plan.op_count(),
        applied=applied,
        skipped=skipped,
        errors=errors,
    )


def _ensure_product(
    session_factory: SessionFactory,
    *,
    spec: DataProductSpec,
    workspace_id: int,
) -> int:
    """Insert or update the top-level :class:`DataProduct` row."""
    contract = {
        "name": spec.name,
        "version": "1.0.0",
        "description": spec.description or "",
        "catalog": spec.catalog,
        "schema_name": spec.schema,
        "tables": [],
    }
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.scalar(
            select(DataProduct)
            .where(DataProduct.workspace_id == workspace_id)
            .where(DataProduct.catalog_name == spec.catalog)
            .where(DataProduct.schema_name == spec.schema)
        )
        if row is None:
            row = DataProduct(
                workspace_id=workspace_id,
                catalog_name=spec.catalog,
                schema_name=spec.schema,
                version="1.0.0",
                description=spec.description or "",
                sla_minutes=None,
                contract_yaml_hash="0" * 64,
                contract_json=json.dumps(contract),
                last_loaded_at=now,
                created_at=now,
            )
            session.add(row)
        else:
            row.description = spec.description or row.description
            row.contract_json = json.dumps(contract)
            row.last_loaded_at = now
        session.commit()
        session.refresh(row)
        return int(row.id)


def _dispatch_op(
    session_factory: SessionFactory,
    *,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    """Route one op to its CRUD helper."""
    if op.kind == "output_port":
        _apply_output_port(session_factory, op, product_id, user_id)
    elif op.kind == "input_port":
        _apply_input_port(session_factory, op, product_id, user_id)
    elif op.kind == "slo":
        _apply_slo(session_factory, op, product_id, user_id)
    elif op.kind == "entity":
        _apply_entity(session_factory, op, product_id, user_id)
    elif op.kind == "contract_test":
        _apply_contract_test(session_factory, op, product_id, user_id)
    elif op.kind == "fixture":
        _apply_fixture(session_factory, op, product_id, user_id)
    elif op.kind == "policies":
        _apply_policies(session_factory, op, product_id, user_id)
    else:
        raise NotImplementedError(f"unknown op kind: {op.kind}")


def _apply_output_port(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    if op.action == "add":
        after = op.after or {}
        create_output_port(
            session_factory,
            data_product_id=product_id,
            name=str(after.get("name", "")),
            kind=str(after.get("kind", "")),
            description=after.get("description"),
            fmt=after.get("format"),
            location=after.get("location"),
            created_by_user_id=user_id,
        )
    elif op.action == "update":
        from pointlessql.services.data_product_ports._crud import list_output_ports

        existing = next(
            (
                r
                for r in list_output_ports(session_factory, data_product_id=product_id)
                if r.name == op.target
            ),
            None,
        )
        if existing is not None:
            delete_output_port(
                session_factory,
                data_product_id=product_id,
                port_id=int(existing.id),
            )
        after = op.after or {}
        create_output_port(
            session_factory,
            data_product_id=product_id,
            name=str(after.get("name", op.target)),
            kind=str(after.get("kind", existing.kind if existing else "sql")),
            description=after.get("description"),
            fmt=after.get("format"),
            location=after.get("location"),
            created_by_user_id=user_id,
        )
    elif op.action == "remove":
        from pointlessql.services.data_product_ports._crud import list_output_ports

        existing = next(
            (
                r
                for r in list_output_ports(session_factory, data_product_id=product_id)
                if r.name == op.target
            ),
            None,
        )
        if existing is not None:
            delete_output_port(
                session_factory,
                data_product_id=product_id,
                port_id=int(existing.id),
            )


def _apply_input_port(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    if op.action == "add":
        after = op.after or {}
        create_input_port(
            session_factory,
            data_product_id=product_id,
            name=str(after.get("name", "")),
            kind=str(after.get("kind", "external")),
            source_ref=after.get("source_ref"),
            description=after.get("description"),
            created_by_user_id=user_id,
        )
    elif op.action in {"update", "remove"}:
        from pointlessql.services.data_product_ports._crud import list_input_ports

        existing = next(
            (
                r
                for r in list_input_ports(session_factory, data_product_id=product_id)
                if r.name == op.target
            ),
            None,
        )
        if existing is not None:
            delete_input_port(
                session_factory,
                data_product_id=product_id,
                port_id=int(existing.id),
            )
        if op.action == "update":
            after = op.after or {}
            create_input_port(
                session_factory,
                data_product_id=product_id,
                name=str(after.get("name", op.target)),
                kind=str(after.get("kind", existing.kind if existing else "external")),
                source_ref=after.get("source_ref"),
                description=after.get("description"),
                created_by_user_id=user_id,
            )


def _apply_slo(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    if op.action in {"add", "update"}:
        after = op.after or {}
        declare_slo(
            session_factory,
            data_product_id=product_id,
            slo_kind=str(after.get("kind", op.target)),
            target_value=after.get("target_value"),
            table_name=after.get("table"),
            comparator=after.get("comparator"),
            created_by_user_id=user_id,
        )
    elif op.action == "remove":
        from pointlessql.services.slo._crud import list_slos

        existing = next(
            (
                r
                for r in list_slos(session_factory, data_product_id=product_id)
                if r.slo_kind == op.target
            ),
            None,
        )
        if existing is not None:
            delete_slo(
                session_factory,
                data_product_id=product_id,
                slo_id=int(existing.id),
            )


def _apply_entity(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    if op.action in {"add", "update"}:
        after = op.after or {}
        entities_service.declare_entity(
            session_factory,
            data_product_id=product_id,
            entity_name=str(after.get("name", op.target)),
            source_table=str(after.get("source_table", "")),
            primary_key_columns=after.get("primary_key_columns") or [],
            description=after.get("description"),
            created_by_user_id=user_id,
        )
    elif op.action == "remove":
        entities = entities_service.list_entities(session_factory, data_product_id=product_id)
        target = next((e for e in entities if e["entity_name"] == op.target), None)
        if target is not None:
            entities_service.delete_entity(session_factory, entity_id=int(target["id"]))


def _apply_contract_test(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    if op.action in {"add", "update"}:
        after = op.after or {}
        declare_contract_test(
            session_factory,
            data_product_id=product_id,
            name=str(after.get("name", op.target)),
            assertion_kind=str(after.get("assertion_kind", "")),
            assertion_spec_json=after.get("assertion_spec", {}),
            severity=str(after.get("severity", "warn")),
            enabled=bool(after.get("enabled", True)),
            created_by_user_id=user_id,
        )
    elif op.action == "remove":
        from pointlessql.services.contract_tests import list_contract_tests

        tests = list_contract_tests(session_factory, data_product_id=product_id)
        target = next((t for t in tests if t["name"] == op.target), None)
        if target is not None:
            delete_contract_test(session_factory, contract_test_id=int(target["id"]))


def _apply_fixture(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    if op.action in {"add", "update"}:
        after = op.after or {}
        declare_fixture(
            session_factory,
            data_product_id=product_id,
            table_name=str(after.get("table_name", op.target)),
            generator_spec_json=after.get("generator_spec", []),
            row_count=int(after.get("row_count", 100) or 100),
            created_by_user_id=user_id,
        )
    elif op.action == "remove":
        from pointlessql.services.contract_tests import list_fixtures

        fixtures = list_fixtures(session_factory, data_product_id=product_id)
        target = next((f for f in fixtures if f["table_name"] == op.target), None)
        if target is not None:
            delete_fixture(session_factory, fixture_id=int(target["id"]))


def _apply_policies(
    session_factory: SessionFactory,
    op: Op,
    product_id: int,
    user_id: int | None,
) -> None:
    after = op.after or {}
    fields = {k: v for k, v in after.items() if v is not None or k == "linked_policy_module_ids"}
    if "linked_policy_module_ids" in fields and isinstance(
        fields["linked_policy_module_ids"], list
    ):
        fields["linked_policy_module_ids"] = json.dumps(fields["linked_policy_module_ids"])
    set_product_policy(
        session_factory,
        data_product_id=product_id,
        fields=fields,
        updated_by_user_id=user_id,
    )
