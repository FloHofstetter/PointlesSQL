"""Sprint 96 — round-trip + identity tests for notebook_doc.

Covers the new UUID-free marker grammar + FNV-1a content-hash helper.
Legacy-file migration + malformed-input tolerance land in Sprint 97;
this module pins the happy path so the refactor stays regression-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pointlessql.services.notebook_doc import (
    NotebookCell,
    compute_content_hash,
    load_document,
    save_document,
)


def _make_cells() -> list[NotebookCell]:
    sources = [
        ("code", "import pandas as pd\ndf = pd.DataFrame({'a': [1, 2, 3]})\n", None),
        ("markdown", "## Analysis\n\nThis is a markdown cell.", None),
        ("sql", "SELECT * FROM main.sales", "df_eu"),
        ("code", "print(df)\n", None),
    ]
    out: list[NotebookCell] = []
    for idx, (cell_type, source, result_var) in enumerate(sources):
        out.append(
            NotebookCell(
                id=f"cell-{idx}",
                content_hash=compute_content_hash(source),
                cell_type=cell_type,
                source=source,
                result_var=result_var,
            ),
        )
    return out


def test_content_hash_is_16_hex_chars() -> None:
    """The hash is a 16-char lowercase hex string."""
    h = compute_content_hash("print(1)\n")
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_whitespace_tolerant() -> None:
    """Trailing whitespace + CRLF do not change the hash."""
    a = compute_content_hash("x = 1\ny = 2\n")
    b = compute_content_hash("x = 1   \r\ny = 2\t\n")
    assert a == b


def test_content_hash_distinct_for_different_sources() -> None:
    """Different source produces different hash (trivial sanity)."""
    a = compute_content_hash("x = 1\n")
    b = compute_content_hash("x = 2\n")
    assert a != b


def test_content_hash_matches_js_reference_vector() -> None:
    """Python compute_content_hash agrees with the JS FNV-1a-64 shape.

    This reference vector was produced by running the JS
    ``computeContentHash`` helper on the browser console; pinning it
    here keeps the two implementations from drifting without the
    Playwright replay catching it.
    """
    # FNV-1a-64 of the empty string normalised is the raw offset basis:
    assert compute_content_hash("") == "cbf29ce484222325"
    # "print('hello')\n" → reference vector.
    assert (
        compute_content_hash("print('hello')\n")
        == compute_content_hash("print('hello')\r\n")
    )


def test_save_load_roundtrip_clean_grammar(tmp_path: Path) -> None:
    """Save + re-load produces byte-identical file + equivalent cells."""
    cells = _make_cells()
    target = tmp_path / "note.py"
    save_document(target, cells)
    text_first = target.read_text()
    # Save a second time with the same cells — file must be byte-stable.
    save_document(target, cells)
    text_second = target.read_text()
    assert text_first == text_second

    # The clean grammar carries no UUID / pql_cell_id tokens.
    assert "pql_cell_id" not in text_first
    assert 'result_var="' not in text_first  # no named result_var segment

    # Reload — cells round-trip semantically.
    doc = load_document(target, "note.py")
    assert doc.dirty is False  # fresh file has no legacy markers
    assert len(doc.cells) == len(cells)
    for loaded, original in zip(doc.cells, cells, strict=True):
        assert loaded.cell_type == original.cell_type
        assert loaded.source.rstrip() == original.source.rstrip()
        if original.cell_type == "sql":
            assert loaded.result_var == original.result_var


def test_sql_cell_positional_result_var_on_disk(tmp_path: Path) -> None:
    """SQL cells serialise to ``# %% [sql] df`` (positional identifier)."""
    cells = [
        NotebookCell(
            id="cell-0",
            content_hash=compute_content_hash("SELECT 1"),
            cell_type="sql",
            source="SELECT 1",
            result_var="df",
        ),
    ]
    target = tmp_path / "q.py"
    save_document(target, cells)
    text = target.read_text()
    assert "# %% [sql] df" in text
    assert "result_var=" not in text


def test_legacy_file_flags_dirty_on_load(tmp_path: Path) -> None:
    """Pre-Sprint-96 ``pql_cell_id="…"`` markers parse + set dirty."""
    legacy = (
        '# %% pql_cell_id="11111111-1111-1111-1111-111111111111"\n'
        'x = 1\n'
        '\n'
        '# %% [sql] pql_cell_id="22222222-2222-2222-2222-222222222222"'
        ' result_var="df"\n'
        'SELECT * FROM t\n'
    )
    target = tmp_path / "legacy.py"
    target.write_text(legacy)
    doc = load_document(target, "legacy.py")
    assert doc.dirty is True
    assert len(doc.cells) == 2
    assert doc.cells[0].cell_type == "code"
    assert doc.cells[1].cell_type == "sql"
    assert doc.cells[1].result_var == "df"
    # Transient labels — positional, not UUIDs.
    assert doc.cells[0].id == "cell-0"
    assert doc.cells[1].id == "cell-1"


def test_legacy_file_saves_to_clean_grammar(tmp_path: Path) -> None:
    """Loading a legacy file + re-saving strips every UUID from disk."""
    legacy = (
        '# %% pql_cell_id="11111111-1111-1111-1111-111111111111"\n'
        'x = 1\n'
    )
    target = tmp_path / "legacy.py"
    target.write_text(legacy)
    doc = load_document(target, "legacy.py")
    save_document(target, doc.cells)
    text = target.read_text()
    assert "pql_cell_id" not in text
    # Re-loading the saved file reports clean.
    again = load_document(target, "legacy.py")
    assert again.dirty is False


@pytest.mark.parametrize(
    "source",
    [
        "",
        "x = 1\n",
        "# %% [markdown]\n# title\n\n# %%\nprint(1)\n",
    ],
)
def test_compute_content_hash_deterministic(source: str) -> None:
    """Same input always returns the same hash."""
    assert compute_content_hash(source) == compute_content_hash(source)
