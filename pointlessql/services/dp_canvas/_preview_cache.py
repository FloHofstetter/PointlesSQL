"""In-memory LRU cache for canvas preview results.

The visual editor's "Preview rows on this node" gesture compiles the
upstream slice of the canvas DAG, runs it through DuckDB, and returns
the first N rows.  Repeated previews on the same node — common while
the user fiddles with downstream block configs — re-run the same SQL
each time, paying the same DuckDB scan + Delta-read cost.

This module memoises the result keyed on
``(upstream-subgraph-hash, upto_node_id, limit)`` so the second hit
returns in microseconds without re-running the scan.  The hash is
computed over only the nodes that flow into ``upto_node_id`` so an
edit *downstream* of the previewed tip does not bust unrelated
caches.

Scope:

* Per-process, per-worker.  Single-uvicorn-worker is the only
  supported topology today; a future multi-worker setup would need
  either Redis or a sticky-routing layer.
* LRU bounded at :data:`MAX_ENTRIES` so a long-lived editor session
  cannot OOM the worker.
* Explicit bust paths: ``clear_for_dp(dp_id)`` is called from
  ``save_graph`` after every successful version mint; the route layer
  also exposes a ``?bust=1`` query param so a steward can force a
  re-run when the underlying Delta location was rewritten out-of-band.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pointlessql.services.dp_canvas._preview import PreviewResult
    from pointlessql.services.dp_canvas._types import CanvasDoc

MAX_ENTRIES = 128


# Per-DP set of (cache_key, doc_hash) tuples — lets us bust everything
# for a given DP without walking the global map.  Both maps are
# protected by Python's GIL since they're in-process only.
_CACHE: OrderedDict[str, PreviewResult] = OrderedDict()
_KEYS_BY_DP: dict[int, set[str]] = {}


def _upstream_doc_hash(doc: CanvasDoc, upto_node_id: str) -> str:
    """SHA-1 over the upstream-slice subset of *doc*.

    Only the nodes that flow into *upto_node_id* (inclusive) plus the
    edges between them participate; positions and downstream nodes are
    excluded so cosmetic / unrelated edits do not bust the cache.
    """
    from pointlessql.services.dp_canvas._preview import (
        _collect_ancestors,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701 — sibling-module helper, both files private
    )

    keep = _collect_ancestors(doc, upto_node_id)
    node_items = sorted(
        (n for n in doc.nodes if n.id in keep),
        key=lambda n: n.id,
    )
    edge_items = sorted(
        (
            e
            for e in doc.edges
            if e.source_node_id in keep and e.target_node_id in keep
        ),
        key=lambda e: (
            e.source_node_id,
            e.source_pin,
            e.target_node_id,
            e.target_pin,
        ),
    )
    nodes = [
        {"id": n.id, "block_type": n.block_type, "config": n.config}
        for n in node_items
    ]
    edges = [
        {
            "source_node_id": e.source_node_id,
            "source_pin": e.source_pin,
            "target_node_id": e.target_node_id,
            "target_pin": e.target_pin,
        }
        for e in edge_items
    ]
    payload = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _key(*, dp_id: int, doc_hash: str, upto_node_id: str, limit: int) -> str:
    return f"{dp_id}|{doc_hash}|{upto_node_id}|{limit}"


def lookup(
    *,
    dp_id: int,
    doc: CanvasDoc,
    upto_node_id: str,
    limit: int,
) -> PreviewResult | None:
    """Return the cached PreviewResult for this preview, or ``None`` on miss."""
    doc_hash = _upstream_doc_hash(doc, upto_node_id)
    key = _key(dp_id=dp_id, doc_hash=doc_hash, upto_node_id=upto_node_id, limit=limit)
    if key not in _CACHE:
        return None
    # Refresh LRU position.
    _CACHE.move_to_end(key)
    return _CACHE[key]


def store(
    *,
    dp_id: int,
    doc: CanvasDoc,
    upto_node_id: str,
    limit: int,
    result: PreviewResult,
) -> None:
    """Memoise *result* under the preview's identity tuple."""
    doc_hash = _upstream_doc_hash(doc, upto_node_id)
    key = _key(dp_id=dp_id, doc_hash=doc_hash, upto_node_id=upto_node_id, limit=limit)
    _CACHE[key] = result
    _CACHE.move_to_end(key)
    _KEYS_BY_DP.setdefault(dp_id, set()).add(key)
    while len(_CACHE) > MAX_ENTRIES:
        evicted_key, _evicted_value = _CACHE.popitem(last=False)
        # Drop the evicted key from every per-DP set we know about.
        for keyset in _KEYS_BY_DP.values():
            keyset.discard(evicted_key)


def clear_for_dp(dp_id: int) -> None:
    """Drop every cached preview belonging to *dp_id*.

    Called from ``save_graph`` so a save-driven canvas mutation cannot
    return stale rows on the next preview call.
    """
    keys = _KEYS_BY_DP.pop(dp_id, set())
    for key in keys:
        _CACHE.pop(key, None)


def clear_all() -> None:
    """Drop the entire cache.  Used by tests."""
    _CACHE.clear()
    _KEYS_BY_DP.clear()


def size() -> int:
    """Return the current entry count.  Used by tests + diagnostics."""
    return len(_CACHE)


__all__ = [
    "MAX_ENTRIES",
    "clear_all",
    "clear_for_dp",
    "lookup",
    "size",
    "store",
]
