"""Translate PointlesSQL entities into Cedar request UIDs.

Cedar wants ``Type::"id"`` strings for principal / action / resource.
This module names the conversion rules so every call-site shares the
same UID shape:

* Principals are ``User::"<id>"`` (or ``User::"anonymous"``).
* Actions are ``Action::"<verb>"`` (``read``, ``write``, ``consume``).
* Resources are ``DataProduct::"<catalog>.<schema>"`` or
  ``OutputPort::"<id>"``.

Resource ids never contain the workspace prefix — Cedar policies are
loaded per-workspace and the workspace boundary is enforced *before*
the engine call, not inside the policy expression.
"""

from __future__ import annotations

from typing import Any

#: Cedar action UIDs the platform may evaluate against.
CEDAR_ACTIONS: tuple[str, ...] = ("read", "write", "consume")


def principal_uid(user: dict[str, Any] | None) -> str:
    """Return the Cedar principal UID for *user* or anonymous."""
    if not user or user.get("id") is None:
        return 'User::"anonymous"'
    return f'User::"{int(user["id"])}"'


def cedar_action(verb: str) -> str:
    """Return the Cedar action UID for *verb*.

    Args:
        verb: One of :data:`CEDAR_ACTIONS`.  Unknown verbs pass
            through unchanged so callers can extend the action set
            without an engine release.

    Returns:
        ``Action::"verb"`` string ready for ``cedar_evaluate``.
    """
    return f'Action::"{verb}"'


def build_resource_id(
    *,
    resource_type: str,
    catalog: str | None = None,
    schema: str | None = None,
    id_value: str | int | None = None,
) -> str:
    """Return the Cedar resource UID for the given identifiers.

    Args:
        resource_type: One of ``DataProduct``, ``OutputPort``,
            ``Table``.
        catalog: UC catalog name when the resource is product-shaped.
        schema: UC schema name when the resource is product-shaped.
        id_value: Database PK when the resource is row-shaped
            (``OutputPort``).

    Returns:
        ``Type::"id"`` string.  Missing identifiers fall back to
        ``"unknown"`` so the engine still has a UID to match against.
    """
    if resource_type == "DataProduct":
        ref = f"{catalog}.{schema}" if catalog and schema else "unknown"
        return f'DataProduct::"{ref}"'
    if id_value is not None:
        return f'{resource_type}::"{id_value}"'
    return f'{resource_type}::"unknown"'
