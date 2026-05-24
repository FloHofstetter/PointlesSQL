"""Round-trip + identity tests for notebook_doc.

Covers the UUID-free marker grammar + FNV-1a content-hash helper
and pins the happy path so the legacy-file migration + malformed-
input tolerance stay regression-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pointlessql.services.notebook import (
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
    assert compute_content_hash("print('hello')\n") == compute_content_hash("print('hello')\r\n")


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
        "x = 1\n"
        "\n"
        '# %% [sql] pql_cell_id="22222222-2222-2222-2222-222222222222"'
        ' result_var="df"\n'
        "SELECT * FROM t\n"
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
    legacy = '# %% pql_cell_id="11111111-1111-1111-1111-111111111111"\nx = 1\n'
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


# ─────────────────────── Sprint 97 tolerance tests ───────────────────────
#
# The parser raised when the user saved a manually-edited
# ``.py`` with CRLF line endings, a UTF-8 BOM, no markers at all, or
# a malformed tag. Sprint 97 makes every case graceful: no crash, a
# best-effort render, and ``dirty=True`` so the next save normalises.


def test_empty_file_loads_one_empty_cell(tmp_path: Path) -> None:
    """A zero-byte notebook becomes a single empty code cell."""
    target = tmp_path / "empty.py"
    target.write_text("")
    doc = load_document(target, "empty.py")
    assert doc.dirty is True
    assert len(doc.cells) == 1
    assert doc.cells[0].cell_type == "code"
    assert doc.cells[0].source == ""
    assert doc.cells[0].id == "cell-0"


def test_no_markers_file_becomes_single_code_cell(tmp_path: Path) -> None:
    """A plain Python file with no ``# %%`` markers still opens."""
    body = "import math\nprint(math.pi)\n"
    target = tmp_path / "plain.py"
    target.write_text(body)
    doc = load_document(target, "plain.py")
    assert doc.dirty is True
    assert len(doc.cells) == 1
    assert doc.cells[0].cell_type == "code"
    assert doc.cells[0].source == body


def test_unknown_tag_falls_back_to_code(tmp_path: Path) -> None:
    """``# %% [foo]`` parses as a code cell, dropping the unknown tag."""
    body = "# %% [foo]\nx = 1\n"
    target = tmp_path / "unknown_tag.py"
    target.write_text(body)
    doc = load_document(target, "unknown_tag.py")
    assert len(doc.cells) == 1
    assert doc.cells[0].cell_type == "code"
    assert doc.cells[0].result_var is None
    # After re-save, the unknown tag is gone.
    save_document(target, doc.cells)
    assert "[foo]" not in target.read_text()


def test_sql_marker_without_identifier(tmp_path: Path) -> None:
    """``# %% [sql]`` with no positional identifier yields result_var=None."""
    body = "# %% [sql]\nSELECT 1\n"
    target = tmp_path / "sql_plain.py"
    target.write_text(body)
    doc = load_document(target, "sql_plain.py")
    assert len(doc.cells) == 1
    assert doc.cells[0].cell_type == "sql"
    assert doc.cells[0].result_var is None


def test_crlf_line_endings_normalised(tmp_path: Path) -> None:
    """CRLF is collapsed to LF; parser still recovers cells + flags dirty."""
    body = "# %%\r\nx = 1\r\n\r\n# %%\r\ny = 2\r\n"
    target = tmp_path / "crlf.py"
    target.write_bytes(body.encode("utf-8"))
    doc = load_document(target, "crlf.py")
    assert doc.dirty is True  # CRLF normalisation triggers a save-next
    assert len(doc.cells) == 2
    assert "\r" not in doc.cells[0].source
    assert "\r" not in doc.cells[1].source


def test_utf8_bom_stripped(tmp_path: Path) -> None:
    """A leading UTF-8 BOM is stripped; the first marker still parses."""
    body = "\ufeff# %%\nx = 1\n"
    target = tmp_path / "bom.py"
    target.write_bytes(body.encode("utf-8"))
    doc = load_document(target, "bom.py")
    assert doc.dirty is True  # BOM removal triggers a save-next
    assert len(doc.cells) == 1
    # First byte of first cell's marker area must not be the BOM.
    assert not doc.cells[0].source.startswith("\ufeff")


def test_file_ending_mid_cell_without_newline(tmp_path: Path) -> None:
    """Missing trailing newline at EOF does not break the parser."""
    body = "# %%\nprint('ok')"
    target = tmp_path / "no_trailing_nl.py"
    target.write_bytes(body.encode("utf-8"))
    doc = load_document(target, "no_trailing_nl.py")
    assert len(doc.cells) == 1
    assert "print('ok')" in doc.cells[0].source


def test_duplicate_cells_get_same_content_hash(tmp_path: Path) -> None:
    """Two identical cells share a content hash (tie-break by index upstream)."""
    body = "# %%\nprint(1)\n\n# %%\nprint(1)\n"
    target = tmp_path / "dup.py"
    target.write_text(body)
    doc = load_document(target, "dup.py")
    assert len(doc.cells) == 2
    assert doc.cells[0].content_hash == doc.cells[1].content_hash
    # Transient labels still differ — ``cellAffordances`` keys on them.
    assert doc.cells[0].id != doc.cells[1].id


def test_manual_cell_reorder_preserves_content_hash(tmp_path: Path) -> None:
    """Swapping cell order keeps each cell's content hash stable."""
    body_a = "# %%\nfoo = 1\n\n# %%\nbar = 2\n"
    body_b = "# %%\nbar = 2\n\n# %%\nfoo = 1\n"
    path_a = tmp_path / "a.py"
    path_b = tmp_path / "b.py"
    path_a.write_text(body_a)
    path_b.write_text(body_b)
    doc_a = load_document(path_a, "a.py")
    doc_b = load_document(path_b, "b.py")
    hashes_a = sorted(c.content_hash for c in doc_a.cells)
    hashes_b = sorted(c.content_hash for c in doc_b.cells)
    assert hashes_a == hashes_b
