"""Authoritative sandbox resolution for the canvas file blocks.

The block layer (:mod:`._blocks._files`) only validates a path's *shape* —
it stays pure so it can run on the validate hot path.  This module is the
second, enforcing layer: it runs at the executor / preview I/O boundary,
where settings are available, and is the single place that turns a
sandbox-relative path into a real absolute path.

Every resolution re-reads :class:`pointlessql.config.CanvasFileIoSettings`
live and refuses to proceed unless (a) a sandbox root is configured,
(b) the requested direction is enabled (``allow_input`` / ``allow_output``),
and (c) the resolved path stays inside the root after ``resolve()`` — which
also defeats symlink / ``..`` normalisation escapes that a pure string check
cannot see.  Anything else raises :class:`ValidationError`, so a misconfigured
or hostile path fails the whole run before any file is touched.
"""

from __future__ import annotations

from pathlib import Path

from pointlessql.config import get_settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.dp_canvas._blocks._files import FILE_SENTINEL_RE


def resolve_sandbox_path(rel: str, *, for_write: bool) -> str:
    """Resolve a sandbox-relative path to an absolute path, or raise.

    Args:
        rel: The relative path (already shape-validated by the block layer).
        for_write: ``True`` for a FileOutput destination (gated on
            ``allow_output``), ``False`` for a FileInput source (gated on
            ``allow_input``).

    Returns:
        The absolute filesystem path, guaranteed to sit inside the sandbox
        root.

    Raises:
        ValidationError: When the file blocks are disabled, the direction is
            not allowed, or the path escapes the sandbox root.
    """
    cfg = get_settings().canvas_file_io
    if cfg.root is None:
        raise ValidationError(
            "Canvas file blocks are disabled; set POINTLESSQL_CANVAS_FILE_ROOT "
            "to a directory to enable them."
        )
    if for_write and not cfg.allow_output:
        raise ValidationError(
            "Canvas file output is disabled; set "
            "POINTLESSQL_CANVAS_FILE_ALLOW_OUTPUT=true to enable it."
        )
    if not for_write and not cfg.allow_input:
        raise ValidationError("Canvas file input is disabled.")

    root = Path(cfg.root).resolve()
    full = (root / rel).resolve()
    if not full.is_relative_to(root):
        raise ValidationError(f"File path {rel!r} escapes the configured sandbox root.")
    # A single quote would break out of the quoted path literal in the
    # DuckDB read_*/COPY statement.  The relative part is allow-listed
    # already; this guards a pathological root configured with a quote.
    if "'" in str(full):
        raise ValidationError("Sandbox path must not contain a single quote.")
    return str(full)


def rewrite_file_sentinels(sql: str) -> str:
    """Replace every ``@@CANVAS_FILE:…@@`` token with a resolved read path.

    A sentinel-free statement is returned unchanged and never reads
    settings, so canvases without a FileInput are wholly unaffected.  Each
    sentinel resolves as a *read* (``for_write=False``); an out-of-sandbox or
    disabled path raises :class:`ValidationError`.
    """
    return FILE_SENTINEL_RE.sub(lambda m: resolve_sandbox_path(m.group(1), for_write=False), sql)


__all__ = ["resolve_sandbox_path", "rewrite_file_sentinels"]
