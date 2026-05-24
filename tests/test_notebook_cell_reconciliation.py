"""save-path cell-identity reconciliation.

Stress-tests the three-pass reconciler against the eight scenarios
called out in the Phase-95 plan plus a reformat-all-cells corner.
Each test seeds an existing ``notebook_cells`` snapshot, runs one
``reconcile`` call, and asserts which UUIDs survived / shifted /
soft-deleted.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.notebook import Notebook, NotebookCellIdentity
from pointlessql.services.notebook import cell_reconciliation
from pointlessql.services.notebook._doc import compute_content_hash


@pytest.fixture
def workspace_notebook() -> Iterator[tuple[int, str]]:
    """Yield ``(workspace_id, notebook_uuid)`` for one fresh notebook."""
    factory = app.state.session_factory
    workspace_id = 1
    notebook_id = str(uuid.uuid4())
    with factory() as session:
        session.add(
            Notebook(
                id=notebook_id,
                workspace_id=workspace_id,
                file_path=f"recon_{notebook_id[:8]}.py",
            )
        )
        session.commit()
    yield workspace_id, notebook_id
    with factory() as session:
        for row in session.execute(
            select(NotebookCellIdentity).where(NotebookCellIdentity.notebook_id == notebook_id)
        ).scalars():
            session.delete(row)
        session.execute(select(Notebook).where(Notebook.id == notebook_id)).scalar_one()
        session.delete(
            session.execute(select(Notebook).where(Notebook.id == notebook_id)).scalar_one()
        )
        session.commit()


def _inp(source: str) -> cell_reconciliation.ReconcileInput:
    """Build a reconcile input from source text alone."""
    return cell_reconciliation.ReconcileInput(
        content_hash=compute_content_hash(source), source=source
    )


def _live(notebook_id: str) -> list[NotebookCellIdentity]:
    """Return live ``notebook_cells`` rows for *notebook_id* ordered by ordinal."""
    factory = app.state.session_factory
    with factory() as session:
        return list(
            session.execute(
                select(NotebookCellIdentity)
                .where(
                    NotebookCellIdentity.notebook_id == notebook_id,
                    NotebookCellIdentity.removed_at.is_(None),
                )
                .order_by(NotebookCellIdentity.ordinal_hint)
            ).scalars()
        )


def _all(notebook_id: str) -> list[NotebookCellIdentity]:
    """Return every row (incl. soft-deleted) for *notebook_id*."""
    factory = app.state.session_factory
    with factory() as session:
        return list(
            session.execute(
                select(NotebookCellIdentity).where(NotebookCellIdentity.notebook_id == notebook_id)
            ).scalars()
        )


def _seed(
    workspace_id: int,
    notebook_id: str,
    sources: list[str],
) -> list[cell_reconciliation.ReconcileResult]:
    """First save — every cell gets a fresh UUID."""
    factory = app.state.session_factory
    with factory() as session:
        results = cell_reconciliation.reconcile(
            session,
            workspace_id=workspace_id,
            notebook_id=notebook_id,
            new_cells=[_inp(s) for s in sources],
        )
        session.commit()
    return results


def _run(
    workspace_id: int,
    notebook_id: str,
    sources: list[str],
) -> list[cell_reconciliation.ReconcileResult]:
    """Second-or-later save — exercise the matcher passes."""
    factory = app.state.session_factory
    with factory() as session:
        results = cell_reconciliation.reconcile(
            session,
            workspace_id=workspace_id,
            notebook_id=notebook_id,
            new_cells=[_inp(s) for s in sources],
        )
        session.commit()
    return results


def test_scenario_a_pure_edit_at_position_keeps_uuid(workspace_notebook):
    """(a) Pure edit at position 3 — UUID survives, hash updates."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = [
        "a = 1\nb = 2",
        "x = 'cell-one'\nprint(x)",
        "y = 'cell-two'\nprint(y)",
        "z = 'cell-three'\nprint(z)",
    ]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    target_uuid = initial[3].cell_id

    # Edit cell 3 — same position, different source.
    edited = seed_sources.copy()
    edited[3] = "z = 'cell-three EDITED'\nprint(z)\nprint('more')"
    results = _run(workspace_id, notebook_id, edited)

    assert results[3].cell_id == target_uuid, "UUID must survive same-position edit"
    assert results[3].was_inserted is False
    assert {r.cell_id for r in initial} == {r.cell_id for r in results}


