"""Unit tests for the local sentence-transformers embedder.

The heavy ``SentenceTransformer`` load is mocked: ``_load`` is patched to
return a fake model exposing ``get_sentence_embedding_dimension`` +
``encode``, so the constructor/dim/embed logic and the per-model cache are
covered without pulling the optional ``[vector]`` dependency or a model.
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.pql.embedders._sentence_transformers import (
    DEFAULT_MODEL,
    SentenceTransformersEmbedder,
    _MODEL_CACHE,
)


class _FakeModel:
    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim

    def encode(self, texts: list[str], **_: Any) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    def _build(model: str | None = None, dim: int = 384) -> SentenceTransformersEmbedder:
        monkeypatch.setattr(
            SentenceTransformersEmbedder, "_load", staticmethod(lambda name: _FakeModel(dim))
        )
        return SentenceTransformersEmbedder(model)

    return _build


def test_default_model_and_name(patched: Any) -> None:
    emb = patched()
    assert emb.model == DEFAULT_MODEL
    assert emb.name == "sentence_transformers"


def test_dim_comes_from_loaded_model(patched: Any) -> None:
    emb = patched(dim=768)
    assert emb.dim == 768


def test_custom_model_passthrough(patched: Any) -> None:
    emb = patched("all-mpnet-base-v2")
    assert emb.model == "all-mpnet-base-v2"


def test_embed_returns_float_lists(patched: Any) -> None:
    emb = patched()
    out = emb.embed(["a", "b"])
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert all(isinstance(x, float) for row in out for x in row)


def test_load_returns_cached_instance() -> None:
    sentinel = object()
    _MODEL_CACHE["__test-cache-model__"] = sentinel
    try:
        assert SentenceTransformersEmbedder._load("__test-cache-model__") is sentinel
    finally:
        _MODEL_CACHE.pop("__test-cache-model__", None)
