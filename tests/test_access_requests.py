"""Access requests: service lifecycle, routes, and table-page integration.

The access-requests router ships unregistered (the navigation
integration wires it into the bootstrap block later), so this module
mounts it onto the app for its own duration and removes the routes on
teardown — mirroring how the serving cockpit tests bootstrap their
page.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from pointlessql.api import access_requests_routes
from pointlessql.api.main import app
from pointlessql.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models import Base, User, UserNotification, Workspace
from pointlessql.services import access_requests as svc
from pointlessql.services.unitycatalog import UnityCatalogClient

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True, scope="module")
def _ensure_schema(_test_engine: tuple[Engine, sessionmaker[Any]]):
    """Create the access-requests table on the session-scoped engine.

    The ledger has no Alembic migration yet; ``create_all`` is
    idempotent so this only adds what is missing.
    """
    engine, _ = _test_engine
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True, scope="module")
def _mount_access_requests_router():
    """Mount the unregistered router for this module's duration."""
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/access-requests" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(access_requests_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``UnityCatalogClient.for_principal`` to ``app.state.uc_client``."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


def _make_uc_mock(
    *,
    owner: str = "test@test.com",
    effective: list[dict[str, Any]] | None = None,
    tags: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """UC stub with enough surface for the request + table-page routes."""
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "shop",
            "schema_name": "sales",
            "table_type": "MANAGED",
            "data_source_format": "DELTA",
            "storage_location": "/tmp/orders",
            "owner": owner,
            "columns": [],
            "comment": "",
            "properties": {},
            "created_at": 1700000000000,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
    client.get_permissions = AsyncMock(return_value=[])
    client.get_tags = AsyncMock(return_value=tags or [])
    client.update_tags = AsyncMock(return_value=[])
    client.update_permissions = AsyncMock(return_value=[])
    client.get_lineage = AsyncMock(
        return_value={
            "upstream": {"nodes": [], "edges": []},
            "downstream": {"nodes": [], "edges": []},
        }
    )
    return client


def _user_id(email: str) -> int:
    factory = app.state.session_factory
    with factory() as session:
        return session.execute(select(User.id).where(User.email == email)).scalar_one()


def _notifications(event_type: str) -> list[UserNotification]:
    factory = app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(UserNotification).where(UserNotification.event_type == event_type)
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


# ---------------------------------------------------------------------------
# Service lifecycle (in-memory factory)
# ---------------------------------------------------------------------------


@pytest.fixture
def factory() -> Any:
    """In-memory session factory seeded with a workspace + two users."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            Workspace(
                id=1,
                slug="w",
                name="Workspace",
                description="seed",
                created_at=_NOW,
            )
        )
        session.add_all(
            [
                User(
                    email="requester@test.com",
                    display_name="Requester",
                    password_hash="x",
                    is_admin=False,
                    created_at=_NOW,
                ),
                User(
                    email="owner@test.com",
                    display_name="Owner",
                    password_hash="x",
                    is_admin=False,
                    created_at=_NOW,
                ),
            ]
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _ids(factory: Any) -> tuple[int, int]:
    with factory() as session:
        requester = session.execute(
            select(User.id).where(User.email == "requester@test.com")
        ).scalar_one()
        owner = session.execute(select(User.id).where(User.email == "owner@test.com")).scalar_one()
        return int(requester), int(owner)


def _create(factory: Any, requester_id: int, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "workspace_id": 1,
        "securable_type": "table",
        "full_name": "shop.sales.orders",
        "requester_user_id": requester_id,
        "requester_email": "requester@test.com",
        "owner_email": "owner@test.com",
        "privileges": ["SELECT"],
        "justification": "need it for a dashboard",
    }
    kwargs.update(overrides)
    return svc.create_request(factory, **kwargs)


class TestServiceLifecycle:
    def test_create_and_serialize(self, factory: Any) -> None:
        requester_id, _ = _ids(factory)
        row = _create(factory, requester_id)
        data = svc.serialize(row)
        assert data["status"] == "pending"
        assert data["privileges"] == ["SELECT"]
        assert data["owner_email_snapshot"] == "owner@test.com"
        assert data["requester_email"] == "requester@test.com"
        assert data["justification"] == "need it for a dashboard"
        assert data["decided_at"] is None

    def test_create_rejects_blank_privilege(self, factory: Any) -> None:
        requester_id, _ = _ids(factory)
        with pytest.raises(ValidationError):
            _create(factory, requester_id, privileges=["SELECT", "  "])

    def test_duplicate_pending_guard(self, factory: Any) -> None:
        requester_id, _ = _ids(factory)
        row = _create(factory, requester_id)
        with pytest.raises(ValidationError):
            _create(factory, requester_id)
        # a terminal status frees the requester to re-request later.
        svc.cancel(factory, request_id=row.id, requester_user_id=requester_id)
        again = _create(factory, requester_id)
        assert again.status == "pending"

    def test_has_pending_request(self, factory: Any) -> None:
        requester_id, _ = _ids(factory)
        common: dict[str, Any] = {
            "workspace_id": 1,
            "securable_type": "table",
            "full_name": "shop.sales.orders",
            "requester_user_id": requester_id,
        }
        assert svc.has_pending_request(factory, **common) is False
        row = _create(factory, requester_id)
        assert svc.has_pending_request(factory, **common) is True
        svc.cancel(factory, request_id=row.id, requester_user_id=requester_id)
        assert svc.has_pending_request(factory, **common) is False

    def test_approve_by_owner_snapshot(self, factory: Any) -> None:
        requester_id, owner_id = _ids(factory)
        row = _create(factory, requester_id)
        updated = svc.approve(
            factory,
            request_id=row.id,
            decider_user_id=owner_id,
            decider_email="owner@test.com",
            is_admin=False,
            note="enjoy",
        )
        assert updated.status == "approved"
        assert updated.decided_by_user_id == owner_id
        assert updated.decision_note == "enjoy"
        assert updated.decided_at is not None

    def test_decide_gate_admin_or_owner_only(self, factory: Any) -> None:
        requester_id, owner_id = _ids(factory)
        row = _create(factory, requester_id)
        with pytest.raises(PermissionDeniedError):
            svc.approve(
                factory,
                request_id=row.id,
                decider_user_id=requester_id,
                decider_email="requester@test.com",
                is_admin=False,
                note=None,
            )
        # an admin with a non-matching e-mail passes the gate.
        updated = svc.approve(
            factory,
            request_id=row.id,
            decider_user_id=owner_id,
            decider_email="someone-else@test.com",
            is_admin=True,
            note=None,
        )
        assert updated.status == "approved"

    def test_deny_requires_note(self, factory: Any) -> None:
        requester_id, owner_id = _ids(factory)
        row = _create(factory, requester_id)
        with pytest.raises(ValidationError):
            svc.deny(
                factory,
                request_id=row.id,
                decider_user_id=owner_id,
                decider_email="owner@test.com",
                is_admin=False,
                note="   ",
            )
        updated = svc.deny(
            factory,
            request_id=row.id,
            decider_user_id=owner_id,
            decider_email="owner@test.com",
            is_admin=False,
            note="ask the steward instead",
        )
        assert updated.status == "denied"
        assert updated.decision_note == "ask the steward instead"

    def test_decide_only_pending(self, factory: Any) -> None:
        requester_id, owner_id = _ids(factory)
        row = _create(factory, requester_id)
        svc.approve(
            factory,
            request_id=row.id,
            decider_user_id=owner_id,
            decider_email="owner@test.com",
            is_admin=False,
            note=None,
        )
        with pytest.raises(ConflictError):
            svc.deny(
                factory,
                request_id=row.id,
                decider_user_id=owner_id,
                decider_email="owner@test.com",
                is_admin=False,
                note="too late",
            )
        with pytest.raises(ResourceNotFoundError):
            svc.approve(
                factory,
                request_id=999,
                decider_user_id=owner_id,
                decider_email="owner@test.com",
                is_admin=False,
                note=None,
            )

    def test_cancel_rules(self, factory: Any) -> None:
        requester_id, owner_id = _ids(factory)
        row = _create(factory, requester_id)
        with pytest.raises(PermissionDeniedError):
            svc.cancel(factory, request_id=row.id, requester_user_id=owner_id)
        updated = svc.cancel(factory, request_id=row.id, requester_user_id=requester_id)
        assert updated.status == "cancelled"
        with pytest.raises(ConflictError):
            svc.cancel(factory, request_id=row.id, requester_user_id=requester_id)

    def test_list_for_requester_newest_first(self, factory: Any) -> None:
        requester_id, _ = _ids(factory)
        first = _create(factory, requester_id, full_name="shop.sales.orders")
        second = _create(factory, requester_id, full_name="shop.sales.items")
        rows = svc.list_for_requester(factory, workspace_id=1, user_id=requester_id)
        assert [r.id for r in rows] == [second.id, first.id]

    def test_list_pending_for_decider_scoping(self, factory: Any) -> None:
        requester_id, owner_id = _ids(factory)
        mine = _create(factory, requester_id)
        other = _create(
            factory,
            requester_id,
            full_name="shop.sales.items",
            owner_email="third@test.com",
        )
        admin_rows = svc.list_pending_for_decider(
            factory, workspace_id=1, email="whoever@test.com", is_admin=True
        )
        assert {r.id for r in admin_rows} == {mine.id, other.id}
        owner_rows = svc.list_pending_for_decider(
            factory, workspace_id=1, email="owner@test.com", is_admin=False
        )
        assert [r.id for r in owner_rows] == [mine.id]
        assert svc.list_pending_for_decider(factory, workspace_id=1, email="", is_admin=False) == []
        _ = owner_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def _file_request(
    client: httpx.AsyncClient, full_name: str = "shop.sales.orders"
) -> dict[str, Any]:
    resp = await client.post(
        "/api/access-requests",
        json={"full_name": full_name, "justification": "dashboard build"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRequestRoutes:
    async def test_create_lists_and_notifies_owner(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(owner="test@test.com")
        data = await _file_request(non_admin_client)
        assert data["status"] == "pending"
        assert data["requester_email"] == "nonadmin@test.com"
        assert data["owner_email_snapshot"] == "test@test.com"
        assert data["privileges"] == ["SELECT"]

        # the owner (the admin fixture user) got an inbox row.
        opened = _notifications("pointlessql.access_request.opened")
        assert [n.recipient_user_id for n in opened] == [_user_id("test@test.com")]

        listed = await non_admin_client.get("/api/access-requests?role=requester")
        assert [r["id"] for r in listed.json()["requests"]] == [data["id"]]

    async def test_create_conflicts_when_select_already_held(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective=[{"principal": "nonadmin@test.com", "privileges": ["SELECT"]}]
        )
        resp = await non_admin_client.post(
            "/api/access-requests", json={"full_name": "shop.sales.orders"}
        )
        assert resp.status_code == 409

    async def test_create_rejects_duplicate_pending(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        await _file_request(non_admin_client)
        resp = await non_admin_client.post(
            "/api/access-requests", json={"full_name": "shop.sales.orders"}
        )
        assert resp.status_code == 422

    async def test_create_rejects_malformed_name(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await non_admin_client.post(
            "/api/access-requests", json={"full_name": "not-three-parts"}
        )
        assert resp.status_code == 422

    async def test_approve_grants_then_flips_and_notifies(
        self, non_admin_client: httpx.AsyncClient, admin_client: httpx.AsyncClient
    ) -> None:
        uc = _make_uc_mock()
        app.state.uc_client = uc
        data = await _file_request(non_admin_client)

        resp = await admin_client.post(
            f"/api/access-requests/{data['id']}/approve", json={"note": "welcome"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "approved"
        assert body["decision_note"] == "welcome"

        uc.update_permissions.assert_awaited_once_with(
            "table",
            "shop.sales.orders",
            [{"principal": "nonadmin@test.com", "add": ["SELECT"], "remove": []}],
        )
        decided = _notifications("pointlessql.access_request.approved")
        assert [n.recipient_user_id for n in decided] == [_user_id("nonadmin@test.com")]

    async def test_deny_needs_note_and_never_grants(
        self, non_admin_client: httpx.AsyncClient, admin_client: httpx.AsyncClient
    ) -> None:
        uc = _make_uc_mock()
        app.state.uc_client = uc
        data = await _file_request(non_admin_client)

        resp = await admin_client.post(f"/api/access-requests/{data['id']}/deny", json={})
        assert resp.status_code == 422

        resp = await admin_client.post(
            f"/api/access-requests/{data['id']}/deny", json={"note": "use the data product"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "denied"
        uc.update_permissions.assert_not_awaited()
        decided = _notifications("pointlessql.access_request.denied")
        assert [n.recipient_user_id for n in decided] == [_user_id("nonadmin@test.com")]

    async def test_decider_gate_rejects_non_owner(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        uc = _make_uc_mock(owner="someone-else@test.com")
        app.state.uc_client = uc
        data = await _file_request(non_admin_client)
        resp = await non_admin_client.post(
            f"/api/access-requests/{data['id']}/approve", json={"note": "self-serve"}
        )
        assert resp.status_code == 403
        uc.update_permissions.assert_not_awaited()

    async def test_owner_snapshot_may_decide_at_route_level(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        uc = _make_uc_mock()
        app.state.uc_client = uc
        row = svc.create_request(
            app.state.session_factory,
            workspace_id=1,
            securable_type="table",
            full_name="shop.sales.orders",
            requester_user_id=_user_id("test@test.com"),
            requester_email="test@test.com",
            owner_email="nonadmin@test.com",
            privileges=["SELECT"],
            justification=None,
        )
        resp = await non_admin_client.post(f"/api/access-requests/{row.id}/approve", json={})
        assert resp.status_code == 200, resp.text
        uc.update_permissions.assert_awaited_once()

    async def test_cancel_requester_only(
        self, non_admin_client: httpx.AsyncClient, admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        data = await _file_request(non_admin_client)

        resp = await admin_client.post(f"/api/access-requests/{data['id']}/cancel")
        assert resp.status_code == 403

        resp = await non_admin_client.post(f"/api/access-requests/{data['id']}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_decider_inbox_scoping(
        self, non_admin_client: httpx.AsyncClient, admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(owner="someone-else@test.com")
        data = await _file_request(non_admin_client)

        admin_view = await admin_client.get("/api/access-requests?role=decider")
        assert [r["id"] for r in admin_view.json()["requests"]] == [data["id"]]

        non_owner_view = await non_admin_client.get("/api/access-requests?role=decider")
        assert non_owner_view.json()["requests"] == []

        bogus = await admin_client.get("/api/access-requests?role=bogus")
        assert bogus.status_code == 422

    async def test_unknown_request_is_404(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await admin_client.post("/api/access-requests/4242/approve", json={})
        assert resp.status_code == 404


class TestAccessRequestsPage:
    async def test_page_renders_with_entry_and_single_quoted_x_data(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        resp = await admin_client.get("/access-requests")
        assert resp.status_code == 200
        body = resp.text
        assert 'data-pql-entry="access_requests.js' in body
        assert "x-data='accessRequests(true)'" in body

    async def test_page_renders_for_non_admin(self, non_admin_client: httpx.AsyncClient) -> None:
        resp = await non_admin_client.get("/access-requests")
        assert resp.status_code == 200
        assert "x-data='accessRequests(false)'" in resp.text

    async def test_page_redirects_anonymous(self, anonymous_client: httpx.AsyncClient) -> None:
        resp = await anonymous_client.get("/access-requests", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/auth/login"


# ---------------------------------------------------------------------------
# Table-page integration (catalog_html_routes)
# ---------------------------------------------------------------------------

_TABLE_URL = "/catalogs/shop/schemas/sales/tables/orders"


class TestTablePageIntegration:
    async def test_no_privileges_still_403(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(effective=[])
        resp = await non_admin_client.get(_TABLE_URL)
        assert resp.status_code == 403

    async def test_select_holder_sees_no_request_button(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective=[{"principal": "nonadmin@test.com", "privileges": ["SELECT"]}]
        )
        resp = await non_admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "Request access" not in resp.text

    async def test_browser_without_select_gets_request_button(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective=[{"principal": "nonadmin@test.com", "privileges": ["USE SCHEMA"]}]
        )
        resp = await non_admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "Request access" in resp.text
        assert "pql-request-access-modal" in resp.text

    async def test_pending_request_swaps_button_for_badge(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective=[{"principal": "nonadmin@test.com", "privileges": ["USE SCHEMA"]}]
        )
        svc.create_request(
            app.state.session_factory,
            workspace_id=1,
            securable_type="table",
            full_name="shop.sales.orders",
            requester_user_id=_user_id("nonadmin@test.com"),
            requester_email="nonadmin@test.com",
            owner_email="test@test.com",
            privileges=["SELECT"],
            justification=None,
        )
        resp = await non_admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "Access requested" in resp.text
        assert "pql-request-access-modal" not in resp.text
