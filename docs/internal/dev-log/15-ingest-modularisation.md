---
title: "Cluster 15 — Phase 82–86 Ingest UI + Modularisation (dev-log)"
audience: contributor
cluster_id: "15"
phases: "82-86"
closed: "2026-05-16"
---

# Cluster 15 — Phase 82–86 Ingest UI + Modularisation (dev-log)

> Phase 82 (Ingest UI: 6 sub-phases, 7 connectors, 60 new pytest), Phase 83-85 (Saved Views + VQB + DP GitHub-polish + dataflow canvas), Phase 86 (modularisation + dedup wave: feed/jobs/alerts/governance routes split, get_templates centralization, star.js extract).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 86 modularisation + dedup wave closed (2026-05-16).**
  Twelve-commit structural pass on files large enough to push past
  LLM-comfort and on the cross-cutting helpers that were duplicated
  file-by-file.  Three mega-templates split into 20 page-scoped
  partials (`data_product.html` 1610 → 206, `feed.html` 1352 → 79,
  `notebook_editor.html` 777 → 225).  Six mega-route modules split
  into per-axis sub-packages mirroring `runs_routes/` /
  `agent_runs_routes/` conventions: `feed_routes`,
  `home_routes`, `jobs_routes`, `alerts_routes`,
  `governance_routes` each become facades exporting the same
  ``router`` (and same public helpers) as before.  `main.py` shrunk
  from 1008 → 770 by extracting the Jinja filters / globals into
  `api/_template_filters.py` and the TemplateResponse wrapper into
  `api/_template_context.py`.  Twenty-two identical `_templates`
  helpers retired in favour of one `get_templates(request)` in
  `api/dependencies.py`; three hand-rolled HTMX header checks
  replaced by `is_htmx_partial`.  `base.html` shed its 121-line
  starred-factory IIFE to `frontend/js/star.js` (asset_version
  bumped 0.1.0rc4 → 0.1.0rc5 so Firefox invalidates the ES-module
  cache).  Thirteen test files lost a duplicated
  ``anonymous_client`` fixture each — 156 tests pass on the
  touched files.  Stale-module audit confirmed all four
  candidates (`repo_assets`, `conventions`, `pointlessql.git`,
  `types`) are actively imported.  Five remaining 1000-LOC files
  (`_polymorphic_handlers.py`, `audit/_legacy.py`, `sql/editor.py`,
  `dbt/routes.py`, `sql/_dispatcher.py`) plus `config/_settings.py`
  carry hidden coupling that warrants its own sprint each; trimmed
  per plan.  Ruff / pyright / pydoclint / alembic gates pass on
  every commit; app boots clean.
