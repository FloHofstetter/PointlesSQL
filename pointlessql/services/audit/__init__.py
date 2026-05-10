"""Audit service surface: log + sinks + reads + saved queries.

This package consolidates the six flat audit-related service
modules (audit 255 + audit_sinks 444 + audit_by_table 179
+ saved_audit_queries 469 + read_audit 133 + soyuz_audit 85
= 1565 LOC) that used to live as siblings at
``pointlessql/services/`` root.

Layout:

* ``_core``        — ``log_action`` (write to ``audit_log``) and
  ``cleanup_old_entries`` (the retention pruner).  Private only
  because callers reach for ``log_action`` so often it's
  re-exported at package level.
* ``_read``        — read-side audit recording (``record_read``).
* ``sinks``        — admin-side audit sink CRUD + dispatch.
* ``by_table``     — per-table audit-event reverse index
  (``runs_by_table``).
* ``saved_queries`` — saved-audit-query CRUD + execution.
* ``_soyuz``       — soyuz cross-repo audit-event helpers (small).

The peer audit-aggregator and audit-fts packages stay separate
(they own their own data plane: aggregations + FTS index) and are
not nested under this package.
"""

from __future__ import annotations

from pointlessql.services.audit._core import (
    AuditIntegrityError,
    cleanup_old_entries,
    log_action,
)

__all__ = [
    "AuditIntegrityError",
    "cleanup_old_entries",
    "log_action",
]
