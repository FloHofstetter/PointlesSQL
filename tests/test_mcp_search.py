"""Tests for the catalog keyword-search ranking used by the MCP search tool."""

from __future__ import annotations

from pointlessql.services.mcp_server import rank_catalog

_TREE = [
    {
        "name": "main",
        "comment": "",
        "schemas": [
            {
                "name": "sales",
                "comment": "",
                "tables": [
                    {"name": "orders", "comment": "customer orders fact"},
                    {"name": "regions", "comment": ""},
                ],
            },
            {
                "name": "ops",
                "comment": "operations data",
                "tables": [{"name": "logs", "comment": ""}],
            },
        ],
    }
]


def test_rank_catalog_returns_matches_and_excludes_non_matches() -> None:
    """A matching table is returned; a non-matching one (score 0) is excluded."""
    hits = rank_catalog(_TREE, "orders", limit=10)
    names = [h["name"] for h in hits]
    assert "main.sales.orders" in names
    assert "main.sales.regions" not in names
    top = hits[0]
    assert top["name"] == "main.sales.orders"
    assert top["type"] == "table"
    assert top["score"] > 0


def test_rank_catalog_matches_comment_text() -> None:
    """Relevance considers the comment, not just the name."""
    hits = rank_catalog(_TREE, "operations", limit=10)
    assert any(h["name"] == "main.ops" and h["type"] == "schema" for h in hits)


def test_rank_catalog_respects_the_limit() -> None:
    """At most ``limit`` matches are returned."""
    hits = rank_catalog(_TREE, "data orders operations customer", limit=1)
    assert len(hits) == 1


def test_rank_catalog_orders_by_descending_score() -> None:
    """Results are sorted best-first."""
    hits = rank_catalog(_TREE, "data orders operations customer", limit=10)
    scores = [h["score"] for h in hits]
    assert len(scores) >= 2
    assert scores == sorted(scores, reverse=True)


def test_rank_catalog_tolerates_a_malformed_tree() -> None:
    """A non-list / absent child collection is treated as empty, not an error."""
    assert rank_catalog([{"name": "c", "schemas": None}], "c", limit=10)[0]["name"] == "c"
    assert rank_catalog([{"name": "x"}], "nomatch", limit=10) == []
