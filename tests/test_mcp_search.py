"""Tests for the catalog keyword-search ranking used by the MCP search tool."""

from __future__ import annotations

from pointlessql.services.mcp_server import rank_catalog

# A tree built so that, at every level (catalog / schema / table), one node is
# reachable ONLY by its name and another ONLY by its comment. That separation
# is what kills the comment-scoring mutants: if the comment text is dropped
# from a level's score, its comment-only node disappears from the results.
_TREE = [
    {
        "name": "retail",  # catalog reachable by comment only ("ecommerce")
        "comment": "ecommerce storefront",
        "schemas": [
            {
                "name": "sales",  # schema reachable by comment only ("revenue")
                "comment": "revenue figures",
                "tables": [
                    # table reachable by comment only ("purchase")
                    {"name": "orders", "comment": "customer purchase records"},
                    {"name": "regions", "comment": ""},  # matches nothing below
                ],
            },
            {
                "name": "inventory",  # schema reachable by name only
                "comment": "",
                "tables": [
                    {"name": "stock", "comment": ""},  # table reachable by name only
                ],
            },
        ],
    },
    {
        "name": "analytics",  # catalog reachable by name only
        "comment": "",
        "schemas": [],
    },
]


def test_catalog_matched_by_name() -> None:
    """A catalog whose name (not comment) matches is returned, typed ``catalog``."""
    hits = rank_catalog(_TREE, "analytics", limit=10)
    assert {"name": "analytics", "type": "catalog"} == {k: hits[0][k] for k in ("name", "type")}
    assert hits[0]["score"] > 0


def test_catalog_matched_by_comment_only() -> None:
    """A catalog match driven solely by its comment text still surfaces.

    ``retail``'s name does not contain ``ecommerce`` — only its comment does —
    so dropping the comment from the catalog score would lose this hit.
    """
    hits = rank_catalog(_TREE, "ecommerce", limit=10)
    assert [h["name"] for h in hits] == ["retail"]
    assert hits[0]["type"] == "catalog"


def test_schema_matched_by_name() -> None:
    """A schema matched by name is returned as ``catalog.schema``, typed schema."""
    hits = rank_catalog(_TREE, "inventory", limit=10)
    assert {"name": "retail.inventory", "type": "schema"} == {
        k: hits[0][k] for k in ("name", "type")
    }


def test_schema_matched_by_comment_only() -> None:
    """A schema match driven solely by its comment ("revenue") still surfaces."""
    hits = rank_catalog(_TREE, "revenue", limit=10)
    assert [h["name"] for h in hits] == ["retail.sales"]
    assert hits[0]["type"] == "schema"


def test_table_matched_by_name() -> None:
    """A table matched by name is returned as ``catalog.schema.table``."""
    hits = rank_catalog(_TREE, "stock", limit=10)
    assert {"name": "retail.inventory.stock", "type": "table"} == {
        k: hits[0][k] for k in ("name", "type")
    }


def test_table_matched_by_comment_only() -> None:
    """A table match driven solely by its comment ("purchase") still surfaces.

    ``orders``'s name does not contain ``purchase`` — only its comment does —
    so dropping the comment from the table score would lose this hit.
    """
    hits = rank_catalog(_TREE, "purchase", limit=10)
    assert [h["name"] for h in hits] == ["retail.sales.orders"]
    assert hits[0]["type"] == "table"


def test_non_matching_securable_is_excluded() -> None:
    """A securable scoring zero (no name/comment overlap) is not returned."""
    hits = rank_catalog(_TREE, "orders", limit=10)
    names = [h["name"] for h in hits]
    assert "retail.sales.orders" in names  # name match
    assert "retail.sales.regions" not in names  # score 0 -> excluded


