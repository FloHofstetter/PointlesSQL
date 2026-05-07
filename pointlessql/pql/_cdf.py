"""Change Data Feed (CDF) bootstrap helpers.

's value-level lineage rests on Delta Lake's Change Data
Feed: when a table has the ``delta.enableChangeDataFeed=true`` table
property, every commit emits ``insert`` / ``update_preimage`` /
``update_postimage`` / ``delete`` events that
``DeltaTable.load_cdf()`` can replay.  PointlesSQL only exposes the
preimage/postimage pairs through ``pql.merge(track_value_changes=True)``,
but the *property* must be on the table from the moment value
tracking might be requested — and the cheapest place to set it is
right after the table is created.

The tracking property is enabled going forward only.  CDF events for
commits that happened *before* the property was set are not
recoverable — that is a Delta-Lake-level limitation, not a
PointlesSQL one.

This module wraps two operations:

* :func:`cdf_creation_config` returns the ``configuration={...}``
  dict to pass to ``deltalake.write_deltalake`` on the create path.
  Centralises the literal so the three primitives don't repeat it.
* :func:`ensure_cdf_enabled` is the retroactive escape hatch:
  if a table was created before  (or by an external writer
  that didn't pass the configuration), call this helper before
  ``load_cdf()`` and the property will be flipped via ``ALTER TABLE``
  in deltalake's :class:`TableAlterer`.  Idempotent — a table that
  already has CDF enabled is a no-op.
"""

from __future__ import annotations

import logging

import deltalake

logger = logging.getLogger(__name__)

CDF_TBLPROP = "delta.enableChangeDataFeed"


def cdf_creation_config() -> dict[str, str]:
    """Return the table-property dict that turns CDF on at table creation.

    Use as ``configuration=cdf_creation_config()`` on the first
    ``deltalake.write_deltalake`` call against a fresh storage path.
    On subsequent appends the configuration kwarg is harmless (it is
    silently ignored), but for clarity the call sites pass it only on
    the create branch.

    Returns:
        Single-entry dict mapping the CDF property name to its
        string-typed ``"true"`` value.  Delta requires a string here,
        not a Python bool.
    """
    return {CDF_TBLPROP: "true"}


def ensure_cdf_enabled(target_location: str) -> bool:
    """Best-effort enable of CDF on an existing Delta table.

    For tables created before , the CDF property is not on
    by default.  Calling ``DeltaTable.load_cdf()`` against such a
    table raises a deltalake error.  This helper opens the table,
    checks the configuration, and — if CDF is missing — issues an
    ``ALTER TABLE`` via the :class:`TableAlterer` so the *next*
    commit lands in the CDF stream.

    Best-effort by design: any failure is logged and yields ``False``
    so the caller can skip value-change capture for the op rather
    than blocking the merge.

    Args:
        target_location: Filesystem path or URI of the Delta table.

    Returns:
        ``True`` when the property is now set (whether already-on or
        just-set by this call).  ``False`` when the helper could not
        reach the table or the alter failed — e.g. the path doesn't
        exist or deltalake raised at open time.
    """
    try:
        dt = deltalake.DeltaTable(target_location)
    except Exception:  # noqa: BLE001 — best-effort
        logger.info(
            "ensure_cdf_enabled: cannot open Delta table at %s",
            target_location,
            exc_info=True,
        )
        return False

    try:
        config = dict(dt.metadata().configuration or {})
    except Exception:  # noqa: BLE001 — best-effort
        logger.info(
            "ensure_cdf_enabled: metadata() failed for %s",
            target_location,
            exc_info=True,
        )
        return False

    if config.get(CDF_TBLPROP, "").lower() == "true":
        return True

    try:
        dt.alter.set_table_properties(cdf_creation_config())
        return True
    except Exception:  # noqa: BLE001 — best-effort
        logger.info(
            "ensure_cdf_enabled: set_table_properties failed for %s",
            target_location,
            exc_info=True,
        )
        return False
