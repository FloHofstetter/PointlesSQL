---
title: "Cluster 05 — Phase 16 + 16.5 Delta-Branching spike (dev-log)"
audience: contributor
cluster_id: "05"
phases: "16-16.5"
closed: "2026-04-29"
---

# Cluster 05 — Phase 16 + 16.5 Delta-Branching spike (dev-log)

> Phase 16 (lineage cockpit) + Phase 16.5 Delta-Branching ADR-0003 spike — zero-copy Delta shallow-clone branches per agent-run. E2E walkthrough included.

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Closed**)

### Closed — Phase 16.5: Delta-Branching (2026-04-29)

Seven sub-sprints (16.5.0 spike + 16.5.1 → 16.5.7) close the
Phase-16.5 design opened post-Phase-16.  Per-agent-run zero-copy
isolation: every run gets its own private branch of the target
schema, promote-to-main goes through an approval, discard is
free.

Spike (`docs/adr/0003-delta-branching-spike.md`) found the
zero-copy ideal isn't viable on cloud storage — delta-rs re-anchors
absolute Add-action paths.  Adopted **hybrid strategy**: symlink
on local FS, deep-copy on cloud (opt-in via
`branch.cloud_strategy`; default `"error"` refuses cloud
branching outright until the operator consciously opts into the
storage cost).

What's now in place:

- **`pql.branch(source, name)`** — atomic create flow that
  classifies storage scheme, picks strategy, creates UC schema
  + tables, clones parquets via
  `DeltaTable.create_write_transaction`, stamps
  `pointlessql.branch.*` tags, emits CloudEvent.
- **`pql.branch_discard(branch)`** — idempotent removal, refuses
  promoted / non-branch schemas, `shutil.rmtree`s the local-FS
  storage tree (symlinks unlink without recursing into source).
- **`pql.branch_promote(branch)`** — pointer-swap rename
  (parent → backup, branch → parent).  Per-table conflict
  detection BEFORE any UC mutation; if the parent moved during
  the branch's lifetime, `BranchPromotionConflictError` aborts
  with zero side effects.
- **`pql.branch_promote_preview(branch)`** — dry-run for the UI.
- **Control-Room UI** at `/branches` (admin-only).  List page
  with status / strategy / parent columns + status chips;
  detail page with metadata cards, parent-version table,
  audit-log tail, and an admin-only Danger-zone with Preview /
  Promote / Discard buttons.  Sidebar icon-rail entry under
  `bi-diagram-3`.
- **Auto-cleanup loop** (default-disabled).  Background task in
  the FastAPI lifespan + scheduler kind `"branch_cleanup"`;
  walks UC schemas, picks active branches past
  `branch.auto_cleanup_retention_days`, calls
  `discard_branch_schema` on each.
- **`branch_audit_log` table** (Alembic `o5k7m9p2r4t6`)
  captures create / promote / discard / auto_cleanup rows so
  audit trails survive the UC schema's deletion.
- **Three new CloudEvents** —
  `pointlessql.branch.created.v1`, `.promoted.v1`,
  `.discarded.v1`.

Tests: 14 (branch_tags) + 35 (create) + 10 (discard) +
11 (promote) + 11 (cleanup) = 81 new green pytest cases.
End-to-end coverage in
`docs/e2e-walkthroughs/branches.md` (notebook + browser combo).
Static gates clean — ruff / pyright / pydoclint / alembic.

> from CHANGELOG.md (bucket: **Added**)

### Added — Phase 16: First-Class Rollback (closed 2026-04-27)

Closes the audit→action loop.  Phases 13–15.7 captured the audit
data plane across five lineage axes; Phase 16 adds the missing
governance primitive: a single ``pql.rollback`` call (and matching
``/runs/{id}`` button) that undoes the changes one run made to one
target Delta table.

Per AskUserQuestion 2026-04-27 the original "Delta-Branching +
first-class Rollback" sketch **splits**: Phase 16 ships rollback
only (4 sub-sprints, audit→action loop closed); Delta-Branching
becomes Phase 16.5, blocked on a ``_delta_log/`` shallow-clone
spike that deltalake-python 1.5.0 doesn't expose first-class.

Sprint 16.0 — Housekeeping:

- Alembic ``i9d0e1f2a3b4`` extends
  ``ck_agent_run_operations_op_name`` to include ``'rollback'``.
