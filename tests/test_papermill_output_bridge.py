"""Tests for the Phase 67.6 papermill → notebook_outputs bridge.

The bridge runs at the end of :func:`_papermill_executor`, reads the
executed ``.ipynb`` written under ``runs/``, and persists one row per
cell-output to ``notebook_outputs`` keyed by ``kernel_session_id =
'job:<run_id>'``. The synthetic session-id prefix lets the editor's
persisted-output replay also surface job-run outputs without a
separate render path.
"""

from __future__ import annotations

import json
from pathlib import Path

import nbformat

from pointlessql.api.main import app
from pointlessql.services.scheduler.executors import _persist_papermill_outputs


def _make_executed_ipynb(target: Path, *, kernel: str = "python3") -> None:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "name": kernel,
        "display_name": "Python 3",
        "language": "python",
    }
    code = nbformat.v4.new_code_cell("print('hello')")
    code.outputs = [
        nbformat.v4.new_output(
            "stream",
            name="stdout",
            text="hello\n",
        ),
    ]
    nb.cells.append(code)
    code2 = nbformat.v4.new_code_cell("x = 42\nx")
    code2.outputs = [
        nbformat.v4.new_output(
            "execute_result",
            execution_count=1,
            data={"text/plain": "42"},
            metadata={},
        ),
    ]
    nb.cells.append(code2)
    nbformat.write(nb, str(target))


def test_persist_writes_one_row_per_output(tmp_path: Path) -> None:
    """Stream + execute_result outputs both land in notebook_outputs."""
    target = tmp_path / "out.ipynb"
    _make_executed_ipynb(target)
    _persist_papermill_outputs(target, "demo.py", 42, factory=app.state.session_factory)
    factory = app.state.session_factory
    from pointlessql.models import NotebookOutput

    with factory() as session:
        rows = list(
            session.scalars(
                # SQLAlchemy 2.0 select compat
                __import__("sqlalchemy").select(NotebookOutput).where(
                    NotebookOutput.file_path == "demo.py",
                    NotebookOutput.kernel_session_id == "job:42",
                ),
            ),
        )
    assert len(rows) == 2
    msg_types = {r.msg_type for r in rows}
    assert msg_types == {"stream", "execute_result"}


def test_persist_is_idempotent(tmp_path: Path) -> None:
    """Running the bridge twice replaces prior rows; no duplicates."""
    target = tmp_path / "out.ipynb"
    _make_executed_ipynb(target)
    _persist_papermill_outputs(target, "demo2.py", 43, factory=app.state.session_factory)
    _persist_papermill_outputs(target, "demo2.py", 43, factory=app.state.session_factory)
    factory = app.state.session_factory
    from sqlalchemy import select

    from pointlessql.models import NotebookOutput

    with factory() as session:
        rows = list(
            session.scalars(
                select(NotebookOutput).where(
                    NotebookOutput.file_path == "demo2.py",
                    NotebookOutput.kernel_session_id == "job:43",
                ),
            ),
        )
    assert len(rows) == 2


def test_persist_skips_markdown_cells(tmp_path: Path) -> None:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    md = nbformat.v4.new_markdown_cell("# Title")
    nb.cells.append(md)
    code = nbformat.v4.new_code_cell("print('ok')")
    code.outputs = [
        nbformat.v4.new_output("stream", name="stdout", text="ok\n"),
    ]
    nb.cells.append(code)
    target = tmp_path / "mixed.ipynb"
    nbformat.write(nb, str(target))
    _persist_papermill_outputs(target, "mixed.py", 44, factory=app.state.session_factory)
    factory = app.state.session_factory
    from sqlalchemy import select

    from pointlessql.models import NotebookOutput

    with factory() as session:
        rows = list(
            session.scalars(
                select(NotebookOutput).where(
                    NotebookOutput.kernel_session_id == "job:44"
                ),
            ),
        )
    assert len(rows) == 1
    assert rows[0].msg_type == "stream"


def test_persist_handles_missing_file(tmp_path: Path) -> None:
    """A missing ipynb path is a no-op (run failed before papermill wrote)."""
    target = tmp_path / "does_not_exist.ipynb"
    # Should not raise.
    _persist_papermill_outputs(target, "ghost.py", 99, factory=app.state.session_factory)


def test_persist_uses_content_hash_for_lookup(tmp_path: Path) -> None:
    """Row content_hash matches `_doc.compute_content_hash` for source."""
    from pointlessql.services.notebook._doc import compute_content_hash

    target = tmp_path / "out.ipynb"
    _make_executed_ipynb(target)
    _persist_papermill_outputs(target, "hash.py", 55, factory=app.state.session_factory)
    factory = app.state.session_factory
    from sqlalchemy import select

    from pointlessql.models import NotebookOutput

    expected_hash = compute_content_hash("print('hello')")
    with factory() as session:
        row = session.scalars(
            select(NotebookOutput).where(
                NotebookOutput.file_path == "hash.py",
                NotebookOutput.content_hash == expected_hash,
            ),
        ).first()
    assert row is not None
    bundle = json.loads(row.mime_bundle)
    assert bundle.get("name") == "stdout"
