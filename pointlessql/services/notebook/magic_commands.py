"""Phase 98.A — thin pre-processor for notebook magic commands.

Recognised magics (line-magic style, one per line):

* ``%sql <query>`` — execute SQL via PQL with route-resolved
  ``approved_tables``.  The route layer must call
  :func:`extract_sql_blocks` to collect SQL fragments, resolve
  approvals, then call :func:`apply_sql_resolutions` to splice the
  resolved calls back in.  The pre-processor itself is sync and pure;
  the async UC privilege check stays in the WS handler.
* ``%md <markdown>`` — renders the rest of the line as Markdown via
  the kernel-side helper ``__pql_magic_md__``.  Multi-line markdown
  is supported via the cell-block form ``%%md`` which captures every
  line until the next ``%%`` or EOF.
* ``%fs ls <path>`` — lists files at ``path`` (local filesystem +
  ``file://`` Delta storage) via ``__pql_magic_fs_ls__``.
* ``%timeit <expr>`` — times a Python expression via the
  ``__pql_magic_timeit__`` helper (stdlib ``timeit``, repeat=3,
  number autoscaled).

Design notes:

* The pre-processor sees raw cell source and emits transformed
  Python.  It runs **only on ``code`` cells** — the WS handler skips
  it entirely for SQL / markdown cells, which have their own paths.
* Lines that do not start with a recognised magic pass through
  untouched, including IPython native magics such as ``%timeit`` if
  the user types it with arguments we cannot parse.  When in doubt,
  we transform — the kernel helpers are tolerant of bad input.
* No side effects: every transform is local to the source string
  and emits ordinary Python code that calls a kernel-side helper.
  The helpers live in :data:`KernelSession._NOTEBOOK_BOOTSTRAP_CODE`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SQL_PLACEHOLDER_PREFIX = "__PQL_SQL_BLOCK_"
_SQL_PLACEHOLDER_SUFFIX = "__"


@dataclass
class SqlBlock:
    """A ``%sql`` magic line awaiting approval resolution.

    Attributes:
        index: Position in :attr:`PreprocessResult.sql_blocks`.
        sql: Raw SQL text the user typed after ``%sql`` (one line).
        result_var: Optional ``-o name`` flag for binding the result.
    """

    index: int
    sql: str
    result_var: str | None = None


@dataclass
class PreprocessResult:
    """Outcome of :func:`preprocess`.

    Attributes:
        source: Transformed Python source; SQL magics are placeholders
            until :func:`apply_sql_resolutions` replaces them.
        sql_blocks: Each ``%sql`` magic in cell order; the caller
            resolves ``approved_tables`` for every entry then calls
            :func:`apply_sql_resolutions`.
        used: The magic names seen in cell order (``sql``, ``md``,
            ``fs_ls``, ``timeit``).  Diagnostic / telemetry hook.
    """

    source: str
    sql_blocks: list[SqlBlock] = field(default_factory=lambda: [])  # noqa: PIE807
    used: list[str] = field(default_factory=lambda: [])  # noqa: PIE807


def preprocess(cell_source: str) -> PreprocessResult:
    """Walk ``cell_source`` line-by-line and emit a Python-only string.

    Args:
        cell_source: Raw cell source from the WS execute frame.

    Returns:
        A :class:`PreprocessResult` whose :attr:`source` is plain
        Python; SQL magics are left as ``__PQL_SQL_BLOCK_<n>__``
        sentinels until the route resolves them.

    The function is intentionally tolerant: a malformed magic line
    (e.g. ``%sql`` with no argument) becomes a no-op comment instead
    of raising — the cell can still execute the remaining code.
    """
    out_lines: list[str] = []
    used: list[str] = []
    sql_blocks: list[SqlBlock] = []

    lines = cell_source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        if stripped.startswith("%%md"):
            collected: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("%%"):
                collected.append(lines[i])
                i += 1
            content = "\n".join(collected)
            out_lines.append(f"{indent}__pql_magic_md__({content!r})")
            used.append("md")
            continue

        if stripped.startswith("%md "):
            content = stripped[4:].rstrip()
            out_lines.append(f"{indent}__pql_magic_md__({content!r})")
            used.append("md")
        elif stripped == "%md":
            out_lines.append(f"{indent}# %md (empty)")
        elif stripped.startswith("%fs ls"):
            arg = stripped[len("%fs ls") :].strip()
            out_lines.append(f"{indent}__pql_magic_fs_ls__({arg!r})")
            used.append("fs_ls")
        elif stripped.startswith("%timeit "):
            expr = stripped[len("%timeit ") :].rstrip()
            out_lines.append(f"{indent}__pql_magic_timeit__({expr!r})")
            used.append("timeit")
        elif stripped.startswith("%sql "):
            raw = stripped[len("%sql ") :].rstrip()
            result_var, sql_text = _parse_sql_flags(raw)
            if not sql_text:
                out_lines.append(f"{indent}# %sql (empty)")
            else:
                idx = len(sql_blocks)
                sql_blocks.append(
                    SqlBlock(index=idx, sql=sql_text, result_var=result_var)
                )
                placeholder = (
                    f"{_SQL_PLACEHOLDER_PREFIX}{idx}{_SQL_PLACEHOLDER_SUFFIX}"
                )
                out_lines.append(f"{indent}{placeholder}")
                used.append("sql")
        else:
            out_lines.append(line)
        i += 1

    return PreprocessResult(
        source="\n".join(out_lines),
        sql_blocks=sql_blocks,
        used=used,
    )


def _parse_sql_flags(raw: str) -> tuple[str | None, str]:
    """Split ``-o varname <sql>`` into (varname, sql).

    Args:
        raw: Text after the ``%sql`` prefix.

    Returns:
        Tuple of optional result-var and the remaining SQL string.
    """
    tokens = raw.split(maxsplit=2)
    if len(tokens) >= 3 and tokens[0] == "-o":
        return tokens[1], tokens[2]
    return None, raw


def apply_sql_resolutions(
    source: str,
    *,
    wrappers: list[str],
) -> str:
    """Replace ``__PQL_SQL_BLOCK_<n>__`` sentinels with kernel wrappers.

    Args:
        source: :attr:`PreprocessResult.source` from :func:`preprocess`.
        wrappers: One kernel-source string per :class:`SqlBlock`, in
            the same order :func:`preprocess` emitted them.  Each
            wrapper is a complete Python expression (typically a call
            to ``__pql_sql_run``).

    Returns:
        Final Python source ready for the kernel.
    """
    out = source
    for idx, wrapper in enumerate(wrappers):
        placeholder = f"{_SQL_PLACEHOLDER_PREFIX}{idx}{_SQL_PLACEHOLDER_SUFFIX}"
        out = out.replace(placeholder, wrapper.rstrip(), 1)
    return out


def has_magics(cell_source: str) -> bool:
    """Cheap check used by the WS handler to skip pre-processing.

    Args:
        cell_source: Raw cell source.

    Returns:
        ``True`` when any line starts with a recognised magic prefix.
    """
    for line in cell_source.splitlines():
        stripped = line.lstrip()
        if (
            stripped.startswith("%sql ")
            or stripped.startswith("%md ")
            or stripped.startswith("%%md")
            or stripped.startswith("%fs ls")
            or stripped.startswith("%timeit ")
        ):
            return True
    return False