- ``VALID_OP_NAMES`` in
  ``pointlessql/services/agent_runs/operations.py`` updated.
- ``RollbackError`` family added (``RollbackTargetNotFound``,
  ``RollbackAmbiguous``, ``RollbackInvalid``, ``RollbackStale``)
  for the four refusal modes the rollback primitive surfaces.
- ``_emit_lineage_after_commit`` skips ``op_name="rollback"``
  ops — restored rows are pre-existing, no row-id mapping is
  meaningful.

Sprint 16.1 — ``pql.rollback`` primitive:

- ``pointlessql/pql/_rollback.py`` wraps the verified
  ``DeltaTable.restore(target_version, ...)`` API.  Atomic, writes
  a new commit (CDF-safe), takes a ``CommitProperties.custom_metadata``
  dict that stamps the rollback's commit log with
  ``pointlessql.rollback_of_run`` / ``pointlessql.rollback_of_op_id``.
- All four refusal gates (target-not-found / ambiguous / invalid /
  stale) fire *before* the ``restore`` call, so any refusal leaves
  Delta state untouched.
- ``pql.rollback`` is the public method on the ``PQL`` class.
- 8 tests in ``tests/test_rollback_primitive.py``.

Sprint 16.2 — Cascade detection + preview API:

- ``pointlessql/services/cascade.py`` exports
  ``find_downstream_tables(source_table)`` — walks
  ``lineage_row_edges`` + ``lineage_column_map`` and reports
  distinct downstream targets aggregated across both axes.
- ``GET /api/runs/{run_id}/rollback-preview?target=<fqn>`` returns
  version delta, staleness flag, intervening-writes list,
  multi-op ``op_candidates``, and downstream warnings.  Admin-only.
- 11 tests in ``tests/test_rollback_preview.py``.

Sprint 16.3 — Rollback UI + CloudEvent + replay:

- Rollback card on ``/runs/{id}`` (admin-only): target dropdown,
  preview modal, stale-checkbox gate, downstream warning panel,
  multi-op ordinal picker.  Modal fetches
  ``/rollback-preview`` JSON; submit posts to
  ``POST /api/runs/{run_id}/rollback`` and redirects to the new
  rollback run.
- ``POST /api/runs/{run_id}/rollback`` spawns a fresh
  ``agent_runs`` row, invokes ``pql.rollback`` on a worker thread,
  marks the run ``succeeded`` on completion (or ``failed`` with
  ``denied_reason`` when a refusal fires).  Refusal-to-HTTP map:
  ``RollbackTargetNotFound`` → 404, ``RollbackAmbiguous`` → 422,
  ``RollbackInvalid`` → 422, ``RollbackStale`` → 422.
- New CloudEvent type ``pointlessql.rollback.executed`` joins
  ``AGENT_RUN_EVENT_TYPES`` — no migration needed (existing CHECK
  is on ``outcome``, not event_type).
- ``docs/e2e-walkthroughs/rollback.md`` covers happy + stale paths
  in headful Firefox plus a refusal-mode CLI smoke matrix.
- 6 route tests in ``tests/test_rollback_route.py``.

### Changed — ROADMAP compression: archive completed phases 0-12.8 + 12.10-13.5 (2026-04-27)

`ROADMAP.md` had grown to 5685 lines, dominated by per-sprint
detail of long-completed phases that no current conversation
references.  Compressed to 1983 lines (-65%) by:

- Collapsing **Phases 0–12.8** into a one-line-per-phase summary
  table at the top of the active roadmap.
- Collapsing **Phases 12.10–13.5** into a second summary table
  immediately after Phase 12.9 (which stays full-detail because
  it's `🔜 in progress`).
- Moving the full per-sprint detail of all collapsed phases
  into a new [`ROADMAP_ARCHIVE.md`](ROADMAP_ARCHIVE.md) file
  (3797 lines, append-only).
- Keeping **Phases 14–15.7** (recently closed, last ~30 days)
  at full detail because they're load-bearing for follow-up
  conversations.
- Keeping **Phases 16–20**, **Some-day**, **Icebox**, and the
  out-of-scope footer at full detail.

`CLAUDE.md` updated to mention the archive convention.  The
"How to update this file" section in `ROADMAP.md` now describes
the collapse trigger (>2000 lines or >3 months no-reference)
so future sessions know how and when to roll out further
phases.

No code change.
