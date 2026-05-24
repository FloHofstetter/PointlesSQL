"""Notebook-widget kernel shim.

Cells that declare a widget (dropdown / slider / text) at the
notebook level
can read its resolved value with ::

    from pointlessql.pql import widgets

    region = widgets.value("region", default="EU")

The WS execute handler pushes the resolved ``{name: value}`` map
into this module's process-local state before every cell run via
:func:`_set_resolved` so the cell sees the *current* value even
when widgets get edited between runs.  When the map carries no
entry for ``name`` the optional ``default`` is returned (matching
Databricks widget-API semantics); the kernel always has a value to
hand back even when the notebook is run outside the editor (e.g.
papermill jobs).
"""

from __future__ import annotations

from typing import Any

# Module-level dict; mutated only via :func:`_set_resolved` so the
# WS handler stays the single writer.  Cell code reads it through
# :func:`value` and :func:`values`.
_RESOLVED: dict[str, Any] = {}


def _set_resolved(values: dict[str, Any]) -> None:
    """Replace the resolved-widget map (called by the WS handler).

    Args:
        values: Fresh ``{name: value}`` snapshot.  Pass an empty
            dict to clear (e.g. when the user removes all widgets).
    """
    _RESOLVED.clear()
    if values:
        _RESOLVED.update(values)


def value(name: str, default: Any = None) -> Any:
    """Return the resolved value for *name*, or *default* when unset.

    Args:
        name: Widget name (matches ``notebook_widgets.name``).
        default: Returned when no widget by *name* is bound — keeps
            ``papermill`` runs of the same ``.py`` outside the editor
            from raising ``KeyError`` when the operator forgot a
            ``-p`` override.

    Returns:
        The widget's current resolved value, or *default*.
    """
    return _RESOLVED.get(name, default)


def values() -> dict[str, Any]:
    """Return a shallow copy of every currently-bound widget value.

    Returns:
        A snapshot ``{name: value}`` dict; safe to mutate without
        affecting the kernel state.
    """
    return dict(_RESOLVED)


__all__ = ["_set_resolved", "value", "values"]
