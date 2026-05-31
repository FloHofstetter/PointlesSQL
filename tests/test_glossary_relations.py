"""Glossary term-relation CRUD + bounded knowledge-graph BFS (F4)."""

from __future__ import annotations

import pytest

from pointlessql.api.main import app
from pointlessql.services import glossary as glossary_service


def _factory():
    return app.state.session_factory


def _seed_term(slug: str, term: str | None = None) -> int:
    row = glossary_service.create_term(
        _factory(),
        workspace_id=1,
        slug=slug,
        term=term or slug.replace("-", " ").title(),
        definition=None,
        creator_user_id=None,
    )
    return int(row.id)


def test_add_relation_persists() -> None:
    a = _seed_term("net-revenue")
    b = _seed_term("revenue")
    result = glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="parent"
    )
    assert result["kind"] == "parent"


def test_add_relation_rejects_unknown_kind() -> None:
    a = _seed_term("x1")
    b = _seed_term("x2")
    with pytest.raises(ValueError):
        glossary_service.add_relation(
            _factory(), source_term_id=a, target_term_id=b, kind="bogus"
        )


def test_add_relation_rejects_self_link() -> None:
    a = _seed_term("self-link-test")
    with pytest.raises(ValueError):
        glossary_service.add_relation(
            _factory(), source_term_id=a, target_term_id=a, kind="synonym"
        )


def test_add_relation_is_idempotent() -> None:
    a = _seed_term("idem-a")
    b = _seed_term("idem-b")
    first = glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="synonym"
    )
    second = glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="synonym"
    )
    assert first["id"] == second["id"]


def test_list_relations_direction_outgoing() -> None:
    a = _seed_term("dir-a")
    b = _seed_term("dir-b")
    glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="related"
    )
    outgoing = glossary_service.list_relations(_factory(), term_id=a, direction="outgoing")
    incoming = glossary_service.list_relations(_factory(), term_id=a, direction="incoming")
    assert len(outgoing) == 1
    assert len(incoming) == 0


def test_delete_relation_removes_row() -> None:
    a = _seed_term("del-a")
    b = _seed_term("del-b")
    rel = glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="related"
    )
    assert glossary_service.delete_relation(_factory(), relation_id=rel["id"]) is True
    assert glossary_service.delete_relation(_factory(), relation_id=rel["id"]) is False


def test_term_graph_returns_root_only_at_depth_one_when_isolated() -> None:
    a = _seed_term("graph-iso")
    graph = glossary_service.term_graph(_factory(), root_term_id=a, depth=1)
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["id"] == a
    assert graph["edges"] == []


def test_term_graph_walks_neighbours_at_depth_one() -> None:
    a = _seed_term("graph-a")
    b = _seed_term("graph-b")
    c = _seed_term("graph-c")
    glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="parent"
    )
    glossary_service.add_relation(
        _factory(), source_term_id=b, target_term_id=c, kind="parent"
    )
    graph = glossary_service.term_graph(_factory(), root_term_id=a, depth=1)
    node_ids = {n["id"] for n in graph["nodes"]}
    assert a in node_ids
    assert b in node_ids
    assert c not in node_ids


def test_term_graph_walks_to_depth_two() -> None:
    a = _seed_term("graph2-a")
    b = _seed_term("graph2-b")
    c = _seed_term("graph2-c")
    glossary_service.add_relation(
        _factory(), source_term_id=a, target_term_id=b, kind="parent"
    )
    glossary_service.add_relation(
        _factory(), source_term_id=b, target_term_id=c, kind="parent"
    )
    graph = glossary_service.term_graph(_factory(), root_term_id=a, depth=2)
    node_ids = {n["id"] for n in graph["nodes"]}
    assert {a, b, c} <= node_ids


def test_term_graph_rejects_zero_depth() -> None:
    a = _seed_term("graph-zero")
    with pytest.raises(ValueError):
        glossary_service.term_graph(_factory(), root_term_id=a, depth=0)


def test_term_graph_raises_for_unknown_root() -> None:
    with pytest.raises(LookupError):
        glossary_service.term_graph(_factory(), root_term_id=999_999, depth=1)
