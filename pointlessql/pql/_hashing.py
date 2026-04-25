"""Sprint 13.8 — input-frame hashing for the agent-run audit trail.

PQL primitives writing into Delta need a stable digest of the data
they appended so a later reviewer can confirm "this run wrote
exactly these bytes".  We hash the Arrow IPC stream representation
because:

* Every engine's frame type (pandas / Polars / PyArrow / DuckDB
  relation) converts to Arrow trivially.
* Arrow IPC is bit-stable across platforms for the same logical
  schema + values, so the same DataFrame produces the same SHA on
  Linux and macOS.
* SHA-256 over the IPC stream is fast enough for the size frames
  agents produce (sub-100MB typical) and matches the ``input_sha``
  column type (``String(64)``).

The helper deliberately re-imports ``pyarrow`` per call instead of
holding a module-level reference — pql is a lazy-import codebase
and the hashing path is rare enough that a sub-millisecond import
cost beats forcing pyarrow at module load time.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any


def arrow_ipc_sha256(frame: Any) -> str:
    """Return the lowercase hex SHA-256 of *frame* as Arrow IPC bytes.

    Accepts whatever PQL primitives flow through their write paths:
    pandas DataFrame, Polars DataFrame, PyArrow Table, or anything
    with a ``.arrow()`` / ``.to_arrow()`` method (DuckDB relations,
    Polars LazyFrames after collect).  The conversion order is
    PyArrow → DuckDB-style ``.arrow()`` → ``.to_arrow()`` →
    ``pa.Table.from_pandas`` (last-resort) so callers don't need
    to remember which method their frame happens to expose.

    Args:
        frame: The data to hash.

    Returns:
        64-character lowercase hex digest of the Arrow IPC stream.

    Raises:
        TypeError: When *frame* cannot be converted to a PyArrow
            Table by any known path.
    """
    import pyarrow as pa

    table: pa.Table
    if isinstance(frame, pa.Table):
        table = frame
    elif hasattr(frame, "arrow") and callable(frame.arrow):
        table = frame.arrow()  # pyright: ignore[reportUnknownMemberType]
    elif hasattr(frame, "to_arrow") and callable(frame.to_arrow):
        candidate = frame.to_arrow()  # pyright: ignore[reportUnknownMemberType]
        table = (
            candidate
            if isinstance(candidate, pa.Table)
            else pa.Table.from_pandas(candidate)  # pyright: ignore[reportUnknownArgumentType]
        )
    else:
        try:
            table = pa.Table.from_pandas(frame)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"arrow_ipc_sha256: cannot convert {type(frame).__name__} to "
                "pyarrow.Table"
            ) from exc

    sink = io.BytesIO()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return hashlib.sha256(sink.getvalue()).hexdigest()


def concat_sha256(parts: list[str]) -> str:
    """SHA-256 over the joined hex strings of *parts*.

    Used by ``pql.autoload`` to record one provenance digest per
    primitive call instead of one per file: the Sprint 13.5.3
    ``autoload_checkpoints`` table already keeps file-level SHAs,
    so the operation row's ``input_sha`` only needs to be a
    deterministic summary.

    Args:
        parts: Hex digest strings to concatenate.

    Returns:
        64-character lowercase hex digest of
        ``"".join(parts).encode("utf-8")``.
    """
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()
