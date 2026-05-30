"""Auto-discovery candidate scoring (Phase 145)."""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductEntity,
    EntityLink,
    EntityLinkCandidate,
)
from pointlessql.services.entities import (
    discover_candidates,
    score_column_similarity,
    score_combined,
    score_pk_overlap,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_entity(catalog: str, schema: str, name: str, pk: list[str]) -> int:
    contract = {"name": f"{catalog}.{schema}", "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(dp)
        session.commit()
        entity = DataProductEntity(
            data_product_id=dp.id,
            entity_name=name,
            source_table="src",
            primary_key_columns=json.dumps(pk),
            description=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(entity)
        session.commit()
        return int(entity.id)


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(EntityLinkCandidate).delete()
        session.query(EntityLink).delete()
        session.query(DataProductEntity).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_pk_overlap_full_match() -> None:
    assert score_pk_overlap(["id"], ["id"]) == pytest.approx(1.0)


def test_pk_overlap_disjoint() -> None:
    assert score_pk_overlap(["id"], ["tenant_id"]) == pytest.approx(0.0)


def test_pk_overlap_partial() -> None:
    score = score_pk_overlap(["id", "tenant_id"], ["id", "external_id"])
    assert score == pytest.approx(1 / 3)


def test_pk_overlap_empty_inputs_zero() -> None:
    assert score_pk_overlap([], []) == 0.0


def test_column_similarity_for_identical_names() -> None:
    e1 = _make_entity(name="customer_master")
    e2 = _make_entity(name="customer_master")
    assert score_column_similarity(e1, e2) == pytest.approx(1.0)


def test_column_similarity_for_disjoint_names() -> None:
    e1 = _make_entity(name="alpha")
    e2 = _make_entity(name="beta")
    assert score_column_similarity(e1, e2) == 0.0


def test_score_combined_uses_weighted_sum() -> None:
    e1 = _make_entity(name="customer_master", pk=["id"])
    e2 = _make_entity(name="customer_master", pk=["id"])
    score = score_combined(e1, e2)
    assert score.pk_overlap == pytest.approx(1.0)
    assert score.column_similarity == pytest.approx(1.0)
    assert score.combined == pytest.approx(1.0)


def test_discovery_persists_candidates_above_threshold() -> None:
    a = _seed_entity("dc", "alpha", "Customer", ["id"])
    b = _seed_entity("dc", "beta", "Customer", ["id"])
    inserted = discover_candidates(_factory(), threshold=0.5)
    assert inserted == 1
    with _factory()() as session:
        rows = session.query(EntityLinkCandidate).all()
        assert len(rows) == 1
        assert {int(rows[0].source_entity_id), int(rows[0].target_entity_id)} == {a, b}


def test_discovery_skips_pairs_below_threshold() -> None:
    _seed_entity("dc", "alpha", "Order", ["order_id"])
    _seed_entity("dc", "beta", "Customer", ["customer_id"])
    inserted = discover_candidates(_factory(), threshold=0.7)
    assert inserted == 0


def test_discovery_dedups_against_existing_entity_links() -> None:
    a = _seed_entity("dc", "alpha", "Customer", ["id"])
    b = _seed_entity("dc", "beta", "Customer", ["id"])
    with _factory()() as session:
        session.add(
            EntityLink(
                source_entity_id=a,
                target_entity_id=b,
                kind="same_as",
                confidence=None,
                declared_by_user_id=None,
                created_at=_now(),
            )
        )
        session.commit()
    inserted = discover_candidates(_factory(), threshold=0.1)
    assert inserted == 0


def test_discovery_dedups_against_existing_candidates() -> None:
    _seed_entity("dc", "alpha", "Customer", ["id"])
    _seed_entity("dc", "beta", "Customer", ["id"])
    first = discover_candidates(_factory(), threshold=0.5)
    second = discover_candidates(_factory(), threshold=0.5)
    assert first == 1
    assert second == 0


def _make_entity(*, name: str, pk: list[str] | None = None) -> DataProductEntity:
    """In-memory entity stub for scorer unit tests."""
    return DataProductEntity(
        id=None,
        data_product_id=1,
        entity_name=name,
        source_table="src",
        primary_key_columns=json.dumps(pk or ["id"]),
        description=None,
        created_at=_now(),
        updated_at=_now(),
    )
