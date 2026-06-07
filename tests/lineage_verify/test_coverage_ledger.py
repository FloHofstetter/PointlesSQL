"""Coverage ledger: every PQL operator is accounted for in the lineage suite.

A registry classifies each public operator on the PQL data-op + governance
mixins as ``property`` (verified by a property class), ``deferred`` (produces
lineage not yet property-covered, with a reason), or ``n/a`` (read-only /
produces no row/column/value lineage).  The meta-test introspects the live
mixins and fails if a new operator appears without an entry — so a future
operator cannot silently ship without a lineage-coverage decision.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from pointlessql.pql._pql_aggregate import _AggregateMixin
from pointlessql.pql._pql_autoload import _AutoloadMixin
from pointlessql.pql._pql_governance import _GovernanceMixin
from pointlessql.pql._pql_read import _ReadMixin
from pointlessql.pql._pql_sql import _SqlMixin
from pointlessql.pql._pql_update_delete import _UpdateDeleteMixin
from pointlessql.pql._pql_vector import _VectorMixin
from pointlessql.pql._pql_write import _WriteMixin

# The lineage-relevant mixins.  ``_ListMixin`` / ``_WidgetsMixin`` are
# deliberately excluded — they are UI/listing helpers that touch no Delta
# data and produce no row/column/value lineage.
_LINEAGE_MIXINS = (
    _ReadMixin,
    _WriteMixin,
    _SqlMixin,
    _VectorMixin,
    _UpdateDeleteMixin,
    _AggregateMixin,
    _AutoloadMixin,
    _GovernanceMixin,
)

# operator -> (status, note).  status is "property" | "deferred" | "n/a".
OPERATOR_COVERAGE: dict[str, tuple[str, str]] = {
    # --- property-covered: produce row/column/value lineage we verify ---
    "write_table": ("property", "test_write_table_lineage_holds_all_invariants"),
    "sql": ("property", "test_sql_projection_preserves_lineage (+ acceptance + opt-out)"),
    "merge": ("property", "test_merge_lineage_holds_all_invariants"),
    "aggregate": ("property", "test_aggregate_fanin_lineage_holds_all_invariants"),
    "update": ("property", "test_update_value_changes_are_real"),
    # --- deferred: produce lineage, not yet a property class (with reason) ---
    "delete": ("deferred", "removes rows; emits no new row/column/value edges"),
    "autoload": (
        "deferred",
        "medallion root: mints initial _lineage_row_id from file sha+offset; "
        "id-determinism property needs file fixtures (future)",
    ),
    "rollback": (
        "deferred",
        "restores a prior version; row-id stability across versions is a "
        "governance property distinct from the 6 invariants",
    ),
    "branch": ("deferred", "copies parquet + Delta log; row ids preserved (governance stability)"),
    "branch_promote": ("deferred", "pointer-swap promotion; ids stable (governance)"),
    # --- n/a: read-only or no row/column/value lineage ---
    "table": ("n/a", "read-only"),
    "table_at_version": ("n/a", "read-only time-travel"),
    "table_at_timestamp": ("n/a", "read-only time-travel"),
    "table_as_of_event_time": ("n/a", "read-only bitemporal"),
    "vector_index": ("n/a", "builds an HNSW index; no row/column/value lineage"),
    "vector_search": ("n/a", "read-only search"),
    "training_context": ("n/a", "ML training context manager; no lineage"),
    "branch_promote_preview": ("n/a", "dry-run conflict check; no mutation"),
    "branch_discard": ("n/a", "deletes a branch; no lineage"),
}

_VALID_STATUSES = {"property", "deferred", "n/a"}


def _live_operators() -> set[str]:
    """Return the public operator method names defined on the lineage mixins."""
    ops: set[str] = set()
    for mixin in _LINEAGE_MIXINS:
        for name in vars(mixin):
            if name.startswith("_"):
                continue
            attr: Any = inspect.getattr_static(mixin, name)
            if isinstance(attr, (staticmethod, classmethod)) or inspect.isfunction(attr):
                ops.add(name)
    return ops


@pytest.mark.lineage_verify
def test_every_operator_is_classified() -> None:
    """Every live PQL operator has a coverage-ledger entry (no silent gaps)."""
    live = _live_operators()
    missing = live - set(OPERATOR_COVERAGE)
    assert not missing, (
        f"new PQL operator(s) without a lineage coverage-ledger entry: {sorted(missing)}; "
        "add a property class or classify as deferred/n/a in OPERATOR_COVERAGE"
    )


@pytest.mark.lineage_verify
def test_ledger_has_no_stale_entries() -> None:
    """Every ledger entry maps to a real operator (the ledger stays honest)."""
    stale = set(OPERATOR_COVERAGE) - _live_operators()
    assert not stale, f"coverage-ledger entries with no matching operator: {sorted(stale)}"


@pytest.mark.lineage_verify
def test_ledger_statuses_are_valid() -> None:
    """Every ledger status is one of property / deferred / n/a with a note."""
    for op, (status, note) in OPERATOR_COVERAGE.items():
        assert status in _VALID_STATUSES, f"{op}: invalid status {status!r}"
        assert note, f"{op}: missing coverage note"
