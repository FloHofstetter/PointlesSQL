"""Point-in-time-consistent cross-product reads.

Reproducibility across products (e.g. ML training) needs every product
read *as of the same instant*.  :func:`resolve_as_of` resolves, for each
declared table of each requested product, the Delta version that was
current at a wall-clock instant and a best-effort row count — the
manifest a consumer (or a PQL ``table_at_timestamp`` read) uses to pull a
consistent snapshot.  The heavy data read stays a PQL primitive; this
returns only the resolved versions + counts.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any

from sqlalchemy import select

from pointlessql.data_products import DataProductContract
from pointlessql.models import DataProduct
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import SessionFactory

logger = logging.getLogger(__name__)


def _version_and_count_at(storage_location: str, when: datetime.datetime) -> dict[str, Any]:
    """Resolve the as-of version + best-effort row count of a Delta table.

    Args:
        storage_location: Filesystem / object-store path of the Delta
            table's root (where its ``_delta_log`` lives).
        when: Timezone-aware wall-clock instant to resolve the table's
            version at.

    Returns:
        ``{"as_of_version": int|None, "row_count": int|None}`` — both
        ``None`` when the table is unreadable at *when*.
    """
    try:
        import deltalake

        dt = deltalake.DeltaTable(storage_location)
        dt.load_as_version(when)
        version = int(dt.version())
    except Exception:  # noqa: BLE001 — resolution is best-effort
        # bare-broad-ok: an unreadable / pre-existence table degrades to
        # "no snapshot" rather than failing the whole manifest.
        return {"as_of_version": None, "row_count": None}
    row_count: int | None = None
    try:
        row_count = int(dt.to_pyarrow_dataset().count_rows())
    except Exception:  # noqa: BLE001 — counting is best-effort
        # bare-broad-ok: the version is the load-bearing field; a count
        # failure leaves it None without losing the resolved version.
        row_count = None
    return {"as_of_version": version, "row_count": row_count}


def _declared_tables(contract_json: str) -> list[str]:
    """Return the declared table names from a serialised contract."""
    try:
        contract = DataProductContract.model_validate(json.loads(contract_json))
    except TypeError, ValueError:
        return []
    return [t.name for t in contract.tables]


async def resolve_as_of(
    session_factory: SessionFactory,
    uc: UnityCatalogClient,
    *,
    workspace_id: int,
    product_ids: list[int],
    when: datetime.datetime,
) -> dict[str, Any]:
    """Resolve a consistent as-of snapshot manifest across products.

    Args:
        session_factory: Sessionmaker callable.
        uc: ``UnityCatalogClient`` used to resolve table storage paths.
        workspace_id: Workspace the products live in.
        product_ids: Products to include in the snapshot.
        when: The as-of wall-clock instant (timezone-aware).

    Returns:
        ``{"when": iso, "products": {ref: {"tables": {name: {as_of_version,
        row_count}}}}}`` — one entry per resolvable product.

    Raises:
        ValueError: When *when* is naive.
    """
    if when.tzinfo is None:
        raise ValueError("point-in-time read requires a timezone-aware datetime")

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProduct).where(
                    DataProduct.workspace_id == workspace_id,
                    DataProduct.id.in_(product_ids or [-1]),
                )
            ).all()
        )
        specs = [(r.catalog_name, r.schema_name, _declared_tables(r.contract_json)) for r in rows]

    products: dict[str, Any] = {}
    for catalog, schema, tables in specs:
        ref = f"{catalog}.{schema}"
        try:
            uc_tables = await uc.list_tables(catalog, schema)
        except Exception:  # noqa: BLE001 — skip per-schema failures
            logger.exception("resolve_as_of: list_tables failed for %s", ref)
            uc_tables = []
        location_by_name = {
            str(t.get("name")): str(t.get("storage_location"))
            for t in uc_tables
            if isinstance(t, dict) and t.get("name") and t.get("storage_location")
        }
        table_manifest: dict[str, Any] = {}
        for table_name in tables:
            location = location_by_name.get(table_name)
            if not location:
                table_manifest[table_name] = {"as_of_version": None, "row_count": None}
                continue
            table_manifest[table_name] = await asyncio.to_thread(
                _version_and_count_at, location, when
            )
        products[ref] = {"tables": table_manifest}

    return {"when": when.isoformat(), "products": products}
