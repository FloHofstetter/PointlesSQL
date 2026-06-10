# pyright: reportUnusedClass=false
"""Vector index + search for the PQL façade (DuckDB vss extension)."""

from __future__ import annotations

from typing import Any, Literal

from pointlessql.pql._pql_base import PQLBase as _PQLBase


class _VectorMixin(_PQLBase):
    """Create or rebuild HNSW vector indexes and run top-K semantic searches."""

    def vector_index(
        self,
        table: str,
        column: str,
        *,
        dim: int | None = None,
        model: str = "all-MiniLM-L6-v2",
        embedder: str | Any = "sentence_transformers",
        metric: Literal["cosine", "l2", "ip"] = "cosine",
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 128,
        rebuild: bool = False,
        workspace_id: int | None = None,
    ) -> dict[str, Any]:
        """Create or rebuild an HNSW vector index over ``table.column``.

        Backed by the DuckDB ``vss`` extension; the index file lives
        at ``<table.storage_location>/_vss/<column>.duckdb`` so a
        table-drop sweeps the index and a workspace export captures
        it.  After the first build, :meth:`merge` writes auto-rebuild
        the index incrementally via the post-commit hook.

        Args:
            table: Three-part UC ``"catalog.schema.table"`` reference.
            column: Source text column on *table*.
            dim: Output vector dimensionality.  ``None`` lets the
                embedder pick its built-in default.
            model: Provider-specific model identifier (e.g.
                ``"all-MiniLM-L6-v2"`` for the default
                ``sentence_transformers`` provider).
            embedder: Either a registry key
                (``"sentence_transformers"``, ``"openai"``,
                ``"hermes"``) or a pre-constructed embedder instance
                (test injection).
            metric: Similarity metric.  ``"cosine"`` is the default
                and the only metric exercised by the chat-panel
                retrieval flow.
            hnsw_m: HNSW ``m`` (max neighbours) build parameter;
                duckdb-vss default 16 is sane for ≤1M rows.
            hnsw_ef_construction: HNSW build-time candidate list
                size; duckdb-vss default 128 is sane for ≤1M rows.
            rebuild: When ``True``, drop and rebuild the index file
                from scratch even when no Delta version change is
                detected.
            workspace_id: PointlesSQL workspace owning the index.
                ``None`` skips the metadata-DB row (interactive
                REPL); the REST path sets this from the request
                context.

        Returns:
            Dict with ``index_id`` (autoincrement int or ``None`` in
            REPL mode), ``path``, ``dim``, ``rows_indexed``,
            ``delta_version_indexed``, ``built_at``, etc.
        """
        from typing import cast

        from pointlessql.pql._vector import create_or_rebuild_index
        from pointlessql.types import RunId

        return create_or_rebuild_index(
            client=self._client,
            table=table,
            column=column,
            dim=dim,
            model=model,
            embedder=embedder,
            metric=metric,
            hnsw_m=hnsw_m,
            hnsw_ef_construction=hnsw_ef_construction,
            rebuild=rebuild,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=cast(RunId | None, self._current_run_id),
            workspace_id=workspace_id,
        )

    def vector_search(
        self,
        table: str,
        column: str,
        query: str,
        *,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Run a top-K semantic search against an existing vector index.

        Args:
            table: Three-part UC ``"catalog.schema.table"`` reference.
            column: Source column on *table* — must already have an
                index built via :meth:`vector_index`.
            query: Free-text query string.  Embedded with the same
                provider that built the index.
            top_k: Number of hits to return (1–200).

        Returns:
            Dict with ``hits`` (list of ``{score, pk, snippet}``)
            plus the index's ``model``, ``embedder``, ``metric``, and
            ``delta_version_indexed`` so callers can report
            freshness.  Propagates :class:`FileNotFoundError` raised
            by :func:`pointlessql.pql._vector.search` when no index
            exists for the column.
        """
        from pointlessql.pql._vector import search

        return search(
            client=self._client,
            table=table,
            column=column,
            query=query,
            top_k=top_k,
            unreachable_msg=self._unreachable_msg(),
        )
