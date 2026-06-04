"""Behaviour tests that pin down the embedder providers' observable contract.

Pure-Python; never imports ``sentence_transformers`` (not installed in
the default lane) — the sentence-transformers provider is exercised by
pre-seeding the module-level model cache with a recording fake, which
short-circuits the lazy import inside ``_load``.  The OpenAI provider is
exercised by stubbing ``_make_client`` with a recording fake client.

These tests assert the exact kwargs each provider forwards to its
backend, the exact stub error message, and the model-default fallback
behaviour — the parts a caller (or a persisted ``vector_indices`` row)
actually observes.
"""

from __future__ import annotations

import pytest

from pointlessql.pql.embedders import EmbedderUnavailableError
from pointlessql.pql.embedders import _sentence_transformers as st_mod
from pointlessql.pql.embedders._hermes import HermesEmbedder
from pointlessql.pql.embedders._openai import (
    DEFAULT_MODEL,
    MODEL_DIMS,
    OpenAIEmbedder,
)
from pointlessql.pql.embedders._sentence_transformers import (
    SentenceTransformersEmbedder,
)

# --------------------------------------------------------------------------
# HermesEmbedder
# --------------------------------------------------------------------------


def test_hermes_model_defaults_to_pending() -> None:
    # No model -> falls back to the exact sentinel "pending" (not None,
    # not a cased variant).  Pins __init__ default-fallback + literal.
    assert HermesEmbedder().model == "pending"
    assert HermesEmbedder(None).model == "pending"


def test_hermes_keeps_explicit_model() -> None:
    # An explicit model must be stored verbatim — ``model or "pending"``,
    # not ``model and "pending"`` (which would clobber it) and not None.
    assert HermesEmbedder("custom-model").model == "custom-model"
    assert HermesEmbedder(model="hermes-v2").model == "hermes-v2"


def test_hermes_static_attrs() -> None:
    assert HermesEmbedder.name == "hermes"
    assert HermesEmbedder().dim == 0


def test_hermes_embed_raises_with_full_message() -> None:
    # Assert the *entire* error message verbatim so any single-fragment
    # mutation of the multi-line string literal is caught.
    expected = (
        "hermes-agent does not currently expose an `embed` tool.  "
        "Use embedder='sentence_transformers' (default) or "
        "embedder='openai' (set OPENAI_API_KEY)."
    )
    with pytest.raises(EmbedderUnavailableError) as excinfo:
        HermesEmbedder().embed(["anything"])
    assert str(excinfo.value) == expected


# --------------------------------------------------------------------------
# SentenceTransformersEmbedder  (cache-seeded fake; no heavy import)
# --------------------------------------------------------------------------


