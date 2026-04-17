"""Integration tests for the pql helper library.

Every test in this module talks to a **live** soyuz-catalog server and
is marked with ``@pytest.mark.integration`` so the default test run
(``uv run pytest``) skips them.  Run explicitly with::

    uv run pytest tests/test_pql_integration.py -m integration
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest
from soyuz_catalog_client.api.catalogs import (
    create_catalog_api_2_1_unity_catalog_catalogs_post as _create_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    delete_catalog_api_2_1_unity_catalog_catalogs_name_delete as _delete_catalog,
)
from soyuz_catalog_client.api.schemas import (
    create_schema_api_2_1_unity_catalog_schemas_post as _create_schema,
)
from soyuz_catalog_client.api.schemas import (
    delete_schema_api_2_1_unity_catalog_schemas_full_name_delete as _delete_schema,
)
from soyuz_catalog_client.api.tables import (
    delete_table_api_2_1_unity_catalog_tables_full_name_delete as _delete_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_catalog import CreateCatalog
from soyuz_catalog_client.models.create_schema import CreateSchema

from pointlessql.pql.pql import PQL
from pointlessql.services.soyuz_client import make_soyuz_client

_CATALOG = "pql_integration_test"
_SCHEMA = "pql_test_schema"
_TABLE = "pql_test_table"
_FULL_NAME = f"{_CATALOG}.{_SCHEMA}.{_TABLE}"


@pytest.fixture
def _soyuz_env(tmp_path: Path):
    """Create a throwaway catalog + schema on the live soyuz-catalog server.

    The schema's ``storage_root`` points at *tmp_path* so Delta files
    stay local and are cleaned up automatically.

    Yields:
        A tuple of ``(PQL, storage_root_path)``.
    """
    client = make_soyuz_client()
    storage_root = str(tmp_path / "warehouse" / _CATALOG / _SCHEMA)

    # Create catalog (ignore 409 if it already exists).
    try:
        _create_catalog.sync(
            client=client,
            body=CreateCatalog(name=_CATALOG),
        )
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise

    # Create schema with storage_root.
    try:
        _create_schema.sync(
            client=client,
            body=CreateSchema(
                catalog_name=_CATALOG,
                name=_SCHEMA,
                storage_root=storage_root,
            ),
        )
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise

    pql = PQL(client=client)

    yield pql, storage_root

    # Teardown: delete table → schema → catalog.
    try:
        _delete_table.sync(_FULL_NAME, client=client)
    except UnexpectedStatus:
        pass
    try:
        _delete_schema.sync(f"{_CATALOG}.{_SCHEMA}", client=client)
    except UnexpectedStatus:
        pass
    try:
        _delete_catalog.sync(_CATALOG, client=client, force=True)
    except UnexpectedStatus:
        pass

    # Remove Delta files from disk.
    delta_dir = Path(storage_root) / _TABLE
    if delta_dir.exists():
        shutil.rmtree(delta_dir)


@pytest.mark.integration
def test_pql_create_write_read_verify(
    _soyuz_env: tuple[PQL, str],
) -> None:
    pql, _storage_root = _soyuz_env

    df = pd.DataFrame(
        {
            "id": pd.array([1, 2, 3], dtype="int64"),
            "name": pd.array(["alice", "bob", "charlie"], dtype="object"),
            "score": pd.array([9.5, 8.0, 7.3], dtype="float64"),
        }
    )

    # Write
    pql.write_table(df, _FULL_NAME)

    # Read back
    result = pql.table(_FULL_NAME)
    assert len(result) == 3
    assert list(result.columns) == ["id", "name", "score"]
    assert list(result["id"]) == [1, 2, 3]
    assert list(result["name"]) == ["alice", "bob", "charlie"]

    # list_tables should include the new table
    tables = pql.list_tables(_CATALOG, _SCHEMA)
    table_names = [t.get("name") for t in tables]
    assert _TABLE in table_names
