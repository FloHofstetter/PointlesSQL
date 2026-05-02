"""Centralised status-to-Bootstrap-badge-class mapping.

Single source of truth shared by:

* Server-rendered Jinja templates via the ``status_class`` global
  registered in :mod:`pointlessql.api.main`.
* Browser sidebars via ``frontend/js/components/sidebars/_base.js``
  consumers, which used to reimplement the same lookup table per
  panel.

Adding a new status only requires a single edit here.  Unknown
statuses fall back to ``secondary`` so the surface degrades to a
neutral gray pill rather than throwing.
"""

from __future__ import annotations

STATUS_BADGE_CLASS: dict[str, str] = {
    # Terminal success
    "ok": "success",
    "succeeded": "success",
    "completed": "success",
    "approved": "success",
    "promoted": "success",
    "ready": "success",
    "READY": "success",
    # In-flight
    "running": "info",
    "queued": "info",
    "active": "info",
    # Failure
    "error": "danger",
    "errored": "danger",
    "failed": "danger",
    "rolled_back": "danger",
    "FAILED_REGISTRATION": "danger",
    # Awaiting human
    "needs_approval": "warning",
    "pending_approval": "warning",
    "PENDING_REGISTRATION": "warning",
    # Cold
    "denied": "secondary",
    "discarded": "secondary",
    "cancelled": "secondary",
    "paused": "secondary",
    "disabled": "secondary",
}

# Statuses whose badge needs ``text-dark`` because the underlying
# Bootstrap colour is too pale to carry white text.
_DARK_TEXT_VARIANTS: set[str] = {"warning", "info"}


def status_class(status: str | None) -> str:
    """Return the full Bootstrap badge class string for ``status``.

    Args:
        status: A status string from the audit / lineage / lifecycle
            domain (e.g. ``running``, ``READY``, ``rolled_back``).

    Returns:
        ``bg-<variant>`` (plus ``text-dark`` when the variant is
        light enough to demand it), or ``bg-secondary`` for an
        unknown status.
    """
    variant = STATUS_BADGE_CLASS.get(status or "", "secondary")
    base = f"bg-{variant}"
    if variant in _DARK_TEXT_VARIANTS:
        return f"{base} text-dark"
    return base