def test_results_are_ordered_best_first() -> None:
    """Results are sorted by descending score, the stronger match ranking first.

    ``retail.sales`` matches two query terms ("revenue", "figures") while
    ``retail.sales.orders`` matches only one ("purchase"), so their scores are
    distinct — making the descending sort order observable (an ascending or
    unsorted order would put the weaker match first).
    """
    hits = rank_catalog(_TREE, "revenue figures purchase", limit=10)
    names = [h["name"] for h in hits]
    scores = [h["score"] for h in hits]
    assert names == ["retail.sales", "retail.sales.orders"]
    assert scores[0] > scores[1]  # strictly descending, not merely tied
    assert scores == sorted(scores, reverse=True)


def test_limit_caps_the_number_of_results() -> None:
    """At most ``limit`` matches are returned even when more would qualify."""
    query = "retail ecommerce revenue purchase inventory stock analytics"
    assert len(rank_catalog(_TREE, query, limit=1)) == 1
    assert len(rank_catalog(_TREE, query, limit=3)) == 3


def test_empty_query_returns_nothing() -> None:
    """A query with no scorable terms yields no hits (every score is zero)."""
    assert rank_catalog(_TREE, "", limit=10) == []


def test_malformed_tree_is_tolerated() -> None:
    """A non-list / absent child collection is treated as empty, not an error."""
    # schemas=None must not raise; the catalog itself still scores by name.
    assert rank_catalog([{"name": "c", "schemas": None}], "c", limit=10)[0]["name"] == "c"
    # a schema with tables=None must not raise either.
    tree = [{"name": "c", "schemas": [{"name": "s", "tables": None}]}]
    assert rank_catalog(tree, "s", limit=10)[0]["name"] == "c.s"
    # a tree where nothing matches yields an empty list.
    assert rank_catalog([{"name": "x"}], "nomatch", limit=10) == []


def test_missing_name_and_comment_keys_default_to_empty() -> None:
    """Nodes lacking ``name``/``comment`` keys score as empty, never raise.

    A catalog with neither key contributes an empty FQN and no match; this
    pins the ``""`` defaults used when the keys are absent.
    """
    tree = [{"schemas": [{"tables": [{}]}]}]
    assert rank_catalog(tree, "anything", limit=10) == []
    # a comment-bearing but nameless catalog matches by comment with an empty FQN
    hits = rank_catalog([{"comment": "weatherdata"}], "weatherdata", limit=10)
    assert hits == [{"name": "", "type": "catalog", "score": hits[0]["score"]}]


def test_nameless_schema_and_table_resolve_with_empty_fqn_segments() -> None:
    """A nameless schema/table matched by comment yields an empty FQN segment.

    With the missing ``name`` defaulting to ``""`` the fully-qualified name has
    an empty segment (``cat.`` / ``cat.sch.``) rather than a stringified
    ``None`` or any other placeholder — pinning the segment-join behaviour.
    """
    schema_tree = [{"name": "cat", "schemas": [{"comment": "uniqueschematoken"}]}]
    schema_hits = rank_catalog(schema_tree, "uniqueschematoken", limit=10)
    assert schema_hits[0]["name"] == "cat."
    assert schema_hits[0]["type"] == "schema"

    table_tree = [
        {"name": "cat", "schemas": [{"name": "sch", "tables": [{"comment": "uniquetabletoken"}]}]}
    ]
    table_hits = rank_catalog(table_tree, "uniquetabletoken", limit=10)
    assert table_hits[0]["name"] == "cat.sch."
    assert table_hits[0]["type"] == "table"


def test_absent_comment_contributes_no_tokens() -> None:
    """A node lacking a ``comment`` key adds no comment tokens to its score.

    The ``""`` default for an absent comment must inject nothing into the
    scored text. A query for the tokens a non-empty default would otherwise
    render therefore matches no node — at catalog, schema, and table level.
    """
    tree = [{"name": "alpha", "schemas": [{"name": "beta", "tables": [{"name": "gamma"}]}]}]
    assert rank_catalog(tree, "none", limit=10) == []
    assert rank_catalog(tree, "xxxx", limit=10) == []
