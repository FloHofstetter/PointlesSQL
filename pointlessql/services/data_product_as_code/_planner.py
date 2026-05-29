"""Compute additive / modification / removal ops between spec and DB.

Plan shape — one :class:`Op` per individual subentity write.  The
planner walks each spec section, queries the matching DB rows for the
product, and emits Ops:

* ``additions``      — present in spec, absent in DB.
* ``modifications``  — present in both with differing field values.
* ``removals``       — present in DB, absent in spec.

Equality is shallow on the discovery-shaped dict — the same shape the
exporter produces — so a round-trip ``plan(export(p))`` returns a
no-op Plan.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    DataProductContractTest,
    DataProductEntity,
    DataProductFixture,
    DataProductInputPort,
    DataProductOutputPort,
    DataProductSLO,
)
from pointlessql.services.data_product_as_code._spec import DataProductSpec
from pointlessql.services.governance._policy import (
    POLICY_FIELDS,
    get_product_policy,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


@dataclasses.dataclass(slots=True, frozen=True)
class Op:
    """One reconciler operation.

    Attributes:
        kind: Subentity kind (``output_port``, ``input_port``, ``slo``,
            ``entity``, ``contract_test``, ``fixture``, ``policies``,
            ``product``).
        action: ``add`` / ``update`` / ``remove``.
        target: Sub-key the op identifies — usually a name.
        before: Discovery-shaped dict of the prior state; ``None`` on add.
        after: Discovery-shaped dict of the desired state; ``None`` on
            remove.
    """

    kind: str
    action: str
    target: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclasses.dataclass(slots=True, frozen=True)
class Plan:
    """The ordered set of ops the applier will run.

    Attributes:
        additions: Ops with ``action='add'``.
        modifications: Ops with ``action='update'``.
        removals: Ops with ``action='remove'``.
        product_present: True when the product already exists; the
            applier uses this to decide whether to insert or update
            the top-level row.
    """

    additions: list[Op]
    modifications: list[Op]
    removals: list[Op]
    product_present: bool

    def op_count(self) -> int:
        """Total number of ops in the plan."""
        return len(self.additions) + len(self.modifications) + len(self.removals)

    def is_noop(self) -> bool:
        """Return True when no op would change anything."""
        return self.op_count() == 0


def plan_spec(
    session_factory: _SessionFactory,
    *,
    spec: DataProductSpec,
    workspace_id: int = 1,
) -> Plan:
    """Compute a :class:`Plan` for *spec* against the live DB state."""
    with session_factory() as session:
        product = session.scalar(
            select(DataProduct)
            .where(DataProduct.workspace_id == workspace_id)
            .where(DataProduct.catalog_name == spec.catalog)
            .where(DataProduct.schema_name == spec.schema)
        )
        product_present = product is not None
        product_id = int(product.id) if product is not None else 0
        live_input_ports = (
            list(
                session.scalars(
                    select(DataProductInputPort).where(
                        DataProductInputPort.data_product_id == product_id
                    )
                )
            )
            if product_id
            else []
        )
        live_output_ports = (
            list(
                session.scalars(
                    select(DataProductOutputPort).where(
                        DataProductOutputPort.data_product_id == product_id
                    )
                )
            )
            if product_id
            else []
        )
        live_slos = (
            list(
                session.scalars(
                    select(DataProductSLO).where(
                        DataProductSLO.data_product_id == product_id
                    )
                )
            )
            if product_id
            else []
        )
        live_entities = (
            list(
                session.scalars(
                    select(DataProductEntity).where(
                        DataProductEntity.data_product_id == product_id
                    )
                )
            )
            if product_id
            else []
        )
        live_tests = (
            list(
                session.scalars(
                    select(DataProductContractTest).where(
                        DataProductContractTest.data_product_id == product_id
                    )
                )
            )
            if product_id
            else []
        )
        live_fixtures = (
            list(
                session.scalars(
                    select(DataProductFixture).where(
                        DataProductFixture.data_product_id == product_id
                    )
                )
            )
            if product_id
            else []
        )

    additions: list[Op] = []
    modifications: list[Op] = []
    removals: list[Op] = []

    if not product_present:
        additions.append(
            Op(
                kind="product",
                action="add",
                target=f"{spec.catalog}.{spec.schema}",
                before=None,
                after=_product_dict(spec),
            )
        )
    elif _product_changed(spec, product):
        modifications.append(
            Op(
                kind="product",
                action="update",
                target=f"{spec.catalog}.{spec.schema}",
                before={"catalog": spec.catalog, "schema": spec.schema},
                after=_product_dict(spec),
            )
        )

    _diff_output_ports(spec, live_output_ports, additions, modifications, removals)
    _diff_input_ports(spec, live_input_ports, additions, modifications, removals)
    _diff_slos(spec, live_slos, additions, modifications, removals)
    _diff_entities(spec, live_entities, additions, modifications, removals)
    _diff_contract_tests(spec, live_tests, additions, modifications, removals)
    _diff_fixtures(spec, live_fixtures, additions, modifications, removals)
    if product_present:
        _diff_policies(
            session_factory, spec, product_id, modifications
        )
    elif spec.policies is not None:
        additions.append(
            Op(
                kind="policies",
                action="add",
                target=f"{spec.catalog}.{spec.schema}",
                before=None,
                after=spec.policies.model_dump(),
            )
        )

    return Plan(
        additions=additions,
        modifications=modifications,
        removals=removals,
        product_present=product_present,
    )


def _product_dict(spec: DataProductSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "catalog": spec.catalog,
        "schema": spec.schema,
        "domain": spec.domain,
        "lifecycle": spec.lifecycle,
        "owner_email": spec.owner_email,
        "description": spec.description,
    }


def _product_changed(spec: DataProductSpec, row: DataProduct) -> bool:
    return (spec.description or "") != (row.description or "")


def _diff_output_ports(
    spec: DataProductSpec,
    live: list[DataProductOutputPort],
    additions: list[Op],
    modifications: list[Op],
    removals: list[Op],
) -> None:
    by_name = {r.name: r for r in live}
    spec_names = set()
    for port in spec.output_ports:
        spec_names.add(port.name)
        desired = port.model_dump()
        existing = by_name.get(port.name)
        if existing is None:
            additions.append(
                Op(
                    kind="output_port",
                    action="add",
                    target=port.name,
                    before=None,
                    after=desired,
                )
            )
        else:
            before = _output_port_dict(existing)
            if before != desired:
                modifications.append(
                    Op(
                        kind="output_port",
                        action="update",
                        target=port.name,
                        before=before,
                        after=desired,
                    )
                )
    for name, row in by_name.items():
        if name not in spec_names:
            removals.append(
                Op(
                    kind="output_port",
                    action="remove",
                    target=name,
                    before=_output_port_dict(row),
                    after=None,
                )
            )


def _output_port_dict(row: DataProductOutputPort) -> dict[str, Any]:
    return {
        "name": row.name,
        "kind": row.kind,
        "description": row.description,
        "format": row.format,
        "location": row.location,
        "identity_requirements": (
            json.loads(row.identity_requirements)
            if row.identity_requirements
            else None
        ),
    }


def _diff_input_ports(
    spec: DataProductSpec,
    live: list[DataProductInputPort],
    additions: list[Op],
    modifications: list[Op],
    removals: list[Op],
) -> None:
    by_name = {r.name: r for r in live}
    spec_names = set()
    for port in spec.input_ports:
        spec_names.add(port.name)
        desired = port.model_dump()
        existing = by_name.get(port.name)
        if existing is None:
            additions.append(
                Op(
                    kind="input_port",
                    action="add",
                    target=port.name,
                    before=None,
                    after=desired,
                )
            )
        else:
            before = {
                "name": existing.name,
                "kind": existing.kind,
                "source_ref": existing.source_ref,
                "description": existing.description,
            }
            if before != desired:
                modifications.append(
                    Op(
                        kind="input_port",
                        action="update",
                        target=port.name,
                        before=before,
                        after=desired,
                    )
                )
    for name, row in by_name.items():
        if name not in spec_names:
            removals.append(
                Op(
                    kind="input_port",
                    action="remove",
                    target=name,
                    before={
                        "name": row.name,
                        "kind": row.kind,
                        "source_ref": row.source_ref,
                        "description": row.description,
                    },
                    after=None,
                )
            )


def _diff_slos(
    spec: DataProductSpec,
    live: list[DataProductSLO],
    additions: list[Op],
    modifications: list[Op],
    removals: list[Op],
) -> None:
    by_kind = {r.slo_kind: r for r in live}
    spec_kinds = set()
    for slo in spec.slos:
        spec_kinds.add(slo.kind)
        desired = slo.model_dump()
        existing = by_kind.get(slo.kind)
        if existing is None:
            additions.append(
                Op(
                    kind="slo",
                    action="add",
                    target=slo.kind,
                    before=None,
                    after=desired,
                )
            )
        else:
            before = {
                "kind": existing.slo_kind,
                "comparator": existing.comparator,
                "target_value": existing.target_value,
                "table": existing.table_name,
                "unit": existing.unit,
            }
            if desired.get("unit") is None:
                desired = {**desired, "unit": existing.unit}
            if before != desired:
                modifications.append(
                    Op(
                        kind="slo",
                        action="update",
                        target=slo.kind,
                        before=before,
                        after=desired,
                    )
                )
    for kind, row in by_kind.items():
        if kind not in spec_kinds:
            removals.append(
                Op(
                    kind="slo",
                    action="remove",
                    target=kind,
                    before={"kind": row.slo_kind},
                    after=None,
                )
            )


def _diff_entities(
    spec: DataProductSpec,
    live: list[DataProductEntity],
    additions: list[Op],
    modifications: list[Op],
    removals: list[Op],
) -> None:
    by_name = {r.entity_name: r for r in live}
    spec_names = set()
    for entity in spec.entities:
        spec_names.add(entity.name)
        desired = entity.model_dump()
        existing = by_name.get(entity.name)
        if existing is None:
            additions.append(
                Op(
                    kind="entity",
                    action="add",
                    target=entity.name,
                    before=None,
                    after=desired,
                )
            )
        else:
            before = {
                "name": existing.entity_name,
                "source_table": existing.source_table,
                "primary_key_columns": (
                    json.loads(existing.primary_key_columns)
                    if existing.primary_key_columns
                    else []
                ),
                "description": existing.description,
            }
            if before != desired:
                modifications.append(
                    Op(
                        kind="entity",
                        action="update",
                        target=entity.name,
                        before=before,
                        after=desired,
                    )
                )
    for name, row in by_name.items():
        if name not in spec_names:
            removals.append(
                Op(
                    kind="entity",
                    action="remove",
                    target=name,
                    before={"name": row.entity_name},
                    after=None,
                )
            )


def _diff_contract_tests(
    spec: DataProductSpec,
    live: list[DataProductContractTest],
    additions: list[Op],
    modifications: list[Op],
    removals: list[Op],
) -> None:
    by_name = {r.name: r for r in live}
    spec_names = set()
    for test in spec.contract_tests:
        spec_names.add(test.name)
        desired = test.model_dump()
        existing = by_name.get(test.name)
        if existing is None:
            additions.append(
                Op(
                    kind="contract_test",
                    action="add",
                    target=test.name,
                    before=None,
                    after=desired,
                )
            )
        else:
            before = {
                "name": existing.name,
                "assertion_kind": existing.assertion_kind,
                "assertion_spec": (
                    json.loads(existing.assertion_spec_json)
                    if existing.assertion_spec_json
                    else {}
                ),
                "severity": existing.severity,
                "enabled": bool(existing.enabled),
            }
            if before != desired:
                modifications.append(
                    Op(
                        kind="contract_test",
                        action="update",
                        target=test.name,
                        before=before,
                        after=desired,
                    )
                )
    for name, row in by_name.items():
        if name not in spec_names:
            removals.append(
                Op(
                    kind="contract_test",
                    action="remove",
                    target=name,
                    before={"name": row.name},
                    after=None,
                )
            )


def _diff_fixtures(
    spec: DataProductSpec,
    live: list[DataProductFixture],
    additions: list[Op],
    modifications: list[Op],
    removals: list[Op],
) -> None:
    by_table = {r.table_name: r for r in live}
    spec_tables = set()
    for fixture in spec.fixtures:
        spec_tables.add(fixture.table_name)
        desired = fixture.model_dump()
        existing = by_table.get(fixture.table_name)
        if existing is None:
            additions.append(
                Op(
                    kind="fixture",
                    action="add",
                    target=fixture.table_name,
                    before=None,
                    after=desired,
                )
            )
        else:
            before = {
                "table_name": existing.table_name,
                "generator_spec": (
                    json.loads(existing.generator_spec_json)
                    if existing.generator_spec_json
                    else []
                ),
                "row_count": int(existing.row_count),
            }
            if before != desired:
                modifications.append(
                    Op(
                        kind="fixture",
                        action="update",
                        target=fixture.table_name,
                        before=before,
                        after=desired,
                    )
                )
    for table_name, row in by_table.items():
        if table_name not in spec_tables:
            removals.append(
                Op(
                    kind="fixture",
                    action="remove",
                    target=table_name,
                    before={"table_name": row.table_name},
                    after=None,
                )
            )


def _diff_policies(
    session_factory: _SessionFactory,
    spec: DataProductSpec,
    product_id: int,
    modifications: list[Op],
) -> None:
    if spec.policies is None:
        return
    current = get_product_policy(session_factory, data_product_id=product_id)
    desired = spec.policies.model_dump()
    delta = {
        field: desired.get(field)
        for field in POLICY_FIELDS
        if desired.get(field) != current.get(field)
    }
    if delta:
        modifications.append(
            Op(
                kind="policies",
                action="update",
                target=f"{spec.catalog}.{spec.schema}",
                before={field: current.get(field) for field in delta},
                after={field: desired.get(field) for field in delta},
            )
        )
