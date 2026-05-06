"""Shared test fixtures for PointlesSQL."""

from __future__ import annotations

import datetime
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Disable optional integrations whose subprocess startup would otherwise
# kick in during the FastAPI lifespan triggered by ``TestClient(app)``.
# Settings() reads env vars at construction time, so this must be set
# before any test imports ``pointlessql.api.main``.
os.environ.setdefault("POINTLESSQL_JUPYTER_ENABLED", "0")
os.environ.setdefault("POINTLESSQL_MLFLOW_ENABLED", "0")

# Phase 31.3 — short-circuit the FastAPI lifespan when run under
# ``TestClient(app)`` / ``ASGITransport``.  The conftest pre-wires
# ``app.state.session_factory`` + ``uc_client`` + cookies for every
# test; running the full production lifespan re-overwrites all of
# that and re-runs ``alembic upgrade head`` against the on-disk
# default URL.  The flag tells ``pointlessql.api.main._lifespan``
# to skip the parts the conftest has already provided.  Tests
# that genuinely need the production startup path explicitly
# unset the env var (none today; future ones can monkeypatch).
os.environ.setdefault("POINTLESSQL_TEST_LIFESPAN_FAST", "1")

# Phase 31.1 — lower the bcrypt work factor in tests.  Production keeps
# pwdlib's default rounds=12 (~250 ms per hash); tests here drop to
# rounds=4 (~16 ms).  The algorithm, salt, and cookie format are
# unchanged — only the cost factor.  Done as a module-attribute rebind
# on ``pointlessql.services.auth._hasher`` because every call site goes
# through ``hash_password`` / ``verify_password`` which read the module
# attribute, so a single rebind covers the whole codebase including
# tests that register their own users.
import pointlessql.services.auth as _pql_auth_for_speedup
from pwdlib import PasswordHash as _PwdlibPasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher as _PwdlibBcryptHasher

_pql_auth_for_speedup._hasher = _PwdlibPasswordHash(  # pyright: ignore[reportPrivateUsage]
    (_PwdlibBcryptHasher(rounds=4),)
)

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
from sqlalchemy import text as _sa_text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.models import Base, User, Workspace, WorkspaceMember
from pointlessql.pql.pql import PQL
from pointlessql.services import auth, csrf
from pointlessql.services.soyuz_client import make_soyuz_client

_TEST_SECRET = "test-secret-key-for-unit-tests!!"
_FTS_AXES: tuple[str, ...] = ("runs", "ops", "queries", "tool_calls", "audit_log")
_FTS_SOURCE_TABLES_SQLITE: dict[str, str] = {
    "runs": "agent_runs",
    "ops": "agent_run_operations",
    "queries": "query_history",
    "tool_calls": "agent_run_tool_calls",
    "audit_log": "audit_log",
}


