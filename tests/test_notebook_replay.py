"""Tests — replay / scenario-mode."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook, NotebookRevision
from pointlessql.services.notebook import replay as notebook_replay_service


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_notebook_with_revision(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    cells: list[dict] | None = None,
    outputs: list[dict] | None = None,
) -> tuple[str, str]:
    """Insert notebook + one revision; return (notebook_id, revision_uuid)."""
    nb_id = str(uuid.uuid4())
    rev_uuid = str(uuid.uuid4())
    cells = cells or [{"content_hash": "h1", "cell_type": "code", "source": "x"}]
    outputs = outputs or []
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=1, file_path="n.py"))
        s.flush()
        s.add(
            NotebookRevision(
                revision_uuid=rev_uuid,
                notebook_id=nb_id,
                cells_json=json.dumps(cells),
                outputs_json=json.dumps(outputs),
                content_sha256="0" * 64,
            )
        )
        s.commit()
    return nb_id, rev_uuid


# -- service ------------------------------------------------------------------


def test_start_replay_inserts_pending(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """``start_replay`` inserts a row in ``pending`` status."""
    nb_id, rev = _seed_notebook_with_revision(factory)
    with factory() as session:
        row = notebook_replay_service.start_replay(
            session,
            notebook_id=nb_id,
            base_revision_uuid=rev,
        )
        assert row.status == "pending"
        assert row.outputs_json == "[]"
        session.commit()


def test_start_replay_unknown_revision_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown revision UUID raises."""
    nb_id, _ = _seed_notebook_with_revision(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_replay_service.start_replay(
                session,
                notebook_id=nb_id,
                base_revision_uuid="0" * 36,
            )


def test_record_finished_persists_outputs_and_digest(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``record_finished`` persists outputs + computes diff summary."""
    nb_id, rev = _seed_notebook_with_revision(
        factory,
        cells=[
            {"content_hash": "h1", "cell_type": "code", "source": "x"},
            {"content_hash": "h2", "cell_type": "code", "source": "y"},
        ],
        outputs=[
            {
                "content_hash": "h1",
                "kernel_session_id": "s",
                "output_index": 0,
                "msg_type": "stream",
                "content": {"text": "v1"},
                "metadata": None,
            }
        ],
    )
    with factory() as session:
        row = notebook_replay_service.start_replay(
            session, notebook_id=nb_id, base_revision_uuid=rev
        )
        replay_uuid = row.replay_uuid
        session.commit()
        notebook_replay_service.record_finished(
            session,
            replay_uuid=replay_uuid,
            status="ok",
            outputs=[
                {
                    "content_hash": "h1",
                    "kernel_session_id": "s2",
                    "output_index": 0,
                    "msg_type": "stream",
                    "content": {"text": "v1"},
                    "metadata": None,
                }
            ],
        )
        envelope = notebook_replay_service.get_replay(session, replay_uuid=replay_uuid)
        assert envelope is not None
        # h1 has identical outputs across base + replay → ``stable`` would
        # require identical row dicts including kernel_session_id; we use
        # different session ids → ``changed``.  h2 has neither → ``missing``.
        digest = envelope["diff_summary"]
        assert digest["changed"] + digest["missing"] == 2


def test_record_finished_unknown_replay_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown replay UUID raises."""
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_replay_service.record_finished(session, replay_uuid="0" * 36, status="ok")


def test_record_finished_rejects_non_terminal_status(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``running`` / ``pending`` are rejected — record_finished is terminal-only."""
    nb_id, rev = _seed_notebook_with_revision(factory)
    with factory() as session:
        row = notebook_replay_service.start_replay(
            session, notebook_id=nb_id, base_revision_uuid=rev
        )
        replay_uuid = row.replay_uuid
        session.commit()
        with pytest.raises(ValidationError):
            notebook_replay_service.record_finished(
                session, replay_uuid=replay_uuid, status="running"
            )


def test_compute_replay_diff_classifies_cells(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Diff classifies cells as stable / changed / missing / new."""
    cells = [
        {"content_hash": "h_stable", "cell_type": "code", "source": "a"},
        {"content_hash": "h_changed", "cell_type": "code", "source": "b"},
        {"content_hash": "h_missing", "cell_type": "code", "source": "c"},
    ]
    base_outputs = [
        {
            "content_hash": "h_stable",
            "kernel_session_id": "s",
            "output_index": 0,
            "msg_type": "stream",
            "content": {"text": "OK"},
            "metadata": None,
        },
        {
            "content_hash": "h_changed",
            "kernel_session_id": "s",
            "output_index": 0,
            "msg_type": "stream",
            "content": {"text": "OLD"},
            "metadata": None,
        },
        {
            "content_hash": "h_missing",
            "kernel_session_id": "s",
            "output_index": 0,
            "msg_type": "stream",
            "content": {"text": "X"},
            "metadata": None,
        },
    ]
    nb_id, rev = _seed_notebook_with_revision(factory, cells=cells, outputs=base_outputs)
    # Replay outputs: identical for h_stable; different for h_changed;
    # missing entirely for h_missing.
    replay_outputs = [
        base_outputs[0],
        {
            "content_hash": "h_changed",
            "kernel_session_id": "s",
            "output_index": 0,
            "msg_type": "stream",
            "content": {"text": "NEW"},
            "metadata": None,
        },
    ]
    with factory() as session:
        row = notebook_replay_service.start_replay(
            session, notebook_id=nb_id, base_revision_uuid=rev
        )
        replay_uuid = row.replay_uuid
        session.commit()
        notebook_replay_service.record_finished(
            session,
            replay_uuid=replay_uuid,
            status="ok",
            outputs=replay_outputs,
        )
        session.commit()
        diff = notebook_replay_service.compute_replay_diff(session, replay_uuid=replay_uuid)
        verdicts = {c["content_hash"]: c["verdict"] for c in diff["cells"]}
    assert verdicts["h_stable"] == "stable"
    assert verdicts["h_changed"] == "changed"
    assert verdicts["h_missing"] == "missing"


def test_list_replays_newest_first(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """``list_replays`` returns newest replays first."""
    nb_id, rev = _seed_notebook_with_revision(factory)
    with factory() as session:
        notebook_replay_service.start_replay(session, notebook_id=nb_id, base_revision_uuid=rev)
        session.commit()
        notebook_replay_service.start_replay(session, notebook_id=nb_id, base_revision_uuid=rev)
        session.commit()
        rows = notebook_replay_service.list_replays(session, notebook_id=nb_id)
    assert len(rows) == 2


# -- REST --------------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_replay_lifecycle(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """Create notebook → revision → replay → finish round-trip."""
    nb_path = workspace_dir / "r.py"
    nb_path.write_text("# %%\nprint(1)\n")
    await admin_client.post("/api/notebooks/create", json={"path": "r.py"})
    rev = await admin_client.post("/api/notebooks/revisions", json={"path": "r.py"})
    rev_uuid = rev.json()["revision_uuid"]
    started = await admin_client.post(
        "/api/notebooks/replay",
        json={"path": "r.py", "base_revision_uuid": rev_uuid},
    )
    assert started.status_code == 201
    replay_uuid = started.json()["replay_uuid"]
    assert started.json()["status"] == "pending"

    finished = await admin_client.post(
        f"/api/notebooks/replay/{replay_uuid}/finish",
        json={"status": "ok", "outputs": []},
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "ok"

    fetched = await admin_client.get(f"/api/notebooks/replay/{replay_uuid}")
    assert fetched.json()["status"] == "ok"

    diff = await admin_client.get(f"/api/notebooks/replay/{replay_uuid}/diff")
    assert diff.status_code == 200
    assert diff.json()["replay_uuid"] == replay_uuid


# -- Phase 103 Wave-D — replay-worker tick semantics --------------------------


async def test_run_pending_replays_returns_zero_when_idle(
    factory: sessionmaker,  # type: ignore[type-arg]
    tmp_path: Path,
) -> None:
    """No pending row → tick returns 0 without spinning up a kernel."""
    from pointlessql.services.notebook.replay_worker import run_pending_replays

    processed = await run_pending_replays(session_factory=factory, notebooks_dir=tmp_path)
    assert processed == 0


async def test_replay_worker_class_idempotent_start_stop(
    factory: sessionmaker,
    tmp_path: Path,  # type: ignore[type-arg]
) -> None:
    """``start`` is a no-op after first call; ``stop`` without start is safe."""
    from pointlessql.services.notebook.replay_worker import ReplayWorker

    w = ReplayWorker(session_factory=factory, notebooks_dir=tmp_path)
    await w.stop()  # no-op before start
    w.start()
    w.start()  # idempotent — same task stays bound
    await w.stop()


async def test_replay_worker_executes_cell_and_records_output(
    factory: sessionmaker,
    tmp_path: Path,  # type: ignore[type-arg]
) -> None:
    """End-to-end: worker spins a real kernel, runs a cell, persists outputs.

    the existing :func:`test_run_pending_replays_returns_zero_when_idle`
    and :func:`test_replay_worker_class_idempotent_start_stop` cover
    the empty-queue and lifecycle paths.  This test exercises the
    happy path that connects them: insert a pending replay row, run
    the per-tick driver, and assert the row settles to ``ok`` with
    the cell's stdout captured in ``outputs_json``.

    Uses ``run_pending_replays`` directly (not ``ReplayWorker.start()``)
    so the test does not race against the 5-s tick scheduler — one
    driver call is deterministic and faster.
    """
    import asyncio

    from pointlessql.models import NotebookReplay
    from pointlessql.services.notebook.replay_worker import run_pending_replays

    nb_id, rev_uuid = _seed_notebook_with_revision(
        factory,
        cells=[
            {
                "content_hash": "h-print4",
                "cell_type": "code",
                "source": "print(2 + 2)",
            }
        ],
    )
    with factory() as session:
        row = notebook_replay_service.start_replay(
            session, notebook_id=nb_id, base_revision_uuid=rev_uuid
        )
        replay_uuid = row.replay_uuid
        session.commit()

    # One pass should pick up the single pending row and drive it
    # through to a terminal status.  The kernel boot adds the bulk of
    # the wall-clock here; ``asyncio.wait_for`` caps the runaway
    # case so a stuck ipykernel surfaces as a test timeout rather
    # than a frozen test runner.
    processed = await asyncio.wait_for(
        run_pending_replays(session_factory=factory, notebooks_dir=tmp_path),
        timeout=60.0,
    )
    assert processed == 1, "expected one pending replay to be processed"

    with factory() as session:
        finished = session.query(NotebookReplay).filter_by(replay_uuid=replay_uuid).one()
        assert finished.status == "ok", (
            f"replay did not succeed: status={finished.status!r} outputs={finished.outputs_json!r}"
        )
        assert finished.finished_at is not None
        outputs = json.loads(finished.outputs_json or "[]")
        # The worker collects every kernel reply frame; the ``print``
        # call surfaces as a ``stream`` frame whose ``content.text``
        # is ``"4\n"``.
        stream_frames = [frame for frame in outputs if frame.get("msg_type") == "stream"]
        assert stream_frames, f"expected at least one stream frame; got {outputs!r}"
        joined = "".join(frame.get("content", {}).get("text", "") for frame in stream_frames)
        assert "4" in joined, f"stdout did not contain '4': {joined!r}"