class _RecordingSTModel:
    """Stand-in for a loaded ``SentenceTransformer``.

    Records the positional/keyword args passed to ``encode`` so tests can
    assert the exact call shape, and returns a deterministic 3-dim vector
    per input row.
    """

    def __init__(self, dim: int = 3) -> None:
        self._dim = dim
        self.encode_calls: list[tuple[object, dict[str, object]]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim

    def encode(self, texts, **kwargs):
        self.encode_calls.append((texts, kwargs))
        # One row per input; values derived from string length so the
        # output is order-preserving and deterministic.
        return [[float(len(t)), 1.0, 2.0] for t in texts]


@pytest.fixture
def seeded_st(monkeypatch):
    """Seed the model cache with a recording fake under a unique name."""
    fake = _RecordingSTModel(dim=3)
    name = "fake-st-model"
    # Patch the cache dict so the lazy import inside ``_load`` never runs.
    monkeypatch.setitem(st_mod._MODEL_CACHE, name, fake)
    return name, fake


def test_st_init_loads_the_requested_model(seeded_st) -> None:
    # ``_load(self.model)`` must receive the *real* model name, not None.
    # If __init__ passed None to _load, the cache lookup would miss and
    # the absent sentence_transformers import would raise.
    name, fake = seeded_st
    emb = SentenceTransformersEmbedder(model=name)
    assert emb.model == name
    assert emb.dim == 3


def test_st_init_missing_model_raises_unavailable(seeded_st) -> None:
    # A model name not in the cache triggers the lazy import, which fails
    # because sentence-transformers isn't installed -> the documented
    # EmbedderUnavailableError (proves _load got the real name, not the
    # cached fake name).
    with pytest.raises(EmbedderUnavailableError, match="sentence-transformers"):
        SentenceTransformersEmbedder(model="definitely-not-cached-xyz")


def test_st_embed_forwards_exact_encode_kwargs(seeded_st) -> None:
    name, fake = seeded_st
    emb = SentenceTransformersEmbedder(model=name)
    emb.embed(["ab", "cde"])

    # One recorded encode call.
    assert len(fake.encode_calls) == 1
    pos_arg, kwargs = fake.encode_calls[0]

    # First positional arg is the materialised list of the input texts.
    assert pos_arg == ["ab", "cde"]
    assert isinstance(pos_arg, list)

    # Exact kwargs: convert_to_numpy MUST be True (not False/None/absent)
    # and show_progress_bar MUST be False (not True/None/absent).
    assert kwargs == {"convert_to_numpy": True, "show_progress_bar": False}


def test_st_embed_returns_plain_float_lists(seeded_st) -> None:
    name, fake = seeded_st
    emb = SentenceTransformersEmbedder(model=name)
    out = emb.embed(["x", "yy"])
    assert out == [[1.0, 1.0, 2.0], [2.0, 1.0, 2.0]]
    # Every scalar is a built-in float, never numpy.
    assert all(type(v) is float for row in out for v in row)


# --------------------------------------------------------------------------
# OpenAIEmbedder  (stubbed client; no network)
# --------------------------------------------------------------------------


class _FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingsResponse:
    def __init__(self, data):
        self.data = data


class _FakeEmbeddingsEndpoint:
    def __init__(self):
        self.create_calls: list[dict[str, object]] = []

    def create(self, *, model, input):
        self.create_calls.append({"model": model, "input": input})
        # Echo one vector per input row; encode the input string so a
        # mismatched model/input is observable downstream.
        data = [_FakeEmbeddingItem([float(len(s)), 9.0]) for s in input]
        return _FakeEmbeddingsResponse(data)


class _FakeOpenAIClient:
    def __init__(self):
        self.embeddings = _FakeEmbeddingsEndpoint()


@pytest.fixture
def openai_emb(monkeypatch):
    """Build an OpenAIEmbedder backed by a recording fake client."""
    fake_client = _FakeOpenAIClient()
    monkeypatch.setattr(OpenAIEmbedder, "_make_client", staticmethod(lambda: fake_client))
    emb = OpenAIEmbedder()  # default model
    return emb, fake_client


def test_openai_default_model_and_dim(openai_emb) -> None:
    emb, _ = openai_emb
    assert emb.model == DEFAULT_MODEL
    assert emb.dim == MODEL_DIMS[DEFAULT_MODEL]


def test_openai_unknown_model_raises(monkeypatch) -> None:
    monkeypatch.setattr(OpenAIEmbedder, "_make_client", staticmethod(lambda: _FakeOpenAIClient()))
    with pytest.raises(ValueError, match="unknown OpenAI embedding model"):
        OpenAIEmbedder(model="text-embedding-bogus")


def test_openai_embed_passes_real_model_kwarg(openai_emb) -> None:
    # The create() call MUST use self.model, not None.
    emb, fake_client = openai_emb
    emb.embed(["hello"])
    assert len(fake_client.embeddings.create_calls) == 1
    call = fake_client.embeddings.create_calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert call["model"] is not None


def test_openai_embed_substitutes_empty_with_single_space(openai_emb) -> None:
    # Empty strings become a single space; non-empty pass through.  The
    # placeholder is exactly " " (one space), not "  " or "".
    emb, fake_client = openai_emb
    emb.embed(["", "kept", ""])
    sent = fake_client.embeddings.create_calls[0]["input"]
    assert sent == [" ", "kept", " "]


def test_openai_embed_returns_lists_in_order(openai_emb) -> None:
    emb, _ = openai_emb
    out = emb.embed(["a", "bb", "ccc"])
    assert out == [[1.0, 9.0], [2.0, 9.0], [3.0, 9.0]]
    assert all(isinstance(row, list) for row in out)
