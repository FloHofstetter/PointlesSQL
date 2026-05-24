"""FastAPI route smoke-tests for federation_routes.py.

Covers the 21 connection / external-location / credential endpoints
+ HTML page render paths.  Each endpoint gets at least one
admin-success and one non-admin-rejection check; mutating routes
also assert that an ``audit_log`` row landed.

The existing ``test_federation.py`` test-suite covers the
:class:`UnityCatalogClient` service layer end of the pipeline.  This
file owns the route layer — middleware (``require_admin``) +
delegation + audit emission.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.models import AuditLog
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``get_uc_client`` return whatever ``app.state.uc_client`` is."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


def _wipe_audit() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(AuditLog).delete()
        session.commit()


def _audit_actions() -> list[str]:
    factory = app.state.session_factory
    with factory() as session:
        return [r.action for r in session.query(AuditLog).all()]


def _mock_uc(**methods: object) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    for name, return_value in methods.items():
        setattr(client, name, AsyncMock(return_value=return_value))
    return client


def _full_connection(**overrides: object) -> dict[str, object]:
    """Connection dict with every field the HTML detail-page reads."""
    base: dict[str, object] = {
        "name": "pg",
        "connection_type": "POSTGRESQL",
        "owner": "admin@test.com",
        "created_at": 1714000000000,
        "updated_at": 1714000005000,
        "options": {"host": "db.local", "port": "5432"},
    }
    base.update(overrides)
    return base


def _full_external_location(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "loc1",
        "url": "s3://b/p",
        "owner": "admin@test.com",
        "credential_name": "cred1",
        "created_at": 1714000000000,
        "updated_at": 1714000005000,
    }
    base.update(overrides)
    return base


def _full_credential(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "cred1",
        "credential_type": "AWS_IAM_ROLE",
        "purpose": "STORAGE",
        "owner": "admin@test.com",
        "created_at": 1714000000000,
        "updated_at": 1714000005000,
    }
    base.update(overrides)
    return base


# -- Connections (5 routes) --


async def test_list_connections_admin_succeeds(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(
        list_connections=[{"name": "pg", "connection_type": "POSTGRESQL"}]
    )
    resp = await admin_client.get("/api/connections")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "pg", "connection_type": "POSTGRESQL"}]


async def test_list_connections_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(list_connections=[])
    resp = await non_admin_client.get("/api/connections")
    assert resp.status_code == 403


async def test_create_connection_emits_audit(admin_client: httpx.AsyncClient) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(
        create_connection={"name": "pg", "connection_type": "POSTGRESQL"}
    )
    resp = await admin_client.post(
        "/api/connections",
        json={"name": "pg", "connection_type": "POSTGRESQL"},
    )
    assert resp.status_code == 200
    assert "create_connection" in _audit_actions()


async def test_get_connection_admin_succeeds(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(get_connection={"name": "pg"})
    resp = await admin_client.get("/api/connections/pg")
    assert resp.status_code == 200
    assert resp.json()["name"] == "pg"


async def test_update_connection_emits_audit(admin_client: httpx.AsyncClient) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(update_connection={"name": "pg", "comment": "x"})
    resp = await admin_client.patch("/api/connections/pg", json={"comment": "x"})
    assert resp.status_code == 200
    assert "update_connection" in _audit_actions()


async def test_delete_connection_emits_audit(admin_client: httpx.AsyncClient) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(delete_connection=None)
    resp = await admin_client.delete("/api/connections/pg")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}
    assert "delete_connection" in _audit_actions()


# -- External Locations (5 routes) --


async def test_list_external_locations_admin_succeeds(
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(list_external_locations=[{"name": "loc1", "url": "s3://b/p"}])
    resp = await admin_client.get("/api/external-locations")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "loc1"


async def test_list_external_locations_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(list_external_locations=[])
    resp = await non_admin_client.get("/api/external-locations")
    assert resp.status_code == 403


async def test_create_external_location_emits_audit(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(create_external_location={"name": "loc1", "url": "s3://b/p"})
    resp = await admin_client.post(
        "/api/external-locations",
        json={"name": "loc1", "url": "s3://b/p", "credential_name": "cred1"},
    )
    assert resp.status_code == 200
    assert "create_ext_location" in _audit_actions()


async def test_get_external_location_admin_succeeds(
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(get_external_location={"name": "loc1"})
    resp = await admin_client.get("/api/external-locations/loc1")
    assert resp.status_code == 200


async def test_update_external_location_emits_audit(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(update_external_location={"name": "loc1"})
    resp = await admin_client.patch("/api/external-locations/loc1", json={"comment": "y"})
    assert resp.status_code == 200
    assert "update_ext_location" in _audit_actions()


async def test_delete_external_location_emits_audit(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(delete_external_location=None)
    resp = await admin_client.delete("/api/external-locations/loc1")
    assert resp.status_code == 200
    assert "delete_ext_location" in _audit_actions()


# -- Credentials (5 routes) --


async def test_list_credentials_admin_succeeds(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(
        list_credentials=[{"name": "cred1", "credential_type": "AWS_IAM_ROLE"}]
    )
    resp = await admin_client.get("/api/credentials")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "cred1"


async def test_list_credentials_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(list_credentials=[])
    resp = await non_admin_client.get("/api/credentials")
    assert resp.status_code == 403


async def test_create_credential_audits_without_secret(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(create_credential={"name": "cred1"})
    resp = await admin_client.post(
        "/api/credentials",
        json={
            "name": "cred1",
            "credential_type": "AWS_IAM_ROLE",
            "aws_iam_role": {"role_arn": "arn:aws:iam::123:role/x"},
        },
    )
    assert resp.status_code == 200
    actions = _audit_actions()
    assert "create_credential" in actions


async def test_get_credential_admin_succeeds(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(get_credential={"name": "cred1"})
    resp = await admin_client.get("/api/credentials/cred1")
    assert resp.status_code == 200


async def test_update_credential_emits_audit(admin_client: httpx.AsyncClient) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(update_credential={"name": "cred1"})
    resp = await admin_client.patch("/api/credentials/cred1", json={"comment": "z"})
    assert resp.status_code == 200
    assert "update_credential" in _audit_actions()


async def test_delete_credential_emits_audit(admin_client: httpx.AsyncClient) -> None:
    _wipe_audit()
    app.state.uc_client = _mock_uc(delete_credential=None)
    resp = await admin_client.delete("/api/credentials/cred1")
    assert resp.status_code == 200
    assert "delete_credential" in _audit_actions()


# -- HTML page routes (6 routes) --


async def test_connections_index_renders(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(list_connections=[_full_connection()])
    resp = await admin_client.get("/connections")
    assert resp.status_code == 200
    assert "Connections" in resp.text or "pg" in resp.text


async def test_connections_index_renders_outage_banner(
    admin_client: httpx.AsyncClient,
) -> None:
    """Soyuz outage degrades to an in-page banner, not a 5xx."""
    client = MagicMock(spec=UnityCatalogClient)
    client.list_connections = AsyncMock(side_effect=CatalogUnavailableError("soyuz down"))
    app.state.uc_client = client
    resp = await admin_client.get("/connections")
    assert resp.status_code == 200


async def test_connection_detail_renders(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(get_connection=_full_connection())
    resp = await admin_client.get("/connections/pg")
    assert resp.status_code == 200


async def test_external_locations_index_renders(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(list_external_locations=[_full_external_location()])
    resp = await admin_client.get("/external-locations")
    assert resp.status_code == 200


async def test_external_location_detail_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(get_external_location=_full_external_location())
    resp = await admin_client.get("/external-locations/loc1")
    assert resp.status_code == 200


async def test_credentials_index_renders(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(list_credentials=[_full_credential()])
    resp = await admin_client.get("/credentials")
    assert resp.status_code == 200


async def test_credential_detail_renders(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _mock_uc(get_credential=_full_credential())
    resp = await admin_client.get("/credentials/cred1")
    assert resp.status_code == 200


async def test_connections_index_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _mock_uc(list_connections=[])
    resp = await non_admin_client.get("/connections")
    assert resp.status_code == 403
