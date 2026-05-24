# pyright: reportUnusedClass=false
"""Notebook widget resolution for the PQL façade (Phase 99)."""

from __future__ import annotations

from typing import Any

from pointlessql.pql._pql_base import PQLBase as _PQLBase


class _WidgetsMixin(_PQLBase):
    """Resolve notebook widget values from the metadata DB."""

    def widgets(self) -> dict[str, Any]:
        """Return the resolved widget values for the active notebook.

        Phase 99 — kernel-side shim over the
        :mod:`pointlessql.services.notebook.widgets` resolver.  Reads
        the active notebook UUID from
        :func:`pointlessql.pql.context.current_notebook_id`; outside
        the notebook editor (interactive REPL, subprocess agent runs
        without the env-bridge) the call returns an empty dict so
        ``params = pql.widgets()`` is safe to write unconditionally.

        Returns:
            Mapping ``widget_name → value``.  Values flow from the
            ``notebook_widgets`` table — ``default_value`` overridden
            by anything the editor's widgets-panel submitted on the
            current execute (the WS bridge feeds the overrides into
            the metadata DB on Save; per-execute form-state overrides
            are not yet wired through the kernel context).  When no
            notebook context is active the mapping is empty.
        """
        from pointlessql.config import get_settings
        from pointlessql.db import get_session_factory, init_db
        from pointlessql.pql.context import current_notebook_id
        from pointlessql.services.notebook.widgets import (
            resolve_widget_values,
        )

        notebook_id = current_notebook_id()
        if not notebook_id:
            return {}
        try:
            factory = get_session_factory()
        except RuntimeError:
            # Kernel subprocess bypasses the FastAPI lifespan; the
            # session factory is unbound on first widget read.
            # ``init_db`` is idempotent — re-running against the same
            # URL is a no-op after the first call.
            init_db(get_settings().db.url)
            factory = get_session_factory()
        with factory() as session:
            return resolve_widget_values(session, notebook_id=notebook_id)
