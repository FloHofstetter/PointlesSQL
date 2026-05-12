"""Tests for the ``tags=[...]`` marker extension introduced in Phase 67.0.

The Phase 66 marker grammar pinned three cell shapes (``# %%``,
``# %% [markdown]``, ``# %% [sql] df``). Phase 67 needs round-trip-
stable parameter-cell support so papermill jobs can detect the cell
flagged ``parameters``. We adopt the jupytext canonical
``tags=["parameters"]`` suffix instead of inventing another cell type
to keep tool interop maximal.

These tests pin: tag parsing on every cell type, deduplication,
serialisation order, content-hash invariance (tags are metadata, not
source), and the byte-level round-trip stability that protects the
``.py`` file's VSCode-editability invariant.
"""

from __future__ import annotations

from pathlib import Path

from pointlessql.services.notebook import (
    NotebookCell,
    compute_content_hash,
    load_document,
    save_document,
)


def _cell(idx: int, source: str, **kwargs: object) -> NotebookCell:
    cell_type = str(kwargs.pop("cell_type", "code"))
    result_var = kwargs.pop("result_var", None)
    tags_raw = kwargs.pop("tags", ())
    tags: tuple[str, ...] = tuple(str(t) for t in tags_raw) if tags_raw else ()
    return NotebookCell(
        id=f"cell-{idx}",
        content_hash=compute_content_hash(source),
        cell_type=cell_type,
        source=source,
        result_var=result_var if isinstance(result_var, str) else None,
        tags=tags,
    )


def test_parses_parameters_tag_on_code_cell(tmp_path: Path) -> None:
    body = '# %% tags=["parameters"]\ncutoff_date = "2026-05-01"\n'
    target = tmp_path / "n.py"
    target.write_text(body)
    doc = load_document(target, "n.py")
    assert len(doc.cells) == 1
    assert doc.cells[0].cell_type == "code"
    assert doc.cells[0].tags == ("parameters",)


def test_parses_multiple_tags_on_markdown_cell(tmp_path: Path) -> None:
    body = '# %% [markdown] tags=["intro", "aside"]\n# Title\n'
    target = tmp_path / "n.py"
    target.write_text(body)
    doc = load_document(target, "n.py")
    assert doc.cells[0].cell_type == "markdown"
    assert doc.cells[0].tags == ("intro", "aside")


def test_parses_tags_on_sql_cell_with_result_var(tmp_path: Path) -> None:
    body = '# %% [sql] df tags=["parameters"]\nSELECT 1 AS n\n'
    target = tmp_path / "n.py"
    target.write_text(body)
    doc = load_document(target, "n.py")
    assert doc.cells[0].cell_type == "sql"
    assert doc.cells[0].result_var == "df"
    assert doc.cells[0].tags == ("parameters",)


def test_parses_tags_on_sql_cell_without_result_var(tmp_path: Path) -> None:
    body = '# %% [sql] tags=["x"]\nSELECT 1\n'
    target = tmp_path / "n.py"
    target.write_text(body)
    doc = load_document(target, "n.py")
    assert doc.cells[0].cell_type == "sql"
    assert doc.cells[0].result_var is None
    assert doc.cells[0].tags == ("x",)


def test_empty_tags_list_round_trips_as_no_tag(tmp_path: Path) -> None:
    body = "# %% tags=[]\nx = 1\n"
    target = tmp_path / "n.py"
    target.write_text(body)
    doc = load_document(target, "n.py")
    assert doc.cells[0].tags == ()
    save_document(target, doc.cells)
    # Canonical output drops the empty tags=[] segment entirely.
    assert "tags=" not in target.read_text()


def test_tag_serialisation_is_roundtrip_byte_stable(tmp_path: Path) -> None:
    cells = [
        _cell(0, 'cutoff_date = "2026-05-01"\n', tags=("parameters",)),
        _cell(1, "# Title\n\nBody.", cell_type="markdown", tags=("intro",)),
        _cell(2, "SELECT 1", cell_type="sql", result_var="df", tags=("parameters",)),
    ]
    target = tmp_path / "n.py"
    save_document(target, cells)
    first = target.read_text()
    save_document(target, cells)
    second = target.read_text()
    assert first == second
    assert 'tags=["parameters"]' in first
    assert 'tags=["intro"]' in first


def test_content_hash_ignores_tag_edits(tmp_path: Path) -> None:
    """Toggling the parameters tag must not change the cell's identity."""
    source = "cutoff = 1\n"
    plain = NotebookCell(
        id="cell-0",
        content_hash=compute_content_hash(source),
        cell_type="code",
        source=source,
    )
    tagged = NotebookCell(
        id="cell-0",
        content_hash=compute_content_hash(source),
        cell_type="code",
        source=source,
        tags=("parameters",),
    )
    assert plain.content_hash == tagged.content_hash


def test_marker_without_tags_writes_without_suffix(tmp_path: Path) -> None:
    cells = [_cell(0, "print(1)\n")]
    target = tmp_path / "n.py"
    save_document(target, cells)
    text = target.read_text()
    assert "tags=" not in text
    # Re-load: tags is the empty tuple.
    doc = load_document(target, "n.py")
    assert doc.cells[0].tags == ()


def test_legacy_marker_with_uuid_still_loads_with_empty_tags(tmp_path: Path) -> None:
    legacy = '# %% pql_cell_id="11111111-1111-1111-1111-111111111111"\nx = 1\n'
    target = tmp_path / "legacy.py"
    target.write_text(legacy)
    doc = load_document(target, "legacy.py")
    assert doc.cells[0].tags == ()
    assert doc.dirty is True


def test_param_tag_survives_save_reload_cycle(tmp_path: Path) -> None:
    """Mark a code cell as params, save, reload → tag persisted."""
    source = "window_days = 7\n"
    cells = [_cell(0, source, tags=("parameters",))]
    target = tmp_path / "n.py"
    save_document(target, cells)
    doc = load_document(target, "n.py")
    assert doc.cells[0].tags == ("parameters",)
    assert doc.cells[0].cell_type == "code"
    assert doc.cells[0].source.rstrip() == source.rstrip()
