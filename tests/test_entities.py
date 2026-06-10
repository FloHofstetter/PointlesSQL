"""Entity-CRUD + polysemic-identity resolution (F3)."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct
from pointlessql.services import entities as entities_service


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract: dict[str, Any] = {
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


def test_declare_entity_persists_and_decodes_pk() -> None:
    dp = _seed_dp("e3", "customers")
    result = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="Customer",
        source_table="customer_master",
        primary_key_columns=["id", "tenant_id"],
        description="Master customer record.",
    )
    assert result["entity_name"] == "Customer"
    assert result["primary_key_columns"] == ["id", "tenant_id"]
    assert result["data_product_id"] == dp


def test_declare_entity_is_idempotent_on_name() -> None:
    dp = _seed_dp("e3b", "customers")
    a = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="Customer",
        source_table="cust",
        primary_key_columns=["id"],
    )
    b = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="Customer",
        source_table="cust_v2",
        primary_key_columns=["id"],
    )
    assert a["id"] == b["id"]
    assert b["source_table"] == "cust_v2"


def test_declare_entity_rejects_empty_pk() -> None:
    dp = _seed_dp("e3c", "x")
    with pytest.raises(ValueError):
        entities_service.declare_entity(
            _factory(),
            data_product_id=dp,
            entity_name="X",
            source_table="t",
            primary_key_columns=[],
        )


def test_list_entities_orders_by_name() -> None:
    dp = _seed_dp("e3d", "orders")
    for name in ("Order", "Customer", "Product"):
        entities_service.declare_entity(
            _factory(),
            data_product_id=dp,
            entity_name=name,
            source_table=name.lower(),
            primary_key_columns=["id"],
        )
    names = [
        e["entity_name"] for e in entities_service.list_entities(_factory(), data_product_id=dp)
    ]
    assert names == sorted(names)


def test_link_entities_same_as_creates_bidirectional_cluster() -> None:
    dp_a = _seed_dp("e3e", "src")
    dp_b = _seed_dp("e3f", "tgt")
    ent_a = entities_service.declare_entity(
        _factory(),
        data_product_id=dp_a,
        entity_name="Customer",
        source_table="t",
        primary_key_columns=["id"],
    )
    ent_b = entities_service.declare_entity(
        _factory(),
        data_product_id=dp_b,
        entity_name="Customer",
        source_table="t",
        primary_key_columns=["id"],
    )
    link = entities_service.link_entities(
        _factory(),
        source_entity_id=ent_a["id"],
        target_entity_id=ent_b["id"],
        kind="same_as",
    )
    assert link["kind"] == "same_as"
    identity = entities_service.resolve_same_as_graph(_factory(), entity_id=ent_a["id"])
    member_ids = {m["id"] for m in identity.members}
    assert member_ids == {ent_a["id"], ent_b["id"]}
    assert identity.canonical_entity_id == min(ent_a["id"], ent_b["id"])


def test_link_entities_rejects_unknown_kind() -> None:
    dp = _seed_dp("e3g", "x")
    a = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="A",
        source_table="t",
        primary_key_columns=["id"],
    )
    b = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="B",
        source_table="t",
        primary_key_columns=["id"],
    )
    with pytest.raises(ValueError):
        entities_service.link_entities(
            _factory(),
            source_entity_id=a["id"],
            target_entity_id=b["id"],
            kind="bogus",
        )


def test_link_entities_rejects_self_link() -> None:
    dp = _seed_dp("e3h", "x")
    ent = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="X",
        source_table="t",
        primary_key_columns=["id"],
    )
    with pytest.raises(ValueError):
        entities_service.link_entities(
            _factory(),
            source_entity_id=ent["id"],
            target_entity_id=ent["id"],
            kind="same_as",
        )


def test_link_is_idempotent_on_identity() -> None:
    dp = _seed_dp("e3i", "x")
    a = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="A",
        source_table="t",
        primary_key_columns=["id"],
    )
    b = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="B",
        source_table="t",
        primary_key_columns=["id"],
    )
    first = entities_service.link_entities(
        _factory(),
        source_entity_id=a["id"],
        target_entity_id=b["id"],
        kind="related_to",
    )
    second = entities_service.link_entities(
        _factory(),
        source_entity_id=a["id"],
        target_entity_id=b["id"],
        kind="related_to",
    )
    assert first["id"] == second["id"]


def test_resolve_same_as_walks_transitive() -> None:
    dps = [_seed_dp(f"e3j{i}", f"s{i}") for i in range(3)]
    ents = [
        entities_service.declare_entity(
            _factory(),
            data_product_id=dp,
            entity_name="Customer",
            source_table="t",
            primary_key_columns=["id"],
        )
        for dp in dps
    ]
    entities_service.link_entities(
        _factory(),
        source_entity_id=ents[0]["id"],
        target_entity_id=ents[1]["id"],
        kind="same_as",
    )
    entities_service.link_entities(
        _factory(),
        source_entity_id=ents[1]["id"],
        target_entity_id=ents[2]["id"],
        kind="same_as",
    )
    identity = entities_service.resolve_same_as_graph(_factory(), entity_id=ents[2]["id"])
    member_ids = {m["id"] for m in identity.members}
    assert member_ids == {e["id"] for e in ents}


def test_resolve_does_not_cross_non_same_as_links() -> None:
    dp = _seed_dp("e3k", "x")
    a = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="A",
        source_table="t",
        primary_key_columns=["id"],
    )
    b = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="B",
        source_table="t",
        primary_key_columns=["id"],
    )
    entities_service.link_entities(
        _factory(),
        source_entity_id=a["id"],
        target_entity_id=b["id"],
        kind="related_to",
    )
    identity = entities_service.resolve_same_as_graph(_factory(), entity_id=a["id"])
    assert {m["id"] for m in identity.members} == {a["id"]}


def test_resolve_by_pk_returns_cluster_for_known_product() -> None:
    dp = _seed_dp("e3l", "customers")
    ent = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="Customer",
        source_table="t",
        primary_key_columns=["id"],
    )
    identity = entities_service.resolve_entity_by_pk(
        _factory(), catalog="e3l", schema="customers", entity_name="Customer"
    )
    assert identity is not None
    assert identity.canonical_entity_id == ent["id"]


def test_resolve_by_pk_returns_none_for_unknown_entity() -> None:
    _seed_dp("e3m", "customers")
    identity = entities_service.resolve_entity_by_pk(
        _factory(), catalog="e3m", schema="customers", entity_name="DoesNotExist"
    )
    assert identity is None


def test_unlink_removes_link() -> None:
    dp = _seed_dp("e3n", "x")
    a = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="A",
        source_table="t",
        primary_key_columns=["id"],
    )
    b = entities_service.declare_entity(
        _factory(),
        data_product_id=dp,
        entity_name="B",
        source_table="t",
        primary_key_columns=["id"],
    )
    link = entities_service.link_entities(
        _factory(),
        source_entity_id=a["id"],
        target_entity_id=b["id"],
        kind="related_to",
    )
    assert entities_service.unlink_entities(_factory(), link_id=link["id"]) is True
    assert entities_service.unlink_entities(_factory(), link_id=link["id"]) is False