def test_scenario_b_insert_at_top_preserves_all_uuids(workspace_notebook):
    """(b) Insert new cell at top — every old UUID shifts down 1, none mint."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["one", "two", "three"]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    original_uuids = [r.cell_id for r in initial]

    new_sources = ["BRAND_NEW_TOP_CELL", "one", "two", "three"]
    results = _run(workspace_id, notebook_id, new_sources)

    # The brand-new cell gets a fresh UUID; the rest match by exact-hash.
    assert results[0].was_inserted is True
    assert results[1].cell_id == original_uuids[0]
    assert results[2].cell_id == original_uuids[1]
    assert results[3].cell_id == original_uuids[2]


def test_scenario_c_delete_middle_cell_soft_deletes_only_that_uuid(
    workspace_notebook,
):
    """(c) Delete middle cell — others survive, the deleted UUID is tombstoned."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["alpha", "beta", "gamma", "delta"]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    deleted_uuid = initial[1].cell_id

    new_sources = ["alpha", "gamma", "delta"]
    results = _run(workspace_id, notebook_id, new_sources)

    surviving = [r.cell_id for r in results]
    assert deleted_uuid not in surviving
    assert initial[0].cell_id in surviving
    assert initial[2].cell_id in surviving
    assert initial[3].cell_id in surviving
    # Soft-deleted row exists.
    all_rows = _all(notebook_id)
    removed = [r for r in all_rows if r.removed_at is not None]
    assert len(removed) == 1
    assert removed[0].id == deleted_uuid


def test_scenario_d_adjacent_swap_preserves_both(workspace_notebook):
    """(d) Adjacent swap — both UUIDs survive via exact-hash matching."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["first", "second", "third"]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    uuid_first = initial[0].cell_id
    uuid_second = initial[1].cell_id

    new_sources = ["second", "first", "third"]
    results = _run(workspace_id, notebook_id, new_sources)

    assert results[0].cell_id == uuid_second
    assert results[1].cell_id == uuid_first


def test_scenario_e_identical_source_pair_edit_keeps_correct_uuid(
    workspace_notebook,
):
    """(e) Two cells share source; edit the second — first keeps its UUID."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["filler", "shared = 1", "shared = 1", "tail"]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    uuid_first_shared = initial[1].cell_id
    uuid_second_shared = initial[2].cell_id

    # Edit the second shared cell at position 2.
    new_sources = ["filler", "shared = 1", "shared = 1\nshared *= 2", "tail"]
    results = _run(workspace_id, notebook_id, new_sources)

    # Pass 1 exact-hash matches the unchanged first shared cell.
    assert results[1].cell_id == uuid_first_shared
    # Pass 2 same-position similarity > 0.5 (both share "shared = 1" prefix).
    assert results[2].cell_id == uuid_second_shared


