"""coedit-compaction scheduler executor tests."""

from __future__ import annotations

import datetime
import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select

from pointlessql.api import notebook_coedit_ws
from pointlessql.api.main import app
from pointlessql.models import Notebook
from pointlessql.models.notebook import NotebookCrdtState
from pointlessql.services.notebook import coedit as coedit_service
from pointlessql.services.scheduler.executors import (
    _coedit_compaction_executor,
)
from pointlessql.types import UserInfo


@pytest.fixture(autouse=True)
def _bind_global_session_factory() -> Iterator[None]:
    """Mirror the app-state session factory onto ``db._session_factory``.

    ``get_session_factory()`` reads a process-global the production
    boot path populates via ``init_db()``.  The conftest skips that
    bootstrap and binds the factory directly onto ``app.state`` —
    fine for request-driven tests, but executors fetch the factory
    via the global, so we mirror it here for the executor pass.
    """
    import pointlessql.db as _db

    previous = _db._session_factory  # noqa: SLF001
    _db._session_factory = app.state.session_factory  # noqa: SLF001
    try:
        yield
    finally:
        _db._session_factory = previous  # noqa: SLF001


@pytest.fixture
def fresh_notebook_with_blob() -> Iterator[str]:
    """Insert a notebook + a non-empty crdt blob, cleanup after."""
    notebook_id = str(uuid.uuid4())
    factory = app.state.session_factory
    # Build a real CRDT update blob so ``compact`` has something to
    # re-encode.  Empty blob would short-circuit ``needs_compaction``
    # (size threshold) — we override the threshold via env in the
    # tests that need a guaranteed trigger.
    from pycrdt import Array, Doc, Map, Text

    doc = Doc()
    doc["cells_order"] = Array()
    doc["cells_text"] = Map()
    doc["cells_text"]["seed"] = Text("hello " * 500)
    doc["cells_order"].append("seed")
    blob = doc.get_update()
    with factory() as session:
        session.add(
            Notebook(
                id=notebook_id,
                workspace_id=1,
                file_path=f"compaction-test-{notebook_id[:8]}.py",
            )
        )
        session.add(
            NotebookCrdtState(
                notebook_id=notebook_id,
                y_doc_blob=blob,
                # Backdate updated_at so the TTL-based needs_compaction
                # branch fires deterministically.
                updated_at=datetime.datetime.now(datetime.UTC)
                - datetime.timedelta(days=30),
                compacted_at=None,
            )
        )
        session.commit()
    yield notebook_id
    notebook_coedit_ws._HUBS.pop(notebook_id, None)
    with factory() as session:
        session.execute(
            delete(NotebookCrdtState).where(
                NotebookCrdtState.notebook_id == notebook_id
            )
        )
        session.execute(delete(Notebook).where(Notebook.id == notebook_id))
        session.commit()


def _zero_user() -> UserInfo:
    return UserInfo(
        id=0,
        email="",
        display_name="",
        is_admin=False,
        is_supervisor=False,
        is_auditor=False,
    )


async def test_compaction_executor_compacts_inactive_notebook(
    fresh_notebook_with_blob: str,
) -> None:
    """A stale blob without an active hub gets compacted."""
    factory = app.state.session_factory
    # Sanity: the row exists with no compacted_at marker.
    with factory() as session:
        row = session.execute(
            select(NotebookCrdtState).where(
                NotebookCrdtState.notebook_id == fresh_notebook_with_blob
            )
        ).scalar_one()
        assert row.compacted_at is None

    await _coedit_compaction_executor(
        job_run_id=0,
        user_info=_zero_user(),
        config={},
        uc_client=None,  # type: ignore[arg-type] — executor never touches it
    )

    with factory() as session:
        row = session.execute(
            select(NotebookCrdtState).where(
                NotebookCrdtState.notebook_id == fresh_notebook_with_blob
            )
        ).scalar_one()
    assert row.compacted_at is not None


async def test_compaction_executor_skips_active_hub(
    fresh_notebook_with_blob: str,
) -> None:
    """When a hub is open for the notebook, compaction skips it."""
    notebook_coedit_ws._HUBS[fresh_notebook_with_blob] = object()  # type: ignore[assignment]
    try:
        await _coedit_compaction_executor(
            job_run_id=0,
            user_info=_zero_user(),
            config={},
            uc_client=None,  # type: ignore[arg-type]
        )
        factory = app.state.session_factory
        with factory() as session:
            row = session.execute(
                select(NotebookCrdtState).where(
                    NotebookCrdtState.notebook_id == fresh_notebook_with_blob
                )
            ).scalar_one()
        # ``compacted_at`` stays None because the hub-skip path bailed.
        assert row.compacted_at is None
    finally:
        notebook_coedit_ws._HUBS.pop(fresh_notebook_with_blob, None)


async def test_compaction_executor_handles_failures_gracefully(
    fresh_notebook_with_blob: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception in compact() is logged and the loop continues."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated compact crash")

    monkeypatch.setattr(coedit_service, "compact", _boom)

    # Must not raise.
    await _coedit_compaction_executor(
        job_run_id=0,
        user_info=_zero_user(),
        config={},
        uc_client=None,  # type: ignore[arg-type]
    )
    # No assertion on row state — the point is that no exception escapes.


async def test_compaction_executor_registered_as_kind() -> None:
    """The default registry binds ``coedit_compaction`` to the executor."""
    from pointlessql.services.scheduler.registry import build_default_registry

    registry = build_default_registry()
    executor = registry.get("coedit_compaction")
    assert executor is _coedit_compaction_executor
    # Sanity unused-import guard so ``os`` doesn't get pruned by lint.
    assert os.path.sep
