"""Snapshot the live DB state of one product into a :class:`DataProductSpec`."""

from __future__ import annotations

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
from pointlessql.services.data_product_as_code._spec import (
    ContractTestSpec,
    DataProductSpec,
    EntitySpec,
    FixtureSpec,
    InputPortSpec,
    OutputPortSpec,
    PolicySpec,
    SloSpec,
)
from pointlessql.services.governance._policy import (
    POLICY_FIELDS,
    get_product_policy,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


def export_data_product(
    session_factory: _SessionFactory,
    *,
    catalog: str,
    schema: str,
    workspace_id: int = 1,
) -> DataProductSpec:
    """Return a :class:`DataProductSpec` for the named product.

    Raises:
        LookupError: When the product does not exist.
    """
    with session_factory() as session:
        product = session.scalar(
            select(DataProduct)
            .where(DataProduct.workspace_id == workspace_id)
            .where(DataProduct.catalog_name == catalog)
            .where(DataProduct.schema_name == schema)
        )
        if product is None:
            raise LookupError(f"data product {catalog}.{schema} not found")
        product_id = int(product.id)
        output_ports = [
            OutputPortSpec(
                name=p.name,
                kind=p.kind,
                description=p.description,
                format=p.format,
                location=p.location,
                identity_requirements=(
                    json.loads(p.identity_requirements)
                    if p.identity_requirements
                    else None
                ),
            )
            for p in session.scalars(
                select(DataProductOutputPort)
                .where(DataProductOutputPort.data_product_id == product_id)
                .order_by(DataProductOutputPort.name)
            )
        ]
        input_ports = [
            InputPortSpec(
                name=p.name,
                kind=p.kind,
                source_ref=p.source_ref,
                description=p.description,
            )
            for p in session.scalars(
                select(DataProductInputPort)
                .where(DataProductInputPort.data_product_id == product_id)
                .order_by(DataProductInputPort.name)
            )
        ]
        slos = [
            SloSpec(
                kind=s.slo_kind,
                comparator=s.comparator,
                target_value=s.target_value,
                table=s.table_name,
                unit=s.unit,
            )
            for s in session.scalars(
                select(DataProductSLO)
                .where(DataProductSLO.data_product_id == product_id)
                .order_by(DataProductSLO.slo_kind)
            )
        ]
        entities = [
            EntitySpec(
                name=e.entity_name,
                source_table=e.source_table,
                primary_key_columns=(
                    json.loads(e.primary_key_columns)
                    if e.primary_key_columns
                    else []
                ),
                description=e.description,
            )
            for e in session.scalars(
                select(DataProductEntity)
                .where(DataProductEntity.data_product_id == product_id)
                .order_by(DataProductEntity.entity_name)
            )
        ]
        contract_tests = [
            ContractTestSpec(
                name=t.name,
                assertion_kind=t.assertion_kind,
                assertion_spec=(
                    json.loads(t.assertion_spec_json)
                    if t.assertion_spec_json
                    else {}
                ),
                severity=t.severity,
                enabled=bool(t.enabled),
            )
            for t in session.scalars(
                select(DataProductContractTest)
                .where(DataProductContractTest.data_product_id == product_id)
                .order_by(DataProductContractTest.name)
            )
        ]
        fixtures = [
            FixtureSpec(
                table_name=f.table_name,
                generator_spec=(
                    json.loads(f.generator_spec_json)
                    if f.generator_spec_json
                    else []
                ),
                row_count=int(f.row_count),
            )
            for f in session.scalars(
                select(DataProductFixture)
                .where(DataProductFixture.data_product_id == product_id)
                .order_by(DataProductFixture.table_name)
            )
        ]
        product_name = product.contract_json
    policy_payload = get_product_policy(
        session_factory, data_product_id=product_id
    )
    policies = (
        PolicySpec(**{f: policy_payload.get(f) for f in POLICY_FIELDS})
        if any(policy_payload.get(f) is not None for f in POLICY_FIELDS)
        else None
    )
    pipeline = None
    from pointlessql.services.data_product_as_code._canvas_pipeline import (
        from_canvas_doc,
    )
    from pointlessql.services.dp_canvas import load_latest_graph

    latest = load_latest_graph(session_factory, data_product_id=product_id)
    if latest is not None:
        pipeline = from_canvas_doc(latest[0])
    return DataProductSpec(
        name=_extract_name(product_name, default=f"{catalog}.{schema}"),
        catalog=catalog,
        schema=schema,
        description=product.description or None,
        input_ports=input_ports,
        output_ports=output_ports,
        slos=slos,
        policies=policies,
        contract_tests=contract_tests,
        fixtures=fixtures,
        entities=entities,
        pipeline=pipeline,
    )


def _extract_name(contract_json: str | None, *, default: str) -> str:
    """Pull the ``name`` field from the contract JSON; fallback to default."""
    if not contract_json:
        return default
    try:
        decoded = json.loads(contract_json)
    except (json.JSONDecodeError, ValueError):
        return default
    if isinstance(decoded, dict) and decoded.get("name"):
        return str(decoded["name"])
    return default
