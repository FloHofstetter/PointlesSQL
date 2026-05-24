"""OpenAI hosted embedder.

Optional provider for users who want hosted embeddings.  The
``openai`` SDK is already a core dependency (:mod:`pointlessql` uses
it for the chat panel), so no extra install is required — but the
provider only activates when ``OPENAI_API_KEY`` is set in the
environment or passed via ``settings.llm.openai_api_key``.

Selected with ``embedder="openai"`` on
:meth:`pointlessql.pql.PQL.vector_index`.  The default model is
``text-embedding-3-small`` (1536-dim, $0.02 / 1M tokens).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from pointlessql.pql.embedders import EmbedderUnavailableError

__all__ = ["OpenAIEmbedder"]


DEFAULT_MODEL = "text-embedding-3-small"
MODEL_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedder:
    """Embed text via the OpenAI ``/v1/embeddings`` API.

    Attributes:
        name: Registry key ``"openai"``.

    Args:
        model: OpenAI embedding model name.  Defaults to
            :data:`DEFAULT_MODEL`.

    Raises:
        ValueError: *model* is not one of :data:`MODEL_DIMS` keys.
    """

    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        # ``_make_client`` raises ``EmbedderUnavailableError`` when
        # the ``openai`` SDK is missing or ``OPENAI_API_KEY`` is not
        # set — surfaced to the caller through the constructor.
        self.model = model or DEFAULT_MODEL
        # MODEL_DIMS is the source-of-truth for known dims; falling
        # back to a probe-call for unlisted models would be costly,
        # so we surface the gap clearly.
        if self.model not in MODEL_DIMS:
            raise ValueError(
                f"unknown OpenAI embedding model {self.model!r}; known: {sorted(MODEL_DIMS)!r}"
            )
        self.dim = MODEL_DIMS[self.model]
        self._client = self._make_client()

    @staticmethod
    def _make_client() -> Any:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EmbedderUnavailableError(
                "OPENAI_API_KEY is not set; cannot use the openai embedder."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise EmbedderUnavailableError("openai SDK is not installed.") from exc
        return OpenAI(api_key=api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of strings via the OpenAI API.

        Args:
            texts: Strings to embed.

        Returns:
            One ``list[float]`` of length :attr:`dim` per input,
            in the same order as the request.
        """
        # OpenAI rejects empty strings — substitute a single space so
        # the index aligns with the input batch.  Downstream consumers
        # of the vector treat near-zero distances correctly for these
        # placeholder rows.
        payload = [(t if t else " ") for t in texts]
        response = self._client.embeddings.create(model=self.model, input=payload)
        return [list(item.embedding) for item in response.data]
