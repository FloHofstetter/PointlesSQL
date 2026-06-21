"""Hybrid retrieval — fuse vector + keyword ranks with RRF.

Lakebase Search combines vector similarity and keyword (BM25) relevance
in one query via Reciprocal Rank Fusion.  PointlesSQL already has the
vector half (``pql.vector_search``); this module adds the fusion half as
a pure, reusable primitive: a lightweight keyword-relevance score over a
hit's text plus the RRF combiner that merges the two rankings into one
agent-native result list.

The RaBitQ quantisation and the Postgres ``lakebase_vector`` /
``lakebase_text`` extensions are engine/storage internals and stay out
of scope; the UI-relevant hybrid *ranking* sits cleanly on top of the
existing vector hits, re-scored by keyword relevance over the same
returned snippets and fused by rank.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_WORD_RE = re.compile(r"\w+")

#: RRF rank-bias constant; larger values flatten the rank weighting.
_DEFAULT_RRF_K = 60


def keyword_relevance(text: str | None, query: str | None) -> float:
    """Score a snippet's keyword relevance to *query* (BM25-lite).

    A saturating term-frequency score summed over the distinct query
    terms present in *text*, weighted by how many of the query's terms
    are covered.  Pure and deterministic — no index required.

    Args:
        text: The candidate snippet text.
        query: The free-text query.

    Returns:
        A non-negative relevance score; ``0.0`` when no query term
        appears (or either input is empty).
    """
    terms = {token for token in _WORD_RE.findall((query or "").lower()) if token}
    if not terms:
        return 0.0
    counts = Counter(_WORD_RE.findall((text or "").lower()))
    if not counts:
        return 0.0
    score = 0.0
    matched = 0
    for term in terms:
        tf = counts.get(term, 0)
        if tf > 0:
            matched += 1
            score += tf / (tf + 1.0)  # saturate so a flood of one term can't dominate
    coverage = matched / len(terms)
    return round(score * (0.5 + 0.5 * coverage), 6)


def reciprocal_rank_fusion(
    rank_lists: list[list[Any]], *, k: int = _DEFAULT_RRF_K
) -> dict[Any, float]:
    """Fuse several best-first ranked key lists into one RRF score map.

    Args:
        rank_lists: Each inner list is keys ordered best-first.
        k: The RRF rank-bias constant.

    Returns:
        ``{key: fused_score}`` summing ``1 / (k + rank)`` (1-based rank)
        across every list the key appears in.
    """
    fused: dict[Any, float] = {}
    for ranked in rank_lists:
        for rank, key in enumerate(ranked):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank + 1)
    return fused


def fuse_vector_hits(
    hits: list[dict[str, Any]], query: str, *, k: int = _DEFAULT_RRF_K
) -> list[dict[str, Any]]:
    """Re-rank vector hits by fusing their vector + keyword rankings.

    The input *hits* are assumed already ordered by vector score
    (best-first).  Each hit is re-scored by :func:`keyword_relevance`
    over its ``snippet``; the vector ordering and the keyword ordering
    are then fused by :func:`reciprocal_rank_fusion`, and the hits are
    returned in fused order, each augmented with ``keyword_score`` and
    ``fused_score``.

    Args:
        hits: Vector hits (each a dict with at least ``snippet``), in
            vector-score order.
        query: The free-text query for keyword scoring.
        k: The RRF rank-bias constant.

    Returns:
        The hits re-ordered by fused score, with the two extra score
        fields added.  An empty input yields an empty list.
    """
    if not hits:
        return []
    keyword_scores = [keyword_relevance(hit.get("snippet"), query) for hit in hits]
    vector_order = list(range(len(hits)))  # already vector-sorted
    keyword_order = sorted(range(len(hits)), key=lambda i: (keyword_scores[i], -i), reverse=True)
    fused = reciprocal_rank_fusion([vector_order, keyword_order], k=k)
    enriched = [
        {**hit, "keyword_score": keyword_scores[i], "fused_score": round(fused.get(i, 0.0), 6)}
        for i, hit in enumerate(hits)
    ]
    enriched.sort(key=lambda hit: hit["fused_score"], reverse=True)
    return enriched
