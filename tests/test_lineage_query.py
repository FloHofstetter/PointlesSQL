"""Graph-shaped lineage queries (D5)."""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductInputPort
from pointlessql.services.lineage import _graph_query as graph_query


def _factory():
    return app.state.session_factory


def _seed_chain(refs: list[tuple[str, str]]) -> list[int]:
    """Seed a producer→consumer chain. refs = [(catalog, schema), ...]."""
    now = datetime.datetime.now(datetime.UTC)
    ids: list[int] = []
    with _factory()() as session:
        for catalog, schema in refs:
            contract = {
                "name": f"{catalog}.{schema}",
                "version": "1.0.0",
                "description": "",
                "catalog": catalog,
                "schema_name": schema,
                "tables": [],
            }
            row = DataProduct(
                workspace_id=1,
                catalog_name=catalog,
                schema_name=schema,
                version="1.0.0",
                description="",
                sla_minutes=None,
                contract_yaml_hash=f"{catalog}_{schema}".ljust(64, "0"),
                contract_json=json.dumps(contract),
                last_loaded_at=now,
                created_at=now,
            )
            session.add(row)
            session.flush()
            ids.append(row.id)
        for i in range(1, len(refs)):
            producer = f"{refs[i-1][0]}.{refs[i-1][1]}"
            consumer_id = ids[i]
            session.add(
                DataProductInputPort(
                    data_product_id=consumer_id,
                    name=f"in_{i}",
                    kind="upstream_product",
                    source_ref=producer,
                    description="",
                    created_at=now,
                )
            )
        session.commit()
    return ids


def test_upstream_returns_direct_producer() -> None:
    _seed_chain([("lq1", "raw"), ("lq1", "silver")])
    upstream = graph_query.find_upstream(
        _factory(), workspace_id=1, product_ref="lq1.silver", depth=1
    )
    refs = [n["ref"] for n in upstream]
    assert refs == ["lq1.raw"]


def test_upstream_respects_depth() -> None:
    _seed_chain([("lq2", "a"), ("lq2", "b"), ("lq2", "c")])
    one = graph_query.find_upstream(
        _factory(), workspace_id=1, product_ref="lq2.c", depth=1
    )
    two = graph_query.find_upstream(
        _factory(), workspace_id=1, product_ref="lq2.c", depth=2
    )
    assert {n["ref"] for n in one} == {"lq2.b"}
    assert {n["ref"] for n in two} == {"lq2.a", "lq2.b"}


def test_downstream_walks_consumers() -> None:
    _seed_chain([("lq3", "src"), ("lq3", "mid"), ("lq3", "snk")])
    down = graph_query.find_downstream(
        _factory(), workspace_id=1, product_ref="lq3.src", depth=2
    )
    assert {n["ref"] for n in down} == {"lq3.mid", "lq3.snk"}


def test_shortest_path_returns_chain() -> None:
    _seed_chain([("lq4", "a"), ("lq4", "b"), ("lq4", "c")])
    path = graph_query.find_shortest_path(
        _factory(), workspace_id=1, source_ref="lq4.a", target_ref="lq4.c"
    )
    assert path == ["lq4.a", "lq4.b", "lq4.c"]


def test_shortest_path_self_returns_singleton() -> None:
    _seed_chain([("lq5", "a")])
    path = graph_query.find_shortest_path(
        _factory(), workspace_id=1, source_ref="lq5.a", target_ref="lq5.a"
    )
    assert path == ["lq5.a"]


def test_shortest_path_none_when_disconnected() -> None:
    _seed_chain([("lq6", "a")])
    _seed_chain([("lq6", "b")])
    path = graph_query.find_shortest_path(
        _factory(), workspace_id=1, source_ref="lq6.a", target_ref="lq6.b"
    )
    assert path is None


def test_unknown_product_raises_lookup() -> None:
    with pytest.raises(LookupError):
        graph_query.find_upstream(
            _factory(), workspace_id=1, product_ref="does.not.exist", depth=1
        )


def test_zero_depth_raises_value() -> None:
    _seed_chain([("lq7", "a")])
    with pytest.raises(ValueError):
        graph_query.find_upstream(
            _factory(), workspace_id=1, product_ref="lq7.a", depth=0
        )


def test_cluster_by_domain_buckets_no_domain() -> None:
    _seed_chain([("lq8", "x"), ("lq8", "y")])
    clusters = graph_query.cluster_by_domain(_factory(), workspace_id=1)
    assert "(no domain)" in clusters
    refs = {n["ref"] for n in clusters["(no domain)"]}
    assert {"lq8.x", "lq8.y"} <= refs
