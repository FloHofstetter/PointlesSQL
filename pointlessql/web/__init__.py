"""Web-layer helpers shared between API routes and Jinja templates.

The ``web`` package collects modules that sit between
:mod:`pointlessql.api` (FastAPI route handlers) and the Jinja2
template tree under ``frontend/templates``.  Today it owns the
contextual-help registry consumed by the small ``i``-icon popovers
across the UI plus the shared status-pill class resolver; future
additions land here when they are template-facing rather than
route-facing.
"""

from __future__ import annotations

from pointlessql.web.help import HELP, HelpEntry, get_help
from pointlessql.web.status_styles import status_class

__all__ = [
    "HELP",
    "HelpEntry",
    "get_help",
    "status_class",
]
