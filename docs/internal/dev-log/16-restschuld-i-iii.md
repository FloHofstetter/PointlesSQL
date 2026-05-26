---
title: "Cluster 16 — Phase 87–89 Restschuld I–III (dev-log)"
audience: contributor
cluster_id: "16"
phases: "87-89"
closed: "2026-05-16"
---

# Cluster 16 — Phase 87–89 Restschuld I–III (dev-log)

> Phase 87 (config/_settings + repo_assets + audit/_legacy splits), Phase 88 (SQL/dbt cluster: _dispatcher + editor + dbt/routes), Phase 89 (Restschuld III endgame: _polymorphic_handlers 9-axis split + main.py lifespan extraction).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 89 Restschuld III (endgame) closed (2026-05-16).**
  Two highest-risk file splits from the Phase-86 trim list,
  closing the modularisation wave:

  1. **89.1** — ``social_routes/_polymorphic_handlers.py`` 2231
     LOC → 9-axis sub-package.  The largest single Python file
     in the repo splits into modules per behavioural axis
     (comments, endorsements, follows, entity reactions, comment
     reactions, stars, READMEs, reviews) plus a shared
     constants/helpers/serialisers module.  ``__init__.py``
     re-exports every public handler the 7 sibling route modules
     already import — call sites are unchanged.  The flat
     ``_polymorphic_handlers.py`` is deleted outright.
  2. **89.2** — ``main.py`` lifespan 358 LOC → new
     ``api/_bootstrap/_lifespan.py`` behind a ``make_lifespan(
     templates)`` factory.  ``main.py`` shrinks 767 → 374 LOC.
     The teardown's 14× repeated cancel-and-await ritual now
     lives in a single ``_cancel_task`` helper.  App.state
     contracts and background-task / subprocess shutdown order
     are byte-identical.

  Pyright stays at 6 / 533 throughout; ruff / pyright /
  pydoclint / alembic all green.  Combined with Phases 87 + 88,
  the Restschuld wave eliminates the ten 1000-LOC hot-path files
  identified in the Phase-86 audit.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 88 Restschuld II (SQL/dbt cluster) closed (2026-05-16).**
  Three medium-risk file splits, three commits on the same
  ``phase-87…`` branch as Phase 87:

  1. **88.1** — ``sql/_dispatcher.py`` 1009 LOC → 8-module package
     (``_types``, ``_privilege``, ``_agent_run``, ``_ast_extract``,
     ``_select``, ``_dml``, ``_ddl``, ``__init__``).  Cross-module
     helpers lost their leading underscore so pyright stops
     tripping on cross-package private access.  External callers
     (saved_views_routes, editor) updated to import from the new
     sub-modules.
  2. **88.2** — ``sql/editor.py`` 1127 LOC → 8-module package
     (``_helpers``, ``_execute``, ``_batch``, ``_cancel``,
     ``_download``, ``_explain``, ``_page``, ``__init__``).  The
     dispatcher's lazy ``from pointlessql.api.sql.editor import
     run_sql_sync`` still resolves through the package facade.
  3. **88.3** — ``dbt/routes.py`` 1061 LOC → 5 sibling modules:
     ``_executor``, ``_lifecycle``, ``_audit``, ``_rollback``,
     ``_run_test``.  Routes module shrinks to 8 handlers (~350
     LOC).  Three test files re-targeted at the new sibling
     modules for their monkeypatches.

  Pyright count stays at 6 errors / 533 warnings at every commit;
  ruff / pyright / pydoclint / alembic all green.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 87 Restschuld I (config + repo_assets + audit) closed
  (2026-05-16).**  First of three follow-up phases to clear the
  trim list from Phase 86.  Three low-risk strands; ruff / pyright
  / pydoclint / alembic all green at every commit, pyright count
  drops 8→6 errors / 539→533 warnings.

  1. **87.1** — ``config/_settings.py`` 922 LOC → ``config/_settings/``
     package with six topical sub-modules (auth, storage, infra,
     audit, features, integrations) plus a shared ``_paths`` for
     ``STARTUP_CWD`` / ``PROJECT_ROOT``.  ``Settings()`` API
     unchanged — sanity probe confirms 23 fields, path validators
     anchor against startup CWD.
  2. **87.2** — ``pointlessql/repo_assets/`` deleted (428 LOC + a
     136-LOC test for it + two stale doc rows + the
     dashboards/saved_queries YAML block in
     ``git-backed-workspaces.md``).  The Phase-51.3 loader for
     dashboards + saved queries was never wired into the
     workspace-repo sync loop; the Phase-86 audit caught it as
     orphaned and Phase 87 confirms the deletion is safe (zero
     production imports).
  3. **87.3** — ``audit/_legacy.py`` 1262 LOC → seven axis modules
     (``_helpers``, ``_metrics``, ``_principal``, ``_pii``,
     ``_history``, ``_cdf``, ``_anomaly_inbox``).  The "legacy"
     filename is gone — PointlesSQL isn't published yet, so no
     backwards-compat shim; the audit ``__init__`` mounts seven
     sibling routers and the combined router still serves the same
     23 paths.  Helper functions promoted out of the file-private
     underscore convention (``resolve_workspace_lens``,
     ``parse_iso8601``, ``record_self``) because every axis module
     now consumes them across module boundaries.
