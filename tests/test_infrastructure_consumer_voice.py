"""Phase 132 — infrastructure declarations + consumer-contributed metadata."""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct, User
from pointlessql.services import consumer_voice as consumer_voice_service
from pointlessql.services import infrastructure as infrastructure_service


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "test@test.com"))


def _non_admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "nonadmin@test.com"))


def _seed_dp(catalog: str, schema: str) -> int:
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
# infrastructure
# ---------------------------------------------------------------------------


def test_infrastructure_default_is_blank() -> None:
    dp_id = _seed_dp("inf", "blank")
    view = infrastructure_service.get_infrastructure(_factory(), data_product_id=dp_id)
    assert view["storage_class"] is None
    assert view["access_methods"] == []


def test_infrastructure_upsert_persists() -> None:
    dp_id = _seed_dp("inf", "set")
    infrastructure_service.set_infrastructure(
        _factory(),
        data_product_id=dp_id,
        fields={
            "storage_class": "delta",
            "compute_runtime": "pql",
            "access_methods": ["sql", "file"],
            "region": "eu-central",
            "notes": "  primary  ",
        },
    )
    view = infrastructure_service.get_infrastructure(_factory(), data_product_id=dp_id)
    assert view["storage_class"] == "delta"
    assert view["compute_runtime"] == "pql"
    assert view["access_methods"] == ["sql", "file"]
    assert view["region"] == "eu-central"
    assert "primary" in (view["notes"] or "")


def test_infrastructure_invalid_storage_class_rejected() -> None:
    dp_id = _seed_dp("inf", "bad")
    with pytest.raises(ValueError):
        infrastructure_service.set_infrastructure(
            _factory(),
            data_product_id=dp_id,
            fields={"storage_class": "lake"},
        )


def test_infrastructure_access_methods_must_be_list() -> None:
    dp_id = _seed_dp("inf", "list")
    with pytest.raises(ValueError):
        infrastructure_service.set_infrastructure(
            _factory(),
            data_product_id=dp_id,
            fields={"access_methods": "sql"},
        )


# ---------------------------------------------------------------------------
# use cases + votes
# ---------------------------------------------------------------------------


def test_add_use_case_returns_serialised_row() -> None:
    dp_id = _seed_dp("uc", "add")
    uc = consumer_voice_service.add_use_case(
        _factory(),
        data_product_id=dp_id,
        title="ML feature input",
        body="Used as the customer-features table.",
        author_user_id=_admin_user_id(),
    )
    assert uc["title"] == "ML feature input"
    assert uc["votes"] == 0


def test_add_use_case_rejects_empty_title() -> None:
    dp_id = _seed_dp("uc", "empty")
    with pytest.raises(ValueError):
        consumer_voice_service.add_use_case(
            _factory(),
            data_product_id=dp_id,
            title="",
            body="",
            author_user_id=None,
        )


def test_list_use_cases_orders_by_votes_desc() -> None:
    dp_id = _seed_dp("uc", "list")
    a = consumer_voice_service.add_use_case(
        _factory(), data_product_id=dp_id, title="A", body="", author_user_id=None
    )
    b = consumer_voice_service.add_use_case(
        _factory(), data_product_id=dp_id, title="B", body="", author_user_id=None
    )
    consumer_voice_service.vote_use_case(_factory(), use_case_id=b["id"], user_id=_admin_user_id())
    rows = consumer_voice_service.list_use_cases(_factory(), data_product_id=dp_id)
    assert rows[0]["id"] == b["id"]
    assert rows[1]["id"] == a["id"]


def test_vote_idempotent_and_unvote() -> None:
    dp_id = _seed_dp("uc", "vote")
    uc = consumer_voice_service.add_use_case(
        _factory(), data_product_id=dp_id, title="C", body="", author_user_id=None
    )
    uid = _admin_user_id()
    r1 = consumer_voice_service.vote_use_case(_factory(), use_case_id=uc["id"], user_id=uid)
    r2 = consumer_voice_service.vote_use_case(_factory(), use_case_id=uc["id"], user_id=uid)
    assert r1["votes"] == 1
    assert r2["votes"] == 1
    r3 = consumer_voice_service.vote_use_case(
        _factory(), use_case_id=uc["id"], user_id=uid, upvote=False
    )
    assert r3["votes"] == 0
    assert r3["voted"] is False


def test_delete_use_case_returns_bool() -> None:
    dp_id = _seed_dp("uc", "del")
    uc = consumer_voice_service.add_use_case(
        _factory(), data_product_id=dp_id, title="D", body="", author_user_id=None
    )
    assert (
        consumer_voice_service.delete_use_case(
            _factory(), data_product_id=dp_id, use_case_id=uc["id"]
        )
        is True
    )
    assert (
        consumer_voice_service.delete_use_case(
            _factory(), data_product_id=dp_id, use_case_id=uc["id"]
        )
        is False
    )


# ---------------------------------------------------------------------------
# ratings
# ---------------------------------------------------------------------------


def test_rating_upsert_replaces_existing_score() -> None:
    dp_id = _seed_dp("rt", "up")
    uid = _admin_user_id()
    consumer_voice_service.upsert_rating(
        _factory(), data_product_id=dp_id, user_id=uid, score=3, comment="OK"
    )
    consumer_voice_service.upsert_rating(
        _factory(), data_product_id=dp_id, user_id=uid, score=5, comment="great"
    )
    summary = consumer_voice_service.list_rating_summary(_factory(), data_product_id=dp_id)
    assert summary["count"] == 1
    assert summary["avg"] == 5.0


def test_rating_score_range_enforced() -> None:
    dp_id = _seed_dp("rt", "range")
    with pytest.raises(ValueError):
        consumer_voice_service.upsert_rating(
            _factory(), data_product_id=dp_id, user_id=_admin_user_id(), score=0
        )
    with pytest.raises(ValueError):
        consumer_voice_service.upsert_rating(
            _factory(), data_product_id=dp_id, user_id=_admin_user_id(), score=6
        )


def test_rating_summary_two_users_averaged() -> None:
    dp_id = _seed_dp("rt", "avg")
    consumer_voice_service.upsert_rating(
        _factory(),
        data_product_id=dp_id,
        user_id=_admin_user_id(),
        score=5,
    )
    consumer_voice_service.upsert_rating(
        _factory(),
        data_product_id=dp_id,
        user_id=_non_admin_user_id(),
        score=3,
    )
    summary = consumer_voice_service.list_rating_summary(_factory(), data_product_id=dp_id)
    assert summary["count"] == 2
    assert summary["avg"] == 4.0


def test_rating_summary_no_ratings_returns_none_avg() -> None:
    dp_id = _seed_dp("rt", "none")
    summary = consumer_voice_service.list_rating_summary(_factory(), data_product_id=dp_id)
    assert summary["count"] == 0
    assert summary["avg"] is None
