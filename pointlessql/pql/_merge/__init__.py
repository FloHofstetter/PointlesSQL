# pyright: reportPrivateUsage=false
"""``pql.merge()`` — thin facade over Delta MERGE, split per concern.

The pre-Phase-111 layout collapsed every concern into one ~770 LOC
``_merge.py`` module.  Phase 111.2 split it along the natural axes:

* :mod:`._constants`  — ``LINEAGE_ROW_ID_COLUMN``, ``MergeStrategy``,
  SCD-2 audit column names.
* :mod:`._resolve`    — target-location resolution + source-frame
  conversion + Arrow coercion (re-exports ``_get_table`` from
  soyuz-catalog-client so tests that monkeypatch
  ``pointlessql.pql._merge._get_table`` keep working).
* :mod:`._strategies` — ``_do_upsert`` / ``_do_scd2`` /
  ``_augment_for_scd2``.
* :mod:`._lineage`    — ``_capture_value_changes`` /
  ``_detect_rejects`` / ``_prepare_lineage``.
* :mod:`._stats`      — ``_merge_rows_affected`` / ``_stats_for_audit``.
* :mod:`._main`       — ``merge_table`` end-to-end orchestration.

The merge primitive is one of the Medallion building blocks that
turn an agent run into a Medallion lakehouse: ``autoload`` lifts
files into bronze, ``merge`` consolidates bronze → silver, and a SQL
aggregation produces gold.  Silver is where upsert semantics matter
— gold writes are typically full-overwrite or append-truncate.

Two strategies in scope:

* ``upsert`` — match on the supplied keys; update all non-key
  columns from source on match, insert new rows otherwise.
  Standard SCD-1 semantics.
* ``scd2`` — append-only history.  Source rows are augmented with
  ``_valid_from`` / ``_valid_to`` / ``_is_current`` columns; a key
  match closes the currently-open target row (``_valid_to=now``,
  ``_is_current=false``) and appends a new current row.

The audit column names are hardcoded in :mod:`._constants` rather
than read from :mod:`pointlessql.conventions` because they are
silver-layer specific (audit columns in conventions are bronze-
specific).
"""

from __future__ import annotations

from pointlessql.pql._merge._constants import (
    LINEAGE_ROW_ID_COLUMN,
    SCD2_IS_CURRENT,
    SCD2_VALID_FROM,
    SCD2_VALID_TO,
    MergeStrategy,
)
from pointlessql.pql._merge._lineage import _capture_value_changes, _detect_rejects
from pointlessql.pql._merge._main import merge_table

# Re-export ``_get_table`` so tests that monkeypatch
# ``pointlessql.pql._merge._get_table`` keep reaching the resolver
# call site after the split.
from pointlessql.pql._merge._resolve import _get_table

__all__ = [
    "LINEAGE_ROW_ID_COLUMN",
    "MergeStrategy",
    "SCD2_IS_CURRENT",
    "SCD2_VALID_FROM",
    "SCD2_VALID_TO",
    "_capture_value_changes",
    "_detect_rejects",
    "_get_table",
    "merge_table",
]
