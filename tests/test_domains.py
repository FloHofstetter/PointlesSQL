"""Domain ownership foundation — service + admin CRUD + browse + assignment.

Covers the data-mesh Domänen-Fundament: the Domain / DomainMember /
DataProductTransformation entities, the admin CRUD surface, the
read-only browse API, and the product↔domain assignment +
transformation-binding endpoints.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct, Notebook, User
from pointlessql.services import domains as domains_service


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "test@test.com"))


def _non_admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "nonadmin@test.com"))


def _seed_dp(catalog: str, schema: str, *, steward_user_id: int | None = None) -> int:
    """Insert a minimal DataProduct row with a valid contract; return its id."""
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            steward_user_id=steward_user_id,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


# ---------------------------------------------------------------------------
# service layer
# ---------------------------------------------------------------------------


def test_create_domain_auto_adds_owner() -> None:
    uid = _admin_user_id()
    domain = domains_service.create_domain(
        _factory(),
        workspace_id=1,
        slug="sales",
        name="Sales",
        archetype="source-aligned",
        creator_user_id=uid,
    )
    assert domain.slug == "sales"
    members = domains_service.list_members(_factory(), domain_id=domain.id)
    assert len(members) == 1
    assert members[0].user_id == uid
    assert members[0].role == "owner"


def test_create_domain_rejects_duplicate_slug() -> None:
    domains_service.create_domain(
        _factory(), workspace_id=1, slug="dup", name="A", archetype="aggregate"
    )
    with pytest.raises(ValueError, match="already exists"):
        domains_service.create_domain(
            _factory(), workspace_id=1, slug="dup", name="B", archetype="aggregate"
        )


def test_create_domain_rejects_bad_archetype() -> None:
    with pytest.raises(ValueError, match="archetype"):
        domains_service.create_domain(
            _factory(), workspace_id=1, slug="x", name="X", archetype="nonsense"
        )


def test_add_member_is_idempotent_role_upsert() -> None:
    uid = _non_admin_user_id()
    domain = domains_service.create_domain(
        _factory(), workspace_id=1, slug="d", name="D", archetype="aggregate"
    )
    domains_service.add_member(_factory(), domain_id=domain.id, user_id=uid, role="developer")
    domains_service.add_member(_factory(), domain_id=domain.id, user_id=uid, role="owner")
    members = domains_service.list_members(_factory(), domain_id=domain.id)
    assert len(members) == 1
    assert members[0].role == "owner"


def test_assign_product_domain_and_clear() -> None:
    dp_id = _seed_dp("main", "svc_a")
    domain = domains_service.create_domain(
        _factory(), workspace_id=1, slug="svc", name="Svc", archetype="source-aligned"
    )
    domains_service.assign_product_domain(
        _factory(), workspace_id=1, data_product_id=dp_id, domain_id=domain.id
    )
    products = domains_service.list_products_for_domain(_factory(), domain_id=domain.id)
    assert [p.id for p in products] == [dp_id]

    domains_service.assign_product_domain(
        _factory(), workspace_id=1, data_product_id=dp_id, domain_id=None
    )
    assert domains_service.list_products_for_domain(_factory(), domain_id=domain.id) == []


def test_assign_product_domain_rejects_unknown_product() -> None:
    domain = domains_service.create_domain(
        _factory(), workspace_id=1, slug="z", name="Z", archetype="aggregate"
    )
    with pytest.raises(ValueError, match="data product"):
        domains_service.assign_product_domain(
            _factory(), workspace_id=1, data_product_id=999999, domain_id=domain.id
        )


def test_bind_notebook_transformation_and_unbind() -> None:
    dp_id = _seed_dp("main", "svc_tx")
    now = datetime.datetime.now(datetime.UTC)
    nb_id = "11111111-1111-4111-8111-111111111111"
    with _factory()() as session:
        session.add(Notebook(id=nb_id, workspace_id=1, file_path="nb/build.py", created_at=now))
        session.commit()

    row = domains_service.bind_transformation(
        _factory(), data_product_id=dp_id, kind="notebook", notebook_id=nb_id
    )
    assert row.kind == "notebook"
    assert row.notebook_id == nb_id
    # idempotent re-bind returns the same row id.
    again = domains_service.bind_transformation(
        _factory(), data_product_id=dp_id, kind="notebook", notebook_id=nb_id
    )
    assert again.id == row.id

    assert domains_service.unbind_transformation(
        _factory(), data_product_id=dp_id, transformation_id=row.id
    )
    assert domains_service.list_transformations(_factory(), data_product_id=dp_id) == []


def test_bind_dbt_transformation_requires_model_name() -> None:
    dp_id = _seed_dp("main", "svc_dbt")
    with pytest.raises(ValueError, match="dbt_model"):
        domains_service.bind_transformation(
            _factory(), data_product_id=dp_id, kind="dbt_model", dbt_model_name=""
        )
    row = domains_service.bind_transformation(
        _factory(), data_product_id=dp_id, kind="dbt_model", dbt_model_name="stg_orders"
    )
    assert row.dbt_model_name == "stg_orders"
    assert row.notebook_id is None


# ---------------------------------------------------------------------------
# admin CRUD API
# ---------------------------------------------------------------------------


async def test_admin_create_list_and_archive_domain() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/domains",
            json={"slug": "fin", "name": "Finance", "archetype": "aggregate"},
        )
        assert post.status_code == 200, post.text
        domain_id = post.json()["id"]
        assert post.json()["archetype"] == "aggregate"

        listing = await client.get("/api/admin/domains")
        assert "fin" in {d["slug"] for d in listing.json()["domains"]}

        archive = await client.post(f"/api/admin/domains/{domain_id}/archive")
        assert archive.status_code == 200
        assert archive.json()["archived_at"] is not None

        active = await client.get("/api/admin/domains")
        assert "fin" not in {d["slug"] for d in active.json()["domains"]}


async def test_admin_create_rejects_bad_archetype() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.post(
            "/api/admin/domains",
            json={"slug": "bad", "name": "Bad", "archetype": "wrong"},
        )
    assert res.status_code in (400, 422)


async def test_admin_domains_requires_admin() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post(
            "/api/admin/domains",
            json={"slug": "nope", "name": "Nope", "archetype": "aggregate"},
        )
    assert res.status_code in (401, 403)


async def test_admin_member_add_and_role_change() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/domains",
            json={"slug": "ops", "name": "Ops", "archetype": "consumer-aligned"},
        )
        domain_id = post.json()["id"]
        add = await client.post(
            f"/api/admin/domains/{domain_id}/members",
            json={"user_email": "nonadmin@test.com", "role": "developer"},
        )
        assert add.status_code == 200
        user_id = add.json()["user_id"]
        assert add.json()["role"] == "developer"

        patch = await client.patch(
            f"/api/admin/domains/{domain_id}/members/{user_id}",
            json={"role": "owner"},
        )
        assert patch.status_code == 200
        assert patch.json()["role"] == "owner"

        delete = await client.delete(f"/api/admin/domains/{domain_id}/members/{user_id}")
        assert delete.status_code == 200
        assert delete.json()["deleted"] is True


# ---------------------------------------------------------------------------
# browse API
# ---------------------------------------------------------------------------


async def test_browse_list_and_detail_with_products() -> None:
    domain = domains_service.create_domain(
        _factory(), workspace_id=1, slug="catalog-team", name="Catalog Team", archetype="aggregate"
    )
    dp_id = _seed_dp("main", "browse_dp")
    domains_service.assign_product_domain(
        _factory(), workspace_id=1, data_product_id=dp_id, domain_id=domain.id
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        listing = await client.get("/api/domains")
        assert listing.status_code == 200
        match = next(d for d in listing.json()["domains"] if d["slug"] == "catalog-team")
        assert match["product_count"] == 1

        detail = await client.get("/api/domains/catalog-team")
        assert detail.status_code == 200
        body = detail.json()
        assert body["name"] == "Catalog Team"
        assert {p["ref"] for p in body["products"]} == {"main.browse_dp"}


async def test_browse_detail_404_for_unknown_slug() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/domains/does-not-exist")
    assert res.status_code == 404


async def test_browse_requires_auth() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        res = await client.get("/api/domains")
    assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# product assignment + transformation endpoints
# ---------------------------------------------------------------------------


async def test_assign_domain_via_api_and_surface_on_detail() -> None:
    domain = domains_service.create_domain(
        _factory(), workspace_id=1, slug="sales-api", name="Sales API", archetype="source-aligned"
    )
    _seed_dp("main", "assign_dp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        patch = await client.patch(
            "/api/data-products/main/assign_dp/domain",
            json={"domain_id": domain.id},
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["domain_id"] == domain.id

        detail = await client.get("/api/data-products/main/assign_dp")
        assert detail.json()["product"]["domain"]["slug"] == "sales-api"

        clear = await client.patch(
            "/api/data-products/main/assign_dp/domain",
            json={"domain_id": None},
        )
        assert clear.status_code == 200
        assert clear.json()["domain_id"] is None


async def test_transformation_bind_list_unbind_via_api() -> None:
    _seed_dp("main", "tx_dp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        bind = await client.post(
            "/api/data-products/main/tx_dp/transformations",
            json={"kind": "dbt_model", "dbt_model_name": "stg_tx"},
        )
        assert bind.status_code == 200, bind.text
        tx_id = bind.json()["id"]

        listing = await client.get("/api/data-products/main/tx_dp/transformations")
        assert listing.json()["transformations"][0]["dbt_model_name"] == "stg_tx"

        delete = await client.delete(f"/api/data-products/main/tx_dp/transformations/{tx_id}")
        assert delete.status_code == 200
        assert delete.json()["deleted"] is True


async def test_assign_domain_blocks_non_steward_non_admin() -> None:
    """A non-steward, non-admin user is rejected by the assignment gate."""
    domain = domains_service.create_domain(
        _factory(), workspace_id=1, slug="gated", name="Gated", archetype="aggregate"
    )
    # Steward is the admin user, so the non-admin client is neither.
    _seed_dp("main", "gated_dp", steward_user_id=_admin_user_id())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.patch(
            "/api/data-products/main/gated_dp/domain",
            json={"domain_id": domain.id},
        )
    assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# page renders (Jinja templates don't 500)
# ---------------------------------------------------------------------------


async def test_browse_page_renders() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/domains")
    assert res.status_code == 200
    assert "Domains" in res.text


async def test_admin_page_renders() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/admin/domains")
    assert res.status_code == 200
    assert "New domain" in res.text


async def test_detail_page_renders() -> None:
    domains_service.create_domain(
        _factory(), workspace_id=1, slug="render-d", name="Render D", archetype="aggregate"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/domains/render-d")
    assert res.status_code == 200


async def test_data_product_detail_page_renders_with_domain_panel() -> None:
    """The product detail page still renders after the domain-panel edit."""
    _seed_dp("main", "render_dp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/data-products/main/render_dp")
    assert res.status_code == 200
    assert "dataProductDomainPanel" in res.text
