"""Pure decision and frame-shaping logic for the replay worker.

The worker spins up a Jupyter kernel, drains its iopub stream, and
writes the captured frames back onto the replay row — all I/O.  The
cell-skip predicate, the kernel-env preparation, the iopub message
routing, the output-frame load-shape, and the error-frame builders are
I/O-free, so they live here for isolated unit testing.  Timestamps are
passed in by the caller (the clock read stays in the shell) to keep
every builder deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Output iopub message types that carry a persistable frame.
_OUTPUT_MSG_TYPES = frozenset({"stream", "execute_result", "display_data", "error"})

#: Synthetic principal the replay kernel runs under when none is inherited.
_REPLAY_PRINCIPAL = "replay-worker@pointlessql.local"


def should_execute_cell(cell_type: str, source: str) -> bool:
    """Return whether a replayed cell should be executed.

    Markdown cells and cells whose source is blank/whitespace are
    skipped; everything else runs.

    Args:
        cell_type: The cell's type (``"code"``, ``"markdown"``, …).
        source: The cell's source text.

    Returns:
        ``True`` for an executable, non-empty code cell.
    """
    return cell_type != "markdown" and bool(source.strip())


def prepare_kernel_env(base_env: Mapping[str, str], branch_name: str | None) -> dict[str, str]:
    """Build the kernel subprocess env for a replay.

    Args:
        base_env: The parent environment to inherit (a copy is made).
        branch_name: Optional bound branch; routes writes through it via
            ``POINTLESSQL_BRANCH`` when set.

    Returns:
        A fresh env dict with ``POINTLESSQL_BRANCH`` set when a branch is
        bound and a default ``POINTLESSQL_PRINCIPAL`` when none is
        already present.
    """
    env = dict(base_env)
    if branch_name:
        env["POINTLESSQL_BRANCH"] = branch_name
    env.setdefault("POINTLESSQL_PRINCIPAL", _REPLAY_PRINCIPAL)
    return env


def message_matches_parent(msg: Mapping[str, Any], expected_msg_id: str) -> bool:
    """Return whether an iopub message belongs to the current execution.

    Args:
        msg: A kernel iopub message.
        expected_msg_id: The ``msg_id`` returned by ``kc.execute``.

    Returns:
        ``True`` when the message's ``parent_header.msg_id`` matches.
    """
    return (msg.get("parent_header") or {}).get("msg_id") == expected_msg_id


def is_idle_status(msg_type: str, content: Mapping[str, Any]) -> bool:
    """Return whether a message signals the kernel has gone idle.

    Args:
        msg_type: The iopub message type.
        content: The message ``content`` dict.

    Returns:
        ``True`` for the terminal ``status``/``idle`` message that ends
        the capture loop.
    """
    return msg_type == "status" and content.get("execution_state") == "idle"


def is_output_message(msg_type: str) -> bool:
    """Return whether a message type carries a persistable output frame.

    Args:
        msg_type: The iopub message type.

    Returns:
        ``True`` for ``stream`` / ``execute_result`` / ``display_data``
        / ``error`` messages.
    """
    return msg_type in _OUTPUT_MSG_TYPES


def frame_has_error(frames: list[dict[str, Any]]) -> bool:
    """Return whether any captured frame is an error.

    Args:
        frames: The frames captured for one cell.

    Returns:
        ``True`` when at least one frame's ``msg_type`` is ``"error"``,
        which short-circuits the replay.
    """
    return any(f["msg_type"] == "error" for f in frames)


def serialise_content(msg_type: str, content: Mapping[str, Any]) -> dict[str, Any]:
    """Pick the JSON-friendly subset of a kernel iopub content frame.

    Args:
        msg_type: Kernel message type.
        content: Raw ``content`` dict.

    Returns:
        Trimmed dict matching the load-shape stored in ``notebook_outputs``.
    """
    if msg_type == "stream":
        return {"name": content.get("name") or "stdout", "text": content.get("text") or ""}
    if msg_type == "error":
        return {
            "ename": content.get("ename"),
            "evalue": content.get("evalue"),
            "traceback": content.get("traceback") or [],
        }
    # execute_result / display_data — pass through the mime bundle.
    return {
        "data": content.get("data") or {},
        "execution_count": content.get("execution_count"),
    }


def build_output_frame(
    *,
    content_hash: str,
    kernel_session_id: str,
    output_index: int,
    msg_type: str,
    content: dict[str, Any],
    metadata: Any,
    created_at: str,
) -> dict[str, Any]:
    """Build a persisted output frame in the ``notebook_outputs`` load-shape.

    Args:
        content_hash: The cell identity column.
        kernel_session_id: The worker session id.
        output_index: 0-based index of this output within the cell.
        msg_type: The iopub message type.
        content: The already-serialised content payload.
        metadata: The raw iopub metadata (stored as-is).
        created_at: ISO-8601 capture timestamp.

    Returns:
        A frame dict matching the load-shape used by the outputs loader.
    """
    return {
        "content_hash": content_hash,
        "kernel_session_id": kernel_session_id,
        "output_index": output_index,
        "msg_type": msg_type,
        "content": content,
        "metadata": metadata,
        "created_at": created_at,
    }


def build_error_frame(
    *,
    content_hash: str,
    kernel_session_id: str,
    ename: str,
    evalue: str,
    created_at: str,
    output_index: int = 0,
    traceback: list[Any] | None = None,
) -> dict[str, Any]:
    """Build a single synthetic ``error`` frame for the diff surface.

    Used for the three failure paths (missing base revision, per-cell
    timeout, worker crash) so the replay row always carries something
    renderable.

    Args:
        content_hash: The cell identity column (or a sentinel like
            ``"__worker__"`` for non-cell failures).
        kernel_session_id: The worker session id.
        ename: Synthetic exception class name.
        evalue: Synthetic exception message.
        created_at: ISO-8601 capture timestamp.
        output_index: 0-based output index (always 0 for these frames).
        traceback: Optional traceback lines; defaults to empty.

    Returns:
        An ``error`` frame dict in the load-shape.
    """
    return {
        "content_hash": content_hash,
        "kernel_session_id": kernel_session_id,
        "output_index": output_index,
        "msg_type": "error",
        "content": {"ename": ename, "evalue": evalue, "traceback": traceback or []},
        "metadata": None,
        "created_at": created_at,
    }
