"""Tests for the hybrid (vector + keyword RRF) retrieval primitive."""

from __future__ import annotations

from pointlessql.services import hybrid_search


def test_keyword_relevance_scores_matches() -> None:
    assert hybrid_search.keyword_relevance("the quick brown fox", "quick fox") > 0
    # More occurrences of a query term score higher.
    one = hybrid_search.keyword_relevance("alpha beta", "alpha")
    many = hybrid_search.keyword_relevance("alpha alpha alpha", "alpha")
    assert many > one
    # Case-insensitive.
    assert hybrid_search.keyword_relevance("ALPHA", "alpha") > 0


def test_keyword_relevance_zero_when_absent() -> None:
    assert hybrid_search.keyword_relevance("nothing here", "missing") == 0.0
    assert hybrid_search.keyword_relevance("text", "") == 0.0
    assert hybrid_search.keyword_relevance("", "query") == 0.0


def test_reciprocal_rank_fusion_rewards_agreement() -> None:
    fused = hybrid_search.reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]], k=1)
    # 'a' is first in both lists → highest fused score.
    assert max(fused, key=lambda key: fused[key]) == "a"
    assert fused["a"] == 1.0


def test_fuse_vector_hits_lifts_keyword_match() -> None:
    # Vector order: h0 best, h1 mid, h2 worst — but only h2 mentions the query.
    hits = [
        {"score": 0.9, "pk": {"id": 0}, "snippet": "alpha"},
        {"score": 0.8, "pk": {"id": 1}, "snippet": "beta"},
        {"score": 0.1, "pk": {"id": 2}, "snippet": "query query"},
    ]
    fused = hybrid_search.fuse_vector_hits(hits, "query")
    snippets = [h["snippet"] for h in fused]
    # The keyword match (low on vectors) is fused above the keyword-less
    # mid-vector hit.
    assert snippets.index("query query") < snippets.index("beta")
    assert all("keyword_score" in h and "fused_score" in h for h in fused)
    by_id = {h["pk"]["id"]: h for h in fused}
    assert by_id[2]["keyword_score"] > 0
    assert by_id[0]["keyword_score"] == 0.0


def test_fuse_vector_hits_empty() -> None:
    assert hybrid_search.fuse_vector_hits([], "q") == []
