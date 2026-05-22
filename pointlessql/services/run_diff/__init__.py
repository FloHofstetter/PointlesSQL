"""Op-by-op + tool-call-by-tool-call + lineage diff service — split per concern.

The pre-Phase-111 layout collapsed every helper into one ~724 LOC
``run_diff.py`` module.  Phase 111.3 split it along the natural axes:

* :mod:`._serialize`  — per-row JSON serializers + one-layer
  ``_params_diff``.
* :mod:`._align`      — ordinal + content alignment for ops and tool
  calls + the per-slot diff helpers.
* :mod:`._detail`     — ``build_detail_diff`` (the cap-bounded
  operations + tool-calls payload) and the ``AlignmentMode`` alias.
* :mod:`._lineage`    — ``build_lineage_diff`` volumes +
  ``build_value_changes_diff`` cell-level + the bucket loaders +
  ``_shift_dict``.
* :mod:`._column`     — ``build_column_lineage_diff`` edge-level
  delta + ``_column_edge_key``.

Two alignment strategies, exposed through the ``align`` parameter on
:func:`build_detail_diff`:

* ``"ordinal"`` — pair op[i] from A with op[i] from B.  Fast,
  deterministic, but sensitive to insertions (one extra op in A
  shifts every later slot).
* ``"content"`` — greedy match on ``(op_name, target_table)`` (or
  ``tool_name`` for tool calls) with the smallest ordinal distance
  breaking ties.  More robust for "same notebook, different inputs"
  comparisons.

Diff fields are deliberately minimal — agents reading the diff
need actionable signal, not exhaustive byte-by-byte comparison.
``params_diff`` walks one JSON layer (added / removed / changed
keys); deeper structures are summarised by length.  The detail
diff caps the combined slot count at 500 to keep an LLM
transcript bounded; consumers can paginate if they really need more.
"""

from __future__ import annotations

from pointlessql.services.run_diff._column import build_column_lineage_diff
from pointlessql.services.run_diff._detail import AlignmentMode, build_detail_diff
from pointlessql.services.run_diff._lineage import (
    build_lineage_diff,
    build_value_changes_diff,
)

__all__ = [
    "AlignmentMode",
    "build_column_lineage_diff",
    "build_detail_diff",
    "build_lineage_diff",
    "build_value_changes_diff",
]
