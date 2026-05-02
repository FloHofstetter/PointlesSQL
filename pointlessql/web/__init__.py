"""Web-layer helpers shared between API routes and Jinja templates.

The ``web`` package collects modules that sit between
:mod:`pointlessql.api` (FastAPI route handlers) and the Jinja2
template tree under ``frontend/templates``.  Today it owns the
contextual-help registry consumed by the small ``i``-icon popovers
across the UI; future additions land here when they are template-
facing rather than route-facing.
"""
