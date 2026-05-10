"""ORM models for the data-observability subsystem: lineage + CDF + external writes.

Four flat sibling modules consolidated into one
``pointlessql.models.lineage`` package whose ``__init__.py``
re-exports the 9 public symbols.

Layout:

* ``_core``     — :class:`LineageRowEdge`, :class:`LineageRowReject`,
                  :class:`LineageColumnMap`, :class:`LineageValueChange`,
                  + ``REJECT_REASONS`` / ``TRANSFORM_KINDS`` constants.
* ``_inbound``  — :class:`ExpectedLineageInbound` (admin-curated
                  expected-producer registry for ingest gating).
* ``_external`` — :class:`UnattributedWrite` (the "Delta commit had
                  no PointlesSQL operation row" detector table).
* ``_cdf``      — :class:`CdfTailEvent` + :class:`CdfTailSubscription`
                  (Change Data Feed tail subscriptions + per-event rows).
"""

from __future__ import annotations

from pointlessql.models.lineage._cdf import CdfTailEvent, CdfTailSubscription
from pointlessql.models.lineage._core import (
    REJECT_REASONS,
    TRANSFORM_KINDS,
    LineageColumnMap,
    LineageRowEdge,
    LineageRowReject,
    LineageValueChange,
)
from pointlessql.models.lineage._external import UnattributedWrite
from pointlessql.models.lineage._inbound import ExpectedLineageInbound

__all__ = [
    "REJECT_REASONS",
    "TRANSFORM_KINDS",
    "CdfTailEvent",
    "CdfTailSubscription",
    "ExpectedLineageInbound",
    "LineageColumnMap",
    "LineageRowEdge",
    "LineageRowReject",
    "LineageValueChange",
    "UnattributedWrite",
]
