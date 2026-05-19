"""Stub embedder targeting a future hermes-agent ``embed`` tool.

The ROADMAP for Phase 92 anticipated routing the default embedder
through hermes-agent so PointlesSQL would not need to take on a new
API-key surface.  hermes-agent does not currently expose an ``embed``
tool, so the default lives in
:mod:`pointlessql.pql.embedders._sentence_transformers` instead.

This stub stays in the registry so when hermes-agent grows the tool,
the only change needed is replacing :meth:`HermesEmbedder.embed`'s
body — every existing ``vector_indices`` row that names
``embedder="hermes"`` then resolves cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence

from pointlessql.pql.embedders import EmbedderUnavailableError

__all__ = ["HermesEmbedder"]


class HermesEmbedder:
    """Reserved registry slot for a future hermes-agent embed tool.

    Constructing an instance is fine (the registry instantiates
    embedders eagerly during :func:`resolve_embedder`) but the first
    :meth:`embed` call raises :class:`EmbedderUnavailableError` with
    a pointer to the (default) sentence-transformers provider.
    """

    name = "hermes"
    model = "pending"
    dim = 0

    def __init__(self, model: str | None = None) -> None:
        self.model = model or "pending"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Always raises until hermes-agent ships an ``embed`` tool.

        Args:
            texts: Unused; the call short-circuits before touching the
                input.

        Returns:
            Never returns — always raises.

        Raises:
            EmbedderUnavailableError: Always; ships as a stub.
        """  # noqa: DOC202 — body has no return statement; documented for clarity
        raise EmbedderUnavailableError(
            "hermes-agent does not currently expose an `embed` tool.  "
            "Use embedder='sentence_transformers' (default) or "
            "embedder='openai' (set OPENAI_API_KEY)."
        )
