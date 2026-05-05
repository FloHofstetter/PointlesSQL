"""Shared test fixtures for PointlesSQL."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

# Disable optional integrations whose subprocess startup would otherwise
# kick in during the FastAPI lifespan triggered by ``TestClient(app)``.
# Settings() reads env vars at construction time, so this must be set
# before any test imports ``pointlessql.api.main``.
os.environ.setdefault("POINTLESSQL_JUPYTER_ENABLED", "0")
os.environ.setdefault("POINTLESSQL_MLFLOW_ENABLED", "0")

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
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.models import Base, User, Workspace, WorkspaceMember
from pointlessql.pql.pql import PQL
from pointlessql.services import auth, csrf
from pointlessql.services.soyuz_client import make_soyuz_client

_TEST_SECRET = "test-secret-key-for-unit-tests!!"


@pytest.fixture(autouse=True)
def _auth_db():
    """Set up an auth DB and authenticated cookie for all tests.

    Respects ``TEST_DATABASE_URL`` to run against Postgres or another
    backend. Defaults to in-memory SQLite when unset.
    """
    db_url = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    engine_kwargs: dict[str, object] = {}
    if db_url.startswith("sqlite"):
        # ``sqlite:///:memory:`` creates a *per-connection* database, so
        # a pooled QueuePool gives each worker thread its own empty
        # copy — ``asyncio.to_thread``-backed code paths like
        # ``_build_home_summary._db_block`` then report "no such
        # table: jobs". Pinning every test to a single shared
        # connection (``StaticPool`` + ``check_same_thread=False``)
        # keeps the schema alive across threads without forcing
        # callers onto a temp file (Sprint 47).
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(db_url, **engine_kwargs)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app.state.session_factory = factory

    # Ensure templates are always available (set in lifespan normally).
    from pointlessql.api.main import _TEMPLATES

    app.state.templates = _TEMPLATES

    # Ensure settings has auth fields.  Some test modules create their
    # own Settings; we patch only if missing. The scheduler is opted out
    # so the background loop never ticks during normal test runs —
    # dedicated scheduler tests flip it back on via ``monkeypatch``.
    if not hasattr(app.state, "settings") or app.state.settings is None:
        from pointlessql.settings import Settings

        app.state.settings = Settings(
            jupyter={"enabled": False},
            scheduler={"enabled": False},
            mlflow={"enabled": False},
        )
    else:
        app.state.settings.scheduler.enabled = False  # type: ignore[attr-defined]
        app.state.settings.mlflow.enabled = False  # type: ignore[attr-defined]

    # Ensure secret_key is always set.
    app.state.settings.auth.secret_key = _TEST_SECRET  # type: ignore[attr-defined]

    # Phase 28.0: seed the default workspace + membership rows.  The
    # production-side bootstrap migration creates these; tests build
    # the schema with ``Base.metadata.create_all`` so we re-create the
    # seed manually here.  Every existing fixture user becomes a
    # member of the default workspace with role mirroring is_admin.
    _seed_default_workspace(factory)

    # Create a test user (admin — first user bootstrap) and attach cookie.
    auth.register(factory, "test@test.com", "Test User", "password123")
    _add_user_to_default_workspace(factory, "test@test.com", role="admin")
    token = auth.login(factory, "test@test.com", "password123", _TEST_SECRET)
    app.state._test_auth_cookie = {auth.COOKIE_NAME: token}

    # Create a second, non-admin user for enforcement tests.
    auth.register(factory, "nonadmin@test.com", "Non Admin", "password123")
    _add_user_to_default_workspace(factory, "nonadmin@test.com", role="member")
    non_admin_token = auth.login(factory, "nonadmin@test.com", "password123", _TEST_SECRET)
    app.state._test_non_admin_cookie = {auth.COOKIE_NAME: non_admin_token}

    yield

    # Drop all tables so each test starts clean (required for Postgres;
    # in-memory SQLite engines are discarded on dispose anyway).
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_default_workspace(factory: Any) -> None:
    """Insert the ``id=1, slug='default'`` row tests rely on.

    Mirrors the Sprint-28.0 bootstrap migration's seed step.  The
    production code path runs alembic; the test path bypasses
    alembic (Base.metadata.create_all is faster) so this helper
    keeps the two paths semantically equivalent.
    """
    import datetime

    with factory() as session:
        existing = session.get(Workspace, 1)
        if existing is not None:
            return
        session.add(
            Workspace(
                id=1,
                slug="default",
                name="Default workspace",
                description="Test-fixture seed (Sprint 28.0).",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


def _add_user_to_default_workspace(factory: Any, email: str, *, role: str) -> None:
    """Add the user named *email* as a member of workspace id=1."""
    import datetime

    with factory() as session:
        user = session.query(User).filter(User.email == email.lower()).first()
        if user is None:
            return
        user.default_workspace_id = 1
        existing = (
            session.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == 1,
                WorkspaceMember.user_id == user.id,
            )
            .first()
        )
        if existing is None:
            session.add(
                WorkspaceMember(
                    workspace_id=1,
                    user_id=user.id,
                    role=role,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
        session.commit()


@pytest.fixture
def auth_cookies() -> dict[str, str]:
    """Return a dict with the auth cookie for the admin test user."""
    return app.state._test_auth_cookie


@pytest.fixture
def non_admin_cookies() -> dict[str, str]:
    """Return a dict with the auth cookie for the non-admin test user."""
    return app.state._test_non_admin_cookie


async def seed_csrf(client: Any) -> str:
    """Seed the CSRF cookie on an ``httpx.AsyncClient`` and return the token.

    The Sprint 42 CSRF middleware rejects any non-safe request that
    arrives without a matching ``pql_csrf`` cookie. Tests that submit
    form POSTs to ``/auth/*`` (or any future non-API HTML form route)
    should ``await seed_csrf(client)`` before the POST to obtain the
    token and let httpx's cookie jar carry the cookie into the POST.
    """
    resp = await client.get("/auth/login")
    return resp.cookies[csrf.COOKIE_NAME]


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
