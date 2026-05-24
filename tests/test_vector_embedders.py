"""Embedder protocol + registry unit tests.

Pure-Python; never imports ``sentence_transformers`` so the suite
runs without the ``[vector]`` extra installed.
"""

from __future__ import annotations

import pytest

from pointlessql.pql.embedders import (
    EMBEDDERS,
    Embedder,
    EmbedderUnavailableError,
    resolve_embedder,
)
from pointlessql.pql.embedders._hermes import HermesEmbedder


class _FakeEmbedder:
    """Deterministic embedder for tests.  Maps every token to a stable vector."""

    name = "fake"
    model = "fake-1"
    dim = 4

    def embed(self, texts):
        return [[float(len(t) % 7), 1.0, 2.0, 3.0] for t in texts]


def test_registry_lists_all_three_providers() -> None:
    assert "sentence_transformers" in EMBEDDERS
    assert "openai" in EMBEDDERS
    assert "hermes" in EMBEDDERS


def test_resolve_embedder_passthrough_for_instance() -> None:
    fake = _FakeEmbedder()
    resolved = resolve_embedder(fake)
    assert resolved is fake


def test_resolve_embedder_unknown_spec_raises() -> None:
    with pytest.raises(ValueError, match="unknown embedder"):
        resolve_embedder("nope")


def test_hermes_stub_embed_always_raises() -> None:
    hermes = HermesEmbedder()
    with pytest.raises(EmbedderUnavailableError, match="hermes-agent"):
        hermes.embed(["foo"])


def test_fake_embedder_implements_protocol() -> None:
    fake = _FakeEmbedder()
    assert isinstance(fake, Embedder)
    vectors = fake.embed(["hi", "world"])
    assert len(vectors) == 2
    assert len(vectors[0]) == fake.dim