def test_scenario_f_paste_duplicate_inherits_no_uuid(workspace_notebook):
    """(f) Paste duplicate of cell 0 as cell 5 — duplicate mints fresh UUID."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["zero", "one", "two", "three", "four"]
    initial = _seed(workspace_id, notebook_id, seed_sources)

    # User pastes a copy of "zero" at position 5.
    new_sources = ["zero", "one", "two", "three", "four", "zero"]
    results = _run(workspace_id, notebook_id, new_sources)

    # The pasted duplicate at position 5 cannot match by exact hash (cell 0
    # already claimed the only "zero" row), and pass 2 has no ordinal-5 row
    # to fall back on → fresh UUID.
    assert results[0].cell_id == initial[0].cell_id
    assert results[5].was_inserted is True
    assert results[5].cell_id not in {r.cell_id for r in initial}


def test_scenario_g_cut_edit_paste_elsewhere_loses_identity(workspace_notebook):
    """(g) Cut + edit + paste elsewhere — identity is intentionally lost.

    Documented limitation: without on-disk cell-UUIDs there is no signal
    to distinguish "move + edit" from "delete + insert at different
    position".  Test pins the behaviour so we notice if it ever
    changes.
    """
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["a", "b", "c", "d", "e", "f", "g", "h"]
    _seed(workspace_id, notebook_id, seed_sources)

    # Remove "d" from position 3; place edited "d_EDITED_LOTS" at position 7.
    new_sources = ["a", "b", "c", "e", "f", "g", "h", "d_EDITED_LOTS_OF_NEW_CONTENT"]
    results = _run(workspace_id, notebook_id, new_sources)

    # Position 7 is *new* per the algorithm: no existing ordinal-7 row at
    # save time after pass-1 absorbs the others, and similarity to the
    # ordinal-7 candidate ("h") is too low.  So position 7 mints fresh.
    assert results[7].was_inserted is True


def test_scenario_h_delete_and_insert_same_position_does_not_steal_uuid(
    workspace_notebook,
):
    """(h) Delete cell 2 + insert different cell at 2 — UUID is NOT stolen."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = [
        "import pandas as pd",
        "df = pd.read_csv('x.csv')",
        "df = df[df.value > 10]\nprint(df.shape)",
        "df.to_parquet('out.pq')",
    ]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    cell2_uuid = initial[2].cell_id

    # User deletes cell 2 and types an unrelated new cell at position 2.
    new_sources = [
        "import pandas as pd",
        "df = pd.read_csv('x.csv')",
        "# completely different — print logo banner\nprint('=' * 80)\nprint('LOGO')",
        "df.to_parquet('out.pq')",
    ]
    results = _run(workspace_id, notebook_id, new_sources)

    # Crucially: the new cell at position 2 does NOT inherit cell2_uuid;
    # similarity gate rejects the ordinal fallback.
    assert results[2].cell_id != cell2_uuid
    assert results[2].was_inserted is True
    # Old cell 2 was soft-deleted.
    all_rows = _all(notebook_id)
    removed = {r.id for r in all_rows if r.removed_at is not None}
    assert cell2_uuid in removed


def test_reformat_all_cells_preserves_uuids_when_no_reorder(workspace_notebook):
    """Reformat-all (e.g. ruff) — every hash changes; UUIDs survive at same position."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = [
        "import os\nimport sys\nprint(os.getcwd())",
        "def hello():\n    print('hi')",
        "x = [1,2,3]\ny = sum(x)",
    ]
    initial = _seed(workspace_id, notebook_id, seed_sources)

    # Reformat — same logical content, different whitespace/quotes.
    new_sources = [
        "import os\nimport sys\n\nprint(os.getcwd())",
        "def hello() -> None:\n    print('hi')",
        "x = [1, 2, 3]\ny = sum(x)",
    ]
    results = _run(workspace_id, notebook_id, new_sources)

    # Each reformat keeps similarity well above 0.5 → UUIDs survive.
    assert results[0].cell_id == initial[0].cell_id
    assert results[1].cell_id == initial[1].cell_id
    assert results[2].cell_id == initial[2].cell_id


def test_no_op_save_keeps_everything_stable(workspace_notebook):
    """Saving the same cell list twice is a no-op for identities."""
    workspace_id, notebook_id = workspace_notebook
    seed_sources = ["one", "two", "three"]
    initial = _seed(workspace_id, notebook_id, seed_sources)
    second = _run(workspace_id, notebook_id, seed_sources)
    assert [r.cell_id for r in initial] == [r.cell_id for r in second]
    assert all(r.was_inserted is False for r in second)


def test_empty_save_soft_deletes_all(workspace_notebook):
    """Saving zero cells soft-deletes every live row for that notebook."""
    workspace_id, notebook_id = workspace_notebook
    _seed(workspace_id, notebook_id, ["a", "b", "c"])
    results = _run(workspace_id, notebook_id, [])
    assert results == []
    live = _live(notebook_id)
    assert live == []
    assert len(_all(notebook_id)) == 3
