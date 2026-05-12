"""Load and save ``.py`` notebooks in jupytext's Percent format.

Single point of contact between the on-disk ``.py`` notebook source
of truth and the HTTP layer that serves cells to the client.

Three invariants:

* **On-disk format is jupytext Percent.** Every cell boundary is a
  ``# %%`` marker (or one of the aliases jupytext parses: ``# ---``,
  ``# COMMAND ----------``, ``# In[N]:``). Write-path normalises to
  ``# %%`` unless the file header pins a different marker through a
  ``jupytext.cell_markers`` entry.
* **Cell identity is derived from source, not persisted in the
  marker.** Cell identity is ``FNV-1a-64(normalized_source)``
  computed at load time; the on-disk grammar carries only what the
  user needs to see: the optional ``[markdown]`` / ``[sql]`` tag
  and, for SQL cells, a positional bare-identifier ``result_var``
  segment (``# %% [sql] df``). The ``.py`` file is therefore
  generically editable in VSCode / Vim / Spyder — removing or
  reordering cells manually cannot break the file because there is
  no ID to go stale. Legacy files carrying an obsolete
  ``pql_cell_id="…"`` marker still load (tolerant regex) and are
  rewritten into the new grammar on the next save via the
  ``dirty`` flow.
* **No execution state lives here.** Outputs, execution counts, and
  kernel sessions belong to the ``notebook_outputs`` table.  This
  module deals with source text and cell metadata only.

The caller is expected to have already resolved the target path under
the notebooks directory via :func:`resolve_py_notebook_path`, which is
the ``.py`` sibling of :func:`notebook_workspace.resolve_upload_target`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jupytext  # type: ignore[import-untyped]
import nbformat  # type: ignore[import-untyped]

from pointlessql.exceptions import ValidationError

_PY_NOTEBOOK_SUFFIX = ".py"
# jupytext's cell metadata never lands in marker lines — we manage
# the extension shape (``[sql]`` tag + positional result_var)
# ourselves via the post-write rewrite below. The ``"-all"`` filter
# tells jupytext to strip every metadata key before serialisation so
# writes stay free of leftover ``title`` / ``tags`` / legacy
# ``pql_cell_id`` entries from round-trips of old files.
_CELL_METADATA_FILTER = "-all"

# Marker grammar (UUID-free):
#
#   ``# %%``                                — code cell
#   ``# %% [markdown]``                     — markdown cell
#   ``# %% [sql]``                          — SQL cell without a result variable
#   ``# %% [sql] df``                       — SQL cell that binds its DataFrame to ``df``
#   ``# %% tags=["parameters"]``            — code cell tagged as papermill parameters
#   ``# %% [markdown] tags=["aside"]``      — markdown cell with arbitrary tag(s)
#   ``# %% [sql] df tags=["parameters"]``   — SQL cell with result_var + tag(s)
#
# Group 1 captures the optional bracketed tag (``markdown`` / ``sql``
# / unknown → fall back to ``code``). Group 2 captures the optional
# positional Python identifier that SQL cells use as their
# ``result_var``. Group 3 captures the optional ``tags=[...]``
# inner content (e.g. ``"parameters"`` or ``"a", "b"``); we parse it
# with :func:`_parse_tags_list` into a tuple. ``cell_parser.js`` on
# the client must stay in lock-step with this shape.
_MARKER_RE = re.compile(
    r"^#\s*%%"
    r"(?:\s+\[(\w+)\])?"
    r"(?:\s+([A-Za-z_][A-Za-z0-9_]*))?"
    r"(?:\s+tags=\[([^\]]*)\])?"
    r"\s*$",
    re.MULTILINE,
)
_TAG_LITERAL_RE = re.compile(r'"([^"]*)"')

# Legacy grammar: every cell carried a ``pql_cell_id="<uuid>"``
# token and SQL cells pinned ``result_var="<name>"`` via a named
# metadata segment. We still parse these on load so migrating from
# pre-rewrite notebooks is a transparent one-time save —
# ``load_document`` sets ``dirty=True`` whenever the tolerant
# legacy regex matches any line so the UI prompts the user to
# re-save into the clean shape above.
_LEGACY_MARKER_RE = re.compile(
    r'^#\s*%%(?:\s+\[(\w+)\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"'
    r'(?:\s+result_var="([A-Za-z_][A-Za-z0-9_]*)")?\s*$',
    re.MULTILINE,
)

# Cheap "is this line a cell marker of any shape?" test used by the
# post-write rewrite that injects our SQL extension back into the
# jupytext output.
_ANY_MARKER_RE = re.compile(r"^#\s*%%")


_FNV_OFFSET_64 = 0xCBF29CE484222325
_FNV_PRIME_64 = 0x100000001B3
_FNV_MASK_64 = 0xFFFFFFFFFFFFFFFF


def compute_content_hash(source: str) -> str:
    r"""Return the 16-char hex identity of a cell's normalized source.

    Uses FNV-1a 64-bit because it has a trivial byte-for-byte mirror
    in JavaScript via ``BigInt`` — the client-side
    ``computeContentHash`` in ``frontend/js/notebook/cell_parser.js``
    computes the exact same 16-hex string so WS frames can round-trip
    a cell identity between Python and the browser without either
    side needing async crypto.

    The hash is stable against whitespace-only edits and cross-platform
    line-ending churn: each line is right-stripped and ``\r\n`` is
    collapsed to ``\n`` before hashing. 64 bits of entropy are
    collision-safe within a single notebook (the query key is
    ``(file_path, content_hash)`` so the birthday bound lives at
    notebook granularity, not globally).

    Args:
        source: Cell source text as the editor / parser produced it.

    Returns:
        The 16-hex lower-case digest of ``FNV-1a-64(normalized)``,
        suitable as the ``content_hash`` column value on
        :class:`NotebookOutput` / :class:`NotebookCellRun` /
        :class:`NotebookCellRunSource`.
    """
    normalized = "\n".join(line.rstrip() for line in source.replace("\r\n", "\n").split("\n"))
    h = _FNV_OFFSET_64
    for byte in normalized.encode("utf-8"):
        h = ((h ^ byte) * _FNV_PRIME_64) & _FNV_MASK_64
    return f"{h:016x}"


@dataclass(frozen=True)
class NotebookCell:
    """A single notebook cell as served to the editor.

    Cell identity is split across two separately-purposed fields:

    * :attr:`id` is a **transient** ordinal label (``cell-0``,
      ``cell-1``, …) minted fresh on every load. It is only used
      as the Alpine.js ``x-for :key`` so the DOM reconciler stays
      stable within one editor session. It is never persisted, never
      sent to the DB, never shown to the user.
    * :attr:`content_hash` is the **stable** identity used for all
      DB lookups (``notebook_outputs``, ``notebook_cell_runs``,
      ``notebook_cell_run_sources``) and all WS frames that address a
      cell. It is the 16-hex FNV-1a-64 digest of
      :func:`compute_content_hash`'s normalised source so that run
      history survives reordering and whitespace-only edits but
      naturally splits when the cell's meaningful source changes —
      analogous to how a new commit gets a fresh SHA.

    Attributes:
        id: Transient ordinal label (``cell-<index>``). Never
            persisted.
        content_hash: 16-hex FNV-1a-64 digest of the cell's
            normalised source. Stable across reloads and
            reorderings.
        cell_type: ``"code"`` / ``"markdown"`` / ``"sql"``.  Raw
            cells are not supported in the editor — they're
            rewritten to markdown on load (one-way).
        source: Cell source text. Markdown cells carry raw markdown
            without comment-escaping; jupytext handles the
            ``# %% [markdown]`` round-trip.
        result_var: Optional pandas-DataFrame name a SQL cell binds
            its result to in the kernel namespace.  ``None`` for
            non-SQL cells and SQL cells without a positional
            identifier after the ``[sql]`` tag.
        tags: Ordered, deduplicated tags carried by the cell marker
            (``# %% tags=["parameters", "aside"]``). Acts as
            metadata — never feeds into ``content_hash`` so a
            params-tag-toggle is a no-op for cell identity. The
            canonical use is ``"parameters"`` (papermill convention),
            but arbitrary tags round-trip losslessly.
    """

    id: str
    content_hash: str
    cell_type: str
    source: str
    result_var: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotebookDocument:
    """A whole ``.py`` notebook as served to the editor.

    Attributes:
        path: Relative path under the notebooks directory.
        cells: Ordered list of cells.
        dirty: ``True`` when the loaded file carries legacy
            ``pql_cell_id="…"`` markers — the editor prompts the
            user for a one-time save that rewrites the file into
            the UUID-free grammar. Subsequent loads of a
            post-migration file report ``False``.
    """

    path: str
    cells: list[NotebookCell]
    dirty: bool


def resolve_py_notebook_path(
    notebooks_dir: Path,
    relative_path: str,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve a ``.py`` notebook path under the notebooks directory.

    Mirrors :func:`notebook_workspace.resolve_upload_target` but for
    ``.py`` files rather than ``.ipynb``. The traversal guard is
    identical — the relative path must stay under ``notebooks_dir``
    after ``Path.resolve``.

    Args:
        notebooks_dir: Absolute notebooks root.
        relative_path: Caller-supplied relative path.
        must_exist: When ``True`` (the default), a missing file is an
            error — used on the load path. When ``False``, the file
            may be brand-new but its parent directory must already
            exist — used on the save path.

    Returns:
        Resolved absolute path.

    Raises:
        ValidationError: Empty / absolute / wrong-suffix / escaping
            path; or a missing file when ``must_exist`` is ``True``;
            or a missing parent when ``must_exist`` is ``False``.
    """
    if not relative_path:
        raise ValidationError("notebook path must be a non-empty string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValidationError(
            f"notebook path must be relative to the notebooks directory: {relative_path!r}"
        )
    if candidate.suffix != _PY_NOTEBOOK_SUFFIX:
        raise ValidationError(
            f"notebook path must end in {_PY_NOTEBOOK_SUFFIX!r}: {relative_path!r}"
        )
    resolved = (notebooks_dir / candidate).resolve()
    try:
        resolved.relative_to(notebooks_dir)
    except ValueError as exc:
        raise ValidationError(
            f"notebook path {relative_path!r} escapes the notebooks directory"
        ) from exc
    if must_exist:
        if not resolved.is_file():
            raise ValidationError(f"notebook not found: {relative_path!r}")
    else:
        if not resolved.parent.is_dir():
            raise ValidationError(f"notebook parent directory does not exist: {relative_path!r}")
    return resolved


def _parse_tags_list(raw_inner: str) -> tuple[str, ...]:
    """Parse the inner contents of a ``tags=[...]`` marker segment.

    The regex captures the bytes *between* the brackets, so we still
    need to peel quoted literals out one by one. Deduplicates while
    preserving first-seen order so a malformed ``tags=["a","a"]``
    round-trips as ``["a"]`` rather than triggering a downstream
    surprise.

    Args:
        raw_inner: The captured inner text (e.g. ``'"a", "b"'``).

    Returns:
        Ordered, deduplicated tags as a tuple of strings. Empty input
        (``tags=[]``) yields ``()``.
    """
    seen: list[str] = []
    for match in _TAG_LITERAL_RE.findall(raw_inner):
        if match not in seen:
            seen.append(match)
    return tuple(seen)


def _scan_marker_extensions(
    raw_text: str,
) -> list[tuple[str | None, str | None, tuple[str, ...]]]:
    """Walk a ``.py`` notebook line-by-line, return marker metadata per cell.

    The list length equals the number of cells jupytext will produce,
    in order. Accepts both the canonical UUID-free grammar and the
    legacy ``pql_cell_id="…"`` grammar so mixed or half-migrated
    files parse transparently.

    Args:
        raw_text: Full file content (UTF-8 decoded).

    Returns:
        One ``(tag, result_var, tags)`` tuple per detected marker line.
        ``tag`` is ``"markdown"`` / ``"sql"`` / ``None``; ``result_var``
        is the positional SQL identifier when present, ``None``
        otherwise; ``tags`` is the parsed ``tags=[...]`` content
        (empty tuple when absent). Legacy markers always return an
        empty ``tags`` tuple — the next save rewrites them anyway.
    """
    out: list[tuple[str | None, str | None, tuple[str, ...]]] = []
    for line in raw_text.split("\n"):
        m_legacy = _LEGACY_MARKER_RE.match(line)
        if m_legacy:
            out.append((m_legacy.group(1), m_legacy.group(3), ()))
            continue
        m_new = _MARKER_RE.match(line)
        if m_new:
            tags_inner = m_new.group(3) or ""
            out.append((m_new.group(1), m_new.group(2), _parse_tags_list(tags_inner)))
    return out


def _normalise_file_text(raw_bytes: bytes) -> str:
    r"""Decode + normalise a ``.py`` notebook's on-disk bytes.

    Hardening helper. Strips a leading UTF-8 BOM if present
    (some Windows editors emit one for ``.py``) and collapses CRLF
    line endings to LF so downstream regex / jupytext calls see a
    single line-separator convention.  Falls back to ``latin-1``
    decoding on an undecodable UTF-8 payload so the parser never
    throws on a user-saved file — a corrupt notebook should render
    as one giant code cell the user can inspect + fix, not a 500.

    Args:
        raw_bytes: The file bytes as read from disk.

    Returns:
        The file content decoded + normalised to LF-only UTF-8-safe
        text.
    """
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def load_document(absolute_path: Path, relative_path: str) -> NotebookDocument:
    """Load a ``.py`` notebook off disk and compute per-cell content hashes.

    Uses :func:`jupytext.read` to parse the Percent format; any marker
    variant jupytext recognises is accepted. The raw file is re-scanned
    with :func:`_scan_marker_extensions` to recover PointlesSQL-specific
    marker details (``[sql]`` tag + positional ``result_var``) that
    jupytext drops on read. Legacy UUID-bearing markers are detected
    and cause the returned document's ``dirty`` flag to be set so the
    editor prompts a one-time save into the clean grammar.

    The parser tolerates every shape a user can produce by editing
    the ``.py`` directly in VSCode / Vim:

    * **No markers at all** — the whole file becomes a single
      ``cell-0`` code cell so the user can still open + inspect + add
      markers from the editor. ``dirty=True`` prompts a save that
      materialises at least one ``# %%`` header on disk.
    * **Unknown tag** (``# %% [foo]``) — falls back to ``code``. The
      parser drops the tag silently; the next save rewrites the line
      to a plain ``# %%`` marker.
    * **Invalid SQL identifier** (``# %% [sql] 123abc``) — the tag
      still resolves to ``sql`` but ``result_var`` is ``None``. The
      next save emits ``# %% [sql]`` without the broken segment.
    * **CRLF / UTF-8 BOM** — normalised to LF + stripped by
      :func:`_normalise_file_text` before parsing.
    * **Empty file** — returns a single empty code cell and sets
      ``dirty=True`` so the first save writes a ``# %%`` header.
    * **File ending mid-cell without trailing newline** — jupytext
      already tolerates this; we pass through unchanged.

    Args:
        absolute_path: Pre-resolved path produced by
            :func:`resolve_py_notebook_path`.
        relative_path: Relative path (as the caller supplied it) —
            stored on the returned document for the editor UI.

    Returns:
        A :class:`NotebookDocument` with ordered cells; each cell
        carries a transient ordinal ``id`` and a stable
        ``content_hash``. The ``dirty`` flag is ``True`` when the
        loaded file still contains legacy UUID markers OR needed a
        tolerance recovery (BOM / CRLF / no markers / empty) that
        the next save will normalise.
    """
    raw_bytes = absolute_path.read_bytes()
    normalised_raw = _normalise_file_text(raw_bytes)
    original_raw = raw_bytes.decode("utf-8", errors="replace")
    # Flag a save-on-next-open when the on-disk bytes carried a BOM
    # or CRLF line endings — the rewrite path emits clean UTF-8 + LF.
    sanitised = original_raw != normalised_raw
    legacy = bool(_LEGACY_MARKER_RE.search(normalised_raw))
    marker_exts = _scan_marker_extensions(normalised_raw)

    # When the file has no markers at all (user wrote a plain .py
    # by hand or the file is empty), jupytext returns a single
    # synthetic cell whose source is the whole file.  We still need
    # to surface that content to the editor so the user can add
    # markers from the UI; materialising a save on next edit writes
    # an explicit ``# %%`` header.
    has_any_marker = bool(marker_exts)

    if not normalised_raw.strip():
        empty = ""
        return NotebookDocument(
            path=relative_path,
            cells=[
                NotebookCell(
                    id="cell-0",
                    content_hash=compute_content_hash(empty),
                    cell_type="code",
                    source=empty,
                    result_var=None,
                ),
            ],
            dirty=True,
        )

    if not has_any_marker:
        # Treat the whole file as a single code cell.  jupytext's own
        # read would do the same (its markerless fallback emits one
        # cell), but routing through our explicit path keeps the
        # dirty-flag semantics legible.
        return NotebookDocument(
            path=relative_path,
            cells=[
                NotebookCell(
                    id="cell-0",
                    content_hash=compute_content_hash(normalised_raw),
                    cell_type="code",
                    source=normalised_raw,
                    result_var=None,
                ),
            ],
            dirty=True,
        )

    # Feed jupytext the already-normalised text rather than the raw
    # path so its parse sees LF-only, BOM-free bytes; otherwise a
    # BOM stays glued to the first cell's source and surfaces in
    # the editor as ``\ufeff`` noise even though our own
    # sanitisation ran.
    notebook = jupytext.reads(normalised_raw, fmt="py:percent")
    cells: list[NotebookCell] = []
    for index, raw_cell in enumerate(notebook.cells):
        raw_type = getattr(raw_cell, "cell_type", "code")
        cell_type = "markdown" if raw_type == "markdown" else "code"
        result_var: str | None = None
        marker_tags: tuple[str, ...] = ()
        if index < len(marker_exts):
            tag, rv, marker_tags = marker_exts[index]
            if tag == "sql":
                cell_type = "sql"
                # rv may already be ``None`` for a ``# %% [sql]`` that
                # omits the identifier; _MARKER_RE's own Python-
                # identifier constraint on group 2 guarantees any
                # returned rv is safe to pass straight through.
                result_var = rv
            # Unknown tags (``# %% [foo]``) fall through to ``code``
            # with result_var=None — the next save rewrites the
            # marker to plain ``# %%``.
        source = raw_cell.source or ""
        cells.append(
            NotebookCell(
                id=f"cell-{index}",
                content_hash=compute_content_hash(source),
                cell_type=cell_type,
                source=source,
                result_var=result_var,
                tags=marker_tags,
            )
        )
    return NotebookDocument(
        path=relative_path,
        cells=cells,
        dirty=legacy or sanitised,
    )


def save_document(absolute_path: Path, cells: list[NotebookCell]) -> None:
    """Write cells back to disk in jupytext Percent format.

    Canonical grammar — no ``pql_cell_id`` / ``result_var="…"``
    segments in markers. Code cells emit ``# %%``, markdown cells
    emit ``# %% [markdown]``, SQL cells emit ``# %% [sql]`` or
    ``# %% [sql] <result_var>``. Optional ``tags=[...]`` suffixes
    round-trip on any cell type. The SQL variants + tag suffixes are
    injected via :func:`_rewrite_cell_markers` after jupytext has
    written the file because jupytext does not know about the
    PointlesSQL-specific marker extensions.

    Round-tripping a legacy file through :func:`load_document` +
    :func:`save_document` strips the old UUID markers losslessly in
    terms of semantics — the cell order, types, sources, and SQL
    ``result_var`` bindings are preserved; only the on-disk
    representation changes from ``# %% pql_cell_id="<uuid>"`` to
    the clean grammar.

    Args:
        absolute_path: Pre-resolved target path.
        cells: Ordered cells to write.
    """
    nb_cells: list[Any] = []
    extensions: list[tuple[str | None, str | None, tuple[str, ...]]] = []
    for cell in cells:
        if cell.cell_type == "markdown":
            nb_cell = nbformat.v4.new_markdown_cell(cell.source)
        else:
            nb_cell = nbformat.v4.new_code_cell(cell.source)
        nb_cells.append(nb_cell)
        if cell.cell_type == "sql":
            extensions.append(("sql", cell.result_var, cell.tags))
        elif cell.cell_type == "markdown":
            extensions.append(("markdown", None, cell.tags))
        else:
            extensions.append((None, None, cell.tags))
    notebook = nbformat.v4.new_notebook(cells=nb_cells)
    notebook.metadata.setdefault("jupytext", {})["cell_metadata_filter"] = _CELL_METADATA_FILTER
    jupytext.write(notebook, absolute_path, fmt="py:percent")
    if any(_marker_needs_rewrite(ext) for ext in extensions):
        _rewrite_cell_markers(absolute_path, extensions)


def _marker_needs_rewrite(
    ext: tuple[str | None, str | None, tuple[str, ...]],
) -> bool:
    """Return True when this cell's marker needs PointlesSQL-side rewriting.

    Jupytext writes plain ``# %%`` and ``# %% [markdown]`` lines on
    its own; we only need to step in for SQL cells (jupytext doesn't
    know our ``[sql]`` tag) and for any cell that carries tags
    (``# %% tags=[...]``).

    Args:
        ext: Per-cell extension tuple ``(tag, result_var, tags)``.

    Returns:
        ``True`` when at least one piece of the marker needs to be
        injected; ``False`` when the jupytext-emitted line is already
        canonical.
    """
    tag, _, tags = ext
    return tag == "sql" or bool(tags)


def _format_marker(
    tag: str | None,
    result_var: str | None,
    tags: tuple[str, ...],
) -> str:
    """Render a canonical marker line for one cell.

    Order: cell-type bracket → positional ``result_var`` (SQL only) →
    ``tags=[...]`` suffix. Empty pieces are elided. The grammar mirrors
    what :data:`_MARKER_RE` accepts so write→read round-trips are
    byte-identical on the marker line.

    Args:
        tag: ``"sql"`` / ``"markdown"`` / ``None`` for plain code.
        result_var: Optional SQL ``result_var`` identifier.
        tags: Ordered tags tuple (already deduplicated).

    Returns:
        The marker line without trailing newline.
    """
    parts = ["# %%"]
    if tag in {"markdown", "sql"}:
        parts.append(f"[{tag}]")
    if tag == "sql" and result_var:
        parts.append(result_var)
    if tags:
        joined = ", ".join(f'"{t}"' for t in tags)
        parts.append(f"tags=[{joined}]")
    return " ".join(parts)


def _rewrite_cell_markers(
    absolute_path: Path,
    extensions: list[tuple[str | None, str | None, tuple[str, ...]]],
) -> None:
    """Inject SQL tag + ``result_var`` + ``tags=[...]`` into cell markers.

    Walks the file jupytext just wrote, counts each marker line, and
    rewrites the lines that need PointlesSQL-side polish (per
    :func:`_marker_needs_rewrite`). Idempotent — running twice produces
    the same output.

    Args:
        absolute_path: File jupytext just wrote.
        extensions: One ``(tag, result_var, tags)`` tuple per cell in
            the same order jupytext emitted them. Cells whose marker
            jupytext already emitted in canonical form
            (``# %%`` plain code or ``# %% [markdown]`` without tags)
            pass through untouched.
    """
    text = absolute_path.read_text()
    lines = text.split("\n")
    cell_index = -1
    for line_index, line in enumerate(lines):
        if not _ANY_MARKER_RE.match(line):
            continue
        cell_index += 1
        if cell_index >= len(extensions):
            continue
        ext = extensions[cell_index]
        if not _marker_needs_rewrite(ext):
            continue
        lines[line_index] = _format_marker(*ext)
    absolute_path.write_text("\n".join(lines))
