"""Table certification state stored as Unity Catalog tags.

A certification is a curated quality signal on a table — either
``certified`` (steward-verified, safe to build on) or ``deprecated``
(plan a migration away).  Instead of a new metadata-DB table, the
state rides on two UC tags so it travels with the securable, shows
up in the regular tags surface, and needs no migration:

* :data:`TAG_KEY` carries the status value.
* :data:`NOTE_KEY` carries an optional free-form note (why it was
  certified, what to migrate to, …).

Reads and writes go through the async UC facade; the pure
:func:`certification_from_tags` mapper is split out so pages that
already fetched the tag list (the table-detail route fetches tags
for its own card) can derive the certification without a second
HTTP round-trip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pointlessql.exceptions import ValidationError

if TYPE_CHECKING:
    from pointlessql.services.unitycatalog import UnityCatalogClient

TAG_KEY = "pointlessql.certification"
"""UC tag key carrying the certification status."""

NOTE_KEY = "pointlessql.certification_note"
"""UC tag key carrying the optional certification note."""

CERTIFICATION_STATUSES: tuple[str, ...] = ("certified", "deprecated")
"""Recognised values of :data:`TAG_KEY`; anything else reads as unset."""


def certification_from_tags(tags: list[Any]) -> dict[str, Any] | None:
    """Derive the certification dict from an already-fetched tag list.

    Args:
        tags: Tag dicts as returned by ``UnityCatalogClient.get_tags``
            (each with ``key`` and ``value`` entries); non-dict
            entries are skipped defensively.

    Returns:
        ``{"status": ..., "note": ...}`` when the status tag holds a
        recognised value, otherwise ``None`` — an unknown or missing
        value reads as "not certified" rather than erroring, so a
        hand-edited tag can never break a page render.
    """
    status: Any = None
    note: Any = None
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        tag_dict = cast("dict[str, Any]", tag)
        if tag_dict.get("key") == TAG_KEY:
            status = tag_dict.get("value")
        elif tag_dict.get("key") == NOTE_KEY:
            note = tag_dict.get("value")
    if status not in CERTIFICATION_STATUSES:
        return None
    return {"status": status, "note": note or None}


async def get_certification(uc: UnityCatalogClient, full_name: str) -> dict[str, Any] | None:
    """Fetch a table's certification state from its UC tags.

    Args:
        uc: The async UC facade.
        full_name: Dotted three-part name of the table.

    Returns:
        ``{"status": ..., "note": ...}`` or ``None`` when the table
        carries no (recognised) certification tag.
    """
    tags = await uc.get_tags("table", full_name)
    return certification_from_tags(tags)


async def set_certification(
    uc: UnityCatalogClient,
    full_name: str,
    status: str | None,
    note: str | None,
) -> dict[str, Any] | None:
    """Set or clear a table's certification via UC tag changes.

    ``status=None`` removes both tags; otherwise the status tag is
    set and the note tag is set or removed depending on whether a
    non-empty note was supplied — a stale note must not survive a
    re-certification that omitted one.

    Args:
        uc: The async UC facade.
        full_name: Dotted three-part name of the table.
        status: ``certified``, ``deprecated``, or ``None`` to clear.
        note: Optional free-form note stored alongside the status.

    Returns:
        The certification derived from the updated tag list, i.e.
        ``None`` after a clear.

    Raises:
        ValidationError: When *status* is neither ``None`` nor one of
            :data:`CERTIFICATION_STATUSES`.
    """
    if status is not None and status not in CERTIFICATION_STATUSES:
        allowed = ", ".join(CERTIFICATION_STATUSES)
        raise ValidationError(f"certification status must be one of: {allowed} (or null)")
    changes: list[dict[str, Any]]
    if status is None:
        changes = [
            {"key": TAG_KEY, "op": "remove"},
            {"key": NOTE_KEY, "op": "remove"},
        ]
    else:
        clean_note = (note or "").strip()
        changes = [{"key": TAG_KEY, "op": "set", "value": status}]
        if clean_note:
            changes.append({"key": NOTE_KEY, "op": "set", "value": clean_note})
        else:
            changes.append({"key": NOTE_KEY, "op": "remove"})
    tags = await uc.update_tags("table", full_name, changes)
    return certification_from_tags(tags)
