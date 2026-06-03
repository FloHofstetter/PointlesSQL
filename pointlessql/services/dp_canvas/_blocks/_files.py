# pyright: reportPrivateUsage=false
"""File source / sink blocks for the visual data-product canvas.

FileInput reads a CSV / Parquet / JSON file and FileOutput writes one,
both confined to the administrator-configured sandbox root (see
:class:`pointlessql.config.CanvasFileIoSettings`).  These blocks step
*outside* Unity Catalog governance, so they are the project's most
security-sensitive surface: a path typed in the web editor must never be
able to read or clobber a file outside the sandbox.

Defence is layered.  This module is the first layer and stays pure (no
filesystem, no settings): it validates the *shape* of a path — relative,
no ``..``, an allow-listed character set that also forecloses SQL-quote
injection — and emits a ``@@CANVAS_FILE:…@@`` sentinel rather than a real
path.  The authoritative ``resolve()`` + ``is_relative_to(root)`` check
against the live sandbox root, plus the read/write feature gates, run at
the executor / preview I/O boundary in
:mod:`pointlessql.services.dp_canvas._file_sandbox`, where settings are
legitimately available.
"""

from __future__ import annotations

import re
from typing import Any

from pointlessql.services.dp_canvas._blocks._base import (
    CompiledBlock,
    _bad_config,
    _coerce_str,
    _unknown_schema,
    register_block,
)
from pointlessql.services.dp_canvas._types import CompileError, PinSchema

# Allow-list for a sandbox-relative path: letters, digits and the handful of
# punctuation real filenames need.  It deliberately excludes quotes,
# backslashes, NUL, whitespace and everything else, so a path can never break
# out of the single-quoted string it is embedded in nor name a Windows / UNC
# location.
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Placeholder a FileInput emits in place of a real path; the executor / preview
# rewrites it to the resolved absolute path right before DuckDB runs.  Using a
# sentinel (rather than a bare path) means a code path that forgets to resolve
# it fails closed — DuckDB errors on the literal ``@@`` token instead of
# silently reading a relative path from the process CWD.
FILE_SENTINEL_RE = re.compile(r"@@CANVAS_FILE:([A-Za-z0-9._/-]+)@@")

_INPUT_FORMATS: tuple[str, ...] = ("csv", "parquet", "json", "auto")
_OUTPUT_FORMATS: tuple[str, ...] = ("csv", "parquet")
_READERS: dict[str, str] = {
    "csv": "read_csv_auto",
    "parquet": "read_parquet",
    "json": "read_json_auto",
}


def make_file_sentinel(rel: str) -> str:
    """Wrap a sandbox-relative path in the resolve-me sentinel token."""
    return f"@@CANVAS_FILE:{rel}@@"


def _safe_relative_path(
    node_id: str, raw: Any, errors: list[CompileError]
) -> str | None:
    """Validate a path's shape only — relative, no traversal, safe charset.

    Pure and string-only on purpose: it never touches the filesystem or
    reads settings, so it is safe to run on the per-keystroke validate path.
    The authoritative sandbox-containment check happens later, at the I/O
    boundary.  Returns the cleaned relative path, or ``None`` (with an error
    appended) when the shape is unacceptable.
    """
    path = _coerce_str(raw).strip()
    if not path:
        errors.append(_bad_config(node_id, "File path is required.", column="path"))
        return None
    if not _SAFE_PATH_RE.match(path):
        errors.append(
            _bad_config(
                node_id,
                "File path may only contain letters, digits, '.', '_', '-' and '/'.",
                column="path",
            )
        )
        return None
    if path.startswith("/"):
        errors.append(
            _bad_config(
                node_id,
                "File path must be relative to the sandbox (no leading '/').",
                column="path",
            )
        )
        return None
    if any(seg in ("", ".", "..") for seg in path.split("/")):
        errors.append(
            _bad_config(
                node_id,
                "File path must not contain '.', '..' or empty segments.",
                column="path",
            )
        )
        return None
    return path


def _reader_for(fmt: str, rel: str) -> str:
    """Pick the DuckDB reader function for a FileInput format / extension."""
    if fmt != "auto":
        return _READERS[fmt]
    lower = rel.lower()
    if lower.endswith(".parquet"):
        return "read_parquet"
    if lower.endswith((".json", ".ndjson")):
        return "read_json_auto"
    return "read_csv_auto"


# --------------------------------------------------------------------- FileInput


def _compile_file_input(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    del inputs  # FileInput is a source — no upstream pins
    rel = _safe_relative_path(node_id, cfg.get("path"), errors)
    if rel is None:
        return None
    fmt = _coerce_str(cfg.get("format"), default="auto").lower().strip()
    if fmt not in _INPUT_FORMATS:
        errors.append(
            _bad_config(node_id, f"FileInput.format must be one of {_INPUT_FORMATS}.")
        )
        return None
    reader = _reader_for(fmt, rel)
    return CompiledBlock(
        sql=f"SELECT * FROM {reader}('{make_file_sentinel(rel)}')",
        output_schema=output_schema,
    )


def _infer_file_input(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del input_schemas
    rel = _safe_relative_path(node_id, cfg.get("path"), errors)
    if rel is None:
        return _unknown_schema()
    # The real columns live in a file on disk; reading them at edit-time would
    # make schema inference touch the filesystem on untrusted input, so the
    # schema stays unknown until the first preview / execute resolves it.
    return seed if seed is not None else _unknown_schema()


register_block(
    type_name="FileInput",
    input_pins=(),
    output_pins=(("out", "table"),),
    compile_fn=_compile_file_input,
    infer_fn=_infer_file_input,
)


# --------------------------------------------------------------------- FileOutput


def _compile_file_output(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="FileOutput requires an upstream input on pin 'in'.",
            )
        )
        return None
    rel = _safe_relative_path(node_id, cfg.get("path"), errors)
    if rel is None:
        return None
    fmt = _coerce_str(cfg.get("format"), default="parquet").lower().strip()
    if fmt not in _OUTPUT_FORMATS:
        errors.append(_bad_config(node_id, "FileOutput.format must be 'csv' or 'parquet'."))
        return None
    # The destination path / format ride on the SinkSpec (built by the
    # compiler's sink loop); the CTE body is a plain passthrough, like
    # OutputPort, and the executor wraps it in a DuckDB COPY.
    return CompiledBlock(
        sql=f"SELECT * FROM {src}",
        output_schema=output_schema,
    )


def _infer_file_output(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del node_id, cfg, errors, seed
    return input_schemas.get("in", _unknown_schema())


register_block(
    type_name="FileOutput",
    input_pins=(("in", "table"),),
    output_pins=(),
    compile_fn=_compile_file_output,
    infer_fn=_infer_file_output,
)
