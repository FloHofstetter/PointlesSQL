"""``pql.vector_index`` / ``pql.vector_search`` unit tests.

Uses a deterministic in-process ``_FakeEmbedder`` so the suite does
not require ``sentence-transformers`` or PyTorch.  ``soyuz_catalog``
is short-circuited by monkeypatching ``_resolve_storage_location``;
the suite therefore exercises the full duckdb-vss path on a real
Delta table written to ``tmp_path``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import deltalake
import pandas as pd
import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.pql import _vector as vmod
from pointlessql.pql._vector import create_or_rebuild_index, search
from pointlessql.pql.embedders import EmbedderUnavailableError


class _FakeEmbedder:
    """Deterministic embedder — vector encodes string length + a constant tail."""

    name = "fake"
    model = "fake-1"
    dim = 4

    def __init__(self, model: str | None = None) -> None:
        # Accepts kwarg so the registry-resolve path works the same way.
        self.model = model or "fake-1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 2.0, 3.0] for t in texts]


@pytest.fixture
def fake_embedder() -> _FakeEmbedder:
    return _FakeEmbedder()


@pytest.fixture
def delta_path(tmp_path: Path) -> str:
    """Bootstrap a Delta table with a small ``description`` text column."""
    loc = str(tmp_path / "docs")
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "description": [
                "alpha bravo charlie",
                "users churn signals",
                "Lorem ipsum dolor sit amet",
                "delta echo foxtrot",
                "agent retrieval augmented generation",
            ],
        }
    )
    deltalake.write_deltalake(loc, df)
    return loc


@pytest.fixture(autouse=True)
def _stub_resolve_storage(delta_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit the soyuz call — return the Delta path for any FQN."""
    monkeypatch.setattr(
        vmod,
        "_resolve_storage_location",
        lambda client, full_name, unreachable_msg: delta_path,
    )


def test_create_builds_index_file(fake_embedder: _FakeEmbedder, delta_path: str) -> None:
    stats = create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=fake_embedder,
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=False,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=None,
    )
    assert stats["rows_indexed"] == 5
    assert stats["dim"] == fake_embedder.dim
    assert stats["embedder"] == "fake"
    file_path = Path(stats["path"])
    assert file_path.exists()
    assert file_path.parent.name == "_vss"


def test_create_then_search_returns_topk(
    fake_embedder: _FakeEmbedder, delta_path: str
) -> None:
    create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=fake_embedder,
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=False,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=None,
    )
    result = search(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        query="agent retrieval",
        top_k=3,
        unreachable_msg="",
        embedder_override=fake_embedder,
    )
    assert len(result["hits"]) == 3
    assert result["model"] == "fake-1"
    assert result["embedder"] == "fake"
    assert result["delta_version_indexed"] == 0
    scores = [h["score"] for h in result["hits"]]
    assert scores == sorted(scores, reverse=True)


def test_rebuild_idempotent_on_unchanged_table(
    fake_embedder: _FakeEmbedder, delta_path: str
) -> None:
    first = create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=fake_embedder,
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=False,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=None,
    )
    second = create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=fake_embedder,
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=True,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=None,
    )
    assert first["rows_indexed"] == second["rows_indexed"]
    assert first["dim"] == second["dim"]


def test_missing_column_raises_validation_error(
    fake_embedder: _FakeEmbedder, delta_path: str
) -> None:
    with pytest.raises(ValidationError, match="not present"):
        create_or_rebuild_index(
            client=None,  # type: ignore[arg-type]
            table="main.silver.docs",
            column="nonexistent",
            dim=None,
            model="fake-1",
            embedder=fake_embedder,
            metric="cosine",
            hnsw_m=16,
            hnsw_ef_construction=128,
            rebuild=False,
            unreachable_msg="",
            agent_run_id=None,
            workspace_id=None,
        )


def test_dim_mismatch_raises_validation_error(
    fake_embedder: _FakeEmbedder, delta_path: str
) -> None:
    with pytest.raises(ValidationError, match="does not match"):
        create_or_rebuild_index(
            client=None,  # type: ignore[arg-type]
            table="main.silver.docs",
            column="description",
            dim=8,  # wrong; fake_embedder has dim=4
            model="fake-1",
            embedder=fake_embedder,
            metric="cosine",
            hnsw_m=16,
            hnsw_ef_construction=128,
            rebuild=False,
            unreachable_msg="",
            agent_run_id=None,
            workspace_id=None,
        )


def test_search_without_index_raises_filenotfound(
    fake_embedder: _FakeEmbedder, delta_path: str
) -> None:
    with pytest.raises(FileNotFoundError, match="no vector index"):
        search(
            client=None,  # type: ignore[arg-type]
            table="main.silver.docs",
            column="description",
            query="anything",
            top_k=5,
            unreachable_msg="",
            embedder_override=fake_embedder,
        )


def test_search_dim_drift_raises_embedder_unavailable(
    fake_embedder: _FakeEmbedder, delta_path: str
) -> None:
    create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=fake_embedder,
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=False,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=None,
    )

    class _DimDrift:
        name = "fake"
        model = "fake-1"
        dim = 8  # drifted

        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            return [[0.0] * 8 for _ in texts]

    with pytest.raises(EmbedderUnavailableError, match="dim"):
        search(
            client=None,  # type: ignore[arg-type]
            table="main.silver.docs",
            column="description",
            query="x",
            top_k=1,
            unreachable_msg="",
            embedder_override=_DimDrift(),
        )
