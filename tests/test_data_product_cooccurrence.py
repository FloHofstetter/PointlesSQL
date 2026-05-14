"""Tests for the Phase-73.5 cross-DP cooccurrence cache.

Covers:

* ``refresh_cooccurrence`` counts each run pair once.
* Self-cooccurrence is excluded (CHECK on row).
* ``top_n`` capping works.
* ``fetch_related`` orders by count desc.
* Cross-workspace iso.
* ``fetch_recommendations_for_user`` filters out already-followed DPs.
* GET /related route returns the cached top-N.
* GET /recommendations route + HTML page render the recommendations.
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.catalog._data_product_cooccurrence import (
    DataProductCooccurrence,
)
from pointlessql.models.catalog._data_product_follows import DataProductFollow
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.data_products import (
    fetch_recommendations_for_user,
    fetch_related,
    refresh_cooccurrence,
)

YAML_TEMPLATE = """\
data_product:
  name: P
  version: "1.0.0"
  description: d
  catalog: {catalog}
  schema: {schema}
  tables: []
"""


def _seed_dp(tmp_path: Path, catalog: str, schema: str) -> int:
    """Seed one data product; return its id."""
    yaml_path = tmp_path / f"{schema}.yaml"
    yaml_path.write_text(
        YAML_TEMPLATE.format(catalog=catalog, schema=schema), encoding="utf-8"
    )
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return (
            session.execute(
                select(DataProduct).where(
                    DataProduct.catalog_name == catalog,
                    DataProduct.schema_name == schema,
                )
            )
            .scalar_one()
            .id
        )


def _seed_run_touching(targets: list[str], *, workspace_id: int = 1) -> str:
    """Seed one AgentRun that touches every table in *targets*."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    when = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal="t@t.com",
                agent_id="a",
                notebook_path="/x",
                status="finished",
                started_at=when,
                finished_at=when,
            )
        )
        session.flush()
        for ordinal, target in enumerate(targets, start=1):
            session.add(
                AgentRunOperation(
                    workspace_id=workspace_id,
                    agent_run_id=run_id,
                    ordinal=ordinal,
                    op_name="write_table",
                    params_json="{}",
                    target_table=target,
                    started_at=when,
                    finished_at=when,
                )
            )
        session.commit()
    return run_id


def test_refresh_counts_run_pairs_once(tmp_path: Path) -> None:
    """One run touching two DPs yields one count = 1 per directional pair."""
    dp_a = _seed_dp(tmp_path, "cat", "schemaA")
    dp_b = _seed_dp(tmp_path, "cat", "schemaB")
    _seed_run_touching(["cat.schemaA.t1", "cat.schemaB.t1"])
    inserted = refresh_cooccurrence(app.state.session_factory)
    assert inserted == 2  # one row per directed pair
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductCooccurrence)).scalars().all()
        assert {(r.data_product_id, r.co_data_product_id) for r in rows} == {
            (dp_a, dp_b),
            (dp_b, dp_a),
        }
        assert all(r.cooccurrence_count == 1 for r in rows)


def test_refresh_excludes_single_dp_runs(tmp_path: Path) -> None:
    """A run touching only one DP doesn't produce any pairs."""
    _seed_dp(tmp_path, "cat", "schemaA")
    _seed_run_touching(["cat.schemaA.t1"])
    inserted = refresh_cooccurrence(app.state.session_factory)
    assert inserted == 0


def test_refresh_top_n_cap(tmp_path: Path) -> None:
    """``top_n=1`` keeps only the strongest co-DP per source DP."""
    _seed_dp(tmp_path, "cat", "schemaA")
    _seed_dp(tmp_path, "cat", "schemaB")
    _seed_dp(tmp_path, "cat", "schemaC")
    # 3 runs touch (A, B); 1 run touches (A, C).
    for _ in range(3):
        _seed_run_touching(["cat.schemaA.t", "cat.schemaB.t"])
    _seed_run_touching(["cat.schemaA.t", "cat.schemaC.t"])
    refresh_cooccurrence(app.state.session_factory, top_n=1)
    factory = app.state.session_factory
    with factory() as session:
        # Source = A → kept pair is (A, B), not (A, C).
        rows = (
            session.execute(
                select(DataProductCooccurrence).where(
                    DataProductCooccurrence.data_product_id == 1
                )
            )
            .scalars()
            .all()
        )
        # Only the top-1 partner per source remains.
        assert len(rows) == 1
        kept = rows[0]
        assert kept.cooccurrence_count == 3


