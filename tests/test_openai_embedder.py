"""Unit tests for the OpenAI hosted embedder.

The model check runs before the client is built, so unknown-model
validation needs no key. The success paths patch ``_make_client`` to a
fake so no real OpenAI call (or ``OPENAI_API_KEY``) is required; the
missing-key path exercises the real ``_make_client`` guard.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.pql.embedders import EmbedderUnavailableError
from pointlessql.pql.embedders._openai import DEFAULT_MODEL, MODEL_DIMS, OpenAIEmbedder


class _FakeClient:
    def __init__(self, dim: int) -> None:
        self._dim = dim
        self.embeddings = SimpleNamespace(create=self._create)
        self.calls: list[Any] = []

    def _create(self, *, model: str, input: list[str]) -> Any:
        self.calls.append(input)
        data = [SimpleNamespace(embedding=[0.0] * self._dim) for _ in input]
        return SimpleNamespace(data=data)


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    """Build an embedder whose client is a fake; returns (embedder, client)."""

    def _build(model: str | None = None) -> tuple[OpenAIEmbedder, _FakeClient]:
        client = _FakeClient(MODEL_DIMS[model or DEFAULT_MODEL])
        monkeypatch.setattr(OpenAIEmbedder, "_make_client", staticmethod(lambda: client))
        return OpenAIEmbedder(model), client

    return _build


def test_unknown_model_raises() -> None:
    with pytest.raises(ValueError, match="unknown OpenAI embedding model"):
        OpenAIEmbedder("text-embedding-9-impossible")


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(EmbedderUnavailableError, match="OPENAI_API_KEY"):
        OpenAIEmbedder()


def test_default_model_and_dim(patched: Any) -> None:
    embedder, _ = patched()
    assert embedder.model == DEFAULT_MODEL
    assert embedder.dim == MODEL_DIMS[DEFAULT_MODEL]
    assert embedder.name == "openai"


def test_large_model_dim(patched: Any) -> None:
    embedder, _ = patched("text-embedding-3-large")
    assert embedder.dim == 3072


def test_embed_returns_one_vector_per_input(patched: Any) -> None:
    embedder, _ = patched()
    out = embedder.embed(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == embedder.dim for v in out)


def test_embed_substitutes_empty_strings(patched: Any) -> None:
    embedder, client = patched()
    embedder.embed(["", "x"])
    # The empty string is replaced with a single space before the call.
    assert client.calls[-1] == [" ", "x"]
