"""Pluggable text-embedder registry for the vector-search primitive.

The :class:`Embedder` protocol defines the minimum contract a
provider needs to implement: a stable ``name`` (registry key), a
``model`` identifier (provider-specific), the embedding ``dim``, and
an :meth:`embed` method that maps a batch of strings to a list of
float vectors.

The :func:`resolve_embedder` factory turns a string spec or an
already-constructed instance into a live :class:`Embedder`.  Embedder
classes lazy-import their heavy dependencies (``sentence_transformers``,
``openai``) so an install without the ``[vector]`` extra never pays
the import cost.

The ROADMAP-anticipated ``hermes`` provider ships as a
:class:`HermesEmbedder` stub that raises :class:`NotImplementedError`.
Once hermes-agent grows an ``embed`` tool, replacing the stub body
is the only change needed — every other site selects embedders by
name.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

__all__ = [
    "EMBEDDERS",
    "Embedder",
    "EmbedderUnavailableError",
    "resolve_embedder",
]


class EmbedderUnavailableError(RuntimeError):
    """An embedder's backing library / API is not installed or reachable.

    Raised at resolve-time or first :meth:`Embedder.embed` call so
    callers can distinguish "you forgot to install the extra" from
    "your query is bad".
    """


@runtime_checkable
class Embedder(Protocol):
    """Minimum contract for a text-embedding provider.

    Implementations are constructed by :func:`resolve_embedder` and
    cached for the lifetime of the process — the model file (for
    local providers) or the HTTP client (for hosted providers) loads
    once.

    Attributes:
        name: Registry key (``"sentence_transformers"``, ``"openai"``,
            ``"hermes"``).  Stored on ``vector_indices.embedder`` so
            search-time can re-resolve.
        model: Provider-specific model identifier (e.g.
            ``"all-MiniLM-L6-v2"`` for sentence-transformers,
            ``"text-embedding-3-small"`` for OpenAI).
        dim: Output vector dimensionality.  Persisted on
            ``vector_indices.dim`` and enforced at search time.
    """

    name: str
    model: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of strings to vectors of length :attr:`dim`.

        Implementations raise :class:`EmbedderUnavailableError` when
        their backing library is not installed or the remote API is
        unreachable.

        Args:
            texts: Strings to embed.  Empty strings are allowed; the
                implementation decides how to handle them
                (typically returning a zero vector).

        Returns:
            One ``list[float]`` of length :attr:`dim` per input
            string, in the same order.
        """
        ...


def resolve_embedder(spec: str | Embedder, *, model: str | None = None) -> Embedder:
    """Construct (or return) an :class:`Embedder` from a string spec.

    Propagates :class:`EmbedderUnavailableError` from the embedder
    constructor when the requested provider's library (or remote
    endpoint) is not available.

    Args:
        spec: Either a registry key (``"sentence_transformers"``,
            ``"openai"``, ``"hermes"``) or an already-constructed
            :class:`Embedder` (returned unchanged so callers can pass
            test doubles).
        model: Provider-specific model identifier.  Forwarded to the
            embedder constructor.  ``None`` lets the embedder pick
            its built-in default.

    Returns:
        A live :class:`Embedder` instance.

    Raises:
        ValueError: The spec is not a known registry key.
    """
    if not isinstance(spec, str):
        return spec
    try:
        klass = EMBEDDERS[spec]
    except KeyError as exc:
        raise ValueError(f"unknown embedder {spec!r}; known: {sorted(EMBEDDERS)!r}") from exc
    # Every concrete embedder accepts a ``model`` kwarg; the Protocol
    # only declares the attribute, so cast to keep pyright happy.
    return klass(model=model) if model else klass()  # type: ignore[call-arg]


# Late-binding imports: the submodules import :class:`Embedder` /
# :class:`EmbedderUnavailableError` from this module, so they must
# load *after* the symbols above are bound.  ``noqa: E402`` is the
# intentional escape from "imports at top".
from pointlessql.pql.embedders._hermes import HermesEmbedder  # noqa: E402
from pointlessql.pql.embedders._openai import OpenAIEmbedder  # noqa: E402
from pointlessql.pql.embedders._sentence_transformers import (  # noqa: E402
    SentenceTransformersEmbedder,
)

EMBEDDERS: dict[str, type[Embedder]] = {
    "sentence_transformers": SentenceTransformersEmbedder,
    "openai": OpenAIEmbedder,
    "hermes": HermesEmbedder,
}
