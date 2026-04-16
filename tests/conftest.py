"""Shared test fixtures for PointlesSQL."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from soyuz_catalog_client import Client
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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.models import Base
from pointlessql.pql.pql import PQL
from pointlessql.services import auth
from pointlessql.services.soyuz_client import make_soyuz_client

_TEST_SECRET = "test-secret-key-for-unit-tests!!"


@pytest.fixture(autouse=True)
def _auth_db():
    """Set up an in-memory auth DB and authenticated cookie for all tests.

    Existing tests that set ``app.state`` manually will override the
    UC client but the auth layer remains functional so the middleware
    doesn't block requests.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app.state.session_factory = factory

    # Ensure templates are always available (set in lifespan normally).
    from pointlessql.api.main import _TEMPLATES

    app.state.templates = _TEMPLATES

    # Ensure settings has auth fields.  Some test modules create their
    # own Settings; we patch only if missing.
    if not hasattr(app.state, "settings") or app.state.settings is None:
        from pointlessql.settings import Settings

        app.state.settings = Settings(jupyter_enabled=False)

    # Ensure secret_key is always set.
    app.state.settings.secret_key = _TEST_SECRET  # type: ignore[attr-defined]

    # Create a test user (admin — first user bootstrap) and attach cookie.
    auth.register(factory, "test@test.com", "Test User", "password123")
    token = auth.login(factory, "test@test.com", "password123", _TEST_SECRET)
    app.state._test_auth_cookie = {auth.COOKIE_NAME: token}

    # Create a second, non-admin user for enforcement tests.
    auth.register(factory, "nonadmin@test.com", "Non Admin", "password123")
    non_admin_token = auth.login(
        factory, "nonadmin@test.com", "password123", _TEST_SECRET
    )
    app.state._test_non_admin_cookie = {auth.COOKIE_NAME: non_admin_token}

    yield

    engine.dispose()


@pytest.fixture
def auth_cookies() -> dict[str, str]:
    """Return a dict with the auth cookie for the admin test user."""
    return app.state._test_auth_cookie


@pytest.fixture
def non_admin_cookies() -> dict[str, str]:
    """Return a dict with the auth cookie for the non-admin test user."""
    return app.state._test_non_admin_cookie

_E2E_CATALOG = "e2e_smoke_catalog"
_E2E_SCHEMA = "e2e_smoke_schema"
_E2E_TABLE = "e2e_smoke_table"
_E2E_FULL_NAME = f"{_E2E_CATALOG}.{_E2E_SCHEMA}.{_E2E_TABLE}"


@pytest.fixture
def soyuz_client() -> Client:
    """Return a configured soyuz-catalog client for integration tests."""
    return make_soyuz_client()


@pytest.fixture
def e2e_env(tmp_path: Path) -> Any:
    """Create a throwaway catalog and schema on live soyuz-catalog.

    Yields a dict with ``pql``, ``client``, ``catalog``, ``schema``,
    ``table``, ``full_name``, and ``storage_root`` keys.
    """
    client = make_soyuz_client()
    storage_root = str(tmp_path / "warehouse" / _E2E_CATALOG / _E2E_SCHEMA)

    try:
        _create_catalog.sync(
            client=client,
            body=CreateCatalog(name=_E2E_CATALOG),
        )
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise

    try:
        _create_schema.sync(
            client=client,
            body=CreateSchema(
                catalog_name=_E2E_CATALOG,
                name=_E2E_SCHEMA,
                storage_root=storage_root,
            ),
        )
    except UnexpectedStatus as exc:
        if exc.status_code != 409:
            raise

    pql = PQL(client=client)

    yield {
        "pql": pql,
        "client": client,
        "catalog": _E2E_CATALOG,
        "schema": _E2E_SCHEMA,
        "table": _E2E_TABLE,
        "full_name": _E2E_FULL_NAME,
        "storage_root": storage_root,
    }

    # Teardown: delete table, schema, catalog.
    try:
        _delete_table.sync(_E2E_FULL_NAME, client=client)
    except UnexpectedStatus:
        pass
    try:
        _delete_schema.sync(f"{_E2E_CATALOG}.{_E2E_SCHEMA}", client=client)
    except UnexpectedStatus:
        pass
    try:
        _delete_catalog.sync(_E2E_CATALOG, client=client, force=True)
    except UnexpectedStatus:
        pass

    delta_dir = Path(storage_root) / _E2E_TABLE
    if delta_dir.exists():
        shutil.rmtree(delta_dir)
