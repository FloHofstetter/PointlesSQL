#!/usr/bin/env python
"""Idempotent seed for the Data-Mesh walkthrough harness.

Creates the metadata-plane substrate the mesh / observability walkthroughs
need but that has no creation UI: two data products where the downstream
declares the upstream as an input port (so the emergent mesh graph has an
edge), per-table statistics (so SLO verdicts, drift and the mesh-health
band rollup have a baseline), and two SLOs — one passing, one failing — so
the health dashboard shows a mixed red/green rollup.

Domains, glossary terms, mesh entities, column classifications and entity
bindings are intentionally NOT seeded here: those have CRUD UIs and are
created by hand during the browser walkthrough (which doubles as
verification of the create endpoints).

Pairs with ``scripts/seed-e2e.py`` (run that first) — the two products
overlay the real ``demo.sales`` and ``demo.hr`` schemas it creates, so the
soyuz-backed catalog tabs on the product page resolve cleanly. All writes
go through PointlesSQL's own metadata DB via the shared session factory;
there is no Delta IO here. Every mutation is guarded by an existence check
so reruns are no-ops.

Run it with::

    uv run python scripts/seed-mesh-demo.py
"""

from __future__ import annotations

import datetime
import json
import sys

from sqlalchemy import select

from pointlessql.config import get_settings
from pointlessql.db import get_session_factory, init_db
from pointlessql.models import (
    DataProduct,
    DataProductInputPort,
    DataProductStatistics,
)
from pointlessql.services import slo as slo_service

WORKSPACE_ID = 1

# (catalog, schema, [(table, row_count, shape, columns)]) — overlays the
# seed-e2e tables. Columns are declared in the contract so the Contract tab
# renders rows (and the glossary badge can attach to a bound column).
_COL = lambda name, type_, nullable=True: {  # noqa: E731
    "name": name,
    "type": type_,
    "nullable": nullable,
    "description": "",
}
_PRODUCTS = {
    "upstream": (
        "demo",
        "sales",
        [
            (
                "customers",
                20,
                {"customer_id": {"null_count": 0, "distinct": 20}},
                [
                    _COL("customer_id", "long", False),
                    _COL("name", "string"),
                    _COL("email", "string"),
                ],
            ),
            (
                "orders",
                50,
                {"order_id": {"null_count": 0, "distinct": 50}},
                [
                    _COL("order_id", "long", False),
                    _COL("customer_id", "long", False),
                    _COL("amount", "double"),
                    _COL("placed_at", "timestamp"),
                ],
            ),
        ],
    ),
    "downstream": (
        "demo",
        "hr",
        [
            (
                "employees",
                10,
                {"employee_id": {"null_count": 0, "distinct": 10}},
                [
                    _COL("employee_id", "long", False),
                    _COL("name", "string"),
                    _COL("department", "string"),
                ],
            ),
            (
                "salaries",
                10,
                {"employee_id": {"null_count": 0, "distinct": 10}},
                [
                    _COL("employee_id", "long", False),
                    _COL("salary", "long"),
                    _COL("currency", "string"),
                ],
            ),
        ],
    ),
}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _get_or_create_product(factory, catalog: str, schema: str, tables: list) -> int:
    """Insert a DataProduct row (idempotent on workspace+catalog+schema)."""
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": f"Demo data product over {catalog}.{schema}",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [{"name": t, "columns": cols} for t, _, _, cols in tables],
    }
    with factory() as session:
        existing = session.scalars(
            select(DataProduct).where(
                DataProduct.workspace_id == WORKSPACE_ID,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        ).first()
        if existing is not None:
            # Refresh the contract so a re-run picks up column edits.
            existing.contract_json = json.dumps(contract)
            session.commit()
            print(f"  = product {catalog}.{schema} exists (id={existing.id}, contract refreshed)")
            return existing.id

        row = DataProduct(
            workspace_id=WORKSPACE_ID,
            catalog_name=catalog,
            schema_name=schema,
            steward_user_id=None,
            version="1.0.0",
            description=contract["description"],
            sla_minutes=60,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(row)
        session.commit()
        print(f"  + product {catalog}.{schema} created (id={row.id})")
        return row.id


def _ensure_input_port(factory, product_id: int, name: str, source_ref: str) -> None:
    """Declare an upstream-product input port (idempotent on product+source)."""
    with factory() as session:
        existing = session.scalars(
            select(DataProductInputPort).where(
                DataProductInputPort.data_product_id == product_id,
                DataProductInputPort.source_ref == source_ref,
            )
        ).first()
        if existing is not None:
            print(f"  = input-port {source_ref} -> product {product_id} exists")
            return
        session.add(
            DataProductInputPort(
                data_product_id=product_id,
                name=name,
                kind="upstream_product",
                source_ref=source_ref,
                created_at=_now(),
            )
        )
        session.commit()
        print(f"  + input-port {source_ref} -> product {product_id}")


def _ensure_statistics(factory, product_id: int, tables: list) -> None:
    """Stamp one light-profile statistics row per table (idempotent)."""
    with factory() as session:
        for table, row_count, shape, _cols in tables:
            existing = session.scalars(
                select(DataProductStatistics).where(
                    DataProductStatistics.data_product_id == product_id,
                    DataProductStatistics.table_name == table,
                )
            ).first()
            if existing is not None:
                print(f"  = stats {product_id}/{table} exist")
                continue
            session.add(
                DataProductStatistics(
                    data_product_id=product_id,
                    table_name=table,
                    delta_log_version=1,
                    row_count=row_count,
                    shape_json=json.dumps(shape, sort_keys=True),
                    profile_kind="light",
                    freshness_lag_minutes=15,
                    created_at=_now(),
                )
            )
            print(f"  + stats {product_id}/{table} (row_count={row_count})")
        session.commit()


def main() -> int:
    """Seed the mesh substrate and print a one-line summary."""
    settings = get_settings()
    init_db(settings.db.url)
    factory = get_session_factory()

    up_cat, up_schema, up_tables = _PRODUCTS["upstream"]
    dn_cat, dn_schema, dn_tables = _PRODUCTS["downstream"]

    print("seeding mesh substrate into the metadata DB")
    upstream_id = _get_or_create_product(factory, up_cat, up_schema, up_tables)
    downstream_id = _get_or_create_product(factory, dn_cat, dn_schema, dn_tables)

    # downstream (hr) declares upstream (sales) -> one emergent graph edge.
    _ensure_input_port(factory, downstream_id, "from_sales", f"{up_cat}.{up_schema}")

    _ensure_statistics(factory, upstream_id, up_tables)
    _ensure_statistics(factory, downstream_id, dn_tables)

    # A passing volume SLO on the upstream (observed 50 >= target 10) and a
    # failing one on the downstream (observed 10 < target 1000) so the
    # mesh-health dashboard shows a mixed green/red rollup.
    slo_service.declare_slo(
        factory,
        data_product_id=upstream_id,
        slo_kind="volume",
        target_value=10.0,
        table_name="orders",
    )
    slo_service.declare_slo(
        factory,
        data_product_id=downstream_id,
        slo_kind="volume",
        target_value=1000.0,
        table_name="employees",
    )
    print(
        "  + SLOs: volume>=10 on demo.sales.orders (pass), volume>=1000 on demo.hr.employees (fail)"
    )

    print("mesh seed ok — 2 products, 1 upstream edge, 4 stats rows, 2 SLOs (1 pass / 1 fail)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