@pytest.fixture(scope="session")
def _test_engine() -> Iterator[tuple[Engine, sessionmaker[Any]]]:  # pyright: ignore[reportUnusedFunction]
    """Build the schema once per test-session, drop it on session exit.

    Phase 31.2 — replaces the previous per-test ``create_all`` /
    ``drop_all`` round-trip (90 DDL statements × 1461 tests).  The
    schema and the engine live for the whole session; per-test
    cleanup ([:func:`_auth_db`]) wipes rows but leaves the schema
    alone.  Tests that need a *fresh* engine for migration-drift
    checks build their own via ``tmp_path`` — they're independent.

    Yields:
        Tuple of (engine, session_factory) bound to whichever
        backend ``TEST_DATABASE_URL`` (or in-memory SQLite by
        default) selects.
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

    yield engine, factory

    Base.metadata.drop_all(engine)
    # ``audit_search_index`` (PG, Sprint 30.1) and ``audit_search``
    # (SQLite FTS5 vtable, Phase 18.7) are created via raw SQL by
    # ``audit_fts.install_index``, not the ORM, so ``drop_all``
    # leaves them in place.  Drop them on session exit so a
    # subsequent run on the same PG (e.g. CI cache) sees a clean
    # slate.
    _drop_audit_fts_artifacts(engine)
    engine.dispose()


def _drop_audit_fts_artifacts(engine: Engine) -> None:
    """Drop the dialect-specific audit-search artefacts.

    Idempotent — silently no-ops if neither path's artefacts exist.
    Used by both the per-test wipe (so tests that opted into FTS
    don't pollute later tests that expect ``available=false``) and
    the session-scope teardown.
    """
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(_sa_text("DROP TABLE IF EXISTS audit_search_index CASCADE"))
            for axis in _FTS_AXES:
                conn.execute(
                    _sa_text(f"DROP FUNCTION IF EXISTS audit_search_{axis}_upsert() CASCADE")
                )
                conn.execute(
                    _sa_text(f"DROP FUNCTION IF EXISTS audit_search_{axis}_delete() CASCADE")
                )
    elif engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            for axis, source in _FTS_SOURCE_TABLES_SQLITE.items():
                # The trigger names match what ``audit_fts.install_index``
                # writes; the ``IF EXISTS`` form keeps this safe when
                # a test never installed FTS in the first place.
                conn.execute(_sa_text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_ai"))
                conn.execute(_sa_text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_ad"))
                conn.execute(_sa_text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_au"))
                # Keep ``source`` referenced so a future shape change
                # to the trigger naming surfaces here, not silently.
                _ = source
            conn.execute(_sa_text("DROP TABLE IF EXISTS audit_search"))


def _wipe_test_rows(engine: Engine) -> None:
    """Delete every row from every ORM table; reset autoincrement.

    Per-test cleanup — runs at fixture entry, not teardown, so the
    last test's residue dies with the session-scope ``drop_all``.
    Schema, sequences, indexes, and (PG) audit-search functions are
    untouched; only row data is wiped.
    """
    # Drop FTS artefacts first — their triggers fire on the source-
    # table DELETEs we're about to run, and we don't need that work.
    _drop_audit_fts_artifacts(engine)

    if engine.dialect.name == "postgresql":
        # One TRUNCATE statement, dialect's fastest path.  ``RESTART
        # IDENTITY`` resets serial sequences so explicit-id INSERTs
        # in the next test (workspace id=1, etc.) don't collide.
        # ``CASCADE`` covers FK chains we'd otherwise have to
        # reverse-order manually.
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with engine.begin() as conn:
            conn.execute(_sa_text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
    else:
        # SQLite: no TRUNCATE, but DELETE on empty/sparse tables is
        # ~µs per table.  Foreign keys are off by default in SQLite
        # but tests sometimes flip them on — drop in reverse FK order
        # to be safe regardless.
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(_sa_text(f"DELETE FROM {table.name}"))
            # Reset rowid auto-increment so explicit-id workspace
            # INSERTs and any tests asserting on id values stay
            # deterministic.  ``sqlite_sequence`` only exists if
            # at least one ``AUTOINCREMENT`` table has been written
            # to, hence the IF EXISTS guard via try/except.
            try:
                conn.execute(_sa_text("DELETE FROM sqlite_sequence"))
            except Exception:
                pass


def _seed_test_users(factory: sessionmaker[Any]) -> tuple[int, int]:
    """Insert the seeded workspace + two test users + memberships.

    Replaces the previous flow of ``auth.register`` + ``auth.login``
    per fixture (4 bcrypt operations).  We hash ``"password123"``
    once at first call; subsequent calls reuse the cached hash so
    the per-test cost is just ~5 INSERTs and the JWT signing.

    Returns:
        ``(admin_user_id, non_admin_user_id)`` — needed for issuing
        the JWT cookies.
    """
    pwd_hash = _CACHED_PWD_HASH
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Workspace(
                id=1,
                slug="default",
                name="Default workspace",
                description="Test-fixture seed (Phase 31.2).",
                created_at=now,
            )
        )
        session.flush()
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            session.execute(
                _sa_text(
                    "SELECT setval('workspaces_id_seq', "
                    "(SELECT COALESCE(MAX(id), 1) FROM workspaces))"
                )
            )
        admin = User(
            email="test@test.com",
            display_name="Test User",
            password_hash=pwd_hash,
            is_admin=True,
            default_workspace_id=1,
            created_at=now,
        )
        non_admin = User(
            email="nonadmin@test.com",
            display_name="Non Admin",
            password_hash=pwd_hash,
            is_admin=False,
            default_workspace_id=1,
            created_at=now,
        )
        session.add_all([admin, non_admin])
        session.flush()
        session.add_all(
            [
                WorkspaceMember(
                    workspace_id=1,
                    user_id=admin.id,
                    role="admin",
                    created_at=now,
                ),
                WorkspaceMember(
                    workspace_id=1,
                    user_id=non_admin.id,
                    role="member",
                    created_at=now,
                ),
            ]
        )
        session.commit()
        return admin.id, non_admin.id


# Hash the seed password once per session — the patched bcrypt at
# rounds=4 takes ~16 ms, so even one hash matters when fanning out
# across 1461 tests.
_CACHED_PWD_HASH = auth.hash_password("password123")


@pytest.fixture(autouse=True)
def _auth_db(  # pyright: ignore[reportUnusedFunction]
    _test_engine: tuple[Engine, sessionmaker[Any]],
) -> Iterator[None]:
    """Per-test wipe + reseed; binds ``app.state`` to the worker engine.

    Phase 31.2 split: schema + engine live in the session-scope
    :func:`_test_engine` fixture; this autouse fixture only handles
    the per-test row wipe and the seeded workspace/users that 84+
    test files implicitly depend on.

    Respects ``TEST_DATABASE_URL`` to run against Postgres or another
    backend — the env-var read happens in :func:`_test_engine`.
    """
    engine, factory = _test_engine

    _wipe_test_rows(engine)
    admin_id, non_admin_id = _seed_test_users(factory)

    app.state.session_factory = factory

    # Sprint 13.x onwards (UC mutations / lineage / external-write
    # cross-refs) read ``app.state.uc_client`` from
    # ``runs_routes._loaders``, ``soyuz_audit``, and friends.  Tests
    # that need real UC behaviour overwrite this with their own
    # ``MagicMock(spec=UnityCatalogClient)`` (see e.g.
    # ``test_error_handlers``); a default MagicMock here keeps the
    # render path crash-free for the majority of tests that don't
    # touch UC at all.  The ``soyuz_audit.fetch_for_run`` swallow-
    # all-exceptions block neutralises any unexpected awaitable
    # mismatches.
    if not hasattr(app.state, "uc_client") or app.state.uc_client is None:
        app.state.uc_client = MagicMock()

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

    # Issue cookies directly — skip ``auth.login`` since we already
    # know the user_id (from the INSERT above) and the password is
    # the one we just inserted.  ``create_jwt`` is microsecond-fast.
    admin_token = auth.create_jwt(admin_id, "test@test.com", True, _TEST_SECRET)
    non_admin_token = auth.create_jwt(non_admin_id, "nonadmin@test.com", False, _TEST_SECRET)
    app.state._test_auth_cookie = {auth.COOKIE_NAME: admin_token}
    app.state._test_non_admin_cookie = {auth.COOKIE_NAME: non_admin_token}

    yield


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