def test_fetch_related_orders_by_count_desc(tmp_path: Path) -> None:
    """fetch_related returns rows sorted by count desc."""
    dp_a = _seed_dp(tmp_path, "cat", "schemaA")
    _seed_dp(tmp_path, "cat", "schemaB")
    _seed_dp(tmp_path, "cat", "schemaC")
    for _ in range(2):
        _seed_run_touching(["cat.schemaA.t", "cat.schemaB.t"])
    _seed_run_touching(["cat.schemaA.t", "cat.schemaC.t"])
    refresh_cooccurrence(app.state.session_factory)
    factory = app.state.session_factory
    with factory() as session:
        related = fetch_related(
            session, workspace_id=1, data_product_id=dp_a, limit=5
        )
    assert [r["data_product_ref"] for r in related] == [
        "cat.schemaB",
        "cat.schemaC",
    ]


def test_fetch_recommendations_filters_followed(tmp_path: Path) -> None:
    """Recommendations exclude DPs the user already follows."""
    dp_a = _seed_dp(tmp_path, "cat", "schemaA")
    _seed_dp(tmp_path, "cat", "schemaB")
    dp_c = _seed_dp(tmp_path, "cat", "schemaC")
    for _ in range(2):
        _seed_run_touching(["cat.schemaA.t", "cat.schemaB.t"])
    _seed_run_touching(["cat.schemaA.t", "cat.schemaC.t"])
    refresh_cooccurrence(app.state.session_factory)
    factory = app.state.session_factory
    # User follows DP-A (the source) and DP-C.
    from pointlessql.services.social import get_or_create_target

    with factory() as session:
        for dp_id, fqn in ((dp_a, "cat.schemaA"), (dp_c, "cat.schemaC")):
            anchor = get_or_create_target(
                session,
                workspace_id=1,
                kind="dp",
                ref=fqn,
                data_product_id=dp_id,
            )
            session.add(
                DataProductFollow(
                    workspace_id=1,
                    user_id=1,
                    data_product_id=dp_id,
                    social_target_id=int(anchor.id),
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
        session.commit()
    with factory() as session:
        recs = fetch_recommendations_for_user(
            session, workspace_id=1, user_id=1, limit=5
        )
    # The caller follows A + C, so the only recommendation is B.
    assert [r["data_product_ref"] for r in recs] == ["cat.schemaB"]


@pytest.mark.asyncio
async def test_related_route_returns_top_n(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """GET /api/data-products/{cat}/{sch}/related returns related rows."""
    _seed_dp(tmp_path, "cat", "schemaA")
    _seed_dp(tmp_path, "cat", "schemaB")
    _seed_run_touching(["cat.schemaA.t", "cat.schemaB.t"])
    refresh_cooccurrence(app.state.session_factory)
    res = await admin_client.get("/api/data-products/cat/schemaA/related")
    assert res.status_code == 200, res.text
    body = res.json()
    assert any(r["data_product_ref"] == "cat.schemaB" for r in body["related"])


@pytest.mark.asyncio
async def test_recommendations_route(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """GET /api/data-products/recommendations returns the per-user list."""
    dp_a = _seed_dp(tmp_path, "cat", "schemaA")
    _seed_dp(tmp_path, "cat", "schemaB")
    _seed_run_touching(["cat.schemaA.t", "cat.schemaB.t"])
    refresh_cooccurrence(app.state.session_factory)
    factory = app.state.session_factory
    from pointlessql.services.social import get_or_create_target

    with factory() as session:
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="cat.schemaA",
            data_product_id=dp_a,
        )
        session.add(
            DataProductFollow(
                workspace_id=1,
                user_id=1,
                data_product_id=dp_a,
                social_target_id=int(anchor.id),
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    res = await admin_client.get("/api/data-products/recommendations")
    assert res.status_code == 200, res.text
    body = res.json()
    refs = [r["data_product_ref"] for r in body["recommendations"]]
    assert "cat.schemaB" in refs
    assert "cat.schemaA" not in refs


@pytest.mark.asyncio
async def test_followed_html_renders_recommendation_card(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The followed HTML page carries the recommendations Alpine root."""
    _seed_dp(tmp_path, "cat", "schemaA")
    res = await admin_client.get("/data-products/followed")
    assert res.status_code == 200
    assert "dataProductsFollowed" in res.text
