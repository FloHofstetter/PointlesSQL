"""Per-notebook ipykernel subprocess manager for the native editor.

Phase 12.6 Sprint 59 — second layer of the native notebook story.
One ipykernel subprocess runs per ``(user_id, notebook_path)`` pair
(ADR 0001 "kernel identity" decision: VSCode-style, not Jupyter-
classic-style-per-tab). Two browser tabs of the same ``.py`` share
one kernel, one namespace, one ``kernel_session_id``.

Sprint 77 split the original 472-LOC ``kernel_session.py`` into:

* :mod:`.messages` — :class:`KernelMessage`, :class:`_Subscription`.
* :mod:`.session` — :class:`KernelSession` lifecycle + ZMQ pump.
* :mod:`.registry` — :class:`KernelRegistry` + :func:`drain` helper.

This package re-exports the public surface so existing
``from pointlessql.services import kernel_session as kernel_session_service``
continues to resolve every symbol the API layer needs.
"""

from __future__ import annotations

from pointlessql.services.kernel_session.messages import (
    KernelMessage,
    Subscription,
)
from pointlessql.services.kernel_session.registry import (
    KernelRegistry,
    drain,
)
from pointlessql.services.kernel_session.session import KernelSession

__all__ = [
    "KernelMessage",
    "KernelRegistry",
    "KernelSession",
    "Subscription",
    "drain",
]
