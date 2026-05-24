"""merge-hook auto-rebuild tests.

Drives ``rebuild_vss_indices_after_commit`` directly against a small
seeded ``vector_indices`` row.  The hook is invariant-checked via:

* no-op when ``error_message`` is set,
* no-op for non-trigger op_names,
* writes ``last_built_rows`` + clears ``last_error`` on success,
* stamps ``last_error`` and does not re-raise on rebuild failure.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

import deltalake
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import Base, VectorIndex
from pointlessql.pql import _vector as vmod
from pointlessql.pql._vector import create_or_rebuild_index
from pointlessql.services.agent_runs.operations._vector_rebuild import (
    rebuild_vss_indices_after_commit,
)


class _FakeEmbedder:
    name = "fake"
    model = "fake-1"
    dim = 4

    def __init__(self, model: str | None = None) -> None:
        self.model = model or "fake-1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 2.0, 3.0] for t in texts]


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def workspace_id(factory: sessionmaker) -> int:  # type: ignore[type-arg]
    from pointlessql.models import Workspace

    with factory() as s:
        ws = Workspace(
            name="test",
            slug="test-ws",
            description=None,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        return int(ws.id)


@pytest.fixture
def delta_path_with_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: sessionmaker,  # type: ignore[type-arg]
    workspace_id: int,
) -> tuple[str, int]:
    """Seed a Delta table + a fresh vector_indices row.

    Returns the (storage_location, vector_index_id) tuple.
    """
    loc = str(tmp_path / "docs")
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "description": ["alpha bravo", "users churn", "agent retrieval"],
        }
    )
    deltalake.write_deltalake(loc, df)

    monkeypatch.setattr(
        vmod,
        "_resolve_storage_location",
        lambda client, full_name, unreachable_msg: loc,
    )
    monkeypatch.setattr(
        vmod,
        "_session_factory_or_none",
        lambda: factory,
    )
    # Also patch the embedder registry so the rebuild hook resolves
    # 'fake' to our test embedder via name.
    from pointlessql.pql import embedders as embedders_mod

    monkeypatch.setitem(embedders_mod.EMBEDDERS, "fake", _FakeEmbedder)

    stats = create_or_rebuild_index(
        client=None,  # type: ignore[arg-type]
        table="main.silver.docs",
        column="description",
        dim=None,
        model="fake-1",
        embedder=_FakeEmbedder(),
        metric="cosine",
        hnsw_m=16,
        hnsw_ef_construction=128,
        rebuild=False,
        unreachable_msg="",
        agent_run_id=None,
        workspace_id=workspace_id,
    )
    return loc, int(stats["index_id"])


def test_hook_skips_when_error_message_set(
    factory: sessionmaker,
    delta_path_with_index: tuple[str, int],  # type: ignore[type-arg]
) -> None:
    _, index_id = delta_path_with_index
    rebuild_vss_indices_after_commit(
        factory,
        op_id=None,
        agent_run_id=None,
        op_name="merge",
        target_table="main.silver.docs",
        error_message="something failed",
    )
    with factory() as s:
        row = s.get(VectorIndex, index_id)
        assert row is not None
        assert row.last_error is None  # hook didn't touch it


def test_hook_skips_for_non_trigger_op_names(
    factory: sessionmaker,
    delta_path_with_index: tuple[str, int],  # type: ignore[type-arg]
) -> None:
    _, index_id = delta_path_with_index
    with factory() as s:
        original_built_at = s.get(VectorIndex, index_id).last_built_at
    rebuild_vss_indices_after_commit(
        factory,
        op_id=None,
        agent_run_id=None,
        op_name="vector_search",  # not in trigger set
        target_table="main.silver.docs",
        error_message=None,
    )
    with factory() as s:
        row = s.get(VectorIndex, index_id)
        assert row is not None
        assert row.last_built_at == original_built_at


def test_hook_rebuilds_on_merge_success(
    factory: sessionmaker,  # type: ignore[type-arg]
    delta_path_with_index: tuple[str, int],
    tmp_path: Path,
) -> None:
    loc, index_id = delta_path_with_index
    # Append more rows so the rebuild has something fresh to embed.
    df2 = pd.DataFrame({"id": [4, 5], "description": ["new row one", "new row two"]})
    deltalake.write_deltalake(loc, df2, mode="append")

    rebuild_vss_indices_after_commit(
        factory,
        op_id=None,
        agent_run_id=None,
        op_name="merge",
        target_table="main.silver.docs",
        error_message=None,
    )
    with factory() as s:
        row = s.get(VectorIndex, index_id)
        assert row is not None
        assert row.last_error is None
        assert row.last_built_rows == 5  # 3 original + 2 appended
        assert row.delta_version_indexed is not None


def test_hook_logs_error_without_reraising(
    factory: sessionmaker,  # type: ignore[type-arg]
    delta_path_with_index: tuple[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loc, index_id = delta_path_with_index
    # Point the index_path at a bogus location so the Delta read inside
    # the rebuild raises — the hook should swallow it.
    with factory() as s:
        row = s.get(VectorIndex, index_id)
        assert row is not None
        row.index_path = "/nonexistent/_vss/description.duckdb"
        s.commit()

    rebuild_vss_indices_after_commit(
        factory,
        op_id=None,
        agent_run_id=None,
        op_name="merge",
        target_table="main.silver.docs",
        error_message=None,
    )
    with factory() as s:
        row = s.get(VectorIndex, index_id)
        assert row is not None
        assert row.last_error is not None
