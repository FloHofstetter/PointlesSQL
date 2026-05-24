"""Per-run notebook context.

Notebook execution carries side-channel context the kernel needs
but cell source code shouldn't reach for directly:

* the bound Delta branch (``POINTLESSQL_BRANCH``);
* the notebook UUID (``POINTLESSQL_NOTEBOOK_ID``);
* the agent-run id (``POINTLESSQL_AGENT_RUN_ID``).

This module is the kernel-side read surface.  The WS execute handler
pushes the per-execute snapshot via :func:`_set_context` before each
cell runs so a binding edited between cells is reflected on the next
run without restarting the kernel.  Startup-time env vars are still
honoured as the initial value, matching the long-standing
``POINTLESSQL_AGENT_RUN_ID`` env-bridge pattern.

The branch routing itself lives in :class:`PQL` (it consults
:func:`current_branch` on every ``read_table`` / ``write_table`` and
remaps the schema segment of the FQN); this module owns nothing more
than the dict.
"""

from __future__ import annotations

import os

# Module-level state.  Initialised from env at import time; updated
# at every cell execute via :func:`_set_context` so a mid-session
# binding change is picked up on the next run without a kernel
# restart.
_CTX: dict[str, str | None] = {
    "branch": os.environ.get("POINTLESSQL_BRANCH") or None,
    "notebook_id": os.environ.get("POINTLESSQL_NOTEBOOK_ID") or None,
    "agent_run_id": os.environ.get("POINTLESSQL_AGENT_RUN_ID") or None,
}


def _set_context(
    *,
    branch: str | None = None,
    notebook_id: str | None = None,
    agent_run_id: str | None = None,
) -> None:
    """Replace the per-execute context snapshot.

    The WS handler calls this in a silent execute prelude before
    each cell so the kernel sees the *current* binding even when
    bindings change between cells.

    Args:
        branch: Active branch name (``None`` clears).
        notebook_id: Notebook UUID for binding lookups.
        agent_run_id: Active agent-run id.
    """
    _CTX["branch"] = branch or None
    _CTX["notebook_id"] = notebook_id or None
    _CTX["agent_run_id"] = agent_run_id or None


def current_branch() -> str | None:
    """Return the bound branch name, or ``None`` for the main lakehouse."""
    return _CTX.get("branch")


def current_notebook_id() -> str | None:
    """Return the active notebook UUID, or ``None`` outside the editor."""
    return _CTX.get("notebook_id")


def current_agent_run_id() -> str | None:
    """Return the active agent-run id, or ``None`` for interactive runs."""
    return _CTX.get("agent_run_id")


def snapshot() -> dict[str, str | None]:
    """Return a shallow copy of the full context dict.

    Returns:
        ``{"branch": ..., "notebook_id": ..., "agent_run_id": ...}``.
    """
    return dict(_CTX)


__all__ = [
    "_set_context",
    "current_agent_run_id",
    "current_branch",
    "current_notebook_id",
    "snapshot",
]
