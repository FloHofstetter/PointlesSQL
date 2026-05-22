"""Per-row + per-column lineage trace routes — split per surface.

The pre-Phase-110 layout collapsed every lineage HTTP surface into one
~780 LOC ``views.py`` module.  Phase 110.4 split it per route family so
each surface owns its own file with the helpers it needs:

* :mod:`._helpers`       — shared auth gate, op-metadata join, value-
  change / CDF-event attachment, PII masking, source-file enrichment.
* :mod:`._row_trace`     — ``/api/lineage/row-trace`` + the HTML page.
* :mod:`._column_trace`  — ``/api/lineage/column-trace`` + the HTML
  page (and its row-trace-style projection helpers).
* :mod:`._value_changes` — ``/api/lineage/value-changes``.
* :mod:`._index`         — ``GET /lineage`` explorer landing.

``router`` mounts each sub-router under the shared ``lineage`` tag.
``pointlessql.api.lineage.__init__`` imports the assembled router
from this package — call-sites need no edits.

Phase 110.4 also fixed a latent Python-2-style ``except A, B:`` in
``_helpers._enrich_with_source_file`` that caught only one of the two
exception types and bound the other to the local name; the new code
uses the explicit tuple form.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.lineage.views._column_trace import router as _column_trace_router
from pointlessql.api.lineage.views._index import router as _index_router
from pointlessql.api.lineage.views._row_trace import router as _row_trace_router
from pointlessql.api.lineage.views._value_changes import router as _value_changes_router

router = APIRouter()
router.include_router(_row_trace_router)
router.include_router(_column_trace_router)
router.include_router(_value_changes_router)
router.include_router(_index_router)

__all__ = ["router"]
