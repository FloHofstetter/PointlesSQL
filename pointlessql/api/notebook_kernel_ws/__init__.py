"""WebSocket bridging browser cells to per-notebook ipykernel subprocesses — split per layer.

The pre-Phase-110 layout collapsed every helper, handler, pump, and the
WS endpoint itself into one ~835 LOC ``notebook_kernel_ws.py`` module.
Phase 110.6 split it along the natural layering:

* :mod:`._protocol` — JSON-RPC envelope helpers (``send_error``,
  ``user_can_use_editor``, ``RESERVED_BOOTSTRAP_HASH`` sentinel).
* :mod:`._pump`     — ZMQ-channel pump (``pump_subscription`` +
  ``handle_kernel_message``) with the persistence side-effect
  (``notebook_outputs`` append + ``query_history`` finalise on
  ``execute_reply``).
* :mod:`._handlers` — JSON-RPC method handlers (``handle_execute``,
  ``handle_interrupt``, ``handle_restart``).
* :mod:`._route`    — the WebSocket endpoint that resolves user +
  notebook path, spins up pump tasks, and dispatches inbound frames.

``router`` is re-exported here so ``api._bootstrap._routers`` keeps
its import path unchanged.
"""

from __future__ import annotations

from pointlessql.api.notebook_kernel_ws._route import router

__all__ = ["router"]
