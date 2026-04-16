#!/usr/bin/env python
"""Idempotent seed for the Playwright MCP walkthrough harness.

Creates the fixed catalog/schema/table shape the five playbooks under
``docs/e2e-walkthroughs/`` expect, plus the Postgres Connection the
``foreign-catalog-sync`` playbook uses to spin up a foreign catalog.

Runs against a live stack brought up with
``docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d``
and is safe to re-run — every mutation is guarded by a "does it exist?"
check so reruns are no-ops.

The script mirrors the contract of the ``e2e_env`` fixture in
``tests/conftest.py``: write-through via the public ``PQL`` API rather
than the generated client directly, so the seeded state is what a user
would produce via notebooks or scripts.

Run it with::

    uv run python scripts/seed-e2e.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.catalogs import (
    create_catalog_api_2_1_unity_catalog_catalogs_post as _create_catalog,
)
from soyuz_catalog_client.api.connections import (
    create_connection_api_2_1_unity_catalog_connections_post as _create_connection,
)
from soyuz_catalog_client.api.connections import (
    get_connection_api_2_1_unity_catalog_connections_name_get as _get_connection,
)
from soyuz_catalog_client.api.schemas import (
    create_schema_api_2_1_unity_catalog_schemas_post as _create_schema,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_catalog import CreateCatalog
from soyuz_catalog_client.models.create_connection import CreateConnection
from soyuz_catalog_client.models.create_connection_connection_type import (
    CreateConnectionConnectionType,
)
from soyuz_catalog_client.models.create_schema import CreateSchema
from soyuz_catalog_client.models.options import Options

from pointlessql.pql.pql import PQL
from pointlessql.services.soyuz_client import make_soyuz_client

CATALOG = "demo"
SCHEMAS = ("sales", "hr")
# Default warehouse root mirrors the compose mount point.  When running
# outside Docker, override via E2E_WAREHOUSE_ROOT so the path points at a
# local directory (the compose mounts ./warehouse on the host into
# /app/warehouse in both containers, so paths are shared automatically).
WAREHOUSE_ROOT = os.environ.get("E2E_WAREHOUSE_ROOT", "/app/warehouse")

CONNECTION_NAME = "pg_e2e"
# Host/port/user/password default to what ``docker-compose.e2e.yml``
# provisions; override via env when pointing at a different target.
PG_HOST = os.environ.get("E2E_POSTGRES_HOST", "postgres-e2e")
PG_PORT = os.environ.get("E2E_POSTGRES_PORT", "5432")
PG_USER = os.environ.get("E2E_POSTGRES_USER", "e2e")
PG_PASSWORD = os.environ.get("E2E_POSTGRES_PASSWORD", "e2e")
PG_DATABASE = os.environ.get("E2E_POSTGRES_DATABASE", "ecommerce")


def _storage_root(catalog: str, schema: str) -> str:
    """Return the Delta storage root for one seeded schema.

    Returned as a ``file://`` URI because soyuz-catalog rejects paths
    without a URI scheme (``INVALID_ARGUMENT`` on ``POST /schemas``).
    """
    path = f"{WAREHOUSE_ROOT.rstrip('/')}/{catalog}/{schema}"
    return f"file://{path}"


def _ensure_catalog(client: Client, name: str) -> None:
    """Create the managed ``demo`` catalog; swallow 409 on rerun."""
    try:
        _create_catalog.sync(
            client=client,
            body=CreateCatalog(name=name, comment="Demo catalog for e2e walkthroughs"),
        )
        print(f"  + catalog {name!r} created")
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise
        print(f"  = catalog {name!r} exists")


def _ensure_schema(client: Client, catalog: str, schema: str) -> str:
    """Create a schema with a concrete ``storage_root``.

    ``PQL.write_table`` derives table-level storage locations from the
    parent schema's ``storage_root``, so we pin it here to a path that
    lives inside the mounted ``./warehouse`` volume.
    """
    storage = _storage_root(catalog, schema)
    try:
        _create_schema.sync(
            client=client,
            body=CreateSchema(
                catalog_name=catalog,
                name=schema,
                storage_root=storage,
            ),
        )
        print(f"  + schema {catalog}.{schema!r} created (storage_root={storage})")
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise
        print(f"  = schema {catalog}.{schema!r} exists")
    return storage


def _ensure_connection(client: Client) -> None:
    """Create the ``pg_e2e`` Connection used by the foreign-catalog playbook.

    The playbook picks this connection from the dropdown in the "Create
    foreign catalog" modal, so seeding it here means the playbook never
    has to fill a long Postgres connection form by hand.
    """
    try:
        _get_connection.sync(name=CONNECTION_NAME, client=client)
        print(f"  = connection {CONNECTION_NAME!r} exists")
        return
    except UnexpectedStatus as exc:
        if exc.status_code != 404:
            raise

    options = Options()
    options["host"] = PG_HOST
    options["port"] = PG_PORT
    options["user"] = PG_USER
    options["password"] = PG_PASSWORD
    options["database"] = PG_DATABASE

    _create_connection.sync(
        client=client,
        body=CreateConnection(
            name=CONNECTION_NAME,
            connection_type=CreateConnectionConnectionType.POSTGRESQL,
            comment="Foreign-catalog target seeded by scripts/seed-e2e.py",
            options=options,
        ),
    )
    print(f"  + connection {CONNECTION_NAME!r} created ({PG_HOST}:{PG_PORT})")


def _seed_tables(pql: PQL) -> int:
    """Write the four demo tables idempotently and return how many were new."""
    written = 0

    # demo.sales.customers — 20 rows
    if not _table_exists(pql, "demo.sales.customers"):
        customers = pd.DataFrame(
            {
                "customer_id": range(1, 21),
                "name": [f"Customer {i}" for i in range(1, 21)],
                "email": [f"c{i}@example.com" for i in range(1, 21)],
            }
        )
        pql.write_table(customers, "demo.sales.customers")
        print("  + table demo.sales.customers (20 rows)")
        written += 1
    else:
        print("  = table demo.sales.customers exists")

    # demo.sales.orders — 50 rows
    if not _table_exists(pql, "demo.sales.orders"):
        orders = pd.DataFrame(
            {
                "order_id": range(1, 51),
                "customer_id": [((i - 1) % 20) + 1 for i in range(1, 51)],
                "amount": [round(10.0 + (i * 3.5) % 200, 2) for i in range(1, 51)],
                "placed_at": pd.date_range("2026-01-01", periods=50, freq="h"),
            }
        )
        pql.write_table(orders, "demo.sales.orders")
        print("  + table demo.sales.orders (50 rows)")
        written += 1
    else:
        print("  = table demo.sales.orders exists")

    # demo.hr.employees — 10 rows
    if not _table_exists(pql, "demo.hr.employees"):
        employees = pd.DataFrame(
            {
                "employee_id": range(1, 11),
                "name": [f"Employee {i}" for i in range(1, 11)],
                "department": ["Engineering", "Sales", "Support"] * 3 + ["Engineering"],
            }
        )
        pql.write_table(employees, "demo.hr.employees")
        print("  + table demo.hr.employees (10 rows)")
        written += 1
    else:
        print("  = table demo.hr.employees exists")

    # demo.hr.salaries — 10 rows
    if not _table_exists(pql, "demo.hr.salaries"):
        salaries = pd.DataFrame(
            {
                "employee_id": range(1, 11),
                "salary": [50000 + i * 2500 for i in range(1, 11)],
                "currency": ["USD"] * 10,
            }
        )
        pql.write_table(salaries, "demo.hr.salaries")
        print("  + table demo.hr.salaries (10 rows)")
        written += 1
    else:
        print("  = table demo.hr.salaries exists")

    return written


def _table_exists(pql: PQL, full_name: str) -> bool:
    """Return True if a three-part name resolves in the catalog."""
    try:
        pql.table(full_name)
    except Exception:  # noqa: BLE001 — any surfacing error means "not readable as-is"
        return False
    return True


def main() -> int:
    """Run the full seed and print a one-line summary."""
    print(f"seeding against {os.environ.get('POINTLESSQL_SOYUZ_CATALOG_URL', 'http://127.0.0.1:8080')}")
    client = make_soyuz_client()
    pql = PQL(client=client)

    _ensure_catalog(client, CATALOG)
    for schema in SCHEMAS:
        _ensure_schema(client, CATALOG, schema)
        fs_path = f"{WAREHOUSE_ROOT.rstrip('/')}/{CATALOG}/{schema}"
        Path(fs_path).mkdir(parents=True, exist_ok=True)

    new_tables = _seed_tables(pql)
    _ensure_connection(client)

    print(
        f"seed ok — 1 catalog, {len(SCHEMAS)} schemas, 4 tables "
        f"({new_tables} newly written), 1 connection"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
