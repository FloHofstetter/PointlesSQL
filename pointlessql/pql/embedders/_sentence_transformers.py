"""Local sentence-transformers embedder.

Default provider for :func:`pointlessql.pql.PQL.vector_index`.  Pulls
in ``sentence-transformers`` lazily — the import only fires at first
use, so a minimal install without the ``[vector]`` extra is unaffected
unless vector-search is actually invoked.

The default model is ``all-MiniLM-L6-v2`` (384-dim, ~90 MB).  Larger
models are selected by passing ``model=`` to
:meth:`pointlessql.pql.PQL.vector_index` — the embedder caches the
loaded ``SentenceTransformer`` instance per-(class, model) so a
notebook session that runs many searches against the same model only
pays the load cost once.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pointlessql.pql.embedders import EmbedderUnavailableError

__all__ = ["SentenceTransformersEmbedder"]


DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_DIM = 384


_MODEL_CACHE: dict[str, Any] = {}


class SentenceTransformersEmbedder:
    """Embed text via a locally-loaded sentence-transformers model.

    The class instance is cheap; the heavy resource is the
    underlying ``SentenceTransformer`` which is cached on a
    module-level dict keyed by model name.  Repeated instantiations
    with the same model reuse the cached instance.

    Attributes:
        name: Registry key ``"sentence_transformers"``.

    Args:
        model: Hugging-Face model identifier.  Defaults to
            :data:`DEFAULT_MODEL` (``all-MiniLM-L6-v2``).
    """

    name = "sentence_transformers"

    def __init__(self, model: str | None = None) -> None:
        # ``_load`` raises ``EmbedderUnavailableError`` when the
        # ``sentence-transformers`` package is not importable — the
        # caller sees that surfaced through the constructor.
        self.model = model or DEFAULT_MODEL
        self._st_model = self._load(self.model)
        # ``get_sentence_embedding_dimension`` returns the output
        # vector size for the loaded model; we trust the library
        # rather than hard-coding the default so non-MiniLM models
        # like ``all-mpnet-base-v2`` (768) work out of the box.
        self.dim: int = int(self._st_model.get_sentence_embedding_dimension())

    @staticmethod
    def _load(model_name: str) -> Any:
        cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            return cached
        try:
            from sentence_transformers import (  # pyright: ignore[reportMissingImports]
                SentenceTransformer,
            )
        except ImportError as exc:
            raise EmbedderUnavailableError(
                "sentence-transformers is not installed.  "
                "Install the optional extra: pip install 'pointlessql[vector]'"
            ) from exc
        loaded = SentenceTransformer(model_name)
        _MODEL_CACHE[model_name] = loaded
        return loaded

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of strings.

        Args:
            texts: Strings to embed.

        Returns:
            One ``list[float]`` of length :attr:`dim` per input.
        """
        # ``encode`` accepts a list[str] and returns a numpy array;
        # we cast to plain Python floats so the result can be JSON-
        # serialised and inserted into DuckDB without a numpy hop.
        arr = self._st_model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)
        return [[float(x) for x in row] for row in arr]
