"""CRUD + lifecycle helpers for the query alerts surface.

Visibility + mutation rules mirror :mod:`pointlessql.services.saved_queries`:
owner + admin see every row; anyone else gets 404 via the API layer.
The scheduler drives alert firing through a hidden backing
:class:`~pointlessql.models.Job` row (``kind="alert_check"``) created
when an alert is first activated and deleted when the alert is
removed — see :func:`pointlessql.services.alerts.crud._sync_backing_job`.

The package is composed of four sibling modules:

* :mod:`.crud` — slug / serialisation helpers, backing-Job lifecycle,
  CRUD (``create_alert``, ``list_visible``, ``get_by_slug``,
  ``update_by_slug``, ``delete_by_slug``).
* :mod:`.destinations` — webhook + feed destinations
  (``add_destination``, ``delete_destination``).
* :mod:`.events` — event recording + listing + pruning
  (``record_event``, ``set_event_outcome``,
  ``list_events_for_alert``, ``list_events_for_owner``,
  ``prune_events_older_than``).
* :mod:`.conditions` — pure helpers (``evaluate_condition``,
  ``build_cloudevent``).

The package re-exports the full public surface so existing
``from pointlessql.services import alerts as alerts_service`` callers
keep working unchanged.
"""

from __future__ import annotations

from pointlessql.services.alerts.conditions import (
    build_cloudevent,
    evaluate_condition,
)
from pointlessql.services.alerts.crud import (
    create_alert,
    delete_by_slug,
    get_by_slug,
    list_visible,
    make_slug,
    update_by_slug,
)
from pointlessql.services.alerts.destinations import (
    add_destination,
    delete_destination,
)
from pointlessql.services.alerts.events import (
    list_events_for_alert,
    list_events_for_owner,
    prune_events_older_than,
    record_event,
    set_event_outcome,
)

__all__ = [
    "add_destination",
    "build_cloudevent",
    "create_alert",
    "delete_by_slug",
    "delete_destination",
    "evaluate_condition",
    "get_by_slug",
    "list_events_for_alert",
    "list_events_for_owner",
    "list_visible",
    "make_slug",
    "prune_events_older_than",
    "record_event",
    "set_event_outcome",
    "update_by_slug",
]
