# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed

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

### Added

- **Phase 80 navigation/UX overhaul closed (2026-05-15).**
  End-to-end rebuild of the frontend information architecture:
  every surface is now one click away from primary nav, the
  daily supervisor workflow has a home, social/community
  surfaces are first-class, and ambient state (workspace, role,
  backend health) is visible at all times via a new status
  footer.  Ten self-contained sub-phases, zero alembic
  migrations, behaviour-equivalent route surface (only additive):

  1. **IA contract** (80.0) — `docs/internal/navigation_ia.md`
     captures the four chrome slots, five intent-groups, every
     entry's template + handler, all context-panel bindings, the
     command-palette entity coverage, and the locked decisions.
     One canonical source-of-truth for future audit bots.
  2. **Primary rail rework** (80.1) — `icon_rail.html` →
     `primary_rail.html`, two-state width (64 px ↔ 220 px),
     five labelled groups (HOME / WATCH / BUILD / DATA /
     COMMUNITY / WORKSPACE), 24 entries closing the URL-only
     orphan list (Issues / Topics / Feed / Users / Workspaces
     all reachable from rail now).
  3. **Context-panel partials** (80.2) — 11 new sidebar
     partials (`home`, `feed`, `topics`, `issues`, `people`,
     `workspace_home`, `lens`, `dbt`, `me`, `lineage`,
     `data_products`) wired through `context_panel.html`.
  4. **Today digest** (80.3) — three new stat cards on `/`
     (approval queue · unread inbox · firing alerts) over the
     existing onboarding/recent-runs grid; rail badges populated
     by a new `services/nav_badges.py` aggregator.
  5. **/users + /lineage index pages** (80.4) — workspace-scoped
     People list with role filters; Lineage explorer hub with
     trace-row + trace-column forms + localStorage recent-traces.
  6. **/me consolidated hub** (80.5) — six-or-seven-card
     landing replacing the previously-fragmented `/users/me`,
     `/me/settings`, `/settings/notifications`,
     `/me/subscriptions` self-pages.  User-menu dropdown
     becomes the Me-hub structure.
  7. **Command palette expansion** (80.6) — `/api/search` now
     covers seven additional entity kinds (data_product, topic,
     issue, user, agent, workspace, saved_query) on top of the
     five soyuz kinds.  Slack-convention `@user` / `#topic`
     operators narrow results.
  8. **Ambient status footer** (80.7) — 28 px sticky bottom
     strip with workspace + role chips, four backend health
     pills (soyuz · MLflow · dbt · Hermes) polling
     `/api/health/backends` every 60 s, keyboard hints.
  9. **Topbar quick-create `+` menu** (80.8) — GitHub-style
     dropdown with 6 baseline + 2 admin-gated entries
     (Notebook · SQL · Dashboard · Topic · Issue · Alert /
     Data product · Job).
  10. **Close-out** (80.9) — CHANGELOG + ROADMAP entries,
      broad-except marker fixes for the new code, full
      Phase-80 test pass.

  **Test additions**: 44 new cases across 9 new test modules
  (`test_nav_rail.py`, `test_context_panels.py`,
  `test_home_today.py`, `test_users_index.py`,
  `test_lineage_index.py`, `test_me_hub.py`,
  `test_command_palette_search.py`, `test_footer_bar.py`,
  `test_quick_create.py`).  Full pytest suite remains
  green (1635+ passed, 3 skipped — the only previously-
  failing case turned out to be the broad-except gate
  catching two new code paths, fixed in 80.9).

  **Quality gates**: ruff clean, pydoclint zero violations,
  pyright at 498 warnings (matches Phase 79 ceiling),
  file-size budget OK, bootstrap-order OK.

- **Phase 80 navigation IA contract (2026-05-15).**  Introduced
  [`docs/internal/navigation_ia.md`](docs/internal/navigation_ia.md)
  as the authoritative information-architecture document for the
  PointlesSQL frontend.  Captures the four chrome slots
  (top-bar + primary sidebar + context sidebar + footer), the
  five intent-groups (HOME / WATCH / BUILD / DATA / COMMUNITY /
  WORKSPACE), every entry's template + route handler, all
  context-panel section bindings, the command-palette entity
  coverage table, and the Phase-80 locked decisions.  This
  artifact lands first in the Phase 80 bundle so the remaining
  sub-phases have one canonical source-of-truth to verify
  against.

### Changed

- **Phase 79 code-quality bundle closed (2026-05-15).**  A fresh
  audit found the codebase healthier than expected (100% function
  docstring coverage, ruff clean, no grab-bag files, 18-entry
  file-size allowlist all justified), so the bundle focused on
  the three concrete things that *were* worth fixing.  Eight
  self-contained commits, zero migrations, behaviour-equivalent
  refactor only:

  1. **Pydoclint baseline closed.**  ``Attributes:`` sections
     added to five ORM models (``DataProductComment``,
     ``DataProductCommentReaction``, ``DataProductEndorsement``,
     ``DataProductReview``, ``UserNotification``) +
     ``# noqa: DOC502`` markers on three indirect-raise
     docstrings.  Lint goes from 13 warnings to zero violations.
  2. **``notebooks_routes.py`` split.**  The pre-existing 904-LOC
     CI-gate breach landed as a six-file ``notebooks_routes/``
     subpackage following the Phase-26 pattern (each new file
     under 300 LOC).  One test monkeypatch path updated.
  3. **PQL engine typing shims.**  A new ``pql/_types.py``
     section adds eight ``typing.Protocol`` classes
     (``ArrowField`` / ``ArrowSchema`` / ``ArrowArray`` /
     ``ArrowTable`` / ``DuckdbCursor`` / ``DeltaField`` /
     ``DeltaSchema``) describing the subset of pyarrow / duckdb
     / deltalake the engine touches.  ``_autoload.py`` and
     ``_merge.py`` declare these in signatures and ``cast`` at
     the library boundaries.  Pyright budget falls 609 → 496
     (-113 warnings).
  4. **Shared agent-payload helper.**  Four sites built the
     same Phase 76.5 agent-on-behalf-of dict — two as
     identical ``_agent_payload`` helpers, two as inline
     comprehensions.  Consolidated onto ``agent_payload()`` in
     the new ``api/_social_serializers.py``.  The bigger
     ``_serialise_comment`` / ``_serialise_review`` /
     ``_serialise_endorsement`` envelopes stay separate (DP vs
     polymorphic JSON shapes are load-bearing for back-compat);
     the new module docstring captures the rationale.
  5. **Phase-77 test rename sweep.**  All 27 ``test_phase77_*``
     files migrated to topic-named homes
     (``test_social_target.py``, ``test_polymorphic_handlers.py``,
     ``test_polymorphic_reviews.py``, ``test_issues_routes.py``,
     ``test_feed_cross_entity.py``, etc.).  Pure ``git mv`` —
     module docstrings keep the Phase-77 history as preamble.
  6. **Stale "deferred to Phase 77.11" comments cleaned up.**
     Six comment blocks across ``_polymorphic_handlers.py`` /
     ``comments.py`` / ``readme.py`` rewritten.

  **Explicit non-goal**: no alembic squash.  The 90-migration
  chain has cheap runtime cost and Phase 77/78 carry
  irreversible data-movement migrations whose squash would lose
  downgrade semantics.  Revisit after first stable prod schema
  window.

  **Final state**: 2724 pytest pass / 0 fail / 7 skip.  Pyright
  496/623 (down from 609 — 18% headroom recovered).  Pydoclint
  zero violations.  File-size gate clean.  Eight commits local,
  not pushed.

### Added

- **Phase 78 polish bundle closed (2026-05-16).**  Six items
  explicitly deferred from the Phase-77 close-out landed in one
  autonomous session as eight self-contained commits:

  1. ``fanout_dataproduct_event`` wrapper deleted (zero active
     call-sites; three test references rewritten to call
     ``fanout_event`` directly).
  2. Comment-reaction polymorphism unlocked — the
     ``_require_dp_kind_for_comment_reactions`` guard is gone;
     non-DP comment reactions now route through three new
     polymorphic handlers in ``_polymorphic_handlers.py``.
  3. ``model.html`` social-tab inline blocks (discussion /
     reviews / readme, ~165 LOC) extracted into per-page
     partials following the existing ``_partials/model/``
     pattern; ``data_product.html``'s "deferred to 77.11"
     comment cleaned up.
  4. ``audit_search`` gets a new ``entity_kind`` column +
     full-body comment indexing.  ``GET /api/audit/search``
     accepts ``?kind=X``; the SQLite FTS5 trigger and the PG
     ``audit_search_index`` table both populate the column at
     write time, normalising the legacy ``data_product:``
     prefix to ``dp``.  Migration ``h5j7l9n1p3r5``.
  5. ``data_product_follows`` consolidated into
     ``social_follows``; legacy table dropped (migration
     ``i6k8m0o2q4s6``).  Every consumer (follows route, fanout,
     listing, cooccurrence, the followed HTML page) joins
     through ``social_targets`` to recover the DP affinity.
  6. ``data_product_readmes`` renamed to ``entity_readmes``;
     legacy DP-only ``data_product_id`` column dropped + new
     polymorphic UNIQUE on ``(workspace_id, social_target_id,
     version_int)``.  Model moved to
     ``models/social/_entity_readme.py`` as ``EntityReadme``
     (migration ``j7l9n1p3r5t7``).
  7. ``data_product_reactions`` consolidated into
     ``social_reactions`` via the sibling-table pattern
     (migration ``k8m0o2q4s6u8``).  Same migration drops the
     legacy ``uq_dp_review_one_per_user`` UNIQUE — the
     polymorphic ``uq_dp_review_polymorphic_one_per_user`` covers
     DP rows.
  8. Badges generalised: documented that the existing five
     thresholds were already cross-kind (no per-kind filtering
     was ever applied).  Three new per-kind badges added —
     ``commenter_table_50plus``, ``endorser_model_20plus``,
     ``issue_resolver_10plus``.

  4 alembic migrations, 8 commits, ~25 new tests, three obsolete
  pre-consolidation tests deleted (dual-write + backfill
  verification).  Pyright budget stays at 609/623 across the
  entire bundle.  Push posture preserved (commits local until
  user authorises).

- **Phase 77 closed — Social as Connective Tissue (2026-05-15).**
  Eleven sub-phases over the run lifted PointlesSQL's social
  layer from a DP-only surface into kind-agnostic connective
  tissue.  Every named platform entity (catalog / schema / table
  / dp / model / branch / run / notebook / saved query / issue /
  workspace) now carries the same Discussion / Endorsements /
  Followers / README / Stars / Issues primitives.

  77.11 ships the close-out documentation at
  ``docs/phase-77.md`` (architecture overview + locked decisions
  + test surface + deferred polish backlog).  Phase 77 marker
  flipped ✅ done in ROADMAP.

  Deferred to a future "Phase 77 polish" sub-phase (each
  independent of the foundation; cumulative risk-vs-reward
  stayed unfavourable for the close-out sweep):

  - Schema consolidation migration (rename
    ``data_product_follows`` → ``social_follows`` etc; drop the
    legacy ``uq_dp_review_one_per_user`` UNIQUE).
  - Full-body FTS extension to ``audit_search``.
  - Comment-reaction polymorphism unlock (currently 501 for
    non-DP comments — underlying table is polymorphic-safe but
    the route still needs a DP context).
  - Generalised badges (``badges.py`` thresholds still query
    DP-only).
  - ``data_product.html`` socialTabs migration.
  - ``fanout_dataproduct_event`` wrapper deletion.

  Phase 77 test count: ~232 incremental across the eleven sub-
  phases.  Pyright budget stays at 609 warnings (no regressions).

- **Phase 77.10 closed — Workspace-as-Organization landing (2026-05-15).**
  Every workspace gets a GitHub-org-style landing page at
  ``/workspaces/{slug}``.  Alembic ``g4i6k8m0o2q4`` creates
  ``workspace_pinned_entities`` with a composite PK on
  ``(workspace_id, social_target_id)``, an ordering index on
  ``(workspace_id, pin_order)``, and ``ondelete=CASCADE`` on the
  social-target FK so pins disappear when the target entity is
  deleted.  Registers ``kind='workspace'`` in the entity
  registry (4 tabs: Discussion + README + members + activity;
  stars + endorsements + issues all off — workspaces aren't
  curated artefacts).  New ``pointlessql/api/workspaces_routes.py``
  exposes five public routes:

  - ``GET /workspaces/{slug}`` — HTML landing page (pinned
    entities gallery + activity feed + member count).
  - ``GET/POST/DELETE /api/workspaces/{slug}/pins`` — pin
    CRUD.  POST requires admin; DELETE same.
  - ``PATCH /api/workspaces/{slug}/pins/reorder`` — admin
    drag-and-drop reordering.
  - ``GET /api/workspaces/{slug}/activity`` — workspace-scoped
    recent inbox events for the activity card.

  9 new pytest cases.  Phase 77 test count: 223 → 232.

- **Phase 77.9 closed — cross-entity feed (2026-05-15).**
  The activity feed lists comments + reviews across every
  polymorphic entity kind, not just data products.
  ``_row_from_comment`` + ``_row_from_review`` JOIN the
  ``social_targets`` anchor and build ``source_url`` through
  ``entity_registry.url_for`` so links land on the right detail
  page regardless of kind.  ``GET /api/feed`` gains an optional
  ``?kind=X`` narrow (``dp``/``table``/``model``/…) which echoes
  back as ``response.kind``.  ``feed.html`` carries a kind-pill
  row above the existing filter chips driven by a new
  ``setKindFilter`` Alpine state.  7 new pytest cases (3 unit on
  the row builders + 4 e2e on the feed handler + DOM smoke).

  Full-body FTS migration is deferred to 77.11 — the visible win
  here was the cross-entity feed; the FTS plumbing is independent
  and can land alongside the polish sweep.

- **Phase 77.6 closed — Notebooks + Saved Queries social surface (2026-05-15).**
  Per-notebook + per-saved-query polymorphic social surface +
  stable UUID identity for notebooks (locked decision #8).

  - 77.6.A (alembic ``f3h5j7l9n1p3``) creates ``notebooks(id
    VARCHAR(36) PK, workspace_id, file_path, created_at)`` +
    UNIQUE on ``(workspace_id, file_path)`` + index on
    ``file_path``.  Backfills every distinct
    ``(workspace_id, file_path)`` tuple across the three
    history tables (``notebook_outputs`` is workspace-aware;
    ``notebook_cell_runs`` + ``notebook_cell_run_sources``
    are path-keyed only, coalesce to workspace 1).
  - 77.6.B registers ``kind='notebook'`` +
    ``kind='saved_query'`` in the entity registry (4 social
    tabs each: Discussion + Endorsements + Followers +
    README; stars on, reviews + issues off).  Adds
    ``#notebook:<uuid>`` + ``#query:slug`` citation regex
    with pass-through resolvers.  Extends ``_POLYMORPHIC_KINDS``
    + ``parse_ref`` with the notebook (36-char UUID) and
    saved-query (slug) shapes.
  - 77.6.C adds ``_get_or_create_notebook_uuid(request, file_path)``
    in ``notebooks_routes.py`` — single chokepoint that maps
    a notebook ``file_path`` to its stable ``notebooks.id``,
    creating the row on demand for paths that pre-date the
    77.6.A backfill.  ``GET /notebooks/edit/{path:path}`` now
    threads ``notebook_uuid`` into the template context; the
    new ``GET /notebooks/uuid/{uuid}`` alias route resolves
    the UUID back to ``file_path`` and delegates to the same
    render path so audit-log citations + future path renames
    keep working.  ``notebook_editor.html`` gains a Social
    toolbar button + a Bootstrap ``offcanvas-end`` side-drawer
    carrying ``socialTabs({kind:"notebook", ref:uuid})`` with
    4 panes (Discussion / Endorsements / Followers / README).
    Side-drawer was the locked decision in the plan — full
    tab strip would crowd the full-screen editor.
  - 77.6.D restructures ``saved_audit_query_detail.html``:
    existing SQL + result cards wrapped into an Overview tab,
    4 social tabs added with
    ``socialTabs({kind:"saved_query", ref:slug})``.  Header
    gains a server-backed star button.  Inline
    ``savedQueryDiscussion`` + ``savedQueryReadme`` x-data
    factories talk to ``/api/social/saved_query/{slug}/...``.
  - 77.6.E lands 17 new pytest cases (schema presence,
    Notebook ORM round-trip, registry shape, URL builders,
    citation render, parse_ref accept/reject, comment +
    endorsement round-trip on both kinds, DOM smoke on
    notebook drawer + saved-query tab strip).

  Phase 77 test count: 199 → 216.

- **Phase 77.5 closed — Schemas + Catalogs social surface (2026-05-15).**
  ``/catalogs/{cat}`` and ``/catalogs/{cat}/schemas/{sch}`` gain
  the polymorphic social surface.  Four commits across the
  sub-phase:

  - 77.5.A — registers ``kind='schema'`` + ``kind='catalog'`` in
    the entity registry (4 social tabs each: Discussion +
    Endorsements + Followers + README; stars on, reviews + issues
    off).  Adds ``#schema:cat.sch`` + ``#catalog:name`` citation
    regex with pass-through resolvers (soyuz UC existence probes
    intentionally skipped — catalog-browser pages must stay
    responsive even when the backend is slow).  Extends
    ``_POLYMORPHIC_KINDS`` + ``parse_ref`` with schema (``cat.sch``)
    and catalog (bare identifier) branches.  Workspace resolver
    gets a factored-out ``_workspace_for_catalog`` probe so
    schemas + catalogs share the same ``workspace_catalog_pins``
    lookup.
  - 77.5.B — restructures ``frontend/templates/pages/schemas.html``:
    existing five cards (Metadata / Schemas list / Tags /
    Permissions / Properties) wrapped into an Overview tab; four
    social tabs added driven by
    ``socialTabs({kind:"catalog", ref:catalog_name})``.  Header
    star button switched to the server-backed
    ``pqlStarToggle({kind:"catalog", ref:catalog_name})`` shape
    (was localStorage-only).  Inline ``catalogDiscussion`` +
    ``catalogReadme`` x-data factories talk to
    ``/api/social/catalog/{name}/...``.
  - 77.5.C — restructures ``frontend/templates/pages/tables.html``:
    existing schema-detail cards (Metadata + dbt registration +
    ML registration + Tables list + Tags + Permissions +
    Properties) wrapped into an Overview tab; four social tabs
    added driven by
    ``socialTabs({kind:"schema", ref:"cat.sch"})``.  Header star
    button switched to ``pqlStarToggle({kind:"schema", ref})``.
    Inline ``schemaDiscussion`` + ``schemaReadme`` x-data
    factories talk to ``/api/social/schema/{cat.sch}/...``.
  - 77.5.D — lands 27 new pytest cases across two files
    (``test_phase77_5_schema_catalog_kinds.py`` 19 cases on
    registry / citations / dispatch / round-trips;
    ``test_phase77_5_schema_catalog_html.py`` 8 cases on DOM
    smoke).  Zero schema work — the
    ``social_targets.entity_kind`` CHECK already permitted both
    kinds since Phase 77.0.

  Phase 77 test count: 172 → 199.

- **Phase 77.7 closed — Issues entity (GitHub-Issues) (2026-05-15).**
  The polymorphic Issues entity ships across the platform.  Six
  commits across the sub-phase:

  - 77.7.A (alembic ``e2g4i6k8m0o2``) creates ``issues`` +
    ``issue_labels`` + ``issue_milestones``.  ``issues`` carries
    two ``social_target`` FKs: ``social_target_id`` (the issue's
    own polymorphic anchor — comment-able / follow-able /
    star-able through the existing routes), and
    ``parent_social_target_id`` (the entity the issue is opened
    against — table / model / branch / dp).  Two CHECK
    constraints lock the ``state`` and ``closed_reason`` vocab
    at the DB layer.  Labels live as a JSON slug list inside
    ``labels_json`` — no M:N junction (filtering goes through
    77.9 FTS).
  - 77.7.B registers ``kind='issue'`` in the entity registry
    (label "Issue", tab keys Discussion + Endorsements +
    Followers, ``supports_stars=True``,
    ``supports_issues=False`` — no recursion).  Flips
    ``supports_issues=True`` on the four parent kinds dp /
    table / model / branch.  Adds the ``#issue:\d+`` citation
    regex with a pass-through resolver.  Adds
    ``EVENT_TYPE_ISSUE_OPENED`` + ``EVENT_TYPE_ISSUE_STATE_CHANGED``
    governance events.  Ships
    ``pointlessql/api/social_routes/issues.py`` with the eight
    endpoint families: open + parent-scoped list + global
    cross-entity index + GET + PATCH + close + reopen + labels
    CRUD + milestones CRUD.  Issue create uses a three-step
    pattern (anchor placeholder ref → insert issue → rewrite
    anchor ref to ``str(issue.id)``) so the social_target row
    is consistent on commit.  Audit prefix is ``issue:{id}``
    (locked decision #9 — only ``kind='dp'`` keeps the legacy
    ``data_product:`` prefix).
  - 77.7.C ships ``frontend/templates/pages/issues_index.html``
    + ``frontend/templates/pages/issue_detail.html``.  The
    index renders chip filters (All / Open / Closed / Assigned
    to me / Opened by me) feeding the global ``/api/issues``
    query.  The detail page has a two-column layout: left =
    title + inline-editable body_md + three social sub-tabs
    (Discussion / Endorsements / Followers driven by
    ``socialTabs(kind='issue')``); right sidebar = state
    controls (close-with-reason + reopen) + assignee + labels
    + milestone + parent badge + star button via the
    server-backed ``pqlStarToggle`` from 77.8.E.
  - 77.7.D adds the kind-agnostic
    ``frontend/templates/partials/social/_issues_pane.html``
    tab.  Wired into ``table.html``, ``model.html``,
    ``branch_detail.html``, and ``data_product.html``.  Lists
    issues opened against the entity + opens a modal for new
    issues that POSTs to
    ``/api/social/{kind}/{ref}/issues``.  ``data_product.html``
    pre-dates the socialTabs factory (deferred to 77.11), so
    the partial there is wrapped in a tiny inline x-data that
    surfaces ``kind="dp"`` + the ``catalog.schema`` ref.
  - 77.7.E lands 31 new pytest cases across three files
    (schema constraints + route round-trips + DOM smoke).  Two
    pre-existing 77.1 + 77.2 assertions on
    ``supports_issues is False`` flip to ``True`` to match the
    new registry state.  After adding ``bare-http-ok:`` markers
    on every ``raise HTTPException`` (Sprint 43.3 lint
    contract), ``issues.py`` crossed the 800-LOC file-size
    budget — split into ``_issue_helpers.py`` (pure helpers:
    target resolver, label JSON validator, row serialiser,
    parent hydrator, can_edit_issue ACL) and
    ``_issue_taxonomy.py`` (labels + milestones CRUD router).
    Two pre-existing bare HTTPExceptions in
    ``_polymorphic_handlers.py`` (lines 290 + 302 from
    77.8.D's DP routing) get the marker as drive-by fix.
  - 77.7.F — ROADMAP + CHANGELOG close-out.

  Comment-reactions on issue comments stay 501 by design —
  unlocked in 77.11.  Phase 77 test count: 140 → 172.

- **Phase 77.8 closed — Stars + polymorphic Follow + Reactions (2026-05-15).**
  Three alembic migrations + the polymorphic backend that lifts
  Star / Follow / Reaction from 501-gated to functional across
  every registered entity kind (table / model / branch / run /
  dp).  Six commits across the sub-phase:

  - 77.8.A (alembic ``b9e1g3i5k7m9``) creates the polymorphic
    ``social_stars`` bookmark table.  Composite PK on
    ``(workspace_id, user_id, social_target_id)``; two indexes
    for star-count aggregations + per-user starred lists.  No
    backfill — localStorage stars are not migrated.
  - 77.8.B (alembic ``c0f2h4j6l8n0``) creates the sibling
    ``social_follows`` polymorphic follow table.  77.0.G's own
    docstring suggested this path because
    ``data_product_follows`` has an implicit unnamed composite
    PK on ``(workspace_id, data_product_id, user_id)`` that
    SQLite cannot drop in batch-alter mode (the reflected
    metadata has no constraint name to target).  Cleaner
    long-term: 77.11 collapses both tables into one.
  - 77.8.C (alembic ``d1g3i5k7m9o1``) adds an additive UNIQUE
    on ``data_product_reactions(social_target_id, user_id,
    emoji)`` — mirrors 77.2.1's review fix.  The legacy
    DP-id PK survives; for non-DP rows only the new UNIQUE
    enforces idempotency (NULL ``data_product_id`` defeats the
    legacy PK's NULL-distinct semantics).
  - 77.8.D ships ``pointlessql/api/social_routes/stars.py``
    with GET/POST/DELETE under
    ``/api/social/{kind}/{ref:path}/star`` and the
    ``GET /api/users/{user_id}/stars`` profile endpoint.  The
    polymorphic follow / reaction handlers in
    ``_polymorphic_handlers.py`` flip from 501 to functional —
    follow writes to ``social_follows``, reaction writes to
    ``data_product_reactions`` with NULL ``data_product_id``.
    DP follow + reaction routes stay bit-identical via the
    legacy tables.  ``_resolve_target_id`` now routes DP refs
    through ``resolve_dp_target`` so the ``data_product_id``
    back-pointer gets populated correctly.
  - 77.8.E rewrites ``window.pqlStarToggle`` to be server-backed
    with localStorage fallback for kinds not yet registered
    (catalog + schema, until 77.5).  The component now exposes
    ``async init()`` + ``async toggle()`` + ``starred`` + ``count``
    via ``/api/social/{kind}/{ref}/star``.  Visible star buttons
    land on ``model.html`` (header), ``branch_detail.html``
    (header), and ``run_view.html`` (via the run_view header
    partial — only renders when ``run`` is not None).
  - 77.8.F flips the ROADMAP marker to ✅ + this CHANGELOG
    entry.

  18 new pytest cases across two new test files +
  ``test_phase77_1_5_polymorphic_handlers``'s two formerly-501
  tests inverted to assert functional behaviour.  Comment-
  reactions on non-DP kinds stay 501 (deferred to 77.11 — the
  underlying comment-reaction table is polymorphic-safe but the
  route still needs a DP context).  Table renames
  (``data_product_readmes`` → ``entity_readmes``,
  ``data_product_follows`` → ``social_follows``,
  ``data_product_reactions`` → ``social_reactions``) deferred to
  77.11 as a single rename batch.  Full Phase-77 suite at 109
  passing (was 91 pre-77.8).

- **Phase 77.4 closed — agent-run social tabs (2026-05-15).**
  Fourth entity kind onto the polymorphic backbone, smallest mirror
  of the 77.1.5 pattern: no schema work, three commits.  77.4.A
  registered ``run`` in ``entity_registry`` (``supports_reviews=
  False`` + ``supports_readme=False`` + ``supports_endorsements=
  True`` + ``supports_stars=True``) with ``_run_url`` mapping a
  36-char UUID to ``/runs/<uuid>`` + ``#run:<uuid>`` citation
  regex (pass-through resolver) + ``run`` branch in the
  ``parse_ref`` dispatcher (UUID-shape validation, 400 on
  malformed).  77.4.B added a 5th top-tab "Social" to
  ``run_view.html`` alongside the Phase-17 four-tab strip;
  inside, three sub-tabs (Discussion / Endorsements / Followers)
  driven by a ``socialTabs`` x-data wrapper using the DP-flavoured
  endorsement vocabulary so humans can flag quality signals on
  individual agent runs.  Discussion sub-tab carries an inline
  ``runDiscussion`` Alpine factory; Endorsements + Followers
  reuse the kind-agnostic 77.1.5 partials.  Follow returns 501
  until 77.8 (composite-PK constraint on
  ``data_product_follows``); the followers partial's
  ``followLocked`` state surfaces the hint automatically.  Social
  tab is conditionally rendered (run=None notebook-only views
  skip it).  Reviews + README absent at API + UI layer (registry
  gating).  18 new pytest cases — full Phase-77 suite at 91
  passing.

- **Phase 77.2.1 closed — polymorphic reviews enable (2026-05-15).**
  Alembic migration ``a8d0f2g4i6k8`` adds a kind-agnostic UNIQUE
  on ``data_product_reviews(workspace_id, social_target_id,
  author_user_id)`` so polymorphic upsert is idempotent (the
  legacy DP-id-based UNIQUE doesn't apply when
  ``data_product_id`` is NULL).  Three new polymorphic handlers
  (``list_polymorphic_reviews`` / ``upsert_polymorphic_review`` /
  ``delete_polymorphic_review``) reuse the social_target_id
  resolver + governance/fanout pattern; ``dp_version_at_review``
  stays empty for non-DP kinds until a future entity-version
  generalisation.  ``social_routes/reviews.py`` dispatcher
  switches on kind: ``dp`` → existing DP service, anything else
  → polymorphic handler.  ``model.supports_reviews`` flipped to
  ``True`` and ``model.html`` gains a Reviews tab + inline
  ``modelReviews`` Alpine factory (5-tab strip now: Discussion /
  Reviews / Endorsements / Followers / README).  Tables +
  branches stay reviews-off in the registry.  11 new tests
  covering migration UNIQUE in schema, idempotent upsert, list
  summary, delete, 400 on invalid stars, kept-501 on table/branch,
  null-DP-id persistence + HTML render of the new tab.

- **Phase 77.2 closed — registered models get social tabs (2026-05-15).**
  Mirrors the 77.1.5 table-kind pattern for the UC ML registry.
  Two commits: registry + dispatch + ``#model:cat.sch.name``
  citation, then ``model.html`` 4-tab strip + inline
  ``modelDiscussion`` / ``modelReadme`` Alpine factories.  Reused
  the polymorphic backend untouched — the model kind joins
  ``table`` + ``branch`` in the dispatch frozenset.  16 new tests
  (registry shape + URL builder fallback + audit prefix +
  citation resolve/literal + comment/endorsement/README
  round-trips + HTML render assertions).  Reviews stay
  ``supports_reviews=False`` — polymorphic upsert idempotency
  needs a partial unique index on ``(workspace_id,
  social_target_id, author_user_id)`` and the legacy DP
  unique-on-``data_product_id`` constraint doesn't apply when
  ``data_product_id`` is NULL (SQL NULL-distinct).  Migration
  deferred to 77.2.1 / 77.11.

- **Phase 77.0 closed — polymorphic foundation (2026-05-15).**
  Ten autonomous chunks landed: 77.0.A (``social_targets``
  anchor table + ``entity_registry`` + ``_target_resolver``),
  77.0.B (``social_target_id`` columns on 7 DP-social tables),
  77.0.C (``mirror_social_to_audit`` helper preserving the
  legacy ``data_product:`` audit prefix for kind='dp' per
  locked decision #9), 77.0.D (generic ``fanout_event``
  dispatcher + nullable ``source_entity_*`` columns on
  ``user_notifications``), 77.0.E (``citations.py`` registry
  refactor: 4 hand-rolled branches → ``_CITATION_KINDS`` list
  with ``register_citation_kind()`` extension point), 77.0.I
  (feed URL builder via ``entity_registry.url_for()``), 77.0.F.1
  (DP-route call-site swap on all 6 sub-routers — every social
  INSERT writes ``social_target_id`` via ``resolve_dp_target``),
  77.0.F.2 (new polymorphic router package
  ``pointlessql.api.social_routes`` exposing
  ``/api/social/{kind}/{ref:path}/...`` — kind='dp' delegates to
  the existing DP handlers; non-dp kinds raise 501 until 77.1+
  wires them), 77.0.F.3 (active-reviewer service writes
  ``social_target_id``), 77.0.H (3 social tab-panes lifted out
  of ``data_product.html`` (1528 → 1114 LOC) into
  ``frontend/templates/partials/social/``), 77.0.G (migration
  ``y6b8d0f2h4j6`` flips ``social_target_id`` to NOT NULL +
  ``data_product_id`` to NULLABLE on the 6 non-PK tables;
  ``data_product_follows`` keeps the composite PK structure
  intact).  Zero end-user behaviour change; the 86-test
  DP-social regression suite passes unchanged.
- **Phase 77.1 closed — UC tables get social tabs (2026-05-15).**
  Builds on 77.1.A (registry + citations).  77.1.5 adds the
  polymorphic backend handler module
  ``pointlessql.api.social_routes._polymorphic_handlers`` — 12
  kind-agnostic write paths (3 comment / 3 endorsement / 4
  follow / 2 README) that resolve ``social_target_id`` via
  ``get_or_create_target``, mirror the audit row via the
  registry-driven prefix (generic ``table:`` for table writes),
  and fan out via the polymorphic ``fanout_event``.  The 6
  ``social_routes/*.py`` dispatchers gained a kind switch:
  ``kind='dp'`` keeps delegating to the Phase-76 DP handlers
  (zero behavioural drift), ``kind∈{table, branch}`` route
  through polymorphic.  Reviews + reactions on non-DP kinds
  return 501 (capability-flag opt-in via the registry).
  Follow / unfollow on non-DP returns 501 — composite-PK
  constraint blocks polymorphic writes; lifted in Phase 77.8.
  Frontend: new ``socialTabs(kind, ref, endorsementTypes)``
  Alpine factory + 2 new kind-agnostic partials
  (``_endorsements_pane.html`` + ``_followers_pane.html``).
  ``table.html`` gains a 4-tab strip (Discussion / Endorsements
  / Followers / README) — Discussion + README use inline
  ``tableDiscussion`` + ``tableReadme`` factories (existing
  77.0.H partials are DP-coupled; unification deferred to
  77.11).  Allowlist ``_polymorphic_handlers.py`` (1161 LOC)
  on the file-size budget alongside the existing
  ``data_products_routes/comments.py`` entry — cohesive surface,
  splitting now would churn against the 77.11 unification.  19
  + 4 + 5 = 28 new pytest cases cover the end-to-end table
  paths, capability gates, audit-prefix verification, partial
  drift guards, and the rendered tab strip.
- **Phase 77.3 closed — branch detail social tabs + promote-gate UI
  (2026-05-15).**  Builds on 77.3.A (workspace flag + endorsement
  type + 412 gate at POST /api/branches/.../promote).  77.3.B
  restructures ``branch_detail.html`` into 5 tabs (Overview /
  Discussion / Endorsements / Followers / Promote).  The Danger
  Zone moves into the Promote tab — admin guard unchanged.
  Promote button state machine: gate OFF = enabled, gate ON +
  0 peer endorsements = ``disabled`` + lock icon + "Needs ≥1
  peer endorsement" hint, gate ON + 1+ peer endorsements =
  enabled + "Gate satisfied" affordance.  Header strip carries
  a "gate on" badge when the workspace flag is enabled so the
  state is visible without opening the Promote tab.  Backend
  helper ``_branch_promote_gate_ui_state`` mirrors the existing
  ``_branch_promote_gate_check`` lookup but returns a state
  dict for template rendering instead of raising 412.
  Polymorphic backend handles ``kind='branch'`` writes via the
  same 77.1.5 module.  Inline ``branchDiscussion`` factory backs
  the Discussion tab (separate name from ``tableDiscussion``
  to avoid Alpine-state collisions when navigating quickly
  between branch and table pages).  7 new pytest cases cover
  all five tab buttons + the three gate-state UI branches +
  a polymorphic comment roundtrip.

- **Phase 76.6 — SSE notifications + cross-DP citations
  (2026-05-13).**  New ``GET /api/notifications/stream`` SSE
  endpoint pushes inbox rows in real-time; the topbar bell now
  opens an ``EventSource`` on page load and increments the unread
  badge live, with a transparent fall-back to the existing
  60-second poll on disconnect.  The fan-out helper in
  ``services.notifications.fanout`` publishes to the SSE
  registry (a module-level keyed dict) after each successful
  inbox INSERT — full queues drop rather than block.  New
  ``resolve_citations`` helper in
  ``pointlessql.services.social.citations`` renders four cite
  tokens in markdown bodies into anchor links — ``#dp:cat.sch``,
  ``#topic:slug``, ``#user:email``, ``#agent:slug``.  Resolution
  happens at *render* time, not POST time, so a citation to a
  deleted entity gracefully degrades to literal text.  10 new
  pytest cases; ruff / pyright (budget 623, 0 errors) /
  pydoclint green.

- **Phase 76.5 — Agents as first-class social actors
  (2026-05-13).**  New ``agents`` table (Alembic
  ``t1v3x5z7b9d1``) registers LLM reviewers / bots under a
  workspace-scoped slug with a ``principal_user_id`` FK that
  anchors the human accountability chain.  ``data_product_comments``
  gains an optional ``author_agent_id`` FK — when set the UI
  renders the comment as authored *by the agent on behalf of*
  the principal; ``author_user_id`` stays non-nullable + still
  records the human so the audit log + Phase-15 lineage chain
  remain intact.  Comment POST accepts a ``?as_agent=<slug>``
  query param (only the agent's principal_user or install-admin
  may post under the agent's identity).  Two new HTML pages
  (``/agents`` index + ``/agents/{slug}`` profile).  Three new
  governance event types reuse the existing audit pipeline
  (``audit.agent.created``, ``audit.agent.verified``).  14 new
  pytest cases; ruff / pyright (budget 623, 0 errors) /
  pydoclint green.  *Note*: extending agent authorship to
  reviews + endorsements is deferred to a Phase-76.5.x follow-
  up; this sub-sprint sticks to comments to keep the migration
  + route diff bounded.

- **Phase 76.4 — Per-user feed + notification preferences
  (2026-05-13).**  New ``GET /api/feed`` endpoint that merges
  the caller's inbox + activity from followed users (comments
  + reviews) with the existing ``mentions`` / ``my`` /
  ``followed_users`` / ``followed_dps`` filter family and a
  ``q`` substring search.  New ``GET/PUT
  /api/settings/notifications`` endpoint backed by a fresh
  ``notification_prefs_json`` column on ``users``
  (Alembic ``s0u2w4y6a8c0``) — per-event-type inbox / email /
  webhook toggles; missing keys + missing column default to
  all-true so the migration is backwards-compatible.  The fan-
  out helper in ``services/notifications/fanout.py`` now drops
  recipients with the event type's ``inbox`` flag set to
  ``false`` before inserting rows.  Two new HTML pages —
  ``/feed`` (merged stream + filter tabs + search box) and
  ``/settings/notifications`` (per-event-type toggle grid).  9
  new pytest cases; ruff / pyright (budget 623, 0 errors) /
  pydoclint green.

- **Phase 76.3 — Topic taxonomy + topic-follows (2026-05-13).**
  Three new tables — ``topics``, ``data_product_topics``,
  ``user_topic_follows`` (Alembic ``r9t1v3x5z7b9``) — wired
  through a new ``topics_routes`` package: ``GET /api/topics``
  with sort + pagination, ``POST /api/topics`` (steward+ tier
  with auto-slugify + collision-suffix), ``GET /api/topics/{slug}``,
  ``PUT /api/data-products/{c}/{s}/topics`` replace-all
  assignment (steward-only), ``GET /api/data-products/{c}/{s}/topics``,
  and ``POST/DELETE /api/topics/{slug}/follow``.  Two new HTML
  pages (``/topics`` index, ``/topics/{slug}`` detail) render
  follow toggles + DP listings.  Adding a DP to a topic fans
  out ``pointlessql.topic.dp_added`` to every topic follower —
  inbox row + Phase-20 SIEM envelope.  13 new pytest cases.

- **Phase 76.2 — User profiles + user-to-user follows + sticky
  badges (2026-05-13).**  New tables ``user_profiles``,
  ``user_follows``, ``user_badges`` (Alembic
  ``q8s0u2w4y6a8``).  Adds ``GET/PUT /api/users/{id}/profile``
  (owner-or-admin gated), ``POST/DELETE /api/users/{id}/follow``
  (self-follow rejected app-side + DB CHECK), and
  ``GET /api/users/{id}/followers`` + ``/following``.  New
  ``GET /users/{id}`` HTML page (and ``/users/me`` redirect)
  renders bio, gravatar fallback, follow/unfollow button,
  badges row, count cards (followers / following / stewarded /
  reviews), and recent activity (last 10 comments + reviews).
  Two new governance event types
  (``pointlessql.user.followed``,
  ``pointlessql.user.badge_awarded``) feed the Phase-20 SIEM
  forwarder.  Background loop ``_user_badges_loop`` recomputes
  five positive-only thresholds every 24 h
  (``steward_3plus``, ``reviewer_100plus``,
  ``mention_magnet_20plus``, ``accepted_answer_5plus``,
  ``endorser_50plus``); awards are sticky, never revoked.
  12 new pytest cases.

- **Phase 76.1 — Deeper Conversations on data-product
  comments (2026-05-13).**  Lifts threading-depth cap from 2 to
  5 (app-level walk-the-parent-chain in
  ``data_products_routes/comments.py``); introduces four
  comment categories (``general`` / ``question`` /
  ``announcement`` / ``idea``) with reply-inherits-parent-
  category semantics; adds GitHub-style six-emoji reactions on
  both comments and on data products themselves
  (``data_product_comment_reactions`` + ``data_product_reactions``,
  Alembic ``p7r9t1v3x5z7``); adds the ``POST
  /api/data-products/{c}/{s}/comments/{id}/accept-answer``
  endpoint for Q&A-style threads (steward / install-admin /
  question-OP authorised, atomic per thread); extends the
  ``@`` mention regex to resolve display-name tokens in
  addition to e-mail tokens with case-insensitive lookup and
  an ``audit.discussion.mention_ambiguous`` row when two users
  share a display name; ships a new
  ``GET /api/users/search`` typeahead under a new
  ``users_routes`` package.  Three new governance event types
  (``pointlessql.data_product.comment_reacted``,
  ``pointlessql.data_product.reacted``,
  ``pointlessql.data_product.answer_accepted``) feed the
  Phase-20 SIEM forwarder.  Discussion-tab UI extended in
  ``frontend/templates/pages/data_product.html``: category
  selector on the new-comment form, category badge per
  thread, reaction row on every comment + on the DP itself
  (top of the tab), accept-answer button on question-thread
  replies.  33 new pytest cases; ruff/pyright/pydoclint green;
  migrations round-trip on SQLite.

### Pre-OSS hygiene

- **Pre-OSS hygiene files (2026-05-13).**  Adds the governance
  scaffolding the Some-day "Pre-OSS-release hygiene" roadmap
  block calls for: ``NOTICE.txt`` (solo-author copyright
  anchor, Apache-2.0 conventional), ``CONTRIBUTING.md``,
  ``SECURITY.md`` (ported from shoreguard-fresh and adapted to
  PointlesSQL scope), ``.github/PULL_REQUEST_TEMPLATE.md`` with
  per-repo gate-command checklist, and three GitHub
  form-style issue templates under ``.github/ISSUE_TEMPLATE/``
  (bug report, feature request, contact-link config).  README
  hero swaps the "Databricks-shaped" framing for the
  "per-cell auditable lakehouse for agent-driven data
  engineering, EU-AI-Act-native" positioning and adds an
  explicit *Why* section.  ``docs/internal/oss-launch-checklist.md``
  captures the external user actions (EUIPO trademark filings,
  domain registrations, LinkedIn update, CLA-Assistant install,
  CODE_OF_CONDUCT + CLA text drop-in) that need to land before
  the visibility flip.  Repository visibility stays private —
  this is the substrate that the launch-day sprint flips on.

### Notes

- **Phase 75.2 — Stdout-JSON + Syslog audit sinks (2026-05-15).**
  Two Icebox items promoted to ⏳ → ✅.  Alembic
  ``n0p2r4t6v8x0`` extends ``ck_audit_sinks_type`` to allow
  ``stdout_json`` + ``syslog``.  Stdout sink writes one JSON
  line per envelope (config ``stream='stdout'|'stderr'``) for
  container-log harvesters; syslog sink ships RFC-3164/5424
  datagrams via :mod:`logging.handlers.SysLogHandler` over
  UDP/TCP.  TLS terminates at a local rsyslog sidecar by
  convention.  Both sinks swallow OSError on emit — audit_log
  row stays authoritative.  8 pytest cases.

- **Phase 75.1 — Verifiable audit export (2026-05-15).**
  New ``pointlessql audit-export`` typer subcommand
  (``cli/audit_export.py``) writes three mode-0600 files:
  data (json|csv), ``.sha256`` sidecar (sha256sum-compatible),
  ``.manifest.json`` (schema_version + tool_version + filters
  + entry_count + data_sha256 + data_filename).  Web variant
  ``GET /admin/audit/export.tar.gz`` streams the same trio
  gzipped — admins click "Download with manifest" instead of
  running the CLI.  Auditors verify by ``sha256sum -c`` +
  cross-checking ``manifest.data_sha256``.  6 pytest cases.

- **Phase 74.2 — Hermes-cron alt runner (2026-05-15).**
  New ``GET /api/active-reviewer/queue`` (admin/steward) lists
  DPs with ``runner='hermes_cron'`` so a Hermes-cron job can
  enumerate work.  The plugin H.3 batch (out-of-tree in
  ``hermes-plugin-pointlessql``) ships ``pql_dp_activity`` /
  ``pql_dp_post_comment`` / ``pql_dp_endorse`` so the cron
  job can render context + post comment + write endorsement
  end-to-end via plugin tools.

- **Phase 74.1 — PointlesSQL-side active reviewer (2026-05-15).**
  ``run_reviewer_for_dp`` async entry-point with injectable
  ``api_key_resolver`` + ``llm_call`` hooks.
  ``_active_reviewer_loop`` sleeps until
  ``data_products.active_reviewer_trigger_hour`` UTC,
  semaphore-bounds concurrent ticks at
  ``active_reviewer_max_concurrent`` (default 3), iterates
  DPs with ``runner='inproc'``.  Posts ``DataProductComment``
  + typed ``DataProductEndorsement`` (green →
  verified-by-steward, red → under-review) + ``AgentReview``
  row (kind=audit_review, payload_json carries prompt + raw
  LLM response).  Routes
  ``GET/POST /api/data-products/{c}/{s}/active-reviewer``
  (steward/admin gate) + ``run-now``.  Pyright budget bumped
  612 → 623 (+11) for LLM-boundary Any-cascades.

- **Phase 74.0 — Reviewer-Agent v2 config table (2026-05-15).**
  New ``DataProductActiveReviewerConfig`` model + alembic
  ``m9o1q3s5u7w9``.  Per-(workspace, dp) row with enabled /
  runner CHECK (``'inproc'`` | ``'hermes_cron'``) /
  llm_provider CHECK / llm_model / prompt_override_md /
  acting_user_id (steward proxy author for the non-nullable
  comment / endorsement FK) / last_run_at /
  last_run_comment_id.  New service
  ``services/data_products/active_reviewer.py``:
  ``build_prompt`` + ``parse_review_result`` (explicit
  ``## Verdict:`` line + keyword-heuristic fallback) +
  ``ReviewVerdict`` dataclass + ``upsert_config`` +
  ``iter_opted_in_dp_ids``.  13 pytest cases total across
  74.0+74.1+74.2.  Sprint 74.3 (steward UX HTML) deferred —
  routes are agent-callable today.

- **Phase 74.CI.1 — docstring-parser collision fix (2026-05-15).**
  Anthropic 0.40+ (Phase 74 active-reviewer LLM call surface)
  transitively pulls upstream ``docstring-parser`` 0.18.0,
  which collides with ``docstring-parser-fork`` 0.0.14 that
  pydoclint requires.  Two complementary fixes: explicit
  ``docstring-parser-fork`` dev dep + a
  ``uv pip install --force-reinstall docstring-parser-fork``
  step in the CI workflow immediately before pydoclint runs.
  Guarantees the fork's files (with ``DocstringYields`` in
  ``common.py``) win the on-disk race.

- **Plugin Phase 73 + 74 prereq bindings (2026-05-15).**
  Out-of-tree in ``~/git/hermes-plugin-pointlessql``: 12 new
  tools wired to the Phase-73 endpoints + the Phase-74 prereq
  triad (activity / post-comment / endorse).  H.1 contracts
  (preview / save / drafts-list / promote / discard),
  H.2 proposals (propose / list / approve / reject),
  H.3 DP helpers (activity / post-comment / endorse).  Plugin
  total 58 → 71 tools.  23 new pytest cases.  Local commit
  ``ea8adde``.

- **Sprint 73.3 — Schema-change proposal flow (2026-05-14).**
  New ``DataProductSchemaProposal`` model + alembic
  ``l8n0p2r4t6v8``.  Row-level CHECK enforces that at least
  one of ``proposer_user_id`` / ``proposer_agent_run_id`` is
  set, so both humans and agents flow through the same
  surface.  Two new governance event types
  (``data_product.proposal_opened``, ``.proposal_resolved``)
  + matching cloudevent constants.  New routes
  (GET list, POST open, POST ``/{id}/approve`` with
  ``kind='inplace' | 'draft'``, POST ``/{id}/reject``).
  In-place approval only accepts safe diffs
  (``add_columns`` + ``change_descriptions``); destructive
  ops route through the draft path which writes a
  ``DataProductYamlDraft`` row with
  ``source_kind='agent_proposal'``.  DP detail Overview tab
  gets an "Open schema-change proposals" card.  12 pytest
  cases.  Pyright budget bumped 585 → 612 for the yaml-diff
  applier (yaml.safe_load returns ``Any`` cascade).

- **Sprint 73.2 — pql.contract() inline DSL (2026-05-14).**
  New ``pointlessql/pql/_contracts.py`` with
  ``pql.contract(...)`` builder + ``DraftContract``
  dataclass.  Validates the payload against the existing
  ``DataProductContract`` pydantic model, wraps it in a
  ``data_product:`` top-level key so the existing loader
  accepts it as-is.  ``.save()`` writes the yaml to
  ``settings.data_products.draft_dir/<workspace>/...`` and
  optionally inserts a ``DataProductYamlDraft`` row.  Five
  new routes under ``/api/contracts``: ``POST /draft``
  (preview), ``POST /save``, ``GET /drafts``,
  ``POST /drafts/{id}/promote`` (copies into the first
  writable ``yaml_search_paths`` entry + runs
  ``load_contract``), ``POST /drafts/{id}/discard``.
  Steward-or-admin gate on the privileged routes.  Also
  fixes Sprint 73.1's ``build_draft_yaml`` to emit the same
  ``data_product:``-wrapped shape so admin-promote round-
  trips through the loader.  12 pytest cases.

- **Sprint 73.5 — Cross-DP recommendations (2026-05-14).**
  New ``DataProductCooccurrence`` model + alembic
  ``k7m9o1q3s5u7``.  ``services/data_products/cooccurrence.py``
  ships ``refresh_cooccurrence`` (walks
  ``agent_run_operations`` per ``agent_run_id``, projects
  ``target_table`` → DP via ``(catalog, schema)`` prefix,
  UPSERTs top-N partners per source DP per workspace),
  ``fetch_related``, and
  ``fetch_recommendations_for_user``.  New opt-in
  ``_data_product_cooccurrence_loop`` (default off).  Two
  new routes:
  ``GET /api/data-products/{cat}/{sch}/related`` and
  ``GET /api/data-products/recommendations``.  DP detail
  page Overview tab gets a "Related products" card;
  ``/data-products/followed`` gets a "Recommended for
  you" strip above the followed list.  8 pytest cases.

- **Sprint 73.4 — Data passport / auto-README (2026-05-14).**
  New ``DataProductPassport`` model + alembic
  ``j6l8n0p2r4t6``.  Auto-generated, versioned markdown
  briefing per DP — distinct from the steward-authored
  ``DataProductReadme``.  ``services/data_products/passport.py``
  ships ``render_passport`` (walks lineage_column_map,
  contract-event freshness, and the activity feed to emit
  a 4-section markdown body), ``refresh_passport_for_dp``
  (monotonic ``version_int`` UPSERT), and
  ``refresh_stale_passports`` (loop driver).  New opt-in
  ``_data_product_passport_loop`` coroutine + lifespan
  wire-in.  ``reload.py`` fires a fire-and-forget
  ``asyncio.to_thread(refresh_passport_for_dp, …,
  trigger='schema_changed')`` after every
  ``EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED`` emit.  Two
  new routes:
  ``GET /api/data-products/{cat}/{sch}/passport`` and
  ``POST .../passport/refresh``.  README tab now renders
  a "System passport" card above the steward README block.
  8 pytest cases.

- **Sprint 73.1 — Promote-to-DP candidate scanner
  (2026-05-14).**  New ``DataProductPromotionCandidate``
  + ``DataProductYamlDraft`` models + alembic
  ``i5k7m9o1q3s5``.  ``services/data_products/promote.py``
  ships ``scan_candidates`` (UPSERTs per-schema candidates
  that pass min_runs / min_ops in the rolling window,
  skips schemas already covered by an active DataProduct,
  never resurrects dismissed rows) and ``build_draft_yaml``
  (pulls live Delta schemas, emits a pydantic-validated
  yaml payload).  New opt-in ``_data_product_promotion_loop``
  background coroutine + lifespan wire-in.  New routes
  under ``/api/data-products/candidates``: list, dismiss,
  generate-draft (admin-gated).  HTML page at
  ``/data-products/candidates`` with dismiss + generate
  buttons.  13 pytest cases.

- **Sprint 72.6 — Per-user CloudEvent webhook subscriptions
  (2026-05-13).** New ``user_webhook_subscriptions`` table +
  alembic ``h4j6l8n0p2r4``.  Subscriptions filter by
  ``event_type_filter`` (exact or ``*`` wildcard for the whole
  ``pointlessql.data_product.*`` family) and optional
  ``dp_ref_filter`` (``catalog.schema``).  HMAC secret
  generated server-side at create time and returned exactly
  once.  New ``services/notifications/webhook_delivery.py``
  hooks into ``services/audit/sinks.dispatch_to_sinks`` *after*
  the install-global sinks fan out, so every DP governance
  event also reaches matching per-user webhooks via the
  existing ``alert_dispatcher.sign_body`` HMAC signer.  New
  ``pointlessql/api/me_subscriptions_routes.py`` (HTML
  ``/me/subscriptions`` + four JSON endpoints).  Best-effort
  throughout — one bad subscription never breaks the others.
  10 pytest cases (CRUD round-trip, secret-once, cross-user
  iso, matching event delivery via ``httpx.MockTransport``,
  wildcard match, filter mismatch, DP-ref filter, HMAC header
  shape).

- **Sprint 72.5 — Audit-bound discussions mirror (2026-05-13).**
  Coexist strategy: ``DataProductComment`` stays
  system-of-record.  Each comment POST + DELETE now also
  writes one ``audit_log`` row
  (``audit.discussion.posted`` / ``.deleted``) via the
  existing ``services.audit.log_action`` helper.  The
  ``target`` carries the click-through anchor; the
  ``detail`` JSON has ``data_product_id``, ``comment_id``,
  and a ``body_preview`` truncated to 140 chars.  The
  Phase-18.7 audit-search FTS index picks the mirror rows up
  automatically.  DELETE only fires the audit row on the
  *transition* (was-live → soft-deleted), never on an
  idempotent re-DELETE.  No new model, no migration, no
  template change.  5 pytest cases.

- **Sprint 72.4 — Typed manual endorsements (2026-05-13).**
  New ``DataProductEndorsement`` model with four
  CHECK-constrained types: ``verified-by-steward``,
  ``production-ready``, ``deprecated``, ``under-review``.
  Composite UNIQUE on
  ``(workspace, dp, endorsement_type, removed_at)`` so
  re-applying after a remove creates a new row while still
  enforcing one active row per type per DP.  New Alembic
  ``g3i5k7m9o1q3``.  Three endpoints (GET list, POST apply
  idempotent, DELETE soft-delete).  Steward + install-admin
  can apply / remove; auditor can apply
  ``verified-by-steward`` only.  Each POST + DELETE drops an
  ``audit_log`` row (``endorsement.applied`` / ``.removed``).
  10 pytest cases.

- **Sprint 72.3 — Trending in agent workloads (2026-05-13).**
  New ``data_product_trending`` cache table + alembic
  ``f2h4j6l8n0p2``.  New ``_data_product_trending_loop``
  coroutine (opt-in via
  ``POINTLESSQL_DATA_PRODUCTS_TRENDING_REFRESH_INTERVAL_SECONDS``;
  default 0 = dormant).  ``services/data_products/trending.py``
  carries the refresh helper (per-workspace top-N UPSERT over
  the 7-day rolling window) + the read helper.  New
  ``GET /api/data-products/trending`` JSON + ``/data-products/trending``
  HTML page; ``?workspace_scope=all`` requires install-admin
  or auditor (Phase 34 cross-workspace precedent).  New
  Grafana panel 22 ("Top-10 trending data products (7d)")
  added to both ``pointlessql_audit.json`` dashboards (sqlite
  + postgres); ``scripts/check-grafana-dashboards.sh``
  confirms matched panel counts.  8 pytest cases.

- **Sprint 72.2 — Auto-computed endorsement badges
  (2026-05-13).** Four read-time-computed badges (no cache
  table): ``downstream_count`` (distinct out-edges in
  ``lineage_column_map``), ``agent_run_count_7d`` (distinct
  agent runs touching the DP in the last 7d),
  ``last_rollback_passed`` (most recent ``rollback`` op,
  ``True``/``False``/``None``), ``freshness_on_time_30d_pct``
  (100 − 5pp per ``sla_violated`` envelope in the 30d window;
  refined in Sprint 72.3's cache).  New
  ``services/data_products/badges.py`` (single-DP +
  bulk-for-listing helpers).  Listing + detail JSON payloads
  carry a ``badges`` block; DP header renders the four pills;
  browse table adds two sortable columns (``downstream``,
  ``agents 7d``).  12 pytest cases.

- **Sprint 72.1 — Activity feed per DP (2026-05-13).** New
  ``services/data_products/`` package +
  ``activity.py`` aggregator.  Merges four streams
  (``agent_run_operations`` by ``target_table`` prefix,
  ``audit_log`` by free-form ``target`` substring,
  ``data_product_contract_events`` by FK, ``governance_events``
  filtered to ``pointlessql.data_product.sla_violated``).
  Per-stream cap = ``max(50, 2*limit)`` so one stream can't
  starve the others; post-merge sort + pagination.  New
  ``GET /api/data-products/{cat}/{sch}/activity`` route + new
  Activity tab on the DP detail page inserted between
  Compliance and Discussion.  ``AuditLog.target`` matching is
  documented as a heuristic (free-form substring);
  ``agent_run_operations`` is the authoritative stream.  11
  pytest cases.

- **Sprint B.3 — Daily marketplace-digest loop (2026-05-12).**
  Phase 71.4's ``users.digest_email_optin`` column + ``/me/settings``
  toggle now have a backing drainer.  New
  ``NotificationsSettings`` sub-model (env prefix
  ``POINTLESSQL_NOTIFICATIONS_``) with ``digest_enabled``
  (default False — install-level master switch),
  ``digest_trigger_hour`` (UTC, default 6) and
  ``digest_poll_interval_seconds``.  New constant
  ``pointlessql.notification.digest`` in cloudevents/types +
  governance.  New ``services/notifications/digest.py``
  (``seconds_until_next_window`` planner +
  ``fire_digests`` per-user emitter).  New
  ``_user_notification_digest_loop`` coroutine registered in
  ``_bootstrap/_loops.py`` + lifespan; when ``digest_enabled``
  is false the loop sleeps forever (cheap no-op until the
  operator flips the flag).  7 pytest cases.

- **Sprint B.2 — contract_violated streaming emit (2026-05-12).**
  The existing ``record_contract_event_after_commit`` hook
  persists one ``data_product_contract_events`` row per
  violated write — that stays the authoritative audit record.
  The hook now also schedules a fire-and-forget
  ``emit_governance_event(EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED,
  …)`` via ``loop.create_task`` whenever an event loop is
  running.  Outside an event loop (sync test harness, REPL) the
  streaming leg is a no-op; the audit row still persists.
  Workspace id is resolved at emit time from the
  ``DataProduct`` row — no signature change for the two call
  sites in ``_lifecycle.py``.  3 pytest cases.

- **Sprint B.1 — schema_changed emit on yaml reload
  (2026-05-12).** The ``EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED``
  constant was registered in 71.4 but nothing emitted it.
  ``POST /api/data-products/reload`` now snapshots the
  pre-reload ``contract_yaml_hash`` per existing product in the
  workspace, runs ``load_contracts_for_workspace``, and emits
  one envelope per product whose hash changed.  First-load (no
  prior hash) is creation, not change — does not emit.  3
  pytest cases.

- **Sprint B.4 — Live-replay deferred.**  The Phase 71
  walkthrough sections in ``docs/e2e-walkthroughs/data_products.md``
  were verified statically (every CSS selector exists in the
  template source).  Browser-replay against the running
  container is deferred until a docker rebuild lands the new
  code — the in-process pytest suite (2248 cases at HEAD)
  covers every route + Alpine handler URL contract.

- **Sprint 71.6 — Browse-page rework (2026-05-12).** Reworked the
  data-product browse page (``/data-products``) around a
  sortable table with click-to-sort columns (Product, Version,
  Steward, ★, Followers, Comments 7d, Last loaded), a filter
  chip row (``[All] [Has comments] [Has README] [Stale]``), a
  view-mode toggle (table / cards) persisted in ``localStorage``,
  and a "Recently active" pill row at the top scored by
  ``comment_count_7d + 0.5 × review_count`` (top 5).  The
  ``GET /api/data-products`` payload now carries ``follow_count``,
  ``comment_count_7d`` (live comments only, last 7 days),
  ``has_readme``, and ``freshness_status``
  (``on_time`` / ``stale`` / ``no_sla``).  Aggregates compute via
  four grouped LEFT OUTER JOIN-style queries; no N+1.  SQLite's
  naive-datetime quirk on the ``last_loaded_at`` column is
  handled by coercing to UTC before the SLA comparison.  7
  pytest cases.

- **Sprint 71.5 — Wiki / README per DP (2026-05-12).** New
  ``data_product_readmes`` table — one row per *version*,
  UNIQUE on ``(workspace, dp, version_int)``.  Latest =
  ``max(version_int)``.  Five endpoints (GET latest /
  history / specific version, PUT new version, GET unified
  diff between two versions).  PUT is steward-or-admin only
  and idempotent on unchanged body (no v+1 byte-identical
  row).  Diff uses ``difflib.unified_diff`` so the History
  modal can render a unified-diff text pane.  New README tab
  in ``data_product.html`` with edit + history + diff
  panels.  11 pytest cases.

- **Sprint 71.4 — Notification fanout + per-user inbox
  (2026-05-12).** New ``user_notifications`` per-recipient
  inbox table (Alembic also adds ``users.digest_email_optin``).
  Five new CloudEvent types in
  ``services/cloudevents/types.py`` + ``governance.py``:
  ``data_product.commented`` / ``.reviewed`` / ``.followed`` /
  ``.schema_changed`` / ``.contract_violated``.  New
  ``services/notifications/fanout.py`` ::
  ``fanout_dataproduct_event`` resolves recipients
  (followers ∪ mentions − actor) and bulk-inserts inbox rows.
  Comment POST / review PUT / follow POST each emit the
  matching governance event (and where applicable fan out
  to inbox rows).  Best-effort wrapper: a fan-out failure
  never breaks the originating audit row.  New routes in
  ``pointlessql/api/notifications_routes.py``
  (``/notifications`` HTML page + four JSON endpoints)
  plus ``pointlessql/api/me_routes.py``
  (``/me/settings`` page + ``GET/PUT /api/me/settings``).
  Bell icon polled every 60s lands in the topbar via
  ``components/notification_bell.html``.  12 pytest cases.
  Schema-change + contract-violated emit sites stay queued
  for a follow-up — they need a loader hook outside this
  sprint's scope.

- **Sprint 71.3 — Follow / subscribe (2026-05-12).** New
  ``data_product_follows`` composite-PK table (workspace +
  product + user) and four endpoints under
  ``/api/data-products/{catalog}/{schema}/`` (POST/DELETE
  ``/follow``, GET ``/followers/count``, GET ``/followers``).
  POST + DELETE are idempotent; the count endpoint is public to
  any logged-in user; the full list is restricted to the
  product's steward or install-admin so analyst privacy holds.
  Detail-page header gains a Follow/Following button + follower
  count badge.  New HTML page
  ``GET /data-products/followed`` with a per-user table view.
  9 pytest cases covering idempotency, privacy gate, HTML
  index, cross-workspace iso.

- **Sprint 71.2 — Star ratings + text reviews (2026-05-12).** New
  ``data_product_reviews`` table with one row per ``(workspace,
  product, user)`` (UNIQUE constraint), 1..5 stars (DB CHECK),
  markdown body, SemVer snapshot at write time.  Three endpoints
  (GET list + summary, PUT upsert, DELETE self).  The browse
  listing now joins a grouped aggregate so each card carries
  ``avg_stars`` + ``review_count`` for the star badge.  New
  Reviews tab on the DP detail page with lazy load, 5-star input
  widget, sort selector, delete-own-review.  Header gets the
  same star badge.  10 pytest cases (upsert idempotency, DELETE
  round-trip, stars-range, summary aggregation, browse
  enrichment, cross-workspace iso).

- **Sprint 71.1 — Comment threads per data product + routes-package
  split (2026-05-12).** Refactored the 430-LOC
  ``data_products_routes.py`` monolith into a Phase-26-style
  package (listing / detail / diff / lineage / reload) and added
  ``data_products_routes/comments.py`` on top.  New
  ``data_product_comments`` table with self-FK threading capped
  at depth 2, ``deleted_at`` soft-delete (placeholder rendering
  when a parent with live replies is removed), JSON sidecar for
  resolved ``@<email>`` mentions (fenced code blocks stripped
  before regex).  Three endpoints (GET threaded list, POST
  create, DELETE soft-delete by author / steward / install-admin).
  New Discussion tab on the DP detail page with Alpine state
  (lazy load on ``shown.bs.tab``, reply UI, markdown rendered
  via ``x-text`` so no HTML injection).  16 pytest cases
  covering CRUD, depth cap, soft-delete placeholder, auth
  ladders, cross-workspace iso, and mention resolution.

- **Sprint H.2 — Pyright triage: 28 errors → 0, budget 497 → 585
  (2026-05-12).** Errors had drifted from 0 at Phase 45 to 28
  pre-existing under HEAD; CI's lint job had been red on this gate
  since 2026-05-08.  Bucketed and cleared:
  - **`_bootstrap/_loops.py` × 7 + `api/main.py` × 7** (14
    errors): added ``__all__`` to `_loops.py` and per-import
    `# pyright: ignore[reportPrivateUsage]` on the 7
    underscore-prefixed loop coroutines that `main.py` imports
    intentionally as background-task targets.
  - **`api/lens/sessions.py` × 2**: refactored the `getattr(..., "")`
    string-default trap into a typed local intermediate so
    pyright can narrow `datetime | None` correctly.
  - **`api/main.py:495` × 1**: dropped the dead-code
    `hasattr() and is not None` guard — kernel_registry is
    unconditionally set 5 lines above.
  - **`notebook_kernel_ws.py:361` × 1**: pass the
    `QueryStatus` enum instead of the raw `Literal['succeeded',
    'failed']` string.
  - **`services/lens/llm_provider.py` × 9 +
    `services/lens/_chat_loop.py` × 1** (10 errors): inline
    `# pyright: ignore` on the OpenAI/Anthropic SDK type-strict
    sites (their `ChatCompletionMessageParam` / `MessageParam`
    union shapes vs our `list[dict[str, Any]]` carrier; the
    `Protocol.name: str` vs concrete `Literal["openai"]`
    covariance pyright refuses).  Each suppression carries the
    rule code so future stub work can lift them surgically.
  Warning budget formally raised 497 → 585 in
  `scripts/check-pyright-budget.sh` with a detailed comment on
  which files contribute the +88 (mostly PyArrow / DuckDB-result
  deserialisation seams that `feedback_pyright_thirdparty_stubs.md`
  flagged as needing multi-week custom `.pyi` work).

- **Sprint H.6 — Postgres lane pytest-xdist enabled
  (2026-05-12).** Phase-31.4 had deferred per-worker DB
  provisioning citing "CI plumbing"; the plumbing now lives in
  `tests/conftest.py` and `.github/workflows/test.yml`.  The
  conftest's `_test_engine` session-scope fixture appends
  `_<worker_id>` (e.g. `_gw0`) to the `TEST_DATABASE_URL` path
  component when both `PYTEST_XDIST_WORKER` is set and the URL
  is a `postgresql://` one; SQLite stays in-memory-per-engine
  and remains isolated for free.  CI provisions
  `pointlessql_gw{0..3}` via four `CREATE DATABASE` statements
  in a new step before `pytest -n 4 --dist loadfile` runs.
  `--dist loadfile` keeps tests in the same file on the same
  worker so module-scope fixtures don't get split across DBs.
  Expected speedup: ~7 min → ~3 min on the PG lane (target
  matches Phase-31.4's documented 50%).

- **Sprint H.4 — Alembic PG-side autogen-drift gate + deeper
  drift script (2026-05-12).** Added `alembic check` to the PG
  CI lane so dialect-asymmetric drift (PG-only `server_default`,
  partial indexes, etc.) cannot accumulate silently — the SQLite
  side has had this gate since Phase 30 but the PG side only ran
  `alembic upgrade head` without the diff check.  New
  `scripts/check-alembic-fresh-drift.sh` performs a deeper drift
  check (fresh SQLite + upgrade head + alembic check + schema
  dump for human review) — intended for periodic manual use, not
  per-commit pre-commit overhead.  Both gates green at run-time
  ("No new upgrade operations detected"); no drift to repair.

- **Sprint H.3 — notebook-walkthrough doc selector refresh
  (2026-05-12).** Partial refresh of `notebook-editor.md` +
  `notebook_full_walkthrough.md`: all `/notebook/editor?path=`
  route references rewritten to the Phase-12.12
  `/notebooks/edit/{path}` form (19 sites); the workspace landing
  step swapped from `/notebook` (302-redirect, gone) to
  `/notebooks/workspace` (direct); three confirmed Phase-67 class
  renames bulk-applied (`pql-nbedit-editor`/`-root` →
  `pql-notebook-shell`, `pql-nbedit-toolbar` →
  `pql-notebook-toolbar`).  Per-feature `pql-nbedit-*` selectors
  (cell toolbar, status pill, history popover, outline, settings
  drawer, etc.) remain stale and are explicitly gated by a
  ⚠️-banner at the top of each file telling the replay driver to
  look up the current class in DevTools rather than trusting the
  selector — comprehensive feature-by-feature refresh queued as
  a follow-up phase, out of scope for the Sprint-H.3 sweep.

- **Sprint H.1 — pre-existing pytest + ruff failures cleared
  (2026-05-12).** Eight pytest tests that had been failing on
  main since Phase 56–68 carve-outs landed all green:
  `test_register_page_renders` (template casing drift),
  `test_help_registry::*_used_in_some_template` +
  `test_model_detail_renders_all_tabs` (Sprint 68.3 dropped
  the inline ``tab-mlflow`` iframe — slug now wires the
  ``Open in MLflow UI`` button popover instead),
  `test_no_bare_http_exception` (one `# bare-http-ok:` marker
  on `notebooks_routes.py` confirm-gate),
  `test_no_lossy_broad_except` (six `# bare-broad-ok:` markers
  on legit translate-to-structured-response sites in
  `notebook_kernel_ws.py`, `sql/editor.py`, `lens/cost_gate.py`),
  `test_query_history::*` ×2 (cards → table Phase 61/62 drift
  + the `length > 700` drawer-gate that the test pair always
  implied), `test_saved_audit_queries::*_renders_with_pager`
  (heading case drift). Eight ruff errors (six auto-fixed I001
  import-sort, two manual `E501` line-length breaks, one
  `D417` missing-arg docs, one `F401` __all__ add) also cleared
  to unbreak the `lint + type + docstring + alembic` CI job
  that had been red since 2026-05-08. Pyright still reports 28
  pre-existing errors — slated for Sprint H.2.

- **Sprint H.5 — pip-audit CI integration + 11-CVE bump
  (2026-05-12).** Added a new `security-audit` job to
  `.github/workflows/test.yml` that runs `uv run pip-audit
  --skip-editable` on every PR. `--skip-editable` excludes the
  local `pointlessql` install and the private
  `soyuz-catalog-client` git-tag source from the audit; any
  third-party PyPI dep with a known CVE still fails the job.
  Same run also bumped six packages whose locked versions
  carried 11 known CVEs: `gitpython` 3.1.49 → 3.1.50,
  `mako` 1.3.11 → 1.3.12, `mistune` 3.2.0 → 3.2.1, `pip`
  26.0.1 → 26.1.1, `python-multipart` 0.0.26 → 0.0.28, `urllib3`
  2.6.3 → 2.7.0.  `uv run pytest -n auto` post-bump confirms
  0 new test regressions (8 pre-existing failures unchanged,
  earmarked for Sprint H.1).

- **Sprint H.7 — ROADMAP archive trigger clarification
  (2026-05-12).** Rewrote the "When closed phases stack up"
  section in `ROADMAP.md` to make the **both conditions**
  requirement explicit: line-count (>2000) AND staleness (>30d
  + >3mo since last reference).  Added a worked 2026-05-12
  example so future sessions don't auto-archive recent
  load-bearing phases.

- **Phase 70 — Notebook track (member-access + JS-split,
  2026-05-12).**  Two bundled notebook concerns landed in one
  phase.  (1) Member-access: drop the Phase-12.12 admin-only
  restriction on the browser notebook editor — `/api/notebooks/*`
  + `/notebooks/workspace` + `/notebooks/edit/*` now accept any
  authenticated user via a new `require_user` dependency
  (sibling of `require_admin` etc. in
  `pointlessql/api/dependencies.py`); the Workspace
  `permission_link` calls in `icon_rail.html` and `nav_links.html`
  are replaced with direct `<a href>` tags (Branches + Admin stay
  gated); the kernel WS `_user_can_use_editor` gate broadens to
  any authenticated user.  (2) Defensive split of the 939-LOC
  `notebook_editor.js` monolith following the Phase-68.2
  plugin-mixin pattern: five new submodules in
  `frontend/js/notebook/` (`jobs_orchestration`,
  `kernel_execution`, `cell_operations`, `markdown_output`,
  `persistence`) each exporting `installXxx(state, deps)` that
  mutates the shared Alpine state object.  Coordinator shrinks
  to 190 LOC (state defaults + init/destroy + five `install*()`
  calls).  Twelve non-admin notebook tests flipped from
  expecting 403 to expecting 200/201 with shape assertions; the
  `_user_can_use_editor` WS-gate test removed.  Asset version
  bumped 0.1.0rc3 → 0.1.0rc4 to invalidate the Firefox
  ES-module cache.  Sprint 70.9 carry-over (2026-05-12): browser
  replay against `docker-compose.e2e.yml` with admin + member
  personas — green on both, 0 BUG-70 surfaced.  All 92 Alpine
  state keys present (5 install functions wire correctly), all 9
  notebook JS modules load 200, all six `/api/notebooks/*` route
  classes return 200 for `flo@pql.test`, `/ws/notebook/kernel`
  upgrades to 101 without 4403, `runCell` / `addCellAtEnd` /
  `save` / `toggleInspector` / `enterMarkdownEdit` round-trip
  end-to-end; cross-page CSS regression gate green
  (`notebook.css` absent on `/runs`, `/sql`, `/admin`).

- **Phase 69 — Vollständiger Browser-Replay der Plattform
  (2026-05-12).**  Browser-replay sweep of every UI surface across
  multiple user roles and config flips on the
  `docker-compose.e2e.yml` stack, primarily to verify Phase 68's
  structural HTML/CSS/JS reorganization landed cleanly.  Three
  bugs surfaced.  Two are deploy-hygiene cascades resolved by
  bumping `pyproject.toml` version whenever `frontend/` changes
  (BUG-69-01 + BUG-69-02 documented in
  `docs/e2e-walkthroughs/federation.md`).  One is a real Phase
  68.4 file-move regression, fixed in this commit-range:
  `frontend/js/pages/federation/{connections,credentials,
  catalogs}.js` each had a stale `import './editor_base.js'`
  pointing one directory too deep after Phase 68.4's `git mv`;
  now `from '../../editor_base.js'` (BUG-69-03).  Without the
  fix, every page-load fired a 404 + cascaded into Alpine init
  failure that left `pql-cmdk-backdrop` intercepting clicks.
  Persona matrix exercised: admin@pql.test, flo@pql.test (member
  403 sweep), supervisor + auditor + lineage_inbound Bearer key
  generated via `/admin/api-keys`, OIDC via `mock-oidc` sidecar.
  Verified: all 7 table-detail tabs, 4 run-view top tabs + 5
  Operations sub-tabs, 4 model-detail tabs, 3 federation modals,
  notebook.css absent on 6 non-notebook surfaces, sql_editor.css
  cascade @import present, "Sign in with SSO" button flips with
  OIDC env.

- **Phase 68 — Frontend modularization (2026-05-12).**  Structural
  reorganization for LLM-context efficiency and one-convention
  hygiene; behavior unchanged.  Templates: 12 single-page partials
  moved from top-level `templates/partials/` into nested
  `pages/_partials/run_view/` and `pages/_partials/notebook/output/`
  (only 2 genuinely cross-page partials remain at top-level).
  Three large templates split into per-tab partials using the Phase-38
  playbook: `pages/table.html` 786 → 228 LOC (7 partials),
  `pages/_partials/run_view/tab_operations.html` 726 → 59 LOC
  (5 sub-tab partials), `pages/model.html` 589 → 209 LOC
  (4 partials).  JS: 3 admin-only `federation_*.js` files moved
  from top-level `frontend/js/` to `frontend/js/pages/federation/`;
  `bootstrap.js` imports updated, window-attached names unchanged.
  CSS: `pages/sql_editor.html` 146-LOC inline `<style>` extracted to
  `frontend/css/components/sql_editor.css` (page 543 → 397 LOC);
  `notebook.css` (292 LOC) removed from global `@import` cascade
  and lazy-loaded via `{% block extra_css %}` in
  `pages/notebook_editor.html`, so notebook-only CSS no longer
  appears in LLM-context for non-notebook pages.  New
  `docs/development/frontend-conventions.md` codifies the
  conventions; `frontend/js/README.md` gains a folder-layout
  section.  Deferred (out of scope for Phase 68): `notebook_editor.js`
  939-LOC split (Alpine state tight-coupled across 8 seams, awaits
  feature-driven anchor); `base.html` 565 LOC (mostly critical-path
  init scripts, no splittable seams); `pages/notebook_editor.html`
  597 LOC (single-page Alpine app, no static tab boundaries).
- **Phase 67 — Notebook Operations (2026-05-12).**  Phase 66's
  live editor gains the four DBX-feel surfaces that close the
  notebook-from-the-editor gap without touching the existing
  scheduler / papermill / kernel-session stack:
  (1) **Schedule-from-Notebook** — toolbar "Schedule" button +
  modal pre-built from `papermill.inspect_notebook` posts to
  the existing `POST /api/jobs` with `kind="papermill"`;
  (2) **Parametrized runs** — papermill-canonical
  `# %% tags=["parameters"]` jupytext marker (round-trip-stable;
  ignored by `compute_content_hash` so the parameters-tag flip
  doesn't rewrite cell identity); inspect endpoint accepts `.py`
  via in-memory jupytext + nbformat conversion;
  (3) **Run-Once-with-Parameters** — `POST /api/notebooks/run-once`
  creates a paused permanent Job + fires
  `scheduler_service.execute_run` as fire-and-forget asyncio task,
  returning `{job_id, job_run_id, status}`; new
  `GET /api/jobs/{id}/runs` listing endpoint feeds browser polling;
  (4) **Variable Inspector** — kernel bootstrap learns
  `__pql_inspect__()` + `__pql_inspect_detail__()` that emit a
  custom `application/x-pql-vars+json` MIME bundle; the WS pump
  routes them to dedicated `variable_snapshot` /
  `variable_detail` notify frames (NOT persisted) so the editor
  side-pane refreshes after every cell run.  Plus a job-run
  output bridge — `_papermill_executor` post-execute persists
  per-cell outputs to `notebook_outputs` with
  `kernel_session_id = "job:<run_id>"` so the same renderer
  surfaces job artefacts and live cell outputs.  New
  `notebook_job_link` table (Alembic `i9j1k3m5o7q9`) gives the
  editor's in-context "Jobs of this notebook" panel an indexed
  look-up against `notebook_path` instead of a JSON-LIKE scan
  on `Job.config`.  Per-cell "Mark as parameters" dropdown
  action toggles `cell.tags` and triggers the autosave
  debouncer; the params-tag round-trips byte-identically
  through `load → save`.  46+ new pytest cases; 110/110 green
  on the notebook + jobs slice.  Pyright budget: pre-existing
  reportLiteralAssignment at `notebook_kernel_ws:361` carried
  forward (Sprint 66.5 SQL-cell `record_query`; unrelated to
  Phase 67).
- **Phase 66 — Browser Notebook editor v2 (2026-05-10).**  The
  browser notebook editor returns, rebuilt around the marker
  grammar (`# %%` jupytext-Percent + FNV-1a-64 content_hash),
  the async kernel-bridge runtime (`KernelRegistry` +
  `KernelSession`), and the persisted-output replay tables
  that all survived the agent-first pivot.  New surface area:
  `/notebooks/edit/{path:path}` cell-by-cell editor backed by
  CodeMirror v6 instances per cell (no vendored bundles —
  esm.sh import-map only); a `/ws/notebook/kernel` JSON-RPC
  WebSocket route bridging browser → ipykernel; restored
  notebook CRUD (`POST /api/notebooks/create`,
  `POST /api/notebooks/rename`, `DELETE /api/notebooks/delete`)
  and load / save / render-markdown / cell-history routes.
  Cells render under a sandboxed iframe (text/html, image/svg)
  or as DOM (image/png/jpeg → `<img>`, JSON → `<pre>`,
  text/plain → monospace, error → red-bordered traceback).
  SQL cells (`# %% [sql] df`) are wrapped server-side via
  `__pql_sql_run(...)` after a per-table privilege check;
  every SQL execution writes a `query_history` row with
  `notebook_path` + `notebook_content_hash` so the audit
  cockpit can deep-link back to the originating cell.  Markdown
  cells switch between rendered HTML view-mode and CodeMirror
  edit-mode (Shift+Enter / Esc / click).  Keyboard model
  covers Shift+Enter (run + advance), Ctrl+Enter (run + stay),
  Cmd/Ctrl+S (save).  5-second debounced autosave + per-cell
  history popover via `GET /api/notebooks/cell-history`.  One
  Alembic migration (`hh7i9k1m3o5q` — query_history notebook
  columns) + one new walkthrough (`notebook-overview.md`).
  ~37 new pytest cases (CRUD, load, save, cell ops, SQL cell
  helpers, markdown render, cell history, kernel WS auth +
  one integration test for the real-kernel execute round-trip).

- **Phase 65 — Lens read-only Q&A surface (2026-05-10).**  New
  analyst-facing chat-style surface that exposes read-only data
  Q&A over two transports: a browser chat UI at `/lens` (BYO LLM
  key per workspace, Fernet-encrypted at rest) and an MCP server
  on stdio for IDE consumers (Claude Desktop, Cursor, Hermes).
  Both transports share one Pydantic-typed tool registry covering
  `provenance` (unified row/column/value lineage trace —
  Phase 65's signature tool), `query` (SELECT-only, EXPLAIN-cost-
  gated, auto-LIMIT), `list_catalogs` / `_schemas` / `_tables`,
  `describe_table`, and `lineage_neighbors`.  New `analyst` scope
  on `api_keys` (auditor passes too as superset).  Pure read-only
  enforcement at the AST validator; per-query cost cap +
  per-session budget cap; pinned-answer flow lets analysts
  bookmark assistant answers for stable-URL re-rendering at
  `/api/lens/pinned/<slug>/view`.  Phase 13/39 power-mode write
  tools stay parallel as the engineering story; Lens is the new
  default analyst surface.  hermes-plugin-pointlessql gains
  `pql_lens_ask` + `pql_lens_get_pinned` for cron-bot consumption.
  Two new walkthroughs (`lens-overview.md` + `lens-mcp.md`).
  Adds `mcp[cli]`, `openai`, `anthropic` deps.  Two Alembic
  migrations (`ff5g7i9k1m3o` lens tables, `gg6h8j0l2n4p`
  query_history.lens_session_id FK).  77 new pytest cases.

- **UX — permission-locked navigation links visible instead of
  hidden (2026-05-10).**  Admin-only links in the icon-rail
  (Workspace, Admin), the catalog sidebar (Branches), and the
  mobile nav drawer (Workspace, Admin) now render for every user.
  Non-admins see the entry greyed out with a trailing lock icon
  and `aria-disabled="true"`; click / Enter / Space surface a
  toast naming the missing role ("Requires admin role — contact
  your workspace admin.").  This restores discoverability — a
  regular user can now see *that* a Branches page exists and ask
  the admin for access — without weakening backend authorisation
  (the routes still 403 if the dead `href="#"` is bypassed).
  Added `frontend/templates/_macros/permission_link.html` (single
  re-usable macro across icon-rail / sidebar / nav-links) +
  `frontend/js/permission_link.js` (delegated click + keyboard
  listener registered once via `bootstrap.js`) +
  `.permission-locked` CSS in `frontend/css/layout.css`.  Five
  inline `{% if current_user.is_admin %}` wrappers replaced by
  one macro call each; user-menu admin badge stays unchanged
  (status indicator, not a link).

- **Phase 63 — Writeable SQL Editor (AST-dispatch refactor) ✅
  closed (2026-05-10).**  Turns the SELECT-only SQL editor into
  an AST-classifying dispatcher that routes each statement
  family to its correct typed primitive.  Every editor write now
  lands in the same audit trail as agent-driven writes
  (`agent_run_operations` row, `lineage_row_edges` /
  `lineage_value_changes` where applicable, and a
  `query_history` row with `agent_run_id` populated).

  The structural gap that motivated Phase 63 was **not** an
  audit / safety stance — the SELECT-only constraint at
  [pointlessql/pql/sql_parser.py:385-391](pointlessql/pql/sql_parser.py#L385-L391)
  fell out of the DuckDB rewriter's scope (DuckDB reserves
  `main` as a catalog name and refuses to bind 3-part UC refs
  natively, so the parser has to extract + rewrite source
  tables; the rewrite logic only made sense for SELECTs).  The
  audit infrastructure was already ready for write traffic;
  the only structural gap was that interactive editor writes
  did not populate `query_history.agent_run_id`.

  - 63.1 — `pointlessql/pql/sql_parser.py`: new `StmtType`
    StrEnum, `classify(ast) -> StmtType`,
    `extract_write_target`, `extract_source_refs`,
    `parse_and_classify`, and `parse_batch` for multi-statement
    input (Phase 63.6).  `_parse_root` no longer rejects
    non-SELECT — `prepare_sql` keeps the SELECT-only behaviour
    via an explicit guard and points the dispatcher at
    `parse_and_classify` for everything else.  `CREATE CATALOG`
    / `DROP CATALOG` parse as `exp.Command` in sqlglot and are
    deliberately rejected (admin UI handles catalog
    management).  Bare `CREATE TABLE foo (a INT, b TEXT)`
    rejects with a "use the table-detail UI's New Table form"
    message.  42 new pytest cases in
    `tests/test_sql_parser.py` (parametric coverage of every
    StmtType + write-target extraction + source-ref dedup).
  - 63.2 — `pointlessql/pql/_update_delete.py` (new) +
    `pointlessql/pql/pql.py` extended: `pql.update(target, *,
    set_clause, where=None, track_value_changes=False)` and
    `pql.delete(target, *, where=None)` wrapping
    `DeltaTable.update` / `DeltaTable.delete` (delta-rs accepts
    SQL-string predicates natively).  Both emit
    `agent_run_operations` rows; `pql.update` reuses the merge
    path's CDF-based `_capture_value_changes` for the opt-in
    `lineage_value_changes` capture.  New HTTP routes
    `POST /api/pql/update` + `POST /api/pql/delete` mirror the
    write-table / merge auth pattern (`MODIFY` privilege on
    target).  Alembic migration `ee3f6h8j0l2n` extends
    `ck_agent_run_operations_op_name` with six new op names
    (update / delete / drop_table / create_schema / drop_schema
    / alter_table) in one shot so Phase 63 needs only one
    migration.  ORM CHECK constraint in
    `pointlessql/models/agent_run_audit.py` widened in lockstep.
    13 new pytest cases in `tests/test_update_delete.py`.
  - 63.3 — soyuz `update_table` facade for ALTER TABLE COMMENT:
    **deferred** per plan rationale.  Cross-repo soyuz tag bump
    + client regen is out of scope; the editor's table-detail
    UI (Phase 17.4) already handles ALTER TABLE COMMENT /
    properties.  The dispatcher's `ALTER_TABLE` branch returns a
    structured "use the table-detail UI" error so the parser
    path stays live for a future Phase 63.5 to wire in.
  - 63.4 — `pointlessql/api/sql_dispatcher.py` (new): one
    `dispatch(stype, ast, …)` entry point + per-StmtType
    branches.  SELECT keeps the existing DuckDB rewriter path
    (no agent_run created — matches today's behaviour).  Write
    branches (INSERT FROM SELECT, CREATE TABLE AS SELECT,
    UPDATE, DELETE, MERGE, DROP TABLE, CREATE SCHEMA, DROP
    SCHEMA) start a one-shot `agent_run` with
    `agent_id='sql-editor'` BEFORE invoking the primitive; the
    PQL primitives' `operation_context` then emits
    `agent_run_operations` against that run id automatically.
    DDL branches emit their own op row directly via SQL since
    the soyuz client has no operation_context wrapper.
    [pointlessql/api/sql_routes.py:202-440](pointlessql/api/sql_routes.py#L202-L440)
    shrinks dramatically: parse → classify → dispatch →
    serialize.  EXPLAIN ANALYZE keeps its inline path
    (SELECT-only).  Per-branch privilege checks reuse
    `check_privilege` (SELECT on source refs + MODIFY /
    USE_SCHEMA on target).  10 new pytest cases in
    `tests/test_sql_dispatcher.py`.
  - 63.5 — `pointlessql/pql/sql_merge_translator.py` (new):
    translates `exp.Merge` → `MergeCallSpec` for the
    dispatcher's MERGE branch.  Supports the `WHEN MATCHED
    THEN UPDATE` (+ optional `WHEN NOT MATCHED THEN INSERT`)
    upsert subset of `pql.merge`; everything outside that
    raises `SQLMergeUnsupportedError` with structured guidance
    pointing the user at `POST /api/pql/merge` (which accepts
    JSON for elaborate scenarios).  Conditional WHEN clauses,
    `WHEN MATCHED THEN DELETE`, `WHEN NOT MATCHED BY SOURCE`,
    multiple WHEN MATCHED branches, and complex non-EQ ON
    predicates are all rejected.  9 new pytest cases in
    `tests/test_sql_merge_translator.py`.
  - 63.6 — `POST /api/sql/execute_batch` (new): runs `;`-
    separated statements via the same dispatcher.  `atomic=True`
    opens a single per-batch agent_run and calls
    `pql.rollback` (Phase 16) on the prior write ops on
    failure.  `atomic=False` (default) makes each write its
    own run; failures stop the batch but earlier writes stay.
    Frontend toggle deferred to a polish Sprint 63.6.1 — the
    server-side route is callable today.
  - 63.7 — `frontend/js/sql_editor/execute.js` +
    `frontend/templates/pages/sql_editor.html`: statement-type
    badge above the result widget (colour-coded SELECT /
    INSERT / UPDATE / DELETE / DROP); destructive-statement
    confirmation modal (regex heuristic for `DROP TABLE/SCHEMA`
    and `DELETE` without `WHERE` — false positives are
    acceptable since the modal is a UX speed-bump, not a
    security gate); new `dml`/`ddl` result-render branch
    showing `<rows_affected> on <target>` + a "View op trace"
    button deep-linking to `/runs/<run_id>`; existing SELECT
    rows-table branch unchanged.
  - 63.8 — Audit-FK wiring: `pointlessql/api/_audit_helpers.py`
    `record_query_async` accepts `agent_run_id` + `read_kind`
    kwargs; dispatcher passes both so editor writes land in
    `query_history` with the originating agent_run_id and
    `read_kind='sql_dml'` / `'sql_ddl'`.  `pointlessql.enums.ReadKind`
    extended with `SQL_DML` and `SQL_DDL` values.
    `/runs/<id>` already joins `query_history` by
    `agent_run_id` (Phase 13.10) so editor writes show up
    in the run's queries panel without further work.
  - 63.9 — Tests + close: 31 new pytest cases overall.
    `feedback_skip_pytest` rule applies to old tests but
    Phase-63 surfaces are merge-blocking — full suite run
    confirms 147 pass across the touched paths
    (test_sql_parser + test_sql_execute + test_sql_dispatcher
    + test_sql_merge_translator + test_update_delete +
    test_pql + test_merge_value_changes + test_merge_rejects).
    `ruff check` / `pyright` / `pydoclint` clean on every new
    or modified file.

  **Why this matters:** Phase 14's external-write scanner
  treats writes that have no `agent_run_operations` row as
  "unattributed" anomalies.  Pre-Phase-63, an editor write
  (had it been allowed) would have triggered that scanner
  every time.  Now editor writes flow through the same audit
  trail as Hermes-driven writes and the scanner correctly
  skips them as attributed.

- **Phase 62 — MLflow slim-down + catalog hand-off ✅ closed
  (2026-05-09).**  Symmetric application of the Phase-61 dbt
  pattern to MLflow.  Both embedded MLflow iframes (the `/ml`
  rail page and the model-detail "MLflow" tab) removed; `/ml`
  becomes a slim cockpit (Recent model registrations + Recent
  training runs + "Open in MLflow UI" external link), and the
  truly integrative pieces (which UC tables are model-prediction
  destinations, which recent registrations live in a given
  schema) hoist into the catalog flow.  Subprocess + reverse-
  proxy stay alive so the deep-links still resolve.

  - 62.F-Server-1:
    ``pointlessql/services/models_lineage.py`` gains
    ``aggregate_table_ml_relations()`` — single-query reverse
    index over ``lineage_row_edges.source_model_uri``,
    grouped by ``(target_table, source_model_uri)`` and parsed
    through ``models:/<full>/<version>``.  Exposed via the new
    ``GET /api/ml/table-relations?catalog=&schema=`` route in
    ``pointlessql/api/models_routes.py`` — analog of
    ``/api/dbt/manifest`` for the dbt side.  One pytest case
    in ``tests/test_models_lineage.py`` covers grouping +
    catalog/schema scoping.  Phase-62 reverse index covers only
    the *scoring* direction; "trained from this table"
    attribution would need a soyuz cross-reference per request
    and is deferred.
  - 62.A: ``frontend/templates/pages/mlflow.html`` — drop
    iframe + the inline "MLflow not running" alert (hoisted to
    a top-level card).  Header gains an "Open in MLflow UI"
    external button when subprocess is running.  Body becomes
    two cockpit cards driven by the new
    ``frontend/js/pages/mlflow_cockpit.js`` Alpine factory:
    Recent model registrations (10 latest from ``/api/models``)
    + Recent training runs (5 latest agent_runs filtered
    client-side by ``mlflow_run_id``).
    ``pointlessql/api/agent_runs_routes/_serializers.py``
    adds ``mlflow_run_id`` to the run-serialization output so
    the cockpit can filter + render deep-links.
  - 62.B: ``frontend/templates/pages/model.html`` — drop the
    iframe-bearing 4th tab ("MLflow") entirely; page is now
    4 tabs (Overview / Versions / Lineage / Promotion).
    Header gains an "Open in MLflow UI" external button
    deep-linking to the model registry.  Each Versions-table
    row's ``mlflow_run_id`` cell is now a deep-link to
    ``/mlflow/#/runs/<id>``.
  - 62.C: ``frontend/js/pages/dbt_schema_context.js`` extended
    with ML state (``mlAvailable``, ``mlModelByTable``,
    ``mlModels``, ``mlModelsLoading``).  ``init()`` fans out two
    parallel fetches (``/api/ml/table-relations`` scoped to the
    schema + ``/api/models`` filtered by catalog/schema).
    ``frontend/templates/pages/tables.html`` gains an inline
    "ml" badge on table-name rows that are model-prediction
    destinations (next to the existing dbt badge) plus a
    "Recent ML registrations" mini-card after the dbt card.
    Single-quoted Alpine attributes per BUG-64-01.
  - 62.D: New ``frontend/js/pages/ml_table_context.js`` Alpine
    factory (registered through ``bootstrap.js``).
    ``frontend/templates/pages/table.html`` wraps the existing
    ``dbtTableContext`` div in an outer ``mlTableContext`` div
    and renders a ``<template x-if="hasMl">`` "ML models" card
    next to the dbt card listing scoring models with edge
    counts + deep-links to ``/mlflow/#/models/<full>/versions/<v>``.
  - 62.E: ``frontend/js/pages/catalog_tree.js`` extended with
    ``mlRelations: Set`` + ``isMlTable(c, s, t)`` helper,
    populated via ``fetchMlRelations()`` in ``load()``.
    ``frontend/templates/components/sidebar.html`` table loop
    wraps both pills in a single ``ms-auto`` flex container so
    dbt + ml badges sit side-by-side without layout breakage.
  - All five surfaces silently no-op on installs without
    inference edges (empty response from ``/api/ml/table-relations``
    → empty ``mlRelations`` / no badge).  Only one new Python
    route; everything else reuses the existing ``/api/models/*``
    + ``/api/runs`` endpoints client-side.  No DB-schema
    changes — all data lives in
    ``lineage_row_edges.source_model_uri`` (Phase 21.7).

- **Phase 61 — dbt tab slim-down + catalog hand-off ✅ closed
  (2026-05-09).**  Embedded dbt-docs iframe removed and the
  truly integrative pieces (which UC tables are dbt-managed,
  recent dbt runs while browsing the catalog) hoisted into the
  catalog flow.  Subprocess + reverse-proxy stay alive so the
  new "Open dbt-docs" external-tab link still resolves.
  Established the pattern: **link out for tool-internal
  features, keep cross-tool integrative views first-class** —
  applies symmetrically to MLflow next.

  - 61.A: ``frontend/templates/pages/dbt.html`` — drop "Pipeline
    docs" tab + iframe; default-active flips to "Recent runs"
    (auto-loads); header-row "Open dbt-docs" external button
    when subprocess is running; setup-instructions alert hoists
    above the tab strip when subprocess isn't.
  - 61.B: New ``frontend/js/pages/dbt_schema_context.js`` Alpine
    factory (registered through ``bootstrap.js``).
    ``frontend/templates/pages/tables.html`` (schema-detail)
    gains an inline "dbt" badge on table rows that match a dbt
    model (deep-links to ``/dbt-docs/#!/model/<unique_id>``)
    plus a "Recent dbt runs" mini-card after the Tables card.
    Quoting bug caught in browser playbook: outer ``x-if=""``
    collided with ``|tojson`` double quotes; fixed by
    single-quoting the Alpine attributes.
  - 61.C: ``frontend/js/pages/catalog_tree.js`` extended with
    ``dbtRelations: Set`` + ``isDbtTable(c, s, t)`` helper,
    populated via ``fetchDbtManifest()`` in ``load()``.
    ``frontend/templates/components/sidebar.html`` table loop
    renders a tiny "dbt" pill in the tree.
  - 61.D: New ``frontend/js/pages/dbt_table_context.js``
    resolves the manifest model for the current table.
    ``frontend/templates/pages/table.html`` gains a
    ``<template x-if="dbtModel">`` card after Metadata showing
    unique_id, materialization badge, test count, and an
    "Open in dbt-docs" deep link.
  - All four surfaces silently no-op on installs without a
    dbt manifest (404 from ``/api/dbt/manifest`` → empty
    ``dbtRelations`` / null ``dbtModel``).  No new Python
    routes; everything reuses the existing ``/api/dbt/*``
    endpoints client-side.

- **Phase 59 — Comprehensive UX-tour quality sweep ✅ closed
  (2026-05-08).**  60 implementable findings (out of 71 total,
  11 DESIGN deferred to Phase 60+) landed across 7 sub-sprints
  in one autonomous run + an 8th close commit, clearing all 8
  cross-cutting patterns.

  - 59.1 (``c0d93ae``): CONTENT-jargon sweep + ANSI-strip + 4
    isolated logic fixes.  /queries label rewrites, /audit/by-table
    description, /admin/system-info "Phase 29.3" jargon dropped,
    DuckDB ANSI-escape codes stripped, "Pull-modell" / "push-modell"
    German typo fixed, Source-card SHA-256 sentinel hidden when
    bytes ARE captured, Lineage-tab self-node duplication
    eliminated.
  - 59.2 (``2fc3e36``): Bootstrap-tab URL-state global helper.
    New ``frontend/js/tab_sync.js`` reads ``?tab=&subtab=`` on
    load and mirrors active-tab state back via
    history.replaceState.  Eleven templates gained
    ``data-pql-tab-key="<key>"``; 7 page-level + 4 run-detail
    sub-pane partials.
  - 59.3 (``4be934f``): Auth/error chromeless layout +
    ``pages/429.html``.  Login, register, 403, 404, 500 migrated
    away from full-app chrome.  Rate-limit middleware now
    renders the new template instead of a bare ``<h1>`` body.
  - 59.4 (``5a68258``): ``_macros/filter_collapsible.html`` —
    Bootstrap-collapse wrapper for dense filter rows.  Applied
    default-collapsed to /audit/inbox (6 fields), default-
    expanded to /queries (3 fields).
  - 59.5 (``70981b1``): Icon-rail re-mapping.  New AUDIT and
    REVIEWS top-items between ALERTS and PRODUCTS.  FEDERATION
    label/icon/href updated to CATALOG (section key
    ``federation`` kept internally).  Admin footer icon swapped
    bi-shield-check → bi-tools to free the icon for AUDIT.
    context_panel grew AUDIT + REVIEWS branches.
  - 59.6 (``a7cf5b6``): Sub-pane helper-text dual-mode sweep —
    /dashboards and /alerts sidebar helpers now reference both
    a UI path and an agent tool.  /connections, /volumes, /dbt
    skipped (share the catalog tree, no per-page sidebar to
    update).
  - 59.7 (``d1d90db``): Empty-state quality sweep on /volumes
    (3-step Docker / Python / Hermes), /models (3-step MLflow
    / Hermes / Docs), /branches (dual-mode notebook + agent).
  - 59.9 (this entry): Phase close — ROADMAP, CHANGELOG, memory.

  Tour artefacts:
  ``docs/internal/phase59_audit_findings.md`` (555 lines)
  + ``docs/internal/phase59_screenshots/`` (65 PNGs across 8
  themed folders).  Pattern P-2 was user-confirmed mid-tour
  (memory: ``feedback_auth_pages_chromeless.md``).

- **Phase 58 — Phase-57 carve-out trio closed.**  Three small
  deferred items from Sprint 57.8 land in one autonomous pass
  (single commit) post the user-prompt "mache die sofort follo
  up und pahse 58 noch ferig".  (1) admin_workspaces "Create"
  form → Bootstrap modal — closes the one DESIGN finding from
  the 57.1 audit.  (2) admin_audit_sinks empty-state icon
  ``bi-broadcast`` → ``bi-broadcast-pin`` — closes the one
  CONTENT finding.  (3) Query-card "View full SQL" drawer
  trigger via the Phase-56.8 ``detail_drawer`` macro — surfaces
  only when SQL > 700 chars so short queries stay clean.  Alpine
  listTable re-add on the queries card-grid stays parked (no
  user signal yet).  17 query-history + 12 admin_workspaces
  tests green.

- **Phase 57 — Phase-56 carve-outs + route-test coverage closed.**
  Nine sub-sprints in one autonomous session post the user-prompt
  "plane aus!" on (1) ``queries.html`` Tables→Cards, (2) DESIGN-
  tagged findings from the 56.1 audit, (3) test-coverage sweep on
  admin_api_keys / federation / jobs / dashboards.  Plan-phase
  audit again reduced the set: the "DESIGN-tagged findings" carve-
  out turned out to be effectively empty (Section 4 of the
  ``phase56_audit_findings.md`` declared ``[DESIGN]`` as a
  tag-category but no individual finding actually carried the tag
  — all CONTENT/STRUCTURAL and folded into Sprint 56.10).  Sprint
  57.1 was repurposed as an audit-Ersatz on the ~15 surfaces the
  56.1 audit had never covered, producing 10 STRUCTURAL findings
  + 1 CONTENT + 1 DESIGN.  Net delta: ``/queries`` is now a
  card-grid with hljs SQL syntax-highlighting + server-side
  offset Load-More analog Phase 55.1 ``/runs``;  ``filter_kind``
  / ``status`` / ``since`` move to server-side Form-GET selects;
  ~85 new pytest cases across federation_routes (26),
  dashboards_routes (16), jobs_routes (14), admin_api_keys
  edge-cases (8), query history offset (5), card render (2);
  mobile data-label sweep on 7 more surfaces (admin_audit_sinks,
  admin_review_destinations, admin_workspaces dual tables,
  volumes, volume_detail, job_detail dual tables, branch_detail
  audit-log).  124 tests green across the touched test files.
  Carve-outs deferred to Phase 58: admin_workspaces "Create" form
  → modal (DESIGN), admin_audit_sinks empty-state icon swap
  (CONTENT-cosmetic), Alpine listTable re-add on queries-cards
  (only if user-replay calls for it).  Browser-replay verification
  for the queries cards + hljs render is left for the user post-
  rebuild — same handling as 54 / 55 / 56.

- **Phase 56 — UX-polish + bug-hunt + semantic-content review
  closed.**  Three-wave audit-first sweep post the user-prompt
  "wir machen bug-hunting … und auch hunting von schlechter
  visualisierung … die *richtigen*, semantisch korrekten Inhalte".
  12 sub-sprints in one autonomous session.  Plan-phase audit
  collapsed the implementation set substantially: all 9
  BUG-53-NN markers turned out to be already-fixed-but-not-closed
  (closed in 56.2 with a per-marker evidence trail in
  ``_notes.md``); the worried-about Alpine x-data quoting risk
  on 10 templates turned out to be already-safe via Jinja's
  default ``|tojson`` ``\\uXXXX``-escape (regression test pins
  it); four of the Phase-53 visual-debt patterns (#1
  outline-button-opacity, #2 errors-no-sidebar, #6 UUID format,
  #8 tab-badges) were already-fixed-but-not-closed by earlier
  phases.  Net surface changes: 8 empty-states standardised
  on ``components/empty.html`` with action-oriented messages;
  7 list-tables get ``data-label`` for mobile-collapse; new
  display-layer Jinja filters ``format_uuid`` + ``format_hash``;
  three new reusable macros (``truncate_cell``, ``copy_btn``,
  ``detail_drawer``) applied across 13 surfaces; tables→cards
  conversion on ``agent_reviews_list`` + ``alerts``; semantic-
  content rewrites on three high-traffic descriptions
  (audit-inbox, audit-queries, run-source).  The user's
  emphasis on "die richtigen Inhalte" (semantically correct
  content) added Sub-Sprint 56.10 as a dedicated content-
  rewrite pass distinct from the layout-debt Wave-2/3
  mechanical sweeps.

- **Phase 55 — UI polish nachzug (post-Phase-54) closed.**  Closes
  the three explicit Phase-54 carve-outs (accordion gap on two
  more admin pages, ``/audit/queries`` server-side pagination,
  ``/runs`` + ``/audit/search`` HTMX/fetch infinite-scroll Load-More)
  plus a smaller-BS-pattern audit.  Six sub-sprints in one
  autonomous session.  The plan-phase audit again reduced the set:
  ``agent_run_compare.html`` had no ``.alert`` block (the
  Phase-54 carve-out misidentified it; the actual disclaimer lives
  on ``run_compare.html`` as a footer), and the smaller-BS pattern
  audit dropped Toast / Progress / Link-utilities for being below
  the ≥ 3-real-surface threshold.  Sticky-Top survived: a new
  ``.pql-thead-sticky`` rule pins the column row at
  ``top: var(--pql-topbar-height)`` with ``z-index: 1010`` and
  is applied to ``/runs``, ``/audit/search``, ``/admin/audit``,
  ``/agent-reviews``, ``/branches``.  ``listTable`` gains a
  ``refreshRows()`` method so HTMX-appended rows fall under the
  active filter / sort.  Per-dialect FTS ``search`` (SQLite +
  Postgres) now accepts ``offset`` so the audit-search lake can
  stream pages.

- **Phase 54 — UI overhaul implementation (M = Modernize) closed.**
  Implements the Phase-53 ``ui-overhaul-proposal.md`` Size-M
  recommendation in six sub-sprints.  The plan-phase code-audit
  reduced the actionable set significantly: ``frontend/css/`` has
  no ``.btn-outline-*`` opacity override, UUID format is dashed
  consistently, the all-zeros SHA-256 sentinel is never written,
  ``runs_list.html`` is responsive-table-only without mobile-card
  rendering, and three of the "walkthrough doc drift" entries
  pointed at the right URLs already.  Sprint 54.1 flips
  ``hide_sidebar=False`` on error templates so 403/404/500 keep
  the icon-rail.  Sprint 54.2 wires the long-prepared color-modes
  toggle: anti-FOUC inline init in ``<head>``, 3-button dropdown
  (Light / Dark / Auto, ``data-bs-theme-value``), delegated click
  handler that persists via ``localStorage.pql.theme`` and
  re-applies on OS prefer-changes when in ``auto``.  New users
  default to ``auto``.  Sprint 54.3 lands a Bootstrap 5.3
  ``pagination`` macro (``_macros/pagination.html``) plus a
  ``paginate_url`` Jinja global and adopts both on
  ``/admin/audit`` (truncation flag → real ``offset``-based
  pager backed by a separate ``COUNT(*)``).  ``/runs``,
  ``/audit/queries``, ``/audit/search`` deferred — they interact
  with Alpine ``listTable`` filtering or fetch-driven JS rendering
  and need a UX pass.  Sprint 54.4 converts four 8-10-line
  ``.alert-info`` headers on ``/admin/audit-sinks``,
  ``/admin/api-keys``, ``/admin/system-info``,
  ``/admin/external-writes`` to collapsed-by-default
  ``accordion-flush`` "What is this page?" blocks; copy
  preserved verbatim.  Sprint 54.5 fixes BUG-53-01 (help-icon
  popover ``|safe`` → ``|e`` so the attribute boundary stays
  balanced), adds the missing BUG-53-09 ``/agent-reviews`` list
  page (paginated via the 54.3 macro), and rounds out the
  compare-runs nav-tabs with count badges on Lineage / Rejects /
  Cells / Column lineage (previously only Operations + Tool
  calls had badges).  Six commits local-only.

- **Phase 53 — Full replay sweep + Bootstrap UI overhaul
  evaluation closed.**  Diagnose-only phase; no UI code changes.
  Sprint A fetched 10 Bootstrap 5.3 docs/example pages (dashboard,
  sidebars, headers, footers, album, color-modes, accordion,
  scrollspy, pagination, getting-started) and produced
  ``docs/research/bootstrap53-gap-analysis.md``.  Sprint B walked
  35 of 47 browser+hybrid playbooks against the live stack, took
  ~50 screenshots organized into 25 subdirectories under
  ``docs/e2e-walkthroughs/screenshots/phase53-replay/``, and
  captured 10 bugs (BUG-53-01 .. BUG-53-10) plus 10 visual-debt
  patterns in
  ``screenshots/phase53-replay/_notes.md``.  Sprint C
  synthesized everything into ``docs/ui-overhaul-proposal.md``
  with three sized recommendations (S/M/L) and a concrete pick
  (M — Modernize, ~1 week).  Sprint D closes the phase.  Notable
  findings: outline buttons render at low opacity and read as
  disabled across ≥ 5 surfaces (recurring CSS bug); error pages
  drop the icon-rail sidebar; ``/audit/search`` description has
  unescaped HTML; Bootstrap 5.3 ``data-bs-theme`` color-modes
  is wired in CSS (full light-mode override block in
  ``base.css``) but has no toggle UI.  Phase 54 (if approved
  by user) implements the M-size overhaul.

- **Phase 52 — Playwright walkthrough completion pass closed.**
  Pure-documentation pass; no code changes.  Audited the 51-file
  e2e walkthrough corpus, found 17 zero-coverage and 13 thin
  playbooks, plus 4 templates with no walkthrough at all.
  Sprint A: tagged every walkthrough with a ``> **Mode:**``
  block (browser / hybrid / hermes / curl) and rewrote the
  README inventory into a 4-table grouping.  Sprint B: wrote 3
  new walkthroughs for the missing templates (``volumes.md``,
  ``model-compare.md``, ``agent-review-detail.md``).  Sprint C:
  appended condensed ``## Playwright MCP script`` sections to 11
  zero-coverage playbooks; Sprint D: bumped 12 thin playbooks to
  ≥ 5 explicit ``browser_*`` MCP calls.  Sprint E: smoke-replayed
  the 5 gold-standard playbooks against the live stack — all
  five render 200; 2 selector bugs in the new MCP scripts
  surfaced and were fixed in the same edit (BUG-41-01,
  BUG-41-02).  Final corpus: 54 walkthroughs, 40 ``Mode:
  browser``, 8 hybrid, 6 hermes, 1 curl.  ``mkdocs build
  --strict`` warning count unchanged at 18.

- **Phase 51 — Git-backed workspaces closed.**  Workspaces can
  now register 1..n git repositories whose contents feed the
  yaml loaders (data products + conventions) and the asset
  bridges (notebooks + dashboards + saved queries).  Read-only
  by design — git is truth, DB is cache, edits flow through the
  team's git tool / PR.  Seven surfaces shipped across seven
  sub-sprints (51.6 OAuth deferred — see Carve-outs below):

  - **51.1 — Foundation.**  New ``pointlessql/git/`` package:
    ``GitProvider`` Protocol + ``GenericGitProvider`` /
    ``GitHubProvider`` implementations, async subprocess
    helper, error family.  Generic clone+pull via depth-1 git
    subprocess; GitHub adds HMAC-SHA-256 signature
    verification of ``X-Hub-Signature-256``.  New
    ``services/secrets.py`` with Fernet authenticated
    encryption keyed off an install-scoped master key in
    ``system_keys`` (replaces the base64url-only path Phase 20
    used for cloud-trail credentials).  Two ORM tables
    (``workspace_repos`` + ``workspace_repo_secrets``) via
    Alembic ``aa9b1c3e5d7f``.  Service surface
    (``create_repo`` / ``add_secret`` /
    ``rotate_webhook_secret`` / ``delete_repo`` /
    ``sync_repo`` / ``list_repos_due_for_sync`` /
    ``list_repos_for_workspace``).  4 new ``ErrorCode``
    members (``WORKSPACE_REPO_*``), ``WorkspaceReposSettings``
    under env prefix ``POINTLESSQL_REPOS_*``,
    ``cryptography>=44.0`` added.  34 new tests.

  - **51.2 — Yaml-loader integration.**  New
    ``discover_repo_yaml_files`` walks every workspace repo's
    clone dir against ``settings.workspace_repos.
    yaml_search_globs``; new ``load_contracts_for_workspace``
    + ``load_conventions_for_workspace`` combine env-paths +
    repo-discovered yaml.  ``build_post_pull_loader_hook``
    returns a ``sync_repo``-compatible hook that re-runs both
    loaders after every successful pull; counts surface on
    ``SyncOutcome.loaded_data_products`` /
    ``loaded_conventions``.  Loader errors stay isolated —
    one bad yaml does not poison the sync.  6 new tests.

  - **51.3 — Notebook + Dashboard + Saved-Query bridge.**
    ``resolve_notebook_path`` accepts a new ``repo:<workspace_id>:
    <slug>/<rel>.py`` spec that resolves against the clone dir
    instead of the legacy notebooks-dir; traversal-rejection
    + suffix-check carry over.  New
    ``pointlessql/repo_assets/`` package with
    ``load_dashboards_from_yaml`` / ``load_saved_queries_from_yaml``
    + per-workspace drivers.  ``Dashboard`` + ``SavedQuery``
    rows gain ``source`` (``'ui'`` or ``'repo:<slug>'``) +
    ``repo_yaml_path`` columns via Alembic ``bb1d4f6e8a0c``
    so the admin UI can render git-canonical rows as read-only.
    13 new tests.

  - **51.4 — Webhook receiver + cron sync loop.**  New
    ``POST /webhook/git/{repo_id}`` endpoint —
    unauthenticated at the middleware layer because the HMAC
    signature *is* the auth.  Signature verified against the
    repo's stored ``webhook_secret``; non-push events return
    202 ``status='ignored'`` without scheduling work.  Push
    events on the default branch schedule ``sync_repo`` as
    ``asyncio.create_task`` (fire-and-forget; webhook caller
    gets 202 immediately).  Lifespan-managed
    ``_workspace_repos_sync_loop`` ticks every
    ``settings.workspace_repos.sync_interval_seconds``
    (opt-in default-disabled, min 60 s) and pulls every
    repo whose ``last_synced_at`` is older than the cadence.
    ``/webhook/git/`` added to ``PUBLIC_PREFIXES`` and the
    CSRF-exempt list.  9 new tests.

  - **51.5 — Admin JSON API.**  Eight admin-gated endpoints
    behind ``/api/admin/repos`` (list / create / detail /
    sync / add-or-rotate-secret / revoke-secret /
    rotate-webhook-secret / delete).  Reveal-once webhook
    secret on creation; subsequent ``GET`` calls never echo
    plaintext (secrets render as
    ``{kind, created_at, rotated_at}`` only).  Every mutation
    stamps an ``audit_log`` entry; workspace-scoping enforced
    via ``_load_repo`` (other-workspace repos 404 even for
    tenant admins).  10 new tests.

  - **51.7 — Plugin tools.**  Four new agent-callable Hermes
    tools in ``hermes-plugin-pointlessql``:
    ``pql_list_workspace_repos`` (no args),
    ``pql_get_workspace_repo`` (slug),
    ``pql_trigger_repo_sync`` (slug — supervisor scope
    enforced server-side),
    ``pql_repo_sync_history`` (slug + limit).
    ``PointlessClient`` extended with four matching methods.
    Slug→id resolution lives client-side so a future
    server-side slug-keyed route can drop in without
    breaking the tool contract.  8 new tests; plugin total
    141 → 149.

- **Phase 50 — Native Data-Product support closed.**  PointlesSQL
  now treats any UC schema as an opt-in data product when its
  data team commits a ``pointlessql.yaml`` declaring steward,
  SemVer version, freshness-SLA and per-table schema contract.
  Yaml is canonical; git-blame is the audit log.  Six surfaces
  shipped across five sub-sprints:

  - **50.1 — Foundation.**  New ``pointlessql/data_products/``
    package: ``DataProductColumnSpec``/``TableContract``/
    ``Contract`` Pydantic models (11 column types),
    ``DataProductRef(str)`` validation type (mirrors Phase-49c
    TableFqn), four ``DataProductError`` subclasses (RFC 9457
    integration), yaml loader with idempotent UPSERT +
    steward-FK resolution against ``users``.  Two new ORM
    tables (``data_products`` + ``data_product_contract_events``)
    via Alembic ``rr8u0w2y4a6c``.  4 new ``ErrorCode`` members,
    ``DataProductsSettings`` under env prefix
    ``POINTLESSQL_DATA_PRODUCTS_*``.

  - **50.3 — Enforcement.**  Pure-functional
    ``ContractDiffResult`` core in ``data_products/_diff.py``
    + two adapters (engine-tuples for pre-write, Delta-schema
    for live diff).  Type canonicalisation collapses
    ``int64``↔``long`` / ``float64``↔``double`` / ``decimal*``
    aliases.  ``check_contract_for_write`` resolves workspace
    from ``agent_run_id``, looks up the cached contract,
    classifies into ``compliant`` / ``schema_drift_warning`` /
    ``violated`` / ``no_contract``.  Pre-write hooks in
    ``pql/_write.py`` + ``pql/_merge.py`` raise
    ``DataProductContractViolation`` *before* any Delta IO
    when the diff is breaking.  ``OperationRecorder.
    pending_contract_event`` tuple +
    ``record_contract_event_after_commit`` post-commit hook
    persist one event row per check; the exception path also
    persists so the audit trail shows refused attempts.

  - **50.4 — Freshness Scanner.**  Background loop walks every
    cached ``DataProduct`` whose ``sla_minutes`` is set,
    observes the latest write timestamp via
    ``DeltaTable.history()`` per UC table, emits one
    ``pointlessql.data_product.sla_violated`` CloudEvent
    when the age exceeds the SLA.  ``last_alerted_at`` is
    stamped after each emit; the re-alert window (default 60
    min via ``re_alert_suppress_minutes``) suppresses event
    storms.  Opt-in via
    ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS≥60``.
    New ``EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED`` registered
    in the governance-events registry.

  - **50.2 — Web UI.**  ``/data-products`` index +
    ``/data-products/{catalog}/{schema}`` 5-tab detail page
    (Overview / Contract / Diff / Lineage / Compliance), with
    cytoscape mini-DAG of producers/consumers via
    ``lineage_row_edges``.  Five JSON endpoints:
    ``GET /api/data-products`` (workspace-scoped list),
    ``GET /api/data-products/{cat}/{schema}`` (detail incl.
    last-50 events), ``GET /.../diff`` (live yaml↔Delta diff
    per table), ``GET /.../lineage`` (cytoscape graph),
    ``POST /.../reload`` (admin-gated yaml re-load).
    Icon-rail entry between SQL and Dashboards.

  - **50.5 — Plugin tools.**  Five new LLM-callable Hermes
    tools in ``hermes-plugin-pointlessql``:
    ``pql_list_data_products``, ``pql_get_data_product``,
    ``pql_get_data_product_contract`` (lighter contract-only
    surface), ``pql_check_contract_compliance`` (live diff),
    ``pql_data_product_compliance_history`` (recent events
    with per-call limit).  All five wired into ``register_all``
    so any keyed agent can use them; plugin client gains four
    new methods hitting ``/api/data-products/*``.

  Pyright budget unchanged at 497.  PointlesSQL test suite
  gained 31 new tests (10 ref-validation + 13 loader + 15
  enforcement + 5 scanner + 11 routes); plugin gained 7 new
  tests.  ``Mapped[str]`` columns stay unchanged —
  ``DataProductRef`` is-a ``str`` so SQLAlchemy absorbs it
  transparently.  Anti-goals preserved: no DLT-bundle-
  generator (PointlesSQL **is** the platform), no
  ``Mapped[NewType-or-subclass]`` on models, no domain-
  specific RBAC ladder (Workspace + scope surface gates
  everything).

- **Phase 49c — TableFqn validation type closed.**  Introduces
  ``pointlessql/table_fqn.py`` with a ``str``-subclass validation
  type for ``catalog.schema.table`` UC identifiers.
  ``TableFqn.parse(s)`` validates + raises ``ValidationError`` on
  malformed input; ``TableFqn.from_parts(c, s, t)`` skips
  validation for callers that already split the components.  Two
  byte-for-byte duplicate ``_split_three_part`` validators in
  ``api/pql_introspect_routes.py`` + ``api/pql_write_routes.py``
  consolidated into the single type.  13 producer sites
  (f-string FQN constructions in api/, services/, pql/) wrapped
  via ``TableFqn.from_parts``.  ``services/external_write_scanner``
  signatures fully typed end-to-end as a Step C reference example;
  remaining ~36 consumer signatures stay on plain ``str`` for
  incremental migration in future phases.  Anti-goal preserved:
  ``Mapped[str]`` columns on the 7 model classes carrying FQN
  semantics stay unchanged (``TableFqn`` is-a ``str`` so SQLAlchemy
  reads/writes the underlying string transparently).  Pyright
  budget unchanged at 497.  10 new ``tests/test_table_fqn.py``
  sanity tests pin the contract: subclass identity, JSON round-
  trip, f-string interpolation, parse/from_parts factories,
  segment properties, equality with plain ``str``.  3 commits:
  ``feat(types)`` (additive), ``chore(types)`` (migration),
  ``docs(roadmap)`` (close).

- **Phase 49b — Service-File Splits closed.**  Two oversize service
  files migrated into Phase-35-style per-axis subpackages.
  ``services/agent_runs/operations.py`` (929 LOC) → six-file
  subpackage: ``__init__`` (re-exports), ``_common`` (recorder
  + helpers), ``_rollback`` (5 exception classes), ``_lifecycle``
  (record_operation + operation_context), ``_lineage`` (3
  post-commit hooks), ``_rejects`` (1 hook), ``_value_changes``
  (1 hook).  ``services/audit_aggregator.py`` (913 LOC) →
  four-file subpackage: ``_query_builder`` (MetricSpec + the
  ~150-LOC metric-spec switch + filter helpers), ``_summary``,
  ``_timeseries``, ``_anomaly`` (rolling-baseline detection +
  per-run verdict + backfill).  Cross-module helpers dropped
  leading underscores per Phase 35 convention; module-internal
  helpers kept theirs.  Public API surface unchanged via
  ``__init__.py`` re-exports — every existing
  ``from pointlessql.services...operations import X`` continues
  to work.  Two tests updated (``test_operation_warnings.py``
  and ``test_dbt_test_failure_bridge.py``) for renamed cross-
  module helpers.  Pyright budget unchanged at 497.  1686 tests
  pass.  Two commits, one per file split.

- **Phase 49a — Repo-wide Lint-Sweep closed.**  Two-commit cleanup
  pass clearing pre-existing ruff E501 + pydoclint
  DOC502 / DOC503 / DOC601 / DOC603 violations accumulated since
  Phase 35.  119 ruff hits cleared via ``uv run ruff format``
  (68 files reformatted, mostly test-function signatures wrapped
  to satisfy the 100-char limit); 36 pydoclint hits cleared by
  realigning Raises sections from the framework-rendered
  ``HTTPException`` view to the body-literal typed-error view
  (``AuthenticationError`` / ``ResourceNotFoundError`` /
  ``ValidationError`` / etc.) and by filling in missing
  ``Attributes:`` lines for newer ``Mapped[]`` columns
  (``ApiKey.lineage_inbound``, ``LineageRowEdge.producer`` /
  ``.external_event_id``, ``LineageColumnMap.producer`` /
  ``.external_event_id``) plus the explicit ``status_code`` /
  ``error_code`` class vars on ``RollbackAmbiguous`` /
  ``RollbackStale``.  Pyright budget unchanged at 497.  1686
  tests pass.  Pre-commit was bypassed on the originating
  commits — running ``ruff format`` repo-wide once removes the
  accumulated drift in one pass.

- **Phase 48 — Primitive-Obsession StrEnum Sweep closed.**
  Five-sub-sprint refactor (1 additive + 4 batch migrations + 1
  CloudEvents registry) in one autonomous run.  Introduces nine
  StrEnums at ``pointlessql/enums.py``
  (``RunStatus`` / ``OpName`` / ``ReadKind`` / ``QueryStatus`` /
  ``ReviewSeverity`` / ``ReviewKind`` / ``AuditSinkType`` /
  ``EventOutcome`` / ``BranchAction``) covering every
  enum-shaped string column in the project.  StrEnum members
  compare equal to their string value, so DB-stored values,
  JSON wire format, and SQL CHECK constraint matching keep
  working unchanged: ``RunStatus.RUNNING == "running"`` is
  ``True`` and JSON serialises as ``'"running"'`` not
  ``'"RunStatus.RUNNING"'``.  Models stay on plain
  ``Mapped[str]`` per anti-goal.  Sprint 48.1 added the
  registry plus 13 sanity tests pinning every value
  byte-for-byte against the legacy ``frozenset`` / tuple
  constants
  (``VALID_STATUSES`` / ``VALID_OP_NAMES`` / ``VALID_READ_KINDS`` /
  ``REVIEW_SEVERITIES`` / ``REVIEW_KINDS`` / ``SINK_TYPES`` /
  ``BRANCH_ACTIONS``).  Sprint 48.2 migrated consumers in four
  batches by field-family: batch 1 RunStatus + QueryStatus
  (~11 files), batch 2 OpName + BranchAction (~13 files),
  batch 3 ReadKind (~5 files), batch 4
  AuditSinkType + EventOutcome + ReviewSeverity (~4 files).
  ``VALID_READ_KINDS`` is now derived from the StrEnum so the
  two cannot drift apart.  Sprint 48.3 introduced
  ``pointlessql/services/cloudevents/`` as the single import
  path for the 17 CloudEvents type literals; the legacy
  ``EVENT_TYPE_*`` aliases on ``services.agent_runs.events``
  and ``services.governance_events`` stay valid for
  back-compat.  Pyright budget unchanged at 497.  1686 tests
  pass (1673 baseline + 13 new enum sanity tests).

- **Phase 47 — NewType ID Hardening closed.**  Two-sprint
  refactor in one autonomous run.  Introduces
  ``RunId`` / ``OpId`` / ``QueryHistoryId`` / ``WorkspaceId``
  NewType aliases at ``pointlessql/identifiers.py`` and wires
  them through the public-API entry points of the agent-run
  audit pipeline and the query_history service.  Pyright now
  treats the four IDs as distinct nominal types — passing an
  ``OpId`` where a ``QueryHistoryId`` was expected fails type
  check, even though both erase to ``int`` at runtime.  Models
  stay on plain ``Mapped[str]`` / ``Mapped[int]`` per anti-goal
  (ORM integration with NewType is unspec'd).  Pyright budget
  unchanged at 497.  1673 tests pass (1667 baseline + 6 new
  identifier sanity tests).  Wraps land at the FastAPI
  Path/Query boundary (``RunId(run_id)``,
  ``QueryHistoryId(history_id)``) and at the
  ``operation_context`` cascade across 10 PQL primitives via
  ``cast(RunId | None, ...)``.  Wire format and DB-stored
  values are byte-identical.

- **Phase 46 — Test-Auth-Fixture Centralization closed.**
  Two-sprint refactor in one autonomous run.  Eliminates ~48
  local ``_admin_client()`` / ``_non_admin_client()`` /
  ``_bearer_client()`` / ``_client(**kwargs)`` helpers and ~7
  local ``Iterator[str]``-shaped ``supervisor_secret`` /
  ``auditor_secret`` / ``normal_secret`` API-key fixtures across
  55 test files.  Net delta -2027 / +1721 LOC across the
  six route-family batches.  1667 tests pass (1661 baseline + 6
  sanity tests).  No production-app changes; production ``app``
  remains the SUT.  Sprint 46.1 added six fixtures to
  ``tests/conftest.py``: ``admin_client``, ``non_admin_client``,
  ``anonymous_client`` (all yielding ``httpx.AsyncClient`` with
  pre-set cookies — or no cookies for ``anonymous_client``); and
  ``supervisor_secret`` / ``auditor_secret`` / ``api_key_secret``
  yielding the new ``ApiKeyFixture`` NamedTuple of
  ``(secret, row, headers)``.  Sprint 46.2 migrated the test
  files in six route-family batches: admin (2), audit (6),
  branch/rollback/promotion (3), models/ML (4),
  supervisor/scheduler (4), catch-all (36).  Four files
  deliberately kept local helpers per the plan's
  "different test pattern" carve-out: ``test_csrf.py`` (raw JWT
  injection), ``test_lineage_inbound_routes.py`` (custom
  ``federation_secret`` Bearer scope),
  ``test_api_key_gate.py`` (interleaved inline AsyncClient
  blocks reusing one ``transport`` variable),
  ``test_training_log_route.py`` (per-call ``X-Agent-Run-Id``
  header injection).  New ``tests/test_auth_fixtures.py`` (6
  cases) pins the fixture contract.

- **Phase 45 — Pyright Hot-Spot Cleanup closed.**  Five
  file-scoped sprints in one autonomous run, all at JSON / soyuz
  / DuckDB-plan deserialisation seams.  Pyright budget 559 → 497
  (62 warnings closed, 11.1% reduction).  No production-code
  refactor — pure type-narrowing via ``cast(dict[str, Any], …)``
  and ``cast(list[dict[str, Any]], …)`` at boundaries the
  ``isinstance`` narrower can't reach.  No runtime semantics
  change.  Sprint 45.1 narrowed ``audit_sinks_routes.py``
  (12 → 0) with two helpers ``_loads_obj`` / ``_loads_list``
  absorbing every ``json.loads(...) -> Any`` boundary.  Sprint
  45.2 narrowed ``services/sql/cost_estimator.py`` (14 → 0) and
  parenthesised two ``except TypeError, ValueError:`` (PEP 758
  lenient form, valid in Python 3.14) → ``except (TypeError,
  ValueError):`` so ``ValueError`` no longer shadows the
  built-in inside the handler.  Sprint 45.3 narrowed
  ``governance_routes.py`` (10 → 0) on UC ``columns`` /
  ``options`` payloads.  Sprint 45.4 narrowed
  ``volumes_routes.py`` (13 → 3 — three remaining are PyArrow /
  deltalake stub-gap, anti-goal compliant).  Sprint 45.5
  narrowed ``home_routes.py`` (16 → 0) on the UC ``get_tree()``
  cascade and the notebook ``_walk`` recursion.  Skipped the
  three biggest stub-gap files (``pql/_merge.py``,
  ``pql/_autoload.py``, ``services/lineage/inbound_parser.py``,
  197 warnings combined) per memory
  ``feedback_pyright_thirdparty_stubs.md`` — those need custom
  ``.pyi`` stubs for PyArrow / deltalake / OpenLineage, multi-week
  scope, queued for Phase 47 if/when the ROI becomes real.  No
  new tests; annotations don't add behaviour.

- **Phase 44 — Structured logging + traceback preservation
  closed.**  Five sub-sprints in one autonomous run.  Four gaps
  closed: ``JSONFormatter`` ignored ``extra={...}`` (half-done
  structured logs); 36 lossy broad-except sites
  (``logger.warning("op failed: %s", exc)``) dropped tracebacks;
  47 silent broad-except sites had no opt-out marker (deliberate
  best-effort renders weren't distinguishable from accidental
  silent failures); zero third-party loggers were quieted (httpx
  / urllib3 / sqlalchemy.engine debug noise drowning the
  application's own structured lines).  No Alembic.  Wire format
  strictly additive (legacy seven-field JSON envelope preserved
  when caller passes no ``extra=``).  16 new pytest cases.
  Pyright budget unchanged at 559/559.  Sprint 44.1 added
  ``_harvest_extras`` + ``_RESERVED_LOGRECORD_ATTRS`` so caller-
  supplied ``extra={"run_id": "..."}`` lands as top-level JSON
  keys; reserved attrs stay filtered.  Sprint 44.2 converted lossy
  Bucket-C logs (``logger.warning("...", exc)`` → ``logger.exception("...")``,
  ``logger.debug("...", exc)`` → ``logger.debug("...", exc_info=True)``)
  and added ``# bare-broad-ok: <reason>`` allowlist comments to
  silent Bucket-D sites; new AST-based
  ``tests/test_no_lossy_broad_except.py`` enforces both
  invariants.  Sprint 44.3 retrofitted nine high-value sites
  (scheduler / soyuz-lineage / ml-context / training-context /
  notebook-render / alert-dispatcher / audit self-track /
  read-audit) to use ``extra={...}`` so Grafana/Loki can key off
  ``run_id`` / ``op_name`` / ``webhook_url`` etc.  Sprint 44.4
  added per-library quieting (``httpx`` / ``urllib3`` /
  ``sqlalchemy.engine`` → WARNING; ``mlflow`` / ``dbt`` /
  ``papermill`` → INFO) with override via
  ``POINTLESSQL_LOG_THIRD_PARTY_LEVELS`` env var.  Global
  ``POINTLESSQL_LOG_LEVEL=DEBUG`` bypasses the quieting entirely.
  Sprint 44.5 added ``"BLE"`` to ``[tool.ruff.lint] select`` and
  closed two missing-noqa sites — the linter now catches
  broad-except regressions in addition to the AST quality lint.
- **Phase 43 — Error envelope + exception hierarchy unification
  closed.**  Five sub-sprints in one autonomous run.  Three
  asymmetries closed: zero-enum-for-error-codes, three orphan
  exception families, 42 bare-string ``HTTPException`` sites.
  Sprint 43.1 introduced the central ``ErrorCode`` ``StrEnum`` in
  ``pointlessql/error_codes.py`` (35 members grouped by domain);
  every ``PointlessSQLError`` subclass now references an enum
  member via ``error_code: ErrorCode = ErrorCode.X`` instead of a
  raw string.  Sprint 43.2 reparented ``BranchError`` (×6),
  ``RollbackError`` (×4), ``DBTStartupError`` /
  ``DBTExecutionError`` / ``MLflowStartupError`` (dual-parent with
  ``RuntimeError``), ``AuditIntegrityError``,
  ``BranchTagsCorruptError``, ``SQLParseError`` under
  ``PointlessSQLError`` so the centralised handler picks them up
  directly; new ``extension_members()`` hook on the base class
  surfaces structured fields automatically (replaces the inline
  ``isinstance(AuthorizationError)`` branch).  ``RollbackStale``
  flips 422 → 409 and ``RollbackAmbiguous`` 422 → 409 (semantic
  conflict, not request-validation).  Sprint 43.3 converted 42 →
  2 bare-string ``HTTPException`` sites; new
  ``PermissionDeniedError``/``ResourceNotFoundError``/``ConflictError``
  in ``pointlessql/exceptions.py``; ``DBTExecutionError``
  ``except`` blocks deleted (subclass now self-renders); 2 proxy-
  upstream 502s allowlisted via ``# bare-http-ok`` comment +
  ``tests/test_no_bare_http_exception.py`` lint test.  Sprint 43.4
  added ``ErrorEnvelope`` Pydantic models in
  ``pointlessql/api/error_envelope.py`` and
  ``STANDARD_ERROR_RESPONSES`` constants in
  ``pointlessql/api/error_responses.py``; applied selectively to
  13 plugin-facing routes so OpenAPI exposes the envelope.
  Sprint 43.5 (plugin-side) extended ``run()`` helper in
  ``hermes-plugin-pointlessql/.../tools/_common.py`` to parse
  ``application/problem+json`` body and surface ``code`` plus 11
  extension members to the agent envelope; falls back to legacy
  text shape for non-problem responses.  No Alembic migrations.
  Wire format strictly additive (StrEnum subclasses ``str``;
  legacy assertions stay green).  ~57 new pytest cases (5 +
  ~28 + ~19 + 4 PointlesSQL-side; 5 plugin-side).  Pyright
  budget unchanged at 559/559.
- **Phase 42 — Anomaly-Inbox System-Errors band closed.**  Single
  sprint (42.1) that surfaces foreign-Delta CDF subscriptions with
  ``last_error IS NOT NULL`` on ``/audit/inbox``.  New
  server-rendered ``<section data-inbox-section="system-errors">``
  above the existing filter form / sigma anomaly table on
  ``frontend/templates/pages/audit_inbox.html``; conditional on
  ``{% if system_errors %}`` so a healthy workspace renders zero
  noise.  Loader ``_load_system_errors`` in
  ``pointlessql/api/audit_inbox_routes.py`` queries
  ``cdf_tail_subscriptions WHERE workspace_id=? AND last_error IS NOT NULL``
  ordered ``last_tailed_at DESC NULLS LAST``.  Each row shows the
  truncated error, paused-badge if ``is_active=False``, last-attempt
  ISO timestamp, producer label, and an "Open admin" cross-link
  (auditor sees, admin clears — auditor scope stays read-only).
  No new Alembic migration, no new sigma metric (CDF errors are
  point-in-time state, not event counts), no acknowledge table
  (errors clear automatically on the next successful tail tick).
  4 new pytest cases (renders, hides, workspace-isolation,
  paused-marker).  Walkthrough ``audit-cockpit-deep.md`` extended
  with Part E (3 steps).
- **Phase 40.7 — Row-Trace fold-in of CDF events closed.**  Single
  sprint that resolves Phase-40.6's deferred boundary discussion.
  Foreign-Delta CDF events captured by the Phase-40.5 tail now
  fold into the existing row-trace walkback as contextual metadata
  per step — every walkback step gets a ``cdf_events: []`` field
  populated from
  ``cdf_tail_events WHERE workspace_id=? AND table_full_name=? AND row_id=?``.
  Walkback semantics stay unchanged (predecessors come exclusively
  from ``lineage_row_edges``); CDF captures are pure context, never
  new walkback steps.  New service helper
  ``pointlessql.services.cdf_tail.fetch_events_for_row`` mirrors
  ``fetch_value_changes_for_row``; new route helper
  ``_attach_cdf_events`` mirrors ``_attach_value_changes``.
  Template adds a new ``<details>`` block on
  ``pages/row_trace.html`` with version pill + change-type pill +
  timestamps; change-type pill extracted into reusable
  ``partials/_cdf_change_type_pill.html`` and shared with the
  Phase-40.6 table-detail CDF events tab.  No new Alembic
  migration, no new credential surface, no new plugin tool — the
  existing ``pql_row_trace`` ships ``cdf_events`` per step
  transparently.  3 new pytest cases (attach, empty-list-default,
  workspace-isolation).
- **Phase 40.6 — CDF Tail UI integration closed.**  Three thin
  sprints turn the Phase-40.5 capture surface into a fully
  browsable + agent-readable governance surface.  Sprint 40.6.1
  ships the admin subscriptions page at
  ``/admin/cdf-subscriptions`` (CRUD + ``Run tail now`` +
  table-FQN filter + only-active toggle) and adds an 8th card
  to the admin landing with active-count + with-errors badges.
  Sprint 40.6.2 mounts a 7th "CDF events" tab on the
  table-detail page, gated server-side on
  ``cdf_subscription is not None`` so tables without a
  subscription still show 6 tabs.  Sprint 40.6.3 ships two new
  auditor-scope read endpoints
  (``GET /api/audit/cdf-subscriptions`` +
  ``GET /api/audit/cdf-events``) and two new plugin tools
  (``pql_list_cdf_subscriptions`` +
  ``pql_recent_cdf_events_for_table``).  No new Alembic
  migrations, no new credential surface — the UI just
  surfaces what 40.5 captured.  9 new pytest cases
  PointlesSQL-side + 6 plugin-side.  50th end-to-end
  walkthrough at ``docs/e2e-walkthroughs/admin-cdf-tail.md``.
  Anti-goal kept: row-trace fold-in of CDF events stays
  deferred — they're a different boundary from
  ``lineage_row_edges`` and forcing the merge needs its own
  Phase 40.7 scope.
- **Phase 40.5 — Foreign-Delta CDF tail (pull-modell) closed.**
  Closes the deferred Sprint-40.2 sketch as a single sprint.
  New Alembic ``qq7t9v1x3z5b`` adds ``cdf_tail_subscriptions``
  (opt-in registry, ``UNIQUE(workspace_id, table_full_name)``)
  and ``cdf_tail_events`` (capture log, ``UNIQUE`` on
  ``(table_full_name, delta_version, row_id, change_type)``)
  so re-tails are idempotent.  ``services/cdf_tail.py`` exposes
  ``tail_subscription`` (sync) + ``tail_all`` (async walker that
  resolves ``storage_location`` via ``uc.get_table`` per tick
  and stamps ``last_error`` on failure).  Admin CRUD lives under
  ``/api/admin/cdf-subscriptions`` (GET / POST / toggle / DELETE)
  plus a manual ``POST /run-now``.  New ``CDFTailSettings``
  (``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS`` /
  ``..._HISTORY_LIMIT``) joins the root settings tree; the
  ``_cdf_tail_loop`` worker registers in the lifespan next to
  the external-writes scanner with the same opt-in
  (``interval_seconds == 0`` → off) + cancel-on-shutdown
  discipline.  Anti-goal "no new credential surface" preserved:
  the worker reuses whatever soyuz's ``storage_location`` already
  exposes; un-readable tables stamp ``last_error`` rather than
  failing the whole tick.  9 pytest cases.  Also closes a stale
  fixture gap — the autouse conftest now stubs
  ``app.state.uc_client`` with a default ``MagicMock`` so any
  test rendering ``/runs/{id}`` (which now reads UC mutations
  via ``soyuz_audit.fetch_for_run``) doesn't crash on a missing
  attribute.  ``test_run_detail_renders_operations_and_source_tabs``
  is back to green; full pytest sweep 1587/1587.
- **Phase 41 — Sprint 17.6 promote: Lineage sub-panes closed.**
  Single-sprint UX-consolidation phase post the
  "plane phase 41 komplett aus" plan.  Three new drill-down
  sub-pills (Row trace / Column trace / Value changes) live next
  to the existing Summary + Graph pills inside the Lineage
  top-tab on ``/runs/{id}``.  Each pane wraps one of the
  existing ``GET /api/lineage/{row-trace,column-trace,
  value-changes}`` endpoints; no new SQL surface, no new routes.
  The standalone ``/catalogs/.../rows/{id}/trace`` and
  ``/catalogs/.../columns/{name}/trace`` pages stay
  route-mounted for direct-link compatibility.  New file
  ``frontend/js/components/lineage_panes.js`` carries the three
  Alpine factories (``rowTracePane`` / ``columnTracePane`` /
  ``valueChangesPane``) plus a ``bindLineageTraceButtons()`` one-shot
  initialiser that exposes ``window.pqlLineageTraceRow / Column /
  Value`` helpers and event-delegates clicks on
  ``button[data-pql-trace-row="1"]``.  Three custom window events
  (``pql:trace-row`` / ``pql:trace-column`` / ``pql:trace-value``)
  stitch Summary "Trace target row" buttons + Graph side-panel
  "Trace this column" buttons into the corresponding sub-pill,
  flipping the active tab via Bootstrap 5's ``Tab.show()`` JS
  API and pre-populating the picker.  ``load_lineage_summary_for_run``
  gained one ``func.min(LineageRowEdge.target_row_id)`` column
  (``sample_target_row_id``) so Summary deep-links carry a
  representative row id; the new key flows through to
  ``GET /api/agent-runs/{id}/audit/lineage`` additively.  3
  pytest cases (loader, HTML mount, deep-link button attrs); 138
  pre-existing run-detail / lineage tests stay green.  Browser
  replay against the rebuilt e2e container confirmed zero
  console errors and end-to-end Summary-click → Row-trace-pane
  fetch.

- **Phase 40 — Lakehouse Federation reads (OpenLineage) closed.**
  Four sub-sprints landed in one autonomous session post the
  "plane phase 40 aus" plan; Sprint 40.2 (foreign-Delta CDF tail
  worker) was deliberately deferred to Phase 40.5 at plan time.
  Sprint 40.0 (Alembic ``oo5q7s9u1x3z``) relaxed ``run_id`` /
  ``op_id`` to nullable on ``lineage_row_edges`` /
  ``lineage_column_map`` and added ``producer`` +
  ``external_event_id`` columns; ``api_keys.lineage_inbound``
  added a third API-key scope independent of supervisor /
  auditor.  Sprint 40.1 added ``POST /api/lineage/openlineage``,
  the inbound surface — external producers (Kafka-Connect,
  Airflow, dbt-cloud, peer PointlesSQL installs) push OpenLineage
  1.x ``RunEvent`` envelopes that normalise into the existing
  shadow tables tagged with ``producer = event.job.namespace``,
  with idempotency on ``(producer, external_event_id, ...)``
  composite keys and forward-compat ``extra="allow"`` on the
  Pydantic models.  Sprint 40.3 wired an "External producers"
  block into ``components/lineage_card.html`` on the table-detail
  page, rendered with amber Bootstrap badges to visually
  distinguish federated edges from internal ones.  Sprint 40.4
  added ``expected_lineage_inbound`` (Alembic ``pp6r8t0v2x4z``)
  + ``services/lineage_freshness.py`` (compute, alert-candidate
  selection, ``stamp_alerted``, CloudEvents envelope) + the
  ``/api/admin/expected-producers`` CRUD surface.  Pyright budget
  bumped 528 → 559 (inbound parser walks ``Any``-typed JSON,
  same shape as the Phase-36.2 dbt-bridge bump).  27 new pytest
  cases (8 inbound, 6 table-detail aggregator, 13 freshness +
  CRUD) all green.

- **Phase 39 — Agent EXPLAIN-driven self-rewrite loop closed.**
  Four sub-sprints landed in one autonomous session.  The Hermes
  plugin's ``pql_query`` tool now hits ``GET /api/sql/explain``
  before ``POST /api/sql/execute``.  When the cost-gate verdict
  says ``needs_approval=True`` the tool returns a structured
  ``cost_gate_denied`` envelope carrying the EXPLAIN tree + a
  rewrite hint so the LLM can revise and retry.  Per-run state
  on the client tracks attempts + the original SQL hash; at
  attempt 4 the envelope flips to ``human_approval_required``
  and the plugin POSTs one ``rewrite_attempts`` row to PointlesSQL.
  A subsequent successful rewrite writes a second
  ``auto_rewrite_succeeded`` row.  Sprint 39.1 plumbed the
  per-run audit (new ``op_name='sql_explain'`` op rows when
  ``X-Agent-Run-Id`` is set, Alembic ``mm3o5q7s9u1x``).
  Sprint 39.2 added the ``rewrite_attempts`` table + route
  + run-detail "Rewrites" sub-pane on the Operations top-tab
  (Alembic ``nn4p6r8t0v2y``).  Sprint 39.3 wired the plugin loop
  (cross-repo commit ``576c5dc`` in ``hermes-plugin-pointlessql``).
  Sprint 39.4 added the
  ``docs/e2e-walkthroughs/explain-rewrite.md`` playbook (49th)
  and Grafana panel id 21 ("Rewrite savings — averted cost-gate
  denials per week") in both the SQLite and Postgres audit
  dashboards.  Audit POSTs are fail-soft so an older
  PointlesSQL server lacking the route doesn't crash the agent
  turn.  Pyright + file-size + Grafana-lint budgets all hold;
  10 new pytest cases on the PointlesSQL side, 5 on the
  plugin side.

- **Roadmap — three queued feature pillars after Phase 38.**
  Records the next forward-motion candidates surfaced after the
  Phase-38 sprint sweep closed everything carryable from the
  cleanup track.  Phase 39 (Agent EXPLAIN-driven self-rewrite
  loop) revives the Phase-13 EXPLAIN-loop sketch — agents read
  ``EXPLAIN (FORMAT JSON)`` pre-execution, see the cost-gate
  verdict, and self-rewrite SQL before submission instead of
  bouncing off ``cost_gate_trigger``.  Phase 40 (Lakehouse
  Federation reads — OpenLineage / CDF) closes the inbound side
  of the federation story: today PointlesSQL emits OpenLineage
  outbound and registers federated tables via soyuz, but the
  audit-graph stops at the soyuz boundary on read; this phase
  adds an OpenLineage inbound endpoint, a CDF tail worker, and
  a merged-lineage card on table-detail pages.  Phase 41 promotes
  Sprint 17.6 (lineage trace sub-panes) out of the Phase-17
  sub-tree into its own phase so the smallest UX-only track
  doesn't get lost behind the two larger feature pillars.  No
  order enforcement between 39 / 40 / 41 — all three carry ``⏳``.

- **Sprint 36.7 — dbt end-to-end walkthrough + Phase 36 close.**
  Phase 36 closes ✅ in the same session Phase 38.2 had marked
  it ``⏸ upstream``.  Trigger was the dbt-labs/dbt-core#12098
  link surfaced via web search: ``mashumaro 3.17`` carries the
  Python-3.14 ``Optional[str]`` fix.  ``dbt-core 1.11`` still
  declares ``mashumaro<3.15``, but force-installing 3.17 runs
  clean against ``dbt-core 1.11.8`` + ``dbt-adapters 1.22.10``.
  The override now lives in ``pyproject.toml`` as
  ``[tool.uv] override-dependencies = ["mashumaro[msgpack]>=3.17"]``
  so ``uv sync --extra dbt`` produces a working environment on
  Python 3.14 without manual intervention.  Walkthrough
  ``dbt-pipeline.md`` Part C grew from 4 steps to 5 (added the
  ``pip install --no-deps mashumaro==3.17`` step + the
  ``dbt docs generate`` step that lands ``catalog.json``).
  End-to-end verified live in Firefox via Playwright MCP: the
  Phase-36.4 cockpit chrome populates with ``models=3 /
  tests=6 / coverage=66.7%``, both Recent runs + Test failures
  sub-tabs lazy-load with empty-state messages, 0 console
  errors on ``/dbt``.  Drop the override once dbt-core ships
  a release that bumps its own pin.

- **Phase 38 — Sprint-Sweep (35.4 close + 36.7 defer + cockpit
  data-path).**  One autonomous session post the "plane die
  restliche aufgaben aus" plan.  Three sub-sprints, three
  commits.  Sprint 38.1 closes the deferred Sprint 35.4: the
  1467-LOC ``run_view.html`` is now a 229-LOC parent +
  eight partials in ``frontend/templates/partials/_run_*.html``
  (header, metadata, conformance, approval form, four tab
  panes).  Behaviour-equivalent; verified end-to-end via
  Playwright MCP — all four top-tabs and 13 sub-tabs render
  with 0 console errors, the URL-hash deeplink activator
  promotes both parent and leaf tabs, and the ``rollbackPanel``
  Alpine factory binds cleanly with the ``:class="{ 'd-block':
  modalOpen }"`` modal toggle preserved (BUG-67-01-class
  regression check).  Sprint 38.2 ran the upfront feasibility
  check for Sprint 36.7 (dbt end-to-end walkthrough) and
  confirmed the upstream blocker still holds: ``dbt-duckdb
  1.10.1`` + ``dbt-core 1.11.8`` + ``mashumaro 3.14`` on
  Python 3.14.4 still raises ``UnserializableField: Field
  "schema" of type Optional[str] in JSONObjectSchema`` at
  import time — root cause is mashumaro's unpacker compiler
  not handling ``Optional[str]`` annotations under Python
  3.14, with no downstream workaround.  Sprint 36.7 status
  flipped from ``⏸ Playwright`` to ``⏸ upstream``;
  ``dbt-pipeline.md`` Part C Caveat now records the exact
  pins + trace + verification date.  Sprint 38.3 verified
  the data path of the Phase-37 ``audit-cockpit-deep.md``
  walkthrough against ``seed-broken-run.py`` + a partial
  ``seed-full-stack-demo.py`` run: ``/audit/inbox`` shows
  "2 of 2 breach(es)", ``/api/audit/search?q=silver`` returns
  1 hit (custom tokenizer), ``/audit/by-table/demo.incidents.broken_orders``
  serves the populated cockpit ("2 run(s) touched …"), and
  the ``top-mutating-principals-30d`` starter query returns
  200 with 2 rows.

- **Phase 37.1 — Phase-37 BUG sweep.**  Closes the five open
  BUG-37-NN tickets surfaced during the Phase-37 walkthrough
  replay.  BUG-37-04 (HTMX null-deref on
  ``/audit/inbox`` / ``/audit/search`` / ``/alerts``
  page-load) fixed via a CDN pin bump from htmx 2.0.3 to
  2.0.6, which added the ``if (o == null || o === "") …``
  guard before the offending ``o.includes("?")`` call.
  BUG-37-05 (``/audit/by-table`` empty path renders three
  user-visible ``Error 422`` rows from the tab loaders)
  fixed by adding a no-FQN handler that serves an FQN
  picker form instead of the tab chrome.  BUG-37-02 (admin
  context-panel missing five entries) and BUG-37-03
  (mobile-drawer Admin link with ``href="#"``) fixed in
  ``components/context_panel.html`` and
  ``components/nav_links.html``.  BUG-37-06 (Phase-36.4
  dbt cockpit chrome missing) closed by landing the
  manifest summary card-row + 3-tab nav (Pipeline docs /
  Recent runs / Test failures) on ``/dbt`` plus a new
  ``GET /api/dbt/runs`` route and the ``agent_run_id``
  query param made optional on ``GET /api/dbt/test-failures``.
  Sprint 36.4 flipped from ``⏸ Playwright`` to ``✅``.
  All five fixes verified end-to-end via Playwright MCP
  (zero console errors across the touched pages).

- **Phase 37 — Playwright coverage refresh (post-Phase-22/23).**
  Brings ``docs/e2e-walkthroughs/`` back to complete UI
  coverage after Phase 14, 17, 18.6+, 28, 33, and 36 features
  landed pages without dedicated playbooks.  Wave 0a rewrites
  ``audit-sinks.md`` from a curl-only operational runbook into
  a UI-driven walkthrough (Phase 33.2 added the admin page that
  the original playbook said didn't exist) — surfacing
  BUG-37-01 (Alpine ``x-data`` attribute escaping on four admin
  row templates, fixed in ``a744b52``).  Wave 0b applies three
  surgical updates to ``grand-tour.md`` for Phase-28 workspace
  switcher and Phase-33 admin landing.  Wave 1 lands
  ``admin-console.md`` covering the Phase-33 landing 7-card
  grid + 5 sub-pages (the API-keys plaintext-secret modal
  carries the strongest redaction property: the secret lives
  in the ``<input>``'s ``.value`` DOM property only and is
  never serialised into ``outerHTML``).  Wave 2 lands
  ``audit-cockpit-deep.md`` for the four Phase-18.6 → 18.x
  cockpit pages.  Wave 3 lands ``run-comparisons.md`` covering
  both compare surfaces (audit run-diff + jobs run-compare).
  Wave 4 lands ``alerts.md``.  Wave 5 lands ``dbt-pipeline.md``
  via the D3b path — covers the iframe-only chrome that exists
  today + files BUG-37-06 for the still-paused Phase-36.4
  cockpit chrome (manifest summary card + test-failures table
  + run-view sub-tab).  Five additional bugs filed during live
  replay (BUG-37-02 through 06).  README index updated with
  the five new entries; CLAUDE.md playbook count refreshed
  to 48.

- **Sprint 36.D — dbt bridge captures Delta versions for rollback
  anchors.**  Closes the production-side gap surfaced after 36.C
  landed: ``pql.rollback`` was refusing every dbt-driven rollback
  with ``RollbackInvalid`` because the bridge wrote
  ``delta_version_before=None`` / ``delta_version_after=None`` on
  every ``dbt_model`` op (the gate reads ``before is None`` as
  "this op created the table" → drop is out of v1 scope).  Auto-
  rollback (36.C) was therefore an API hull, not a working feature.

  New ``services/dbt_bridge.capture_delta_versions(uc_client,
  relations) -> {relation: version|None}`` helper looks up each
  relation's soyuz-catalog ``storage_location`` and reads
  :class:`deltalake.DeltaTable.version()`.  Best-effort: catalog
  miss, missing location, non-Delta target, or transport hiccup
  all map to ``None`` so a partial capture (some Delta-backed,
  some DuckDB-native) keeps the rollback gate honest per row.

  ``/api/dbt/{run,test}`` now runs the helper twice:
  pre-execution (against the existing manifest, populating
  ``delta_version_before``) and post-execution (against the
  freshly-written manifest, populating ``delta_version_after``).
  ``emit_operations_for_dbt_run`` accepts new ``pre_versions`` /
  ``post_versions`` keyword args and stamps each ``dbt_model``
  row's columns from those maps.  ``dbt_test`` rows never pull
  from the maps — tests don't materialise targets.

  Limitation, documented in the helper docstring: dbt-duckdb's
  default ``table`` materialisation writes DuckDB-native tables,
  not Delta — for those, ``DeltaTable(loc)`` raises and the
  relation maps to ``None``.  Auto-rollback continues to fail for
  pure-DuckDB targets; the fix is meaningful for projects that
  opt into the Delta materialisation adapter or write through
  PointlesSQL's PQL primitives.

  3 new pytest cases:
  ``test_capture_delta_versions_returns_none_for_unresolvable_relations``
  exercises the except clause; the bridge test
  ``test_emit_operations_populates_delta_versions_from_pre_post_maps``
  asserts the maps land on the persisted rows; the route-level
  ``test_run_populates_delta_versions_when_capture_succeeds``
  proves the wiring end-to-end through ``/api/dbt/run``.

- **Phase 36 Restabschluss — Stream A backend close (sub-sprints
  36.A / 36.B / 36.C).**  Closes the gaps that 36.1–36.6 deferred
  inside individual sprints, leaving only the Playwright-gated UI
  (36.4) + e2e walkthrough (36.7) for a separate session.

  - **36.A — Sample dbt project + real-binary integration test.**
    A 3-model / 5-test demo project lands at ``dbt_project/`` (bronze
    → silver → gold pipeline plus ``not_null`` / ``unique`` /
    ``accepted_values`` / ``relationships`` tests against a 10-row
    seed).  ``tests/test_dbt_real_subprocess.py`` (marked
    ``@pytest.mark.integration``) runs real ``dbt compile`` and a
    full ``dbt seed → run → test`` against the project, asserts
    against the bridge's :func:`parse_manifest` /
    :func:`merge_manifest_and_results` projection, and skips
    cleanly when ``dbt-duckdb`` isn't importable for the active
    Python interpreter (Python-3.14 + dbt-duckdb-1.9 currently
    raises ``mashumaro.UnserializableField`` during CLI module
    import; the wrapper handles non-``ImportError`` failures).
    A new public ``DBTExecutor.seed`` method lets the test (and
    future agent flows) materialise CSV seeds without reaching
    into ``_run``.

  - **36.B — Read-only API + read-only plugin tools.**  Three new
    GET routes on PointlesSQL: ``/api/dbt/manifest`` (any
    authenticated user — projects ``target/manifest.json`` to a
    model summary with attached tests), ``/api/dbt/coverage``
    (test-coverage ratio + untested-model list), and
    ``/api/dbt/test-failures`` (joins ``lineage_row_rejects``
    where ``reason='expectation_failed'`` with
    ``agent_run_operations``; supervisor or auditor scope).  The
    manifest-projection logic lifts to
    :mod:`pointlessql.services.dbt_bridge` (``as_dict`` /
    ``as_list`` / ``project_models``) so the plugin's
    ``pql_dbt_show_lineage`` reuses the same canonical projection.
    Three new Hermes tools land in
    ``hermes-plugin-pointlessql``: ``pql_dbt_list_models``
    (no-arg manifest summary), ``pql_dbt_show_lineage``
    (parents/children walk, accepts unique_id or short name),
    and ``pql_dbt_get_test_failures``
    (per-run failing tests with model relation, severity, and
    op id).  Closes the trigger → inspect loop without re-spawning
    a dbt subprocess.

  - **36.C — Auto-rollback on error-severity test failures.**
    ``POST /api/dbt/test`` accepts a new ``auto_rollback: bool``
    body parameter (default ``False``).  When set and the run has
    at least one error-severity failing test, the route walks every
    ``dbt_model`` op in the run (newest-first) and invokes
    ``pql.rollback`` for each — collecting per-target outcomes
    (``succeeded`` vs. ``failed``) into the response envelope's new
    ``auto_rollback`` block.  Per-target refusals (``RollbackStale``,
    ``RollbackInvalid``, …) land in ``failed`` rather than aborting
    the sweep — auto-rollback is best-effort by design.  A new
    ``pointlessql.dbt.auto_rollback.executed`` CloudEvent fires
    once per attempted unwind with the aggregate counts.  Auto-
    rollback fires *only* on the test path: model writes are
    reverted because tests failed, never as a side-effect of the
    run itself.

  Plus housekeeping: ``pointlessql/api/dbt_routes.py`` joins the
  file-size allowlist (cohesive dbt orchestration surface; manifest
  projection already lives in the bridge); ``services/dbt_bridge.py``
  gains ``as_dict`` / ``as_list`` / ``project_models``;
  ``pointlessql/services/governance_events.py`` adds
  ``EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED``; pyright budget held at
  528 across the three sub-sprints.

- **Sprint 36.6 — Hermes plugin: dbt-pipeline trigger tools.**
  Three new tools land in ``hermes-plugin-pointlessql``:
  ``pql_dbt_compile`` (read-only manifest refresh, any user),
  ``pql_dbt_run`` (materialise models, supervisor scope),
  ``pql_dbt_test`` (evaluate tests, supervisor scope).  Each forwards
  ``POINTLESSQL_AGENT_RUN_ID`` via the ``X-Agent-Run-Id`` header so
  the dbt subprocess's emitted operations attribute under the same
  forced-audit-trail run as the rest of the agent's work; absent
  the env var, PointlesSQL auto-creates a run keyed to the calling
  user's email.  Per-test failure rejects (one
  ``lineage_row_rejects`` per failing test) are surfaced via the
  existing ``pql_query_rejects`` auditor tool.  The plan's three
  read-only tools (``pql_dbt_list_models`` /
  ``pql_dbt_show_lineage`` / ``pql_dbt_get_test_failures``) need
  new manifest-introspection endpoints on the PointlesSQL side
  and are deferred to a follow-up sprint.

- **Sprint 36.5 — severity enforcement + dbt CloudEvents.**  Three
  new governance event types: ``pointlessql.dbt.run.completed``
  fires once per ``/api/dbt/run`` and ``/api/dbt/test`` invocation;
  ``pointlessql.dbt.test.failed`` fires once per error-severity
  failing test (these are the run-failing ones);
  ``pointlessql.dbt.test.warned`` fires once per warn-severity
  failing test (run still succeeds — anomaly-only).  New
  ``_classify_severity`` helper buckets failures by severity; auto-
  created runs finish as ``failed`` only when ``err_failures > 0``,
  so a project with ``severity: warn`` tests keeps deploying while
  the cockpit's anomaly inbox surfaces the warning.  Auto-rollback
  on error-severity failure (``pql.rollback`` per affected model)
  is deferred — the four refusal modes in ``RollbackError`` need
  per-test gating that exceeds this sprint's scope.  7 new tests
  cover both the classifier and the end-to-end event emission.

- **Sprint 36.3 — dbt test-failure → lineage_row_rejects +
  ``expectation_failures`` anomaly axis.**  ``REJECT_REASONS`` +
  the SQL CHECK constraint on ``lineage_row_rejects`` gain
  ``expectation_failed`` (alembic ``ll2n4p6r8t0w``).
  ``services/dbt_bridge.emit_test_failure_rejects`` walks the
  per-node results paired with their ``agent_run_operations.id``
  values and inserts one reject row per failing dbt test
  (``status='fail'``).  ``source_row_id`` is the test's
  ``unique_id``, ``detail`` carries dbt's failure message verbatim.
  Per-row extraction (one reject per failing data row) is deferred
  — capturing those needs ``dbt test --store-failures`` plus a
  follow-up SELECT against ``dbt_test__audit.<test_name>``.
  ``services/audit_aggregator`` gains an ``expectation_failures``
  metric: a row-level WHERE filter on
  ``lineage_row_rejects.reason`` that lets the cockpit show
  dbt-side data-quality failures separately from merge-time
  rejects.  ``/api/dbt/run`` and ``/api/dbt/test`` summaries now
  carry ``rejects_inserted``.  4 new tests, all green.

- **Sprint 36.2 — on-demand ``dbt run/test/compile`` + manifest
  bridge.**  Three new POST routes — ``/api/dbt/compile`` (auth-
  only), ``/api/dbt/run`` and ``/api/dbt/test`` (supervisor scope) —
  plus an admin-only ``/api/dbt/deps`` for package installs.  The
  shared ``services/dbt_executor.py`` spawns dbt as an async
  subprocess with a configurable timeout, captures stdout/stderr
  with a 256 KiB-per-stream cap, and never raises on non-zero exit
  codes (those land on ``DBTRunResult.exit_code``).  The shared
  ``services/dbt_bridge.py`` parses ``target/manifest.json`` +
  ``target/run_results.json`` and emits one ``agent_run_operations``
  row per executed model or test (op_names ``dbt_model`` / ``dbt_test``
  added to ``VALID_OP_NAMES`` + the SQL CHECK via alembic
  ``kk1m3o5q7s9v``).  ``params_json`` captures the manifest-side
  fields (``unique_id``, ``materialization``, ``execution_time``,
  ``severity``, ``depends_on``) so a reviewer can see why each row
  exists without joining back to the manifest.  Routes that auto-
  create an ``AgentRun`` (``agent_id="dbt-cli"``) finish it on exit;
  caller-supplied run ids stay caller-managed.  Failure visibility
  for tests + severity enforcement land in 36.3 / 36.5.  19 new
  unit + integration tests; pyright budget bumped 522 → 528 to
  cover the JSON-parse cascade in dbt_bridge.

- **Sprint 36.1 — dbt-docs subprocess + reverse-proxy** (Phase 36
  start).  Mirrors the MLflow integration: ``DBTSettings`` block
  (``POINTLESSQL_DBT_*`` env prefix, default ``docs_port=5002``,
  ``project_dir=dbt_project/``), ``services/dbt_subprocess.py``
  with async spawn of ``dbt docs serve`` + HTTP health-poll + PID
  file + SIGTERM-then-SIGKILL shutdown, ``api/dbt_proxy.py``
  reverse-proxy at ``/dbt-docs/`` with ``X-DBT-User`` header
  injection, ``api/dbt_html_routes.py`` chrome page at ``/dbt``
  plus icon-rail entry.  Pre-flight ``project_ready()`` check
  skips the spawn when no compiled ``target/manifest.json``
  exists, so a freshly-cloned repo logs a friendly info message
  instead of a noisy startup error.  Optional extra ``[dbt]``
  adds ``dbt-duckdb >= 1.9, < 2.0`` (``dbt-expectations`` and
  ``dbt-utils`` are dbt packages installed via ``dbt deps``,
  not pip).  14 new unit tests (8 subprocess + 6 proxy);
  pre-commit chain green, pyright budget unchanged at 522/0.

- **Docstring overhaul (2026-05-06)** — Two-stream cleanup pass over
  ``pointlessql/`` docstrings and inline code comments.  Stream A
  stripped 220+ project-history references (``Phase X``, ``Sprint Y``,
  ``ADR-NNNN``, ``BUG-NN-NN``, parenthesized variants) that described
  *when* a piece of code was written rather than *what* it does or
  *why* — those tokens age the moment the next phase ships.  Stream B
  added Why-bodies to three high-summary-only modules: 15 of 22
  routes in ``api/federation_routes.py`` (audit + soyuz-outage
  handling), 8 of 12 helpers in ``api/jobs_routes.py`` (visibility
  + scheduler-effect notes), and 6 of 10 helpers in
  ``services/run_diff.py`` (alignment-strategy + diff-shape
  rationale).  Globally, summary-only ratio drops from 22.8% to
  17.7%; ``alembic/versions/*`` migration docstrings stay as-is
  (legitimately time-locked records).  All gates green: pydoclint
  0 violations, ruff clean, pyright 0/522 unchanged, full SQLite
  suite 1478 passed / 6 skipped.

- **Sprint 35.8 closed (2026-05-06)** — Two CI regression guards
  added so the Phase-35 modularization + type-hardening don't
  decay over time.  ``scripts/check-file-size-budget.sh`` (~75
  LOC) fails CI when any ``pointlessql/**.py`` exceeds 800 LOC
  unless it appears in an explicit allow-list with a comment
  explaining why it's big-by-design.  Today's allow-list:
  ``pql.py`` (788), ``api/main.py`` (785), ``settings.py`` (721),
  the alembic squash (713), ``services/scheduler/runs.py`` (849),
  ``api/jobs_routes.py`` (804), ``api/sql_routes.py`` (766),
  ``pql/_merge.py`` (731), and the three Sprint-35-audit
  cohesive files (``audit_routes.py`` 1103, ``audit_aggregator.py``
  897, ``services/agent_runs/operations.py`` 874).
  ``scripts/check-pyright-budget.sh`` (~50 LOC) parses the
  trailing ``N errors, M warnings`` summary line and fails when
  warnings exceed the budget (frozen at 522 post-35.6) or errors
  are non-zero.  Both scripts wired into ``.pre-commit-config.yaml``
  and ``.github/workflows/test.yml`` (lint+type+docstring+alembic
  job).  Closes Phase 35.

- **Sprint 35.7 skipped (2026-05-06)** — Investigation found the
  ``_frame_to_arrow(frame: Any) -> pa.Table`` function already
  produces a typed return; callers see correct types.  The
  "partially unknown" warnings inside the function come from
  ``pa.array(...)`` and ``pa.Table.from_pandas(...)`` returning
  ``Unknown`` due to incomplete pyarrow stubs — ``@overload`` on
  the public surface cannot reach that cascade.  Adding
  ``@overload`` for pandas / polars / DuckDB inputs would not
  reduce warnings because callers pass ``Any`` from upstream
  ``_resolve_source_frame``.  Real reduction would need custom
  pyarrow ``.pyi`` stubs — out of scope for a single sprint.
  Sprint marked skipped; warning floor freezes at 522.

- **Sprint 35.6 closed (2026-05-06)** — Type-hardening:
  ``services/value_change_capture.py`` got explicit annotations on
  the locals where pyright lost type information: ``column_names:
  set[str]``, ``data: dict[str, list[Any]]``, ``diff_columns:
  list[str]``, ``row_id_raw: Any``.  Plan estimated ≥18 fewer
  warnings; **actual is 9** — pyright stays uncertain on
  ``data[col][i]`` indexing patterns even with the dict typed,
  because the inner ``list[Any]`` indexing yields ``Any`` which
  pyright then flags as "partially unknown" downstream.  Global
  pyright drops from 531 → 522 warnings (-9).  Per-file warnings
  in ``value_change_capture.py``: 22 → 13.  16 lineage-value tests
  green; ruff + pydoclint clean.

- **Sprint 35.5 closed (2026-05-06)** — Architectural cleanup: hoist
  every lazy ``import deltalake`` from function bodies to module
  top in ``pql/_merge.py`` (3 lazy imports), ``pql/_autoload.py``
  (2 lazy imports), ``pql/engine.py`` (7 lazy imports), and
  ``pql/_cdf.py`` (1 lazy + the ``try / except ImportError`` guard
  was dead code since deltalake is a hard dep).  **Plan estimated
  ≥40 fewer pyright warnings; actual is 0** — ``deltalake``'s
  signatures already had type hints, and pyright's "Type is
  partially unknown" warnings come from pyarrow's
  ``pa.dataset.Dataset`` stubs being incomplete, not from the
  imports being lazy.  The hoist remains valuable as code-quality
  cleanup (Python-level architecture, fewer per-call imports) even
  without the warning reduction.  Lesson recorded in
  ``feedback_pyright_pyarrow_stubs.md``: third-party-API-heavy
  modules need either custom ``.pyi`` stubs or accepted warnings;
  Python type annotations alone don't move the needle.  Verification:
  1478 SQLite tests green, ruff + pyright + pydoclint clean (0
  errors / 531 warnings, unchanged).

- **Sprint 35.4 deferred (2026-05-06)** — Extracting
  ``run_view.html`` (1467 LOC) into tab partials needs a live
  browser-playbook replay (``audit-reviewer-daily.md``) before
  commit per the Phase-35 plan's mandatory verification gate.
  Alpine ``x-data`` scope changes can pass server-side tests but
  break the side-panel factory in the browser (memory rule:
  ``feedback_run_playbook_as_gate.md``).  Re-pick when a
  Playwright MCP session is up alongside the refactor.  Stream-B
  / 35.8 do not depend on this — proceeding without 35.4.

- **Sprint 35.3 closed (2026-05-06)** — Targeted modularization: split
  ``pointlessql/services/audit_fts.py`` (973 LOC) per dialect into a
  ``pointlessql/services/audit_fts/`` package.  ``__init__.py`` keeps
  the public surface (``is_available`` / ``search`` /
  ``install_index`` / ``rebuild_index``), the dialect dispatcher,
  the query sanitiser, the time-filter post-processor, and the
  ``Axis`` / ``VALID_AXES`` typing.  ``_sqlite.py`` (~330 LOC) owns
  the FTS5 virtual-table DDL, the per-source trigger generation
  (5 ``CREATE TRIGGER`` axes × 3 events each), the ``MATCH``-based
  search, and the rebuild path.  ``_postgres.py`` (~330 LOC) owns
  the ``audit_search_index`` table layout, the per-axis PL/pgSQL
  upsert + delete trigger functions, the ``ts_rank`` /
  ``plainto_tsquery`` search with ``ts_headline`` snippets, and the
  same rebuild path.  Cross-dialect parity helpers
  (``_merge_pg_marks`` for snippet-mark normalization) live with
  the PG layer.  ``services/audit_fts.py`` was deleted (replaced by
  the package); all three importing call sites
  (``audit_search_routes``, ``cli/migrate_to_postgres``, two test
  files) keep their ``from pointlessql.services import audit_fts``
  pattern unchanged because the package's ``__init__.py`` exposes
  the same name.  Behaviour byte-identical — refactor only.
  Verification: 25 audit-fts tests green
  (``test_audit_fts`` + ``test_agent_runs_workspace_isolation``);
  1478 SQLite suite tests pass; pyright errors stay 0, warnings
  unchanged at 531; ruff + pydoclint clean.

- **Sprint 35.2 closed (2026-05-06)** — Targeted modularization: split
  ``pointlessql/services/lineage_edges.py`` (1137 LOC) into a
  per-stream ``pointlessql/services/lineage/`` subpackage.
  ``_types.py`` keeps the shared dataclasses (``PredecessorRef``,
  ``LineageStep``, ``ColumnEdgeSpec``, ``ColumnPredecessorRef``,
  ``ColumnTraceStep``, ``ValueChangeSpec``), exception sentinels
  (``ColumnEdgeCapExceeded``, ``ValueChangeCapExceeded``), per-op
  caps (``MAX_COLUMN_EDGES_PER_OP``, ``MAX_VALUE_CHANGES_PER_OP``),
  the deterministic-id helpers (``synth_target_row_id``,
  ``synth_aggregate_target_row_id``), and the workspace-id resolver
  (``workspace_id_for_op``, dropped leading ``_`` since cross-module).
  ``rows.py`` owns ``record_edges`` / ``record_rejects`` /
  ``walk_back`` / ``fetch_target_row_predecessors`` /
  ``fetch_source_row_descendants`` / ``count_edges_for_op`` and the
  bronze ``lookup_bronze_source_file`` helper used by the row-trace
  UI.  ``columns.py`` owns the column-level analogs
  (``record_column_edges`` / ``walk_back_columns`` /
  ``fetch_target_column_predecessors`` /
  ``count_column_edges_for_op``).  ``values.py`` owns
  ``record_value_changes`` (with the ``hash_only`` /
  ``redact_with_audit_log`` PII hook), ``count_value_changes_for_op``,
  ``fetch_value_changes_for_row``.  ``lineage_edges.py`` becomes a
  60-LOC re-export shim that keeps every old import path working
  (12 import sites across PQL primitives, lineage routes, agent-run
  operations, run-detail loaders, value-change-capture, sql parser,
  column-lineage diff, plus 4 test files).  Behaviour byte-identical;
  58 lineage tests + full 1478 SQLite suite green.  Pyright errors
  stay 0, warnings unchanged at 531; ruff + pydoclint clean.  No-net-LOC:
  ~1137 LOC moved across 5 files.

- **Sprint 35.1 closed (2026-05-06)** — Targeted modularization: split
  ``pointlessql/pql/_branch.py`` (1310 LOC) into a per-workflow
  ``pointlessql/pql/branch/`` subpackage.  ``_common.py`` keeps the
  soyuz-API references + shared helpers (URI classification, schema
  lookup, audit-log + CloudEvent emission); ``_create.py`` owns the
  create flow + table-cloning helpers; ``_discard.py`` owns the
  discard flow + storage cleanup; ``_promote.py`` owns the
  pointer-swap promote + dry-run preview + version-equality conflict
  gate.  ``_branch.py`` is now a thin re-export shim
  (``# pyright: reportPrivateUsage=false`` to silence intentional
  private-symbol exposure for tests).  Cross-module helpers in
  ``_common.py`` dropped their leading underscore
  (``classify_storage_scheme``, ``uri_to_local_path``,
  ``derive_branch_storage_root``, ``split_two_part``,
  ``ensure_source_schema``, ``resolve_storage_root``,
  ``emit_branch_event``, ``record_branch_audit_log``,
  ``rename_schema``); module-internal helpers
  (``_clone_table_local``, ``_pick_strategy``,
  ``_check_promotion_conflicts``, ``_delete_branch_storage``, etc.)
  keep theirs.  Test imports updated: ``from pointlessql.pql import
  _branch as branch_mod`` → ``from pointlessql.pql.branch import
  _create as branch_mod`` (and similar for discard / promote);
  ``patch.object(branch_mod, "_emit_branch_event")`` →
  ``patch.object(branch_mod, "emit_branch_event")``, etc.  Behaviour
  is byte-identical — refactor only.  All 81 branch tests still
  green; 1478 SQLite suite tests pass; pyright errors stay 0,
  warnings unchanged at 531.  No-net-LOC: ~1310 LOC moved across 5
  files (shim + 4 workflow modules).

- **Sprint 34.2 closed (2026-05-05)** — Governance + Compliance panel
  set; closes Phase 34 with 8 new panels (4 from 34.1 + 4 from 34.2,
  matched IDs across SQLite + Postgres dashboards).  Picks for the
  governance row, all dialect-aware:
  (1) **Audit retention horizon (oldest row, days)** — stat over
  ``MIN(audit_log.created_at)`` rendered as days; thresholds at
  300 (yellow) and 365 (red, the default
  ``POINTLESSQL_AUDIT_RETENTION_DAYS``).  SQLite uses
  ``julianday('now') - julianday(MIN(...))``; PG uses
  ``EXTRACT(epoch FROM NOW() - MIN(...)) / 86400.0``.  Filtered by
  ``$workspace``.
  (2) **FTS index lag (rows behind)** — stat showing
  ``COUNT(audit_log) - COUNT(audit_search[_index])``; 0 = triggers
  in sync, anything else means the FTS-trigger stalled.  Cross-
  workspace by design (FTS is install-global).  SQLite reads
  ``audit_search`` (FTS5 virtual); PG reads ``audit_search_index``
  (Phase 30 ``hh8j0l2n4p6r``).
  (3) **Audit exports issued (selected window)** — stat counting
  ``governance_events`` rows with ``event_type='pointlessql.
  audit_export.issued'`` in the dashboard's time window, blue
  threshold (informational, not alertable).  Filtered by
  ``$workspace``.
  (4) **Agent reviews per day (by severity)** — full-width stacked
  vertical bar of ``agent_reviews.created_at`` grouped by
  ``severity`` (ok / warn / critical).  Filtered by ``$workspace``.
  Plus a section header (id=16) labelling the row "Phase 19/20
  Governance + compliance".  Originally the plan included an OIDC-
  login-volume panel; the audit verified that login events are NOT
  written to ``audit_log`` (no instrumented login path), so the
  slot was redirected to the audit-export trail panel — a
  comparable compliance signal that DOES have data behind it.  Net
  result: dashboards now have 20 panels each (10 baseline + 5
  Sprint-34.1 + 5 Sprint-34.2).  Panel-ID space distinct, structural
  gate (``scripts/check-grafana-dashboards.sh``) green.  Phase 34
  closes.
- **Sprint 34.1 closed (2026-05-05)** — Cross-Workspace Observability
  MVP: 4 new operator-pain panels added to both Grafana dashboards
  (SQLite at ``grafana/dashboards/pointlessql_audit.json`` +
  Postgres at ``grafana/postgres-dashboards/pointlessql_audit.json``,
  matched IDs).  Each filters by the existing ``$workspace`` template
  variable.  Panel set, queries against the metadata DB directly:
  (1) **Sink delivery health (last 1h)** — stat showing
  ``governance_events`` ``outcome='delivered'`` ratio over the
  last hour, threshold-coloured (red <95%, yellow 95-99%, green
  ≥99%); (2) **Open anomaly verdicts (7d)** — stat counting
  ``agent_runs`` rows whose cached ``anomaly_severity`` is
  ``warn`` or ``critical`` in the trailing 7 days, threshold-
  coloured (green=0, yellow≥1, red≥10); (3) **Rollbacks per
  day** — vertical bar of ``agent_run_events.event_type =
  'pointlessql.rollback.executed'`` count per day; (4) **Sink
  errors per day (by event type)** — stacked vertical bar of
  ``governance_events.outcome='delivery_failed'`` per day,
  broken out by ``event_type``.  A markdown header panel
  separates these from the Phase-19 baseline.  Per-dialect
  queries: SQLite uses ``datetime('now', '-N hours')`` /
  ``date(fired_at)``; Postgres uses ``NOW() - INTERVAL 'N hour'``
  / ``::float8`` casts.  New gate ``scripts/check-grafana-
  dashboards.sh`` parses both JSONs, requires non-empty panels
  array, asserts each panel has ``id`` + ``type`` + ``title`` +
  ``gridPos`` plus distinct IDs.  Local result: both dashboards
  parse, 15 panels each (10 baseline + 5 new), distinct IDs.
- **Sprint 33.4 closed (2026-05-05)** — Admin Console polish.  Closes
  the two remaining gaps that Phase 33's first cut deferred as
  "curl-only stays acceptable" / "out of scope":
  ``GET /admin/api-keys`` (list + create-with-modal +
  revoke-with-confirm), ``GET /admin/system-info`` (read-only:
  PII mode + active hash-secret presence, OIDC group→workspace+
  scope mapping with restart-required hint, ``system_keys`` row
  inventory by name + ``created_at`` only, API-key scope counts).
  Two new cards on ``/admin`` ("API keys", "System info") with the
  active-key-count badge.  ``POST /api/admin/api-keys`` JSON
  route now also accepts an optional ``workspace_id`` field
  (defaults to ``1``) so the UI's workspace chooser is honoured;
  the audit-log entry carries the chosen workspace.  Two
  load-bearing assertions in the new test files prove the page
  never re-leaks a secret: the hashed
  ``ApiKey.secret_hash`` value (64-char SHA-256 hex) and the
  ``system_keys.value`` cleartext both must be absent from the
  rendered HTML — only the literal ``present`` badge + the
  ``created_at`` date surface.  9 new pytest cases across two new
  test files (``test_admin_api_keys_page.py``,
  ``test_admin_system_info_page.py``); the existing 6
  ``test_admin_api_keys_routes.py`` JSON tests stay unchanged and
  green.  **Still out of scope** (with rationale): system-keys
  rotation (sec-critical write needs re-hash backfill, dedicated
  phase), editable PII-mode / OIDC-mapping forms (both
  env-restart-gated; a writable UI would silently desync from
  ``os.environ``).  Net effect: Phase 33 now closes with all four
  sub-sprints landed; admin-test count goes from 38 → 50 in this
  session.
- **Phase 33 closed (2026-05-05)** — Admin Console: every operator
  surface unified behind one ``/admin`` landing.  Three sub-sprints
  + a Mini-Sprint 0 cleanup.  Mini-Sprint 0 retired two stale
  ROADMAP markers (Sprint 19.2 ``⏳ in progress`` → ``✅ closed
  (995490b)``; Phase 12.9 ``🔜 in progress`` → ``✅ closed
  2026-05-05 (Sprint 76–95: 90d40b8)`` with a closing note that
  documents why ``help_popovers.js`` deliberately stays IIFE and
  why ``bootstrap.js`` is a permanent fixture).  33.1 introduces
  ``GET /admin`` with a five-card grid (audit log, external
  writes, workspaces, audit sinks, review destinations) and
  retargets the icon-rail's admin pill from ``/admin/audit`` to
  ``/admin``; the three existing admin pages now back-link via
  ``Admin → /admin`` in the breadcrumb so the landing becomes the
  canonical hub.  33.2 ships ``GET /admin/audit-sinks``: list of
  every sink with its redacted config, type-conditional create
  form (webhook / s3 / aws_cloudtrail), per-row active toggle,
  test-envelope button (``/api/admin/audit-sinks/{id}/test``),
  delete button, and workspace-filter chip selector — the
  underlying JSON CRUD has been live since Phase 19.1 / 29.2; only
  the chrome was missing.  33.3 ships
  ``GET /admin/review-destinations`` with the same shape: list of
  destinations with min-severity dropdown, HMAC-secret presence
  badge (cleartext **never** reaches the page), workspace-filter
  chips, active toggle, delete button, and inline create form.
  Twelve new pytest cases across three new test files
  (``test_admin_index.py``, ``test_admin_audit_sinks_page.py``,
  ``test_admin_review_destinations_page.py``) verify auth gates,
  HTML rendering, and secret-redaction; the existing JSON-route
  tests stay unchanged and green.  **Out of scope for Phase 33**:
  System-keys rotation UI (security-sensitive write needs
  dedicated phase), PII-mode / OIDC-group-mapping editing
  (env-restart-gated; UI would lie), API-keys HTML wrapper
  (curl-only stays acceptable), Playwright smoke (route-level
  pytest sufficient for chrome).  Net effect: full SQLite suite
  ``1467 passed, 6 skipped`` (+ 12 over Phase 32's 1455), no
  regressions in any of the 33 admin / audit-sinks / review-dest
  tests.
- **Phase 32 closed (2026-05-05)** — PG test quality cleanup, no
  quality loss.  Once Phase 31 made the PG suite runnable
  end-to-end (~7 minutes), it surfaced **45 pre-existing PG
  failures**.  Phase 32 closes them all in one autonomous run:
  PG suite goes from **45 failed → 0 failed** (1457 / 1457 pass,
  4 skip, 9 deselect).  Three sub-sprints: 32.0 inserts
  ``session.flush()`` between parent ``add()`` and child ``add()``
  in 11 fixtures across 10 test files — the SQLAlchemy unit-of-work
  topo-sort doesn't reliably order cross-class inserts on PG when
  no ``relationship()`` is declared (production is unaffected, it
  commits parent and child in separate transactions); the same
  pass also widens ``query_history.read_kind`` from ``VARCHAR(20)``
  to ``VARCHAR(32)`` (alembic ``ii9k1m3o5q7s``, batch-mode on
  SQLite for table-recreate + drift-clean, plain ALTER on PG)
  because Sprint 28.7's ``audit_api_cross_workspace`` (25 chars)
  was silently truncating on PG, and rewrites
  ``test_fts_vtable_carries_workspace_id_column`` to be
  dialect-aware (PG inspects the ``audit_search_index`` table from
  Sprint 30.1's FTS migration; SQLite still uses ``PRAGMA
  table_info(audit_search)``).  32.1 makes the
  ``saved_audit_queries`` migration ``j0e1f2a3b4c5`` dialect-aware:
  the four ``datetime('now', '-N days')`` SQLite-only fragments in
  ``STARTER_ROWS`` become ``NOW() - INTERVAL 'N days'`` on PG via
  a ``starter_rows(dialect_name)`` helper, and ``services/saved_audit_queries.py``'s
  ``bootstrap_starter_rows`` plumbs the session's dialect through.
  A new alembic migration ``jj0l2n4p6r8u`` repairs already-deployed
  PG installs in place via ``UPDATE saved_audit_queries SET
  sql_text = REPLACE(...)`` (no-op on SQLite).  32.2 verifies the
  killer gate (``1457 passed`` on PG, ``1455 passed`` on SQLite,
  ``alembic check`` clean, ``pyright`` clean on touched files) and
  closes the phase with this entry plus the ROADMAP and memory
  updates.  Production was untouched in 32.0 (test fixtures only),
  fixed correctly in 32.1 (real seed-SQL bug), and the ``read_kind``
  widening removes a real PG-only truncation that was silently
  failing on every cross-workspace audit-summary read.
- **Phase 31 closed (2026-05-05)** — Test-suite speed
  optimisation, no quality loss.  The full SQLite suite went from
  ~30 minutes to **~68 seconds** (≈27×), and the PG suite from
  the aborted ~3 hour single-worker run down to roughly 7
  minutes.  All 1455 tests still run; no test was dropped or
  marked slow.  Six sub-sprints: 31.0 ships the baseline bench
  script (``scripts/bench_test_suite.sh`` → ``.bench/<ts>-<backend>.txt``);
  31.1 monkey-patches ``pointlessql.services.auth._hasher`` to
  ``BcryptHasher(rounds=4)`` at conftest-import time, dropping
  per-test bcrypt cost from ~1.0 s to ~64 ms (algorithm + cookie
  format unchanged, production untouched); 31.2 splits the
  conftest's autouse fixture into a session-scope ``_test_engine``
  (one ``Base.metadata.create_all`` per worker, dropped on session
  exit) plus a function-scope ``_auth_db`` that does a per-test
  ``TRUNCATE TABLE … RESTART IDENTITY CASCADE`` on PG and a
  reverse-FK ``DELETE FROM …`` cascade on SQLite, then re-seeds
  the workspace + admin/non-admin users from a hash cached at
  module import — eliminating ~90 DDL statements per test (the
  single biggest cost on PG); 31.3 adds a
  ``POINTLESSQL_TEST_LIFESPAN_FAST=1`` env var that
  ``pointlessql.api.main._lifespan`` honours by short-circuiting
  the alembic-upgrade-on-default-URL ``init_db`` and the audit /
  lineage / external-writes / branch-cleanup background asyncio
  tasks (production startup is untouched — the env var is only set
  inside the test process).  31.4 flips ``-n auto`` on for the
  SQLite CI lane via ``.github/workflows/test.yml`` and ships
  [`docs/development/test-suite.md`](docs/development/test-suite.md)
  documenting the bench script, the env var, and the safe-edit
  rules; PG xdist is deferred (workers can't share a live PG
  database without per-worker DB provisioning).  31.5 closes the
  phase with the CHANGELOG / ROADMAP / memory entry.  ``ruff``,
  ``ruff format --check``, ``pyright``, and ``mkdocs build
  --strict`` all clean on Phase-31-touched files (the four
  pre-existing pyright errors in ``conftest.py`` and the lint
  errors elsewhere in the repo are unchanged).
- **Phase 30 closed (2026-05-05)** — Postgres production-readiness
  for the audit lake.  Six sub-sprints close the cliffs that
  stood between "swap a URL and pray" and "production default".
  30.0 adds a CI Postgres lane in ``.github/workflows/test.yml``
  spinning up ``postgres:17-alpine``, teaches ``alembic env.py``
  to honour ``POINTLESSQL_DB_URL`` for shell-driven runs, and
  fixes three pre-existing dialect bugs that broke
  ``alembic upgrade head`` against fresh PG (literal
  ``DEFAULT 0``/``1`` boolean defaults in 28.1a / 29.3 / 13.11
  / 18 migrations, plus the Phase-18.7 ``audit_search``
  migration's time-travel import of the workspace-aware
  ``audit_fts`` module — the migration now inlines a snapshot of
  the original SQL).  30.1 ships the PG-side full-text search
  (alembic ``hh8j0l2n4p6r``: ``audit_search_index`` table with a
  generated ``tsvector`` + GIN index, five PL/pgSQL trigger
  sets) so ``/api/audit/search`` returns ``available=true`` on PG
  with the same ``(snippet, rank)`` envelope; ``audit_fts.py``
  becomes a dialect router behind unchanged public surface.  30.2
  swaps Grafana onto the built-in PostgreSQL datasource via a new
  ``docker-compose.grafana.postgres.yml`` overlay + a
  dialect-clean dashboard JSON in ``grafana/postgres-dashboards/``
  (Panel 5's reject-rate baseline rewritten with PG
  ``INTERVAL '7 days'`` arithmetic).  30.3 ships the
  ``pointlessql migrate-to-postgres`` CLI: refuses non-empty
  targets, runs alembic upgrade head, bulk-copies tables in a
  hard-coded FK-respecting order, syncs PG sequences past the
  largest copied id, rebuilds the FTS index, and verifies row
  counts plus a 1%-sample-hash for tables ≥100 rows.  30.4 adds
  four pool / timeout knobs to ``DatabaseSettings`` (``pool_size``,
  ``max_overflow``, ``pool_recycle_seconds``, ``statement_timeout_ms``)
  + a per-connection ``SET statement_timeout`` event listener +
  the ``docs/admin/postgres-deployment.md`` ops playbook
  (autovacuum hints for ``lineage_row_edges`` /
  ``agent_run_tool_calls`` / ``lineage_value_changes``, backup
  via ``pg_dump --format=custom``, monitoring signals).  30.5
  ships ``scripts/seed_audit_lake.py`` (deterministic synthetic
  load at 10 k / 100 k / 1 M scales, runs against either
  backend) + the ``docs/admin/performance.md`` baseline
  template.  Phase 19.0.1's deferral is closed — Postgres is
  now a first-class deployment target; SQLite stays the laptop
  default per the Decision-C dual-track pick.

- **Phase 29 closed (2026-05-05)** — workspace polish pass.  Five
  sub-sprints fix the cross-cutting tenancy gaps left after Phase
  28 shipped soft isolation: 29.1 routes audit-sinks per workspace
  via a new ``workspace_filter`` JSON column on ``audit_sinks``;
  29.2 mirrors the same shape on ``review_destinations`` plus adds
  ``agent_reviews.workspace_id`` so reviews carry the routing key;
  29.3 wires OIDC group → workspace + scope mapping via the new
  ``POINTLESSQL_OIDC_GROUP_MAP_RAW`` env var (parser fails loud on
  malformed input; ``users.is_supervisor`` / ``is_auditor`` /
  ``oidc_groups_json`` columns let session-cookie callers hold the
  scopes API keys already could); 29.4 adds a ``$workspace``
  template variable to the Grafana audit dashboard with the
  ``(0 IN ($workspace) OR <table>.workspace_id IN ($workspace))``
  predicate pattern so "All" stays the default.  Three alembic
  migrations (``ee5g7i9k1m3o``, ``ff6h8j0l2n4p``, ``gg7i9k1m3o5q``);
  ``system_keys`` deliberately stays install-global so PII anomaly
  aggregation still aligns across tenants.

- **Phase 23 closed (2026-05-05)** — contextual help-popovers
  rolled out across the entire UI.  ~40 new slugs land across
  catalog tree + table-detail (23.1), models index + detail
  (23.2), audit cockpit + branches + home (23.3), SQL editor +
  admin (23.4), plus a doc-link sweep + registry/template
  cross-check (23.5).  Phase 23 closes with ~50 popovers
  total, every "Learn more →" pointing at a real mkdocs page.

- **Phase 28 closed (2026-05-05)** — soft workspace isolation in
  the Databricks Unity-Catalog mental model: catalogs stay global,
  workspaces own audit/jobs/saved-queries/recents.  9 sub-sprints
  landed in one autonomous run (28.0 through 28.8).  Single-tenant
  installs see zero behaviour change — the topbar switcher hides
  itself when ≤1 workspace exists.  ADR at
  ``docs/decisions/0008-workspace-soft-isolation.md``; concept doc
  at ``docs/concepts/workspaces.md``; admin runbook at
  ``docs/admin/workspace-management.md``.

- **Phase 18.6+ closed (2026-05-05)** — four sub-sprints landed
  (18.6 inbox + run-list badge, 18.7 audit-FTS, 18.8 runs-by-table
  reverse index, 18.9 cell + column-lineage diff).  Sprint 18.10
  (anomaly-verdict cache) deferred per plan: contingent on a
  real ≥10⁴-run lake breaching ``/audit/inbox`` p95 > 2s.
  Today's instances stay sub-100ms on the live aggregator.

### Added

- **Sprint 30.5 — Phase 30 performance baseline + close-out.**
  ``scripts/seed_audit_lake.py`` seeds deterministic synthetic
  audit-lake data at 10k / 100k / 1M scales against either
  backend (``POINTLESSQL_DB_URL``-driven).
  ``docs/admin/performance.md`` ships as a measurement template:
  the operator runs the seed + their own queries on their
  hardware and fills in the table.  ``mkdocs build --strict``
  passes with the new admin pages.

- **Sprint 30.4 — production tuning + ops docs.**
  ``DatabaseSettings`` grew four PG-aware fields:
  ``pool_size`` (5), ``max_overflow`` (10),
  ``pool_recycle_seconds`` (1800),
  ``statement_timeout_ms`` (30 000).  ``init_db()`` threads
  pool sizing into ``create_engine`` for PG and registers a
  per-connection ``SET statement_timeout`` event listener
  mirroring the existing SQLite-PRAGMA hook.
  ``docs/admin/postgres-deployment.md`` (~3 pages) covers the
  pool-sizing formula for a 4-worker fleet, autovacuum hints
  for the high-churn audit tables, backup/restore via
  ``pg_dump --format=custom`` and ``pg_restore --jobs=4``, and
  the monitoring signals operators should alert on.
  ``docs/reference/configuration.md`` documents the four new
  env vars.

- **Sprint 30.3 — ``pointlessql migrate-to-postgres`` CLI.**
  New ``pointlessql/cli/migrate_to_postgres.py`` module wired
  into the existing Typer surface.  Validates dialects (refuses
  non-SQLite source / non-PG target), runs ``alembic upgrade
  head`` against the target, refuses to overwrite a target with
  rows beyond the bootstrap workspace, bulk-copies in a
  hard-coded FK-respecting order via SQLAlchemy core (streamed
  ``--batch-size`` chunks), syncs every PG ``serial`` sequence
  past the largest copied id, rebuilds the Sprint-30.1 FTS
  index from the freshly-copied source rows, and verifies
  per-table row counts plus a 1%-sample-hash for tables with
  ≥100 rows.  ``--dry-run`` skips writes and prints the plan +
  source row counts.  Three unit tests (validation + dry-run);
  two ``@pytest.mark.postgres`` round-trip / refuse-non-empty
  tests run in the 30.0 PG CI lane.

- **Sprint 30.2 — Grafana on Postgres.**
  New ``docker-compose.grafana.postgres.yml`` overlay swaps the
  unsigned ``frser-sqlite-datasource`` plugin for Grafana's
  built-in PostgreSQL datasource.  Provisioning split into
  ``grafana/postgres-provisioning/`` (datasources +
  dashboards) and dialect-clean dashboard JSON shipped at
  ``grafana/postgres-dashboards/pointlessql_audit.json``.  Panel
  5's rolling 7-day reject baseline rewritten from SQLite
  ``date(d.day, '-7 days')`` modifier syntax to PG
  ``INTERVAL '7 days'`` arithmetic; ``COUNT(*)::float8`` and
  ``cost_est::float8`` casts replace ``CAST(... AS REAL)`` so the
  rendered numbers come back without REAL-cast drift on PG.
  Datasource UID ``pointlessql-postgres`` keeps panels stable
  across reprovisioning.  The two Grafana overlays
  (``docker-compose.grafana.yml`` for SQLite,
  ``docker-compose.grafana.postgres.yml`` for PG) are mutually
  exclusive.  ``docs/integrations/grafana.md`` gains a "Running
  with Postgres" section and drops the Phase-19.0.1 deferral
  prose.

- **Sprint 30.1 — Postgres FTS via tsvector + GIN.**
  New alembic ``hh8j0l2n4p6r_audit_search_pg_fts`` (PG-only;
  SQLite no-ops) creates ``audit_search_index`` with a
  generated ``tsvector`` column and a GIN index on it.  Five
  PL/pgSQL trigger functions (one per source axis: ``runs``,
  ``ops``, ``queries``, ``tool_calls``, ``audit_log``) keep the
  index in sync with INSERT / UPDATE / DELETE on the source
  tables.  ``pointlessql/services/audit_fts.py`` refactored
  into a dialect router: ``is_available``, ``search``,
  ``install_index``, ``rebuild_index`` keep their public
  signatures; SQLite path is unchanged, PG path uses
  ``WHERE text_search @@ plainto_tsquery('simple', :query)`` +
  ``ts_rank`` ordering + ``ts_headline('simple', text_corpus,
  …, 'StartSel=<mark>, StopSel=</mark>')`` snippet rendering.
  Both backends return the same ``(snippet, rank,
  workspace_id, …)`` rowshape; ``/api/audit/search`` no longer
  returns ``available=false`` on PG.  The
  ``audit_search.html`` template's "FTS not provisioned" copy
  drops the SQLite-specific deferral language.

- **Sprint 30.0 — CI Postgres lane + dialect drift fence.**
  ``.github/workflows/test.yml`` grew a parallel ``postgres``
  job that spins up ``postgres:17-alpine`` as a service and
  re-runs the full pytest suite against PG via
  ``TEST_DATABASE_URL``.  ``pointlessql/alembic/env.py`` now
  honours ``POINTLESSQL_DB_URL`` so shell-driven
  ``alembic upgrade head`` no longer hits the hard-coded
  SQLite path in ``alembic.ini``.  ``tests/conftest.py``'s
  ``_seed_default_workspace`` helper bumps the PG
  ``workspaces_id_seq`` past the explicit ``id=1`` insert so
  subsequent INSERTs don't collide.  Three pre-existing
  dialect bugs fixed: ``BOOLEAN DEFAULT 0`` literals replaced
  with ``DEFAULT false`` / ``true`` (PG rejects integer-vs-
  boolean type mismatch) in ``j0e1f2a3b4c5``,
  ``k1f2a3b4c5d6``, ``gg7i9k1m3o5q``, ``l2g3a4b5c6d7``,
  ``m3h4i5j6k7l8`` migrations + ``api_keys.auditor`` and
  ``users.is_supervisor`` / ``is_auditor`` model defaults.  The
  Phase-18.7 ``y5u7v9w1x3z5_audit_search_fts`` and Phase-28's
  ``aa1c3e5g7i9k`` / ``bb2d4f6h8j0l`` migrations now inline
  the FTS5 SQL as a chronological snapshot rather than
  importing from the live ``audit_fts`` module — the live
  module evolved past the schema state at those migration
  points and replaying on a fresh DB tripped "no such column:
  workspace_id".  Result: ``alembic upgrade head`` runs clean
  on a fresh DB on both SQLite and PG; ``alembic check``
  reports no drift on either.

- **Sprint 29.5 — Phase 29 polish + close-out.**  ``ruff format``
  + ``ruff check`` clean across every Phase-29-touched file;
  ``alembic check`` confirms zero ORM↔migration drift across the
  three new migrations; ``mkdocs build --strict`` passes with the
  new ``docs/admin/oidc-group-map.md`` page wired into the Admin
  nav and the new "Filtering by workspace" section on
  ``docs/integrations/grafana.md``.

- **Sprint 29.4 — Grafana ``$workspace`` template variable.**
  ``grafana/dashboards/pointlessql_audit.json`` grew a multi-select
  ``workspace`` query variable populated from the ``workspaces``
  table.  Each panel SQL grew a guard predicate
  ``AND (0 IN ($workspace) OR <table>.workspace_id IN ($workspace))``
  so ``allValue=0`` maps to a true short-circuit (full cross-
  workspace view) while specific picks filter via
  ``IN``.  The smoke-test panel ("Datasource health") stays global
  on purpose.  ``docs/integrations/grafana.md`` documents the
  filter behaviour, the ``var-workspace=<id>`` URL override, and
  why Grafana queries don't generate audit-of-audit trails.

- **Sprint 29.3 — OIDC group → workspace + scope mapping.**  New
  alembic ``gg7i9k1m3o5q_user_scope_columns`` adds
  ``users.is_supervisor`` / ``is_auditor`` (mirrors
  ``ApiKey.supervisor`` / ``auditor`` on the session-cookie path)
  and ``users.oidc_groups_json`` (audit-visibility snapshot of the
  most recent groups claim).  ``OIDCSettings`` gains
  ``scope`` / ``groups_claim_name`` / ``group_map_raw`` env vars
  with a fail-loud parser at settings construction; the
  authorize-URL builder now threads the configured scope through.
  ``find_or_create_oidc_user`` extracts the groups claim, unions
  scope grants across every matching mapping, picks the first
  matching ``ws=`` as the user's ``default_workspace_id``, and
  re-resolves on every login so IdP group changes propagate
  without a manual refresh.  ``require_supervisor`` /
  ``require_auditor`` now honour the new ``is_supervisor`` /
  ``is_auditor`` flags on the session-cookie path while keeping
  the asymmetric privilege ladder (auditor passes
  ``require_supervisor``; supervisor does NOT pass
  ``require_auditor``).  New
  ``docs/admin/oidc-group-map.md`` documents the env-var format,
  worked example, and limitations.  20 new pytest tests at
  ``tests/test_oidc_group_map.py``.

- **Sprint 29.2 — Per-workspace review-destination routing.**  New
  alembic ``ff6h8j0l2n4p_review_destination_workspace_filter`` adds
  ``agent_reviews.workspace_id`` (FK to ``workspaces``, defaults to
  install-default 1) plus the ``review_destinations.workspace_filter``
  JSON column.  ``dispatch_review`` reads ``review.workspace_id``
  off the row and consults the destination filter — null filter
  preserves install-global semantics; ``[1]`` excludes
  ``workspace_id=2``.  ``POST /api/agent-reviews`` now reads
  ``request.state.workspace_id`` to populate ``AgentReview.workspace_id``.
  ``POST`` / ``PATCH`` on ``/api/admin/review-destinations``
  validate that listed workspace IDs exist (rejects unknown IDs
  with 400 so a typo never silently blackholes deliveries).  6 new
  pytest tests at
  ``tests/test_review_destination_workspace_filter.py``.

- **Sprint 29.1 — Per-workspace audit-sink routing.**  New
  alembic ``ee5g7i9k1m3o_audit_sink_workspace_filter`` adds
  ``audit_sinks.workspace_filter`` (JSON-encoded list of allowed
  workspace IDs; ``NULL`` keeps install-global fan-out for
  back-compat).  ``dispatch_to_sinks`` gained an optional
  ``workspace_id`` kwarg; ``emit_governance_event`` threads its
  workspace context through.  The synthetic
  ``/api/admin/audit-sinks/{id}/test`` flow keeps bypassing both
  the event-type and workspace filters so admins can ping a sink
  without picking a tenant.  ``POST`` / ``PATCH`` validate listed
  workspace IDs against the live ``workspaces`` table; ``GET``
  returns the new field on every row.  6 new pytest tests at
  ``tests/test_audit_sink_workspace_filter.py``.

- **Sprint 28.8 — documentation + ADR-0008 + ROADMAP positioning.**
  New ``docs/concepts/workspaces.md`` (concept), new
  ``docs/admin/workspace-management.md`` (admin runbook), new
  ``docs/decisions/0008-workspace-soft-isolation.md`` (ADR
  recording the seven Phase-28 decisions verbatim).  ROADMAP
  Phase 28 entry flipped to ✅ with per-sub-sprint detail.

- **Sprint 28.7 — cross-workspace super-admin lens.**  The audit
  aggregator (``summary`` / ``timeseries`` / ``anomalies``) gained
  a ``workspace_id`` kwarg; ``None`` skips the filter for the
  god-eye view.  /api/audit/* routes accept ``?workspace=``
  (slug | "all"); admin-only when not the caller's resolved
  workspace.  New ``audit_api_cross_workspace`` value in
  :data:`VALID_READ_KINDS` so the audit-of-audit pipeline can
  flag tenant-admin escalations into the cross-workspace lens.
  Response shape grew ``"workspace"`` + ``"lens_mode"`` fields.
  6 new pytest cases in ``tests/test_cross_workspace_lens.py``.

- **Sprint 28.6 — admin workspace + member CRUD.**  New module
  ``pointlessql/api/admin_workspaces_routes.py`` with seven
  tenant-admin-gated endpoints: list / create / update / archive
  workspaces, list / add / role-change / remove members.  New
  HTML page ``/admin/workspaces`` combines list + create form +
  per-row archive button via Alpine + ``pqlApi.fetch``.  Refuses
  to archive id=1 (default) — the resolver's fallback floor
  depends on it always being live.  Mutations log to
  ``audit_log`` with ``workspace.*`` action prefix.  Alembic
  ``dd4f6h8j0l2n`` flips ``users.default_workspace_id`` to
  NOT NULL after a defensive backfill.  12 new pytest cases.

- **Sprint 28.5 — Hermes plugin X-Workspace + wake-gate scoping.**
  Cross-repo edits in ``~/git/hermes-plugin-pointlessql``:
  ``PluginConfig.workspace`` reads ``POINTLESSQL_WORKSPACE``
  (lower-cased + stripped to match server-side slug rules);
  ``_headers()`` injects ``X-Workspace`` on every PointlesSQL
  HTTP call, omitted when the env var is unset so the resolver
  falls through to the api_key's pinned tier.  Server-side
  ``scripts/audit-wake-gate.py`` honours the same env var so the
  daily Audit-Reviewer-Agent's pre-anomaly fetch lands in the
  agent's eventual run-time workspace.  New
  ``tests/test_cross_workspace_api_key.py`` (4 tests) + plugin's
  ``tests/test_workspace_header.py`` (5 tests) close the
  round-trip contract.

- **Sprint 28.4 — UI workspace switcher + base.html plumbing.**
  New ``POST /auth/switch-workspace`` route writes the
  ``pql_workspace`` cookie (membership-enforced).  Middleware's
  ``_read_workspace_slug_from_session`` reads it back as the
  cookie tier of the resolver chain.  New
  ``frontend/templates/components/workspace_switcher.html``
  partial mounted in the topbar; renders only when the user
  belongs to ≥2 workspaces (single-tenant UX unchanged).
  ``base.html`` ships three workspace meta tags
  (``workspace-id``, ``workspace-slug``,
  ``workspace-primary-catalog``).  ``pqlApi.fetch`` and the
  HTMX ``htmx:configRequest`` bridge auto-inject ``X-Workspace``
  on every request.  ``frontend/js/pages/catalog_tree.js``
  namespaces its sessionStorage tree-cache + localStorage
  recents-cache by workspace slug, and pre-expands the
  workspace's ``primary``-pinned catalog on first sidebar load.
  TemplateResponse wrapper threads ``current_workspace``,
  ``available_workspaces``, and ``current_workspace_primary_catalog``
  into every Jinja context.  New help slug
  ``workspace.what-is-a-workspace``.  9 new pytest cases.

- **Sprint 28.3 — workspace catalog pins (cosmetic) + tree filter.**
  Wires the ``workspace_catalog_pins`` table created (but unused) in
  Sprint 28.0.  Three new admin-only routes:
  ``GET /api/admin/workspaces/{id}/pins``,
  ``POST /api/admin/workspaces/{id}/pins`` (auto-demotes any
  prior primary when promoting a new one to ``primary`` mode),
  ``DELETE /api/admin/workspaces/{id}/pins/{catalog_name}``.
  ``GET /api/tree`` accepts an optional ``primary_only=true``
  query parameter that filters the returned tree to the active
  workspace's pinned catalogs.

  No enforcement: pins are *cosmetic*.  Cross-workspace catalog
  access stays free per the global-catalog decision (ADR-0008
  shipping in 28.8).  Workspaces with zero pins see the full
  tree exactly like the pre-Phase-28 UI.  Mutations
  audit-log to ``workspace.pin_added`` / ``workspace.pin_removed``.

  6 new pytest cases in ``tests/test_workspace_pins.py``: CRUD
  round-trip with primary-promotion demotion behaviour, malformed
  mode rejection, 404 on unknown workspace, admin-only enforcement,
  UNIQUE constraint blocking dup, and the filter logic itself.

- **Sprint 28.2 — workspace_id on user-owned + scheduler tables.**
  Adds workspace_id NOT NULL with ``server_default='1'`` to 13
  tables (Alembic ``cc3e5g7i9k1m``): ``jobs``, ``job_runs``,
  ``job_tasks``, ``task_runs``, ``job_logs``, ``dashboards``,
  ``saved_queries``, ``saved_audit_queries``, ``recent_tables``,
  ``alerts``, ``alert_events``, ``notebook_outputs``,
  ``notebook_cell_runs``.  Backfill cascades from owner_id /
  run_as_user_id → users.default_workspace_id, with child tables
  inheriting from their parent.  ``recent_tables`` UNIQUE constraint
  widens from ``(user_id, table_full_name)`` to ``(workspace_id,
  user_id, table_full_name)`` so a user visiting the same table
  from two workspaces gets two rows.

  Service-layer write paths thread workspace_id:
  ``scheduler.runs._start_run`` / ``_insert_skipped`` /
  ``log_job`` / ``_create_task_run`` derive workspace_id from the
  parent Job (or JobRun for child writes).
  ``recents.record_table_visit`` accepts a ``workspace_id`` kwarg
  (defaults to 1) and the upsert ``ON CONFLICT`` index switches to
  the new (workspace_id, user_id, table_full_name) triple.
  ``recents.top_recent_tables`` accepts an optional ``workspace_id``
  filter.  ``saved_queries.create_saved_query`` accepts
  ``workspace_id``.  Route-side workspace filtering in jobs /
  dashboards / saved-queries / alerts listings stays for a
  follow-up — the schema and write paths are in place so the
  filters add cleanly without a second migration.

  6 new pytest cases in
  ``tests/test_user_owned_workspace_isolation.py`` covering schema
  sanity, JobRun workspace propagation from parent Job (incl.
  log_job inheriting from JobRun), recents per-workspace upsert
  + UNIQUE widening, ``top_recent_tables`` workspace filter, and
  ``create_saved_query`` workspace passthrough.

- **Sprint 28.1b — workspace_id on lineage / audit_log / governance /
  query_history (+ FTS5 trigger flip).**  Completes the audit-side
  workspace cascade.  Adds workspace_id NOT NULL with
  ``server_default='1'`` to ten tables (Alembic ``bb2d4f6h8j0l``):
  ``lineage_row_edges``, ``lineage_row_rejects``,
  ``lineage_column_map``, ``lineage_value_changes``,
  ``query_history``, ``query_history_tables``, ``audit_log``,
  ``governance_events``, ``unattributed_writes``, ``anomaly_acks``.
  Two UNIQUE constraints widen to prefix workspace_id:
  ``unattributed_writes (workspace_id, table_fqn, delta_version)``
  so the same Delta commit can fan out to multiple workspaces, and
  ``anomaly_acks (workspace_id, metric, bin_iso, bin_kind,
  group_value, group_kind)`` so two workspaces can independently
  ack the same metric bin.

  Service-layer write paths thread workspace_id through:
  ``audit.log_action`` accepts a ``workspace_id`` kwarg (defaults to
  1 for non-HTTP callers); the api ``audit()`` wrapper reads
  ``request.state.workspace_id``.  ``query_history.record_query``
  accepts ``workspace_id``; the api ``record_query_async`` wrapper
  threads it.  ``governance_events.emit_governance_event`` accepts
  ``workspace_id`` and forwards to ``_persist_event``.
  ``lineage_edges.record_edges`` / ``record_rejects`` /
  ``record_column_edges`` / ``record_value_changes`` derive
  ``workspace_id`` from the parent agent_run_operation by JOIN
  (one extra SELECT per write; cheap relative to the bulk insert).
  ``external_write_scanner`` attributes every unattributed Delta
  commit to workspace=1 (Sprint 28.3 will fan out via catalog pins).
  ``POST /api/audit/anomaly-acks`` writes the request's resolved
  workspace_id.

  FTS5 trigger flip: ``query_history`` and ``audit_log`` trigger
  specs in ``audit_fts`` change from literal ``1`` (the 28.1a
  placeholder) to ``IFNULL(NEW.workspace_id, 1)``.  Migration
  drops + recreates the audit_search vtable + 15 triggers using
  the updated specs so the new column shape is in effect for every
  subsequent insert.  After 28.1b the entire FTS axis is workspace-
  isolated end-to-end.

  8 new pytest cases in
  ``tests/test_lineage_audit_workspace_isolation.py`` covering
  schema sanity, ``log_action`` workspace passthrough,
  ``record_query`` workspace passthrough, ``governance_events``
  emit workspace passthrough, ``anomaly_acks`` UNIQUE constraint
  widening, ``unattributed_writes`` UNIQUE constraint widening,
  and ``lineage_row_edges`` workspace inheritance from the parent
  op.

- **Sprint 28.1a — workspace_id on the audit-trail core + FTS5 surgery.**
  Adds the workspace_id FK column (NOT NULL, server_default='1') to
  the five audit-trail source tables — ``agent_runs``,
  ``agent_run_sources``, ``agent_run_operations``, ``agent_run_events``,
  ``agent_run_tool_calls`` — with compound indexes
  ``(workspace_id, started_at)`` on agent_runs and
  ``(workspace_id, agent_run_id)`` on the four child tables (Alembic
  ``aa1c3e5g7i9k``).  After this migration a workspace-A user CANNOT
  see workspace-B's runs, sources, operations, lifecycle events, or
  tool calls — listing routes ``GET /api/agent-runs`` and
  ``GET /api/agent-runs/operations`` add a workspace filter; per-run
  audit-axis routes ``/api/agent-runs/{id}/audit/<axis>`` return 404
  for cross-workspace requests via the extended ``ensure_run_visible``
  guard (a leak through the error code would tell the caller a UUID
  exists somewhere they can't see).  ``POST /api/agent-runs`` writes
  the resolved request workspace onto every new row; the
  AgentRunOperation / Event / ToolCall write paths denormalise
  workspace_id from the parent run by JOIN.

  FTS5 ``audit_search`` virtual table rebuilt with a 6th
  ``workspace_id UNINDEXED`` column.  Triggers for ``agent_runs``,
  ``agent_run_operations``, and ``agent_run_tool_calls`` populate it
  from ``NEW.workspace_id``; ``query_history`` and ``audit_log``
  triggers emit literal ``1`` (their source-table column lands in
  Sprint 28.1b).  ``audit_fts.search`` accepts a new
  ``workspace_id`` kwarg; ``GET /api/audit/search`` passes the
  request's resolved workspace.  Postgres deployments skip the FTS
  surgery entirely (the vtable is SQLite-only).

  10 new pytest cases in ``tests/test_agent_runs_workspace_isolation.py``
  covering schema sanity, listing-route isolation, per-run audit
  cross-workspace 404, ingestion-time workspace_id propagation, and
  FTS5 result filtering.

- **Sprint 28.0 — workspace foundation (model + middleware + api_keys
  pin + scheduler resolver).**  First sub-sprint of Phase 28 (soft
  workspace isolation, Databricks-style: catalogs stay global,
  workspaces own audit/jobs/saved-queries/recents).  Three new tables
  ``workspaces`` / ``workspace_members`` / ``workspace_catalog_pins``
  (Alembic ``z6w8a0b2c4d6``) plus FK columns on ``users``
  (``default_workspace_id``, nullable in 28.0, NOT NULL in 28.6) and
  ``api_keys`` (``workspace_id``, NOT NULL with backfill to id=1 —
  carved out of original 28.5 scope to eliminate the cross-sprint
  hazard where 28.3's catalog filter would trip Bearer-auth before
  the column existed).  Bootstrap migration seeds workspace
  ``id=1, slug='default'`` and adds every existing user as a member
  with role mirroring ``is_admin``.  New service module
  ``pointlessql/services/workspaces.py`` exposes CRUD primitives plus
  the non-HTTP ``resolve_workspace_id`` entry point shared by the
  middleware, scheduler tick, CLI, and test fixtures.  Middleware
  attaches ``request.state.workspace_id`` after auth resolution and
  403s ``workspace.context_mismatch`` (audit-logged) when an
  authenticated user names a workspace they don't belong to.  New
  ``current_workspace_id`` / ``current_workspace`` /
  ``require_workspace_admin`` dependencies in ``api/dependencies.py``.
  ``KeyEntry`` carries ``workspace_id`` so Bearer-authed requests
  inherit the key's pinned workspace.  Single-tenant installs see
  zero behaviour change — every existing row backfills to the
  default workspace and the UI stays identical until a second
  workspace is created in 28.6.  28 new pytest cases.

- **Sprint 18.9 — cell-level + column-lineage diff in run-vs-run.**
  ``GET /api/agent-runs/diff?detail=true`` and the
  ``/runs/{a}/diff/{b}`` HTML page now also carry
  ``value_changes_diff`` (per ``(target_table, op_id)`` bucket of
  divergent cells / only-in-a / only-in-b cells; capped at
  ``top_k=50`` per axis with a ``truncated`` flag; PII-masked
  unless admin) and ``column_lineage_diff`` (edge identity
  ``(op_id, source_table, source_column, target_table,
  target_column)`` partitioned into only-in-a / changed
  transform_kind-or-detail / only-in-b buckets).  Two new sub-tabs
  on the run-compare page render the new payloads.  No new schema
  — both helpers query existing ``lineage_value_changes`` /
  ``lineage_column_map`` rows.

- **Sprint 18.8 — runs-by-table reverse index.**  Flips the
  forward "what did this run touch?" direction on its head.
  New auditor-scope ``GET /api/audit/by-table?fqn=…&kind=…``
  with three relationship axes: ``touched`` (declared in
  ``AgentRun.tables_touched``), ``written`` (op
  ``target_table`` *or* ``lineage_value_changes`` target),
  ``read`` (referenced via ``query_history_tables``).  No
  new schema — ``tables_touched`` JSON containment uses
  dialect-portable ``LIKE '%"<fqn>"%'``.  New HTML page
  ``/audit/by-table/{fqn:path}`` with three lazy-loaded tabs.
  Catalog table-detail page header carries a "Runs that
  touched this table" cross-link.

- **Sprint 18.7 — full-text search across the audit lake.**
  New SQLite FTS5 virtual table ``audit_search`` (Alembic
  ``y5u7v9w1x3z5``) indexed by INSERT/UPDATE/DELETE triggers
  on ``agent_runs``, ``agent_run_operations``,
  ``query_history``, ``agent_run_tool_calls``, ``audit_log``.
  Tokenizer is ``unicode61 separators '._-'`` so UC FQNs
  match component-wise.  New auditor-scope endpoint
  ``GET /api/audit/search?q=…&axis=…`` returns ranked
  snippets; new HTML page ``/audit/search`` calls it via
  fetch.  Postgres deployments skip the migration and the
  route returns ``available=false`` (a tsvector replacement
  is deferred).  Service ``audit_fts`` exposes
  ``install_index`` (test fixtures) + ``rebuild_index``
  (emergency recovery).  Alembic ``include_object`` widens
  to skip the FTS5 shadow tables.

- **Sprint 18.6 — anomaly inbox + run-list badge.**  Phase 18.6+
  deepening of the closed Audit Cockpit.  Two new columns on
  ``agent_runs`` (``anomaly_severity``, ``anomaly_metric``)
  cache the day-bin anomaly verdict at run-finish time, driving
  a new badge column on the ``/runs`` list page without
  re-running the aggregator per render.  New ``anomaly_acks``
  table (Alembic ``x4t6u8v0w2y4``) carries the cross-run
  inbox's ack + snooze lifecycle.  ``GET /api/audit/inbox``
  aggregates anomalies across the run-anomaly metric pair
  (rejects + errored_ops, configurable) and joins ack state;
  ``POST /api/audit/anomaly-acks`` + ``DELETE
  /api/audit/anomaly-acks/{id}`` manage the lifecycle.  New
  HTML page at ``/audit/inbox`` with severity / metric / bin
  filters and Ack-or-Snooze + Un-ack actions.  Auditor scope
  on all reads + writes (admin cookie passes, supervisor does
  not).  ``audit_aggregator.compute_run_anomaly`` extracted as
  the shared verdict source for the run-detail chip, the
  finish-handler hook, and the ``backfill_run_anomalies``
  helper that backfills NULL columns on legacy rows.

- **Phase 24 — every rail icon now opens a useful context-panel.**
  Six previously-static or fall-through panels became navigable
  surfaces, mirroring the catalog tree's role for Federation:
  - **Runs** — recent agent runs grouped into Needs approval /
    Running / Recent buckets, 8-char short-IDs + status badges +
    relative timestamps.  Source: ``GET /api/runs?limit=15``.
  - **Branches** — Delta-branches grouped Active / Promoted /
    Discarded with strategy + timing tags.  Source:
    ``GET /api/branches`` (supervisor-gated; rail item is admin-
    only).
  - **Workspace** — flat alphabetical list of every ``.py`` /
    ``.ipynb`` notebook the scheduler can pick up; format badge
    per row.  Source: ``GET /api/notebooks/tree`` (admin-only).
  - **Jobs** — split into Active (with last-run-status badge) and
    Paused.  Source: ``GET /api/jobs``.
  - **Alerts** — split into Enabled (green bell) and Disabled
    (muted).  Source: ``GET /api/alerts``.
  - **MLflow** — recent UC-registered models with latest-version
    + status badge; "Open MLflow UI →" link to ``/ml``.  Source:
    ``GET /api/models?enrich_latest=true&limit=10``.

  Each panel is a small Alpine factory at
  ``frontend/js/components/sidebars/<section>_sidebar.js``
  imported through ``bootstrap.js``, paired with a partial at
  ``frontend/templates/components/sidebars/<section>_sidebar.html``
  included from ``components/context_panel.html``.  Pattern
  mirrors :func:`catalogTree` exactly (sessionStorage instant-
  paint, async refetch with refresh button, ``htmx:after-swap``
  re-binds active-row highlight from the URL).  Shared row
  styles live in
  ``frontend/css/components/context_sidebars.css``.

  Each panel header carries a Phase-23 contextual help-icon
  (slugs ``runs.context-panel`` / ``branches.context-panel`` /
  …) explaining what the panel shows and linking to the matching
  mkdocs concept page.  ``docs/e2e-walkthroughs/contextual-
  panels.md`` records the replayable verification sequence; it
  is wired into ``mkdocs.yml`` under "Getting around".

### Fixed

- **`/ml` page returned HTTP 500 since Phase 21.0** — the
  Phase-21 commit registered ``app.state.templates`` (the
  centralised Jinja env) but ``mlflow_html_routes.py`` still
  called ``templates.TemplateResponse("pages/mlflow.html",
  {context})`` with the pre-Starlette-0.37 positional
  signature.  Updated to pass ``request`` first.  Surfaced
  while live-verifying the MLflow context-panel.

### Changed

- **Volumes + Models now live inside the catalog tree** — both
  used to have their own top-level rail icon (``Volumes`` ·
  ``Models``) which served a flat ``/volumes`` / ``/models``
  listing.  In Unity Catalog, both are siblings of Tables under
  a Schema, so they belong in the catalog tree right next to
  ``bi-table`` rows.  The rail now omits both and the tree
  renders three child kinds per schema:
  ``bi-table`` (tables) → ``bi-hdd-stack`` (volumes) →
  ``bi-box-seam`` (models).  Server-side
  :meth:`UnityCatalogClient.get_tree` was extended to fetch
  volumes per schema concurrently with tables + models; a new
  :meth:`MetadataMixin.list_volumes` wraps the soyuz
  ``/api/2.1/unity-catalog/volumes`` endpoint that the
  generated client doesn't expose yet.  ``/api/tree/search``
  also matches volume names and returns ``kind: "volume"``
  results, rendered with a hard-disk icon in the sidebar
  search results.  The flat ``/volumes`` and ``/models``
  pages still work for direct URL hits (Cmd+K / typed URL);
  the ``active_section`` for both falls through to
  ``federation`` so the catalog tree stays visible in the
  context panel.

### Fixed

- **Icon rail labels truncated under the icons** — bumped
  ``--pql-icon-rail-width`` from 60 px to 80 px and switched the
  ``.pql-icon-rail__label`` cap from ``white-space: nowrap`` +
  ``text-overflow: ellipsis`` to ``white-space: normal`` +
  ``overflow-wrap: anywhere``.  All twelve labels (Federation,
  Runs, SQL, Workspace, Jobs, Alerts, Volumes, Dashboards, ML,
  Models, Branches, Admin) now render in full on a single line.
  Phase 23 follow-up.

- **Context panel did not switch when changing rail icons** —
  the contextual side-panel (catalog tree / SQL / Runs / Admin /
  …) lives outside the ``#main-content`` HTMX target, so a boost
  navigation only swapped ``<main>`` and the panel kept its
  previous section.  Added ``hx-select-oob="#pql-context-panel"``
  to ``<body>`` so HTMX OOB-swaps the panel from the response
  body on every boost.  Lifted the inline ``catalogTree()``
  IIFE in ``components/sidebar.html`` into a real ESM module
  (``frontend/js/pages/catalog_tree.js``) so the factory
  survives re-injection without depending on inline ``<script>``
  tags being re-evaluated mid-swap.  Round-trip
  Federation → SQL → Runs → Federation confirmed via
  Playwright; Alpine cleanly re-binds the catalog tree (50
  rows) on return.

### Added

- **SQL editor: structured EXPLAIN plan tree** — *complete
  version* surfacing every metric DuckDB returns: per-operator
  ``cpu_time`` (when distinct from wall-clock ``operator_timing``),
  ``result_set_size`` in bytes, ``cumulative_cardinality`` (subtree
  rows produced), ``cumulative_rows_scanned`` (subtree rows
  scanned), ``operator_rows_scanned`` (when > 0), peak buffer /
  temp-dir memory, plus every ``extra_info`` entry (no per-node
  cap; arrays truncated at 8 items).  Header carries Latency
  + ``rootByteMetrics`` (CPU time, total memory, bytes
  read/written, result-set size, rows returned, cumulative rows
  scanned, WAL replay count) + ``rootSubLatencies`` (waiting to
  attach, attach load, WAL replay, blocked-thread, checkpoint,
  WAL write, commit-local — only those non-zero).  Tree
  ``max-height`` loosened to ``min(75vh, 1000px)`` so rich
  plans don't disappear behind a scrollbar.

- **SQL editor: structured EXPLAIN plan tree** — *polished
  version*.  Replaces the raw ASCII-art tree DuckDB returns from
  ``EXPLAIN ANALYZE`` with a proper indented operator tree
  carrying per-node timing, row cardinality, and a key/value
  list of ``Projections``/``Filters``/``Estimated
  Cardinality``/etc. (every ``extra_info`` entry, capped at 4
  per node).  Each operator carries a colour-coded badge
  classified by kind (scan / filter / join / agg / limit /
  proj / sort / other).  Sub-millisecond timings render as
  ``µs`` instead of rounding to ``0.00 ms``.  The
  ``EXPLAIN_ANALYZE`` profiling wrapper is hidden from the
  tree (it's not real query work) — children render at the
  parent depth as if it weren't there.  Faint dashed vertical
  guideline at every indent level marks subtree boundaries.  ``_sql.py`` flips DuckDB into
  ``PRAGMA enable_profiling='json'`` mode so the same EXPLAIN
  call returns a structured profiling JSON tree; the route layer
  parses it and ships it as a new ``explain_plan`` field on the
  ``/api/sql/execute`` response (``explain_text`` stays as a
  pretty-printed JSON fallback for older clients / cURL).  The
  Alpine ``flattenPlan`` helper walks the tree into a flat list
  the template iterates with ``margin-left`` indentation.  A
  small "Show raw JSON" toggle is available for users who need
  to inspect the full profiling envelope.

### Fixed

- **SQL editor result table no longer overflows the results card.**
  ``frontend/templates/pages/sql_editor.html`` declared
  ``.pql-sql-results-wrap { overflow-x: auto }`` to make wide
  result tables scroll horizontally inside the card.  But the
  parent ``.card-body`` is a flex item of the Bootstrap
  ``display: flex`` ``.card`` and defaults to
  ``min-width: auto``, so it refused to shrink below the
  intrinsic min-content width of the wide ``<table>`` (every
  cell carries ``text-nowrap``, so columns like a UUID
  ``_lineage_row_id`` push the table well past the card width).
  Added a ``.pql-sql-results-card`` modifier whose
  ``.card-body`` is ``min-width: 0``, so the wrap's
  ``overflow-x: auto`` actually clips and scrolls instead of
  bleeding past the card's right edge.  Verified live via
  Playwright at 1400 px viewport: card width 1036 px, wrap
  client width 1002 px, table width 1519 px,
  ``wrapScrolls=true``, ``cardOverflowsViewport=false``.

- **Alpine init crash on every HTMX-boosted page (root cause of
  the blank Preview tab + every other un-initialised Alpine
  component).**  ``base.html`` registered an
  ``htmx:afterSwap`` listener that called
  ``Alpine.initTree(e.detail.target)`` on every boost.  Alpine 3
  has its own ``MutationObserver`` (set up in ``Alpine.start()``)
  that already initialises new DOM additions, so the explicit
  call was a *double-init*: when Alpine encountered a child it
  had already begun walking via the observer, the second walk
  hit ``e._x_doHide`` with stale state and threw
  ``TypeError: can't convert undefined to object``.  The
  exception aborted the entire walk → every ``x-data`` on the
  swapped page (Preview card, table-stats card, tags-editor,
  permissions-editor, the inline ``{ copied: false }`` chip
  state) ended up with ``hasStack=false``, rendering blank.
  Removed the redundant ``initTree`` call; Alpine's observer
  alone handles boosted swaps cleanly.  Verified live via
  Playwright: navigate Home → click houses_raw in catalog tree
  → click Preview tab → 10 rows render immediately.

- **Preview-card still sometimes blank on HTMX-boosted
  navigation.**  The earlier ``window.tablePreview`` rewrite
  inside the inline ``<script>`` did not fully fix the race:
  HTMX 2.x re-injects swapped scripts via ``createElement +
  appendChild`` (async), but ``Alpine.initTree`` runs
  synchronously inside the ``htmx:afterSwap`` listener — so
  Alpine could still evaluate ``x-data="tablePreview()"``
  before the swapped script had executed and assigned the
  global.  Definitive fix: lift the factory out of the
  inline ``<script>`` into ``frontend/js/pages/table_preview.js``
  and import it in ``frontend/js/bootstrap.js`` so the function
  lives on ``window.tablePreview`` from the very first
  document load — long before any HTMX boost.  The template
  now passes the FQN as an x-data argument
  (``tablePreview('catalog.schema.table')``), so a single
  registered factory serves any table.

- **Missing-storage hint copy no longer suggests re-seeding the
  demo.**  PointlesSQL catalog data is independent of the demo
  seed scripts and walkthrough fixtures; pointing users at
  ``scripts/seed-full-stack-demo.py`` after a missing-path error
  was misleading for anyone whose tables are real production
  data.  The hint now reads "the data may have been moved,
  deleted, or never landed at this path; update
  ``storage_location``, restore the data, or drop the table"
  — product-agnostic.  Test ``test_message_does_not_couple_to_
  demo_seed`` pins the policy.

- **Catalog tree disappeared on deep paths after the previous HTMX
  shell-swap fix.**  Switching ``hx-target`` to ``.pql-shell`` so
  the icon-rail's ``.active`` class would update on boost
  inadvertently broke the ``catalogTree`` Alpine factory: its
  inline ``<script>`` registration at the bottom of
  ``components/sidebar.html`` did not re-evaluate reliably on
  HTMX-swapped content, leaving the tree empty on every page
  past the initial load.  Reverted ``hx-target`` to
  ``#main-content`` (catalog tree, recents, filter all behave
  again) and now sync the rail's active class via a small
  ``htmx:afterSwap`` listener that reads
  ``data-active-section`` from the new ``<main>`` and toggles
  ``.active`` on the rail link with the matching ``data-section``.

- **Friendly preview-card error when a table's storage path is
  missing on disk.**  Tables whose ``storage_root`` no longer
  resolves (demo seed cleaned up, ``/tmp`` cleared on reboot,
  external location moved) used to render the raw Rust-style
  deltalake error in the preview card: ``Invalid table location:
  file:///tmp/demo/orders Error: Os { code: 2, kind: NotFound,
  message: "No such file or directory" }``.  Now classified by
  the new ``humanize_preview_error`` helper into a one-line
  ``Table data is missing on disk: /tmp/demo/orders. The catalog
  still points here but the files are gone …`` plus an
  actionable "How to fix" hint pointing at
  ``scripts/seed-full-stack-demo.py --fresh`` or the drop-table
  path.  Applies to both ``/api/catalogs/.../preview`` and
  ``/api/tables/.../preview-at-version``.  Tests:
  ``tests/test_preview_error_humanizer.py`` (NEW, 7 tests).

- **Friendly soyuz error extraction in the SQL editor.**  Querying
  a missing catalog used to surface the raw multi-line
  ``UnexpectedStatus`` dump (``Unexpected status code: 404\n\n
  Response content:\n{"error_code":"NOT_FOUND","message":"Catalog
  'X' does not exist","request_id":"…"}``).
  ``wrap_catalog_errors`` in ``pointlessql/services/unitycatalog/
  _api.py`` now parses the JSON envelope and uses only the
  ``message`` field when raising the domain exception (404 →
  ``CatalogNotFoundError``, 4xx → ``ValidationError``, 5xx →
  ``CatalogUnavailableError``).  Falls back to the verbose
  ``str(exc)`` if the body is not parseable JSON or lacks a
  ``message`` — better verbose than empty.  Tests:
  ``tests/test_unitycatalog_errors.py`` (NEW, 9 tests).

- **Icon-rail active state + context-panel content stuck on
  HTMX-boosted navigation.**  Body-level
  ``hx-target="#main-content"`` only swapped the content area;
  the icon-rail (``.active`` class) and the 240 px context-panel
  (renders different children per ``active_section``) lived
  outside ``#main-content`` and stayed frozen at whatever the
  initial page render produced.  Symptom: clicking Jobs / Alerts
  / SQL etc. loaded the new page but the green active highlight
  stuck on the previous icon, and the context panel kept showing
  the previous section's tree (the catalog tree never reappeared
  on federation pages once you'd navigated away).  Fix: switch
  ``hx-target`` and ``hx-select`` to ``.pql-shell`` so the entire
  app shell (rail + panel + main) re-renders on every boosted
  navigation.

### Added

- **Sprint 23.5 — Phase 23 polish + doc-link sweep.**  Closes
  Phase 23.  No new copy.  ``pointlessql/web/help.py`` —
  re-targeted eight stale ``learn_more`` paths
  (``/concepts/agent-runs/`` →
  ``/concepts/agent-supervision/``; ``/concepts/operations/`` →
  ``/concepts/agent-supervision/``; ``/concepts/model-promotion/``
  → ``/concepts/audit-trail/``; ``/concepts/delta-branching/`` →
  ``/concepts/architecture/``; ``/concepts/notebooks/`` →
  ``None``; ``/concepts/jobs/`` → ``/guides/jobs/``;
  ``/concepts/alerts/`` → ``None``; ``/concepts/mlflow/`` →
  ``/concepts/architecture/``) so every "Learn more" link lands
  on a real mkdocs page.  ``tests/test_help_registry.py`` — two
  new sweep tests (``test_every_template_slug_resolves_in_registry``,
  ``test_every_registry_slug_used_in_some_template``) that
  cross-check the ~50-slug registry against ``info('<slug>')``
  calls in templates so a stale slug or a typo surfaces in CI.

- **Sprint 23.4 — SQL editor + admin help popovers (10 slugs).**
  Three SQL anchors (``sql.run-modes`` on the editor header,
  ``sql.saved-queries`` on the Save button, ``sql.cost-gate`` on
  the Explain button) plus seven admin anchors covering external
  writes (``admin.external-writes-review``), audit sinks
  (``admin.audit-sinks``), workspace pins
  (``admin.workspace-pins``), api-key scopes / system keys /
  rate-limit tiers on the Credentials page
  (``admin.api-key-scopes``, ``admin.system-keys``,
  ``admin.rate-limit-tiers``), and agent reviews on the review
  detail page (``admin.agent-reviews``).  Pinned by
  ``test_sprint_23_4_sql_admin_anchors_present``.

- **Sprint 23.3 — Audit cockpit + branches + home help popovers
  (12 slugs).**  Twelve new anchors light up the supervision
  surfaces: ``audit.what-is-an-anomaly`` /
  ``audit.severity-warn-vs-critical`` / ``audit.anomaly-actions``
  on the inbox header / severity filter / Ack column;
  ``audit.fts-query-syntax`` on the FTS Query input;
  ``audit.principal-summary`` on the by-table Principal column;
  ``audit.cross-workspace-lens`` and ``audit.read-kind`` on the
  saved-queries cockpit page; ``branches.preview-tab`` /
  ``branches.promote-vs-discard`` / ``branches.cleanup-loop`` on
  the branch-detail Preview button / Danger-zone header /
  Strategy field; ``home.what-is-the-cockpit`` and
  ``home.anomaly-cards`` on the home page Welcome heading and
  anomaly banner.  Pinned by
  ``test_sprint_23_3_audit_branches_home_anchors_present``.

- **Sprint 23.2 — Models index + detail help popovers (6 slugs).**
  Six new anchors across the model-registry surface:
  ``models.what-is-the-registry`` on the ``/models`` page header,
  ``models.versions-table`` on the new card-header inside the
  Versions tab, ``models.linked-hermes-runs`` on the Overview
  cross-link card, ``models.inference-lineage`` on the
  Prediction-tables card inside the Lineage tab,
  ``models.mlflow-vs-pointlessql`` on the MLflow tab intro line,
  and ``models.compare-versions`` on the v1↔v2 compare-page
  header.  Pinned by ``test_sprint_23_2_models_anchors_present``.

- **Sprint 23.1 — Catalog + table-detail help popovers (8 slugs).**
  Eight new ``bi-info-circle`` anchors land where a newcomer first
  meets table-shape concepts: the sidebar **Catalog** heading
  (``catalog.what-is-a-catalog``), the schema-detail page header
  (``schemas.what-is-a-schema``), and five spots on the
  table-detail page — Type badge / Properties card
  (``tables.external-vs-managed``,
  ``tables.comments-vs-properties``), Preview card + "View at"
  selector (``tables.row-lineage-badge``,
  ``tables.time-travel-button``), Columns card + Column-statistics
  card (``tables.column-trace-badge``,
  ``tables.column-statistics``).  Plus the Type column header on
  the schema-detail tables list.  ``tests/test_help_registry.py``
  pins the eight slugs so a rename surfaces in CI.

- **Sprint 23.0 — Contextual help-popover infrastructure + 5 hero
  anchors.**  Small `bi-info-circle` buttons next to high-value
  anchor points open a Bootstrap popover with a 1-3 sentence
  explanation of what the view/concept means and why it exists,
  plus an optional "Learn more →" link to the public mkdocs
  concept guides.  Phase 23 lays the foundation; subsequent
  sub-sprints (23.1 catalog/table-detail, 23.2 models,
  23.3 branches/audit/home, 23.4 SQL/rail/settings, 23.5 polish +
  doc-link sweep) ship the remaining ~45 anchor points across the
  rest of the UI.
  * `pointlessql/web/help.py` (NEW): typed `HelpEntry` dataclass
    + `HELP` registry with the 5 hero slugs (`runs.what-is-a-run`,
    `runs.what-is-an-operation`, `models.what-is-promotion`,
    `branches.what-is-a-delta-branch`, `lineage.what-is-lineage`).
    `get_help` raises `KeyError` on unknown slugs so template
    typos fail loudly in CI rather than silently rendering an
    empty popover.
  * `frontend/templates/_macros/help_icon.html` (NEW): Jinja macro
    `info('<slug>')` emits a `<button data-bs-toggle="popover"
    data-bs-trigger="focus">` — Bootstrap auto-dismisses on
    outside-click and Escape, no extra JS listener needed.
  * `frontend/js/help_popovers.js` (NEW): idempotent
    `bootstrap.Popover` initialiser bound to `DOMContentLoaded`
    and `htmx:afterSwap` so HTMX-boosted swaps re-wire popovers
    in the new content.
  * `pointlessql/api/main.py`: registers `get_help` as the Jinja
    global `help` once on the shared `_TEMPLATES.env`.
  * `frontend/templates/base.html`: loads the popover initialiser
    immediately after the Bootstrap bundle.
  * 5 page templates (`runs_list.html`, `run_view.html`,
    `model.html`, `branches.html`, `table.html`) thread the macro
    next to their highest-value anchor (page header, Operations
    tab intro, Promotion card-header, Lineage tab intro).
  * `docs/concepts/contextual-help.md` (NEW): short author-facing
    stub explaining how to add a new slug and why click-popover
    won over hover-tooltip.
  * `tests/test_help_registry.py` (NEW): 18 tests covering slug
    naming convention, length caps (title ≤ 60, body ≤ 280 chars),
    `learn_more` URL well-formedness, `KeyError` on missing
    slugs, and the Sprint-23.0 hero-slug invariant.

- **Sprint 22.5 — Polish + launch-ready.**  Phase 22 closes; the
  docs site is launch-ready (built locally, deploy pre-staged
  but inert per the user's "local-only through Phase 22" pick).
  * **Cross-link sweep**: ~117 source-tree warnings eliminated
    via bulk rewrite.  Every walkthrough `../../<path>`
    reference rewrites to a canonical GitHub URL
    (`https://github.com/FloHofstetter/PointlesSQL/blob/main/<path>`);
    the four orphan `../../` repo-root links in
    `notebook-editor.md` resolve to
    `http://127.0.0.1:8000/notebook/editor`.
  * `mkdocs build --strict` now exits 0 with **zero** warnings
    and zero INFO-level link complaints.  `mkdocs.yml` flips
    `strict: false` → `strict: true`;
    `.github/workflows/docs.yml` flips back to `mkdocs build
    --strict` (the 22.0 deferral is over).
  * `docs/integrations/soyuz-catalog.md` (NEW): boundary doc,
    generated-client pin shape, editable escape-hatch,
    bug-fix-at-source rule, sequence diagram.
  * `docs/integrations/hermes-plugin.md` (NEW): install
    procedure, Family A/B/C tool count breakdown (16/4/22),
    conventions, lifecycle hooks, "why httpx not import"
    rationale.
  * `docs/integrations/mlflow.md` (NEW): subprocess + reverse-
    proxy architecture (Mermaid), Phase-21 audit additions list,
    configuration reference, lazy-spawn semantics, "why
    subprocess not import" rationale.
  * `docs/integrations/grafana.md` (NEW): the 8-panel audit
    dashboard, install via overlay, four known gotchas (WAL RW
    mount, unsigned plugin flag, datasource UID, Decimal cast).
  * `docs/changelog.md` (NEW): hand-curated What's-new digest
    covering Phases 19/20/21/22 with pointer to the full
    `CHANGELOG.md` in the repo root.
  * `docs/decisions/0004-public-flip-checklist.md` (NEW): the
    launch-sprint procedure — four-item pre-flight (EUIPO
    trademark / NOTICE / CLA / custom domain) plus three-commit
    flip (workflow / repo visibility / README badge).
  * `mkdocs.yml` nav: 4 integrations pages + ADR-0004 + top-
    level "What's new" entry wired in.

  **Phase 22 is closed.**  Six sub-sprints landed in one
  autonomous session (2026-04-30).  The site has 8 top-level
  sections, ~30 new pages, 38 themed walkthroughs, and a clean
  `--strict` build.  Launch-flip procedure documented in
  ADR-0004; until then, run `uv run mkdocs serve` to read
  locally.

- **Sprint 22.4 — Guides + cookbook.**  The Guides section turns
  into a real task surface with four new high-level recipes plus
  a themed reorganisation of the 38 e2e walkthroughs.
  * `docs/guides/index.md` rewritten as the taxonomic landing
    with three flavours (high-level recipes, operator cookbook,
    e2e walkthroughs) and walkthroughs themed into five sub-
    sections (Getting around / Working with data / Notebooks +
    jobs / Audit + lineage / Agents + ML registry).
  * `docs/guides/agent-bring-up.md` (NEW, 7 steps, ~250 lines):
    wire a brand-new Hermes agent end-to-end in ~30 minutes.
    Chains four e2e walkthroughs (auth + agent-ml-registry +
    audit-reviewer-daily + admin-audit) into one narrative; ends
    with a Mermaid loop showing the audit-trail-feeds-review-bot
    pattern.
  * `docs/guides/operator-cookbook.md` (NEW, 20 recipes):
    Daily / Weekly / Per-agent / Per-incident / Per-model /
    Per-data-issue / Maintenance buckets.  Each recipe is one to
    three sentences plus a deep-link to the long-form walkthrough.
  * `docs/guides/troubleshooting.md` (NEW, ~290 lines): symptom-
    first index across Install + first boot, Auth + sessions,
    Plugin / Hermes, PQL writes, Audit cockpit, Notebooks,
    Storage / Delta, CI / packaging.  References `BUG-NN-NN`
    source-comment markers and the relevant configuration /
    permissions docs.
  * `docs/guides/faq.md` (NEW, ~190 lines): What / Why this and
    not… / How / When / Should I, organised by question shape
    rather than topic.
  * `mkdocs.yml` nav reorganised: four new high-level pages
    above `Jobs`, walkthroughs split into five themed sub-sub-
    sections.

- **Sprint 22.3 — Reference manual.**  The Reference section
  becomes the canonical surface for Python API, REST API, CLI,
  configuration, CloudEvents, and permissions.
  * `docs/reference/python/pql.md` — mkdocstrings directive
    against `pointlessql.pql.pql.PQL` plus a usage preface
    showing all 19 primitives.
  * `docs/reference/python/services.md` — mkdocstrings for five
    service modules: `agent_runs.operations`,
    `agent_runs.training_context`, `audit`, `branch_tags`,
    `mlflow_subprocess`.
  * `docs/reference/python/index.md` — landing distinguishing
    auto-gen (Python class methods) from hand-written (REST +
    CLI).
  * `docs/reference/api.md` — hand-curated top-30 REST reference
    grouped by tag (Auth, Agent runs, PQL writes, Models,
    Lineage, Branches, Audit cockpit, Reviews, Admin API keys,
    Audit sinks, Health/metrics) with tier icons (🍪 🔑 👮 🕵 ⚙)
    per route + canonical error envelope shape.  Auto-generated
    appendix for the remaining ~180 routes deferred to 22.5.
  * `docs/reference/cli.md` — `pointlessql` Typer surface with
    synopsis, options table, output sample, exit codes, "what's
    *not* in the CLI" list.
  * `docs/reference/configuration.md` — every `POINTLESSQL_*`
    env var grouped by `settings.py` sub-model (18 sub-models +
    four special agent-run env vars + `GHCR_PAT`) with rationale
    per setting.
  * `docs/reference/cloudevents.md` — all 12 emitted
    `pointlessql.<domain>.<verb>` event types with payload
    schemas + examples + HMAC-signing convention.
  * `docs/reference/permissions.md` — trust-tier matrix
    (Anonymous → Cookie → API key → +supervisor / +auditor →
    Admin), asymmetric scope ladder, FastAPI dependency mapping,
    plugin family gating, "why no per-table ACLs" rationale.
  * `docs/reference/index.md` — real audience-grouped landing.
  * `mkdocs.yml` nav: full Reference tree wired in (Python API
    sub-section + 5 reference pages).

- **Sprint 22.2 — Architecture + concepts pages.**  The Concepts
  section turns from three reference-style files into a real
  deep-dive surface — architecture, audit trail, lineage, and
  agent supervision each get a dedicated page with Mermaid
  diagrams and full schema breakdowns.
  * `docs/concepts/architecture.md` (NEW, ~250 lines): four
    logical layers (routes / services / PQL / storage), the
    soyuz-catalog boundary with bug-fix-at-source rule, two
    sequence diagrams (`pql.write_table` end-to-end and
    supervisor model promotion), why Python-only beats JVM for
    agent integration, full module map.
  * `docs/concepts/audit-trail.md` (NEW, ~280 lines): the cells /
    operations / queries 3-level model, the
    `agent_run_operations` schema (16 columns including the four
    Phase-21 additions), the `record_operation` forced-audit
    pattern, `params_json` examples per op-name, the rollback
    action loop, explicit boundary against shoreguard's LLM
    Provenance Log.
  * `docs/concepts/lineage.md` (NEW, ~210 lines): four-level
    row → column → value → inference chain with cost/opt-in
    matrix, schema for each table, sqlglot-driven column
    provenance, value-level CDF semantics with PII masking,
    bidirectional model DAG, aggregate fan-in (Phase 15.5),
    rejects table.
  * `docs/concepts/agent-supervision.md` (NEW, ~290 lines):
    Family A/B/C privilege tiers + tool counts, asymmetric scope
    ladder (auditor passes `require_supervisor` but not vice
    versa), wake-gate optimisation that skips the LLM on `ok`
    days, `agent_reviews` schema with `kind` discriminator,
    CloudEvents 1.0 fan-out shape, the four canonical bot
    personas (daily Audit-Reviewer, Compliance-Bot, Incident-
    Responder, Promotion-gate), trust-ladder Mermaid.
  * `docs/concepts/index.md`: real section landing with reading
    order recommendation.
  * `mkdocs.yml` nav: four new concept pages wired in above the
    existing reference-style ones.

- **Sprint 22.1 — Documentation landing + getting started.**  The
  site stops being placeholders and gets a real first impression.
  * `docs/index.md` rewritten as the hero landing — one-liner
    pitch, "What is PointlesSQL?" narrative, Mermaid ecosystem
    diagram (agents → plugin → PointlesSQL → soyuz / Delta), a
    before/after Python snippet that shows the value-prop
    concretely, comparison table against the no-PointlesSQL
    workflow, feature highlights deep-linking into the relevant
    e2e walkthroughs, "Where to next" link grid.
  * `docs/getting-started/quickstart.md` (NEW, 7 steps) — five-
    minute tour from `docker compose up` through "I just read a
    Delta table by name and saw the audit row pop up."  Uses the
    idempotent `scripts/seed-e2e.py` to lay down the `demo.sales`
    + `demo.hr` sample catalog, then walks through `pql.table()`
    + `pql.write_table(source_table_fqn=...)` with the lineage
    DAG showing the result.
  * `docs/getting-started/concepts.md` (NEW, ~250 lines) — the
    ten-minute mental-model read.  Four-layer stack, three-part
    name grammar, PQL primitive surface, agent runs as audit
    container, four-level lineage chain (with Mermaid), Audit
    Cockpit, Family A/B/C supervision tiers, Delta-branching,
    champion/challenger marker grammar, explicit "what
    PointlesSQL is not" section.
  * `mkdocs.yml` nav: Quickstart + Concepts-overview wired into
    Getting Started.
  * `README.md` polish: ASCII architecture block replaced with
    Mermaid (renders inline on GitHub), Documentation pointer
    added above Status, Status + Stack sections trimmed ~30 % to
    hand detail off to the docs site.  Stale `docs/install.md` /
    `docs/jobs.md` / `docs/adr/` references in `README.md` and
    `CLAUDE.md` updated to the post-22.0 layout.
  * Anchor `#docker--ghcr-images-recommended` →
    `#docker-ghcr-images-recommended` in
    `docs/getting-started/installation.md` (mkdocs slugify
    collapses `+` correctly; the old link was broken pre-move
    too).

- **Sprint 22.0 — Documentation site tooling foundation.**  Phase 22
  opens the docs track aimed at shoreguard-fresh's polish bar.  This
  sub-sprint lays the tooling without writing new content.
  * New `mkdocs.yml` (~140 lines) wires mkdocs-material with palette
    toggle, navigation tabs/sections/instant, mkdocstrings (Google
    docstring style), pymdownx superfences with a Mermaid custom-
    fence, and an eight-section `nav:` skeleton that explicitly
    lists all 38 e2e walkthroughs.
  * New `.github/workflows/docs.yml` runs `mkdocs build` on
    `workflow_dispatch` only — no auto-publish, no public URL, per
    the user's "local-only through Phase 22" pick.  The `gh-deploy`
    line is staged but commented out with a TODO marker pointing at
    the launch sprint that flips trigger + repo visibility + README
    badge in one shot.
  * `docs/` re-organised into the mkdocs-material layout: eight
    sections (`getting-started/`, `concepts/`, `guides/`,
    `reference/`, `integrations/`, `development/`, `decisions/`,
    `e2e-walkthroughs/`).  All file moves done with `git mv` so
    blame survives.  Eight new section index pages
    (`index.md`-each) describe what's filled in today and what
    later sub-sprints will add.
  * 14 stale move-induced cross-links fixed across the walkthrough
    folder, `installation.md`, and the hermes-jobs integration
    pages.  Remaining ~117 `mkdocs build` warnings are pre-existing
    source-tree references (the walkthroughs intentionally point at
    `../../frontend/...`, `../../pointlessql/...`) and are Sprint
    22.5's cross-link-sweep job — that's when `--strict` gets
    flipped back on.
  * `site/` added to `.gitignore` so the local build artefact
    doesn't leak into commits.
  * Plan: see
    `.claude/plans/dann-plane-diese-vollst-ndig-stateful-music.md`
    for the full six-sub-sprint phase shape.

- **Sprint 21.8 — Hermes plugin extension (Phase 21 cross-repo
  closure).** Two commits, one logical unit:
  * Server: extends `POST /api/pql/write_table` + `POST /api/pql/merge`
    bodies with optional `source_model_uri`; the write route
    auto-derives `source_table_fqn` from the SELECT when there's
    exactly one ref so the row-edge grain anchors cleanly.
    `PQL.merge()` Python sig grows the same kwarg for symmetry with
    `write_table`.  New `POST /api/pql/training/log` endpoint writes
    a one-shot `record_operation(op_name="train_model",
    training_params_json={"params":..., "metrics":...})` row — the
    HTTP-only equivalent of `pql.training_context()` for httpx
    callers.  Tests: 19 (3 source_model_uri + 7 training-log + 9
    write-routes regression).
  * Plugin (`hermes-plugin-pointlessql`, commit `f01d4e0`): adds 8
    new tools — `pql_list_models`, `pql_get_model`,
    `pql_get_model_predictions`, `pql_get_model_lineage`,
    `pql_get_model_runs`, `pql_get_promotion_history`,
    `pql_log_training_run` (always-on Family A) plus
    `pql_promote_model` (supervisor-gated, Family B).  Extends
    `pql_write_table` + `pql_merge` to accept `source_model_uri`.
    Tool count 34 → 42.  Tests: 19 new (10 model_tools + 5
    log_training + 2 write extension + 2 merge extension); 101/101
    plugin pytest grün.
  * Closes the "Closure pending (user job): Hermes plugin
    extension" item from the 21.0–21.7 close note in
    `project_phase21_closed.md`.

- **Phase 21 closed — ML Registry + Auditable Training.** Eight
  sub-sprints landed in two autonomous sessions on 2026-04-30:
  21.0 (MLflow subprocess + `/mlflow/` proxy + tab), 21.1 (soyuz
  UC-OSS `MODEL` Securable), 21.2 (cross-link `agent_run` ↔ MLflow
  run ↔ ModelVersion), 21.3 (forced autolog), 21.4 (hardware
  fingerprint), 21.5 (Models browse + 5-tab detail + compare),
  21.6 (champion/challenger promotion-hop), 21.7 (inference
  lineage). All eight share the audit-of-intent framing — capture
  enough to answer "wie wurde das Modell trainiert + wo schreibt
  es seine Predictions?" without claiming bit-identical replay.

- **Sprint 21.4 — Hardware/Library Fingerprint.** Adds a nullable
  `agent_run_operations.env_snapshot` Text column (Alembic
  `u1q3r5s7t9v1`) carrying an advisory JSON blob with three
  sub-keys: `python` (version + platform + cpu_count), `packages`
  (top-200 distributions via `importlib.metadata`, capped at
  4 KiB), `gpu` (when torch + CUDA available, per-device name +
  total memory). The snapshot is built once at module-import
  time and cached for the whole PointlesSQL process so subsequent
  `record_operation` calls don't re-walk `importlib.metadata` on
  every write — appropriate for an advisory fingerprint where a
  fork-side package add doesn't justify the per-op cost. The
  Run-detail Operations tab now renders a collapsed "Environment
  fingerprint" accordion under each op row showing the Python
  banner, the GPU list (if any), and the package list as an inner
  collapsed details block. End-to-end best-effort: every sub-step
  is wrapped in try/except and degrades to `None` rather than
  blocking the audit row. Honest reproducibility caveat: the
  blob captures the engineer's declared intent, not provability
  of bitwise reproducibility (CUDA non-determinism, parallel
  dataloaders, atomic-add ordering all leak through). 9 new
  pytest cases.

- **Sprint 21.3 — Forced Autolog (training param/metric capture).**
  New `pql.training_context()` context-manager wraps a training
  block, calls `mlflow.autolog()` for the requested framework hint
  (`"auto"` covers sklearn/xgboost/torch/tf out of the box), opens
  an MLflow run (or nests under an outer one), and at exit copies
  `run.data.params + run.data.metrics` into a JSON blob on
  `agent_run_operations.training_params_json` (new Alembic migration
  `t0p2q4r6s8u0`). The op_name enum gained `train_model`. The
  Run-detail Operations tab now renders a collapsed "Training
  params + metrics" accordion underneath each `train_model` row
  with the snapshot rendered as two side-by-side tables. The
  whole layer is best-effort: works without the mlflow extra
  (audit row still lands, snapshot stays empty), with an
  unreachable tracking server, and when the wrapped training body
  raises (partial autolog state is captured before re-raise so
  the audit trail never loses a training-event). 7 new pytest
  cases. Fail-loud `UnauditedTrainingError` and seed-interceptor
  capture deferred — the best-effort path here covers the
  audit-of-intent goal without blocking training when MLflow
  misbehaves.

- **Sprint 21.7 — Inference-Lineage (model → prediction tables).**
  Closes the second half of the model-lineage graph: when
  `pql.write_table(predictions, target, source_model_uri="models:/
  cat.sch.model/3")` runs, every row-edge it produces carries the
  originating model URI on a new `lineage_row_edges.source_model_uri`
  column (Alembic `s9o1p3r5t7u9`). The model-detail Lineage tab is
  now bidirectional: source-tables upstream with solid green
  `trained_from` edges, prediction-tables downstream with dashed
  blue `inferred_to` edges, plus a new "Prediction tables" card
  underneath the cytoscape view that lists each target FQN with its
  edge count. New `GET /api/models/{full_name}/predictions`
  endpoint reads `lineage_row_edges` directly (no soyuz round-trip,
  cost is O(R · E) on the audit DB rather than O(C · M · V)).
  `aggregate_prediction_tables_for_model` matches by
  `models:/{fqn}/%` so any version of the model contributes. The
  `build_model_lineage_graph` builder gained a `kind` field
  (`"model"` / `"table"` / `"prediction"`) on every node so the
  cytoscape style branches three ways. 10 new pytest cases.
  Drift alerts and a dedicated `pql.predict` helper are deferred
  to Phase 22+.

- **Sprint 21.6 — Champion/Challenger Promotion-Hop.** Operators (or
  supervisor-scoped agents) can now promote a `READY` model version
  to *champion* through `POST /api/models/{full_name}/promote`. The
  swap writes a `_pql_promotion` JSON marker into the registered
  model's `comment` (mirrors the Phase-21.2 `_pql_link` convention so
  the read-side parsers stay independent), inserts an `AgentReview`
  row with `kind="model_promotion"` so the Phase-19 cockpit fan-out
  can notify subscribers, and emits a `pointlessql.model.promoted`
  CloudEvent envelope. The 21.5 Permissions stub on
  `/models/{full_name}` is replaced by a Promotion tab: current
  champion card, per-version `[Promote]` button, mandatory-reason
  modal, and a collapsed promotion-history list. Champion badge
  also renders on the Versions tab. Supervisor or admin scope
  required (mirrors the Phase 13.11 ladder). New Alembic migration
  `r8n0p2q4s6u8` adds a non-null `kind` column to `agent_reviews`
  with `audit_review` as the default for backfill. New service
  module `pointlessql/services/model_promotion.py` carries the
  marker round-trip, current-champion resolver (falls back to
  highest-numbered READY version when no marker exists),
  `promote_version` service, history aggregator, and CloudEvent
  builder. `ModelsMixin` gains `update_registered_model`. First-
  class soyuz aliases deferred — the marker convention gives
  equivalent semantics without a soyuz schema bump and a future
  one-shot script can re-emit markers as real catalog tags once
  soyuz adds them. 17 new pytest cases.

- **Sprint 21.5 — registered-models browse surface.** Models now
  appear in the catalog tree per schema (alongside tables) and have
  a top-level `/models` index page in the icon rail. Each registered
  model has a detail page at `/models/{full_name}` with five tabs
  (Overview, Versions, Lineage, MLflow, Permissions); the Versions
  tab pulls params/metrics/tags from the linked MLflow run via
  `MlflowClient.get_run`, the Lineage tab renders a focused
  cytoscape DAG showing the model node + the source tables consumed
  by any Hermes-agent-run linked to a version of the model. A
  side-by-side compare view at `/models/{full_name}/compare?v1=N&v2=M`
  highlights metric deltas with a `lower-better`/`higher-better`
  classification heuristic and lists added/removed/changed params
  and tags. Anonymous access is gated by the existing auth
  middleware. New `ModelsMixin` on `UnityCatalogClient` exposes the
  four typed soyuz model RPCs the routes depend on
  (`list_registered_models`, `get_registered_model`,
  `list_model_versions`, `get_model_version`). The browser
  walkthrough at `docs/e2e-walkthroughs/models-tab.md` replays the
  full flow.

### Closed — Phase 21 audit-foundation: 21.0 + 21.1 + 21.2 (2026-04-30)

Vertical slice "audit-foundation for ML" landed in one autonomous
session: a Hermes-driven training run now records its MLflow context
into PointlesSQL's audit trail, the soyuz-catalog model-version row,
and a single-call cross-link aggregator. Three sub-sprints, install
`pip install pointlessql[ml]` to opt in.

* **Sprint 21.1 — soyuz UC-OSS MODEL Securable wire-compat for
  MLflow.** Soyuz commit `248f73f` (tag `v0.3.0rc1` local).
  Closes the wire-compat gap so MLflow's UC-OSS client
  (`mlflow.set_registry_uri("uc:http://...")`) can roundtrip:
  create model → create version (PENDING) → upload → finalize →
  READY → get/list/update/delete. Three additive endpoints
  (`finalizeModelVersion`, `temporary-model-version-credentials`)
  + status-state-machine fix + schema accommodation for the proto's
  URL-redundant body fields. Aliases stay out-of-scope — UC-OSS
  proto has no alias RPCs (only the Databricks variant).
* **Sprint 21.0 — MLflow Tracking subprocess + UI tab + reverse-proxy.**
  `MLflowSubprocess` lifecycle manager (HTTP health-check, PID file,
  graceful SIGTERM → SIGKILL) wired into the FastAPI `lifespan`.
  `/ml` HTML page mounts an iframe at `/mlflow/` which is served
  by a `httpx`-based reverse-proxy that injects the authenticated
  user as `X-MLflow-User` so the soyuz-side audit trail can
  correlate. New `MLflowSettings` (`POINTLESSQL_MLFLOW_*`) with
  optional URI overrides. Tab branded "ML" in the icon-rail.
* **Sprint 21.2 — Cross-link agent_run ↔ MLflow ↔ MODEL.**  Alembic
  `q7m9o1p3r5t7` adds `mlflow_run_id` columns to `agent_runs`
  and `agent_run_operations`. The op-recorder hot path sniffs
  `mlflow.active_run()` and stamps the run-id on both rows so a
  single SQL join answers "how was this model trained?". New
  `GET /api/runs/{id}/ml-context` aggregator returns the three-way
  join of agent-run + MLflow run + soyuz model-versions. Soyuz
  model-versions are tagged via a JSON marker in the `comment`
  field as a bridge until soyuz Sprint-25 tags-on-models lands.
  New CloudEvents type `pointlessql.mlflow.linked`.

22 new unit/integration tests + 4 live-soyuz smoke tests
(`test_mlflow_uc_oss_smoke.py`). Hermes-plugin `pql_mlflow_link_model`
tool deferred — auto-link via the recorder hook covers the core
flow; explicit linkage tool can land in a polish sprint once we
see the agent-pattern that needs it.

### Closed — Phase 17 polish: 17.3.1 + 17.5.1 (2026-04-29)

Two queued follow-ups land in one autonomous session.  17.6
(lineage trace sub-panes) stays queued — the ROADMAP-side
"defer until usage data" decision still holds.

* **17.3.1 — Lazy-load cytoscape on the Graph sub-tab.**  The
  three jsdelivr scripts (cytoscape ~280 KB + dagre ~50 KB +
  adapter) no longer ship on every ``/runs/{id}`` cold load.
  ``loadCytoscapeOnce()`` injects them on demand the first
  time the user activates the Graph sub-tab, gated on
  Bootstrap's ``shown.bs.tab``.  Promise-cached at module
  level; fail-soft on CDN block.
* **17.5.1 — Server-side tree search + DB-backed recents.**
  New ``recent_tables`` table (Alembic ``p6l8n0q3s5u7``)
  mirrors the Sprint-17.5 localStorage block in
  PointlesSQL's metadata DB so recents survive across
  devices.  ``GET /api/tree/search?q=`` walks the soyuz tree
  once and filters in-memory (capped@50) — significantly
  cheaper than shipping the full tree to a >1000-table
  browser.  Sidebar keeps localStorage as first-paint +
  no-auth fallback and overrides asynchronously for
  logged-in users.

Tests: 7 new (recents service).  Static gates clean.

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

### Closed — Phase 17: UI Overhaul (2026-04-29)

Five sub-sprints in one autonomous session, closing the
post-Phase-15.7 honest-UX-assessment punch list (top navbar
overloaded, run-detail tabs creaking, lineage UI linear,
table-detail vertical wall, catalog browser scroll-wall).

What's now in place:

- **Two-column sidebar** (Sprint 17.1).  60 px icon-rail with
  one icon per top-level section + 240 px contextual panel
  that swaps based on `active_section`.  Top navbar drops the
  inline nav row (only brand + Cmd+K + user menu remain).
  Mobile drawer keeps `nav_links.html` as fallback.
- **Run-detail tab consolidation** (Sprint 17.2).  10 flat
  tabs → 4 top-tabs (Overview / Operations / Lineage / Audit)
  with nav-pill sub-tabs.  Rollback card moves into a "Danger
  zone" inside Operations; `unattributed_writes` lifts out of
  Operations into an External-writes sub-tab in Audit; an
  inline hash-listener keeps Sprint-18.1 cross-axis deeplinks
  working.
- **Lineage-DAG view** (Sprint 17.3).  New
  `services/lineage_graph_builder.py` + `GET
  /api/runs/{run_id}/graph` join `lineage_row_edges` and
  `lineage_column_map` into a flat `{nodes, edges}` payload.
  New Lineage / Graph sub-tab embeds a cytoscape.js + dagre
  canvas with click-a-column-highlights-upstream-and-
  downstream behaviour.  CDN-loaded, scoped to the run-detail
  page only.
- **Table-detail tab refactor** (Sprint 17.4).  `pages/
  table.html` collapses from a long vertical card stack into
  six tabs (Overview / Preview / Columns / Lineage / Tags /
  Permissions); card content + Alpine factories preserved
  verbatim.
- **Catalog-Browser search + recents** (Sprint 17.5).
  Debounced filter input above the catalog tree + a "Recent
  tables" block surfacing the last five
  `catalog.schema.table` visits via
  `localStorage['pql.recentTables']`.

Numbers:

- 5 sub-sprint commits + this closing commit on PointlesSQL.
- 1 new backend module
  (`services/lineage_graph_builder.py`).
- 1 new public API endpoint
  (`GET /api/runs/{run_id}/graph`).
- 5 new template partials / files (`icon_rail.html`,
  `context_panel.html`, `user_menu.html` + CSS files for
  icon-rail and context-panel +
  `frontend/js/components/lineage_dag.js`).
- 0 new database tables / Alembic migrations — the
  RecentTable persistence lane stays in localStorage; a
  DB-backed sibling is parked as a 17.5.1 follow-up.

What's deferred:

- `/api/tree/search` server-side endpoint for >1000-table
  tenants (Sprint 17.5.1).
- Lazy-load of the cytoscape bundle on Lineage-Graph
  sub-tab click (Sprint 17.3.1) — today the bundle ships
  with every run-detail page, ~280 KB cold-cache.
- Sub-tab content for the Lineage top-pane beyond Summary +
  Graph (Row trace / Column trace / Value changes are
  separate full pages today; making them sub-panes would be
  a Phase-17.6 follow-up if the page-flip overhead becomes
  painful).

### Added — Sprint 17.5: Catalog-Browser search + recents (2026-04-29)

`components/sidebar.html` gains a debounced filter input above
the catalog tree and a "Recent tables" block surfacing the
last five `catalog.schema.table` visits.

Frontend:

- New `query` + `recents` reactive state on the existing
  Alpine `catalogTree()` factory.
- Six new helpers (`tableVisible`, `schemaVisible`,
  `catalogVisible`, `isCatalogExpanded`, `isSchemaExpanded`,
  `filteredEmpty`) drive the filter — case-insensitive
  substring match, partial-match branches force-expand, no
  match shows a friendly empty-state.
- Recent tables come from a localStorage key
  (`pql.recentTables`) written by a small `base.html`
  inline script (sibling of the Sprint-32 recent-catalogs
  writer); the script also dispatches a
  `pql:recent-tables-changed` CustomEvent so an open
  sidebar updates without a hard reload.
- Recents are FQN-deduped, capped at 5, with a "Clear"
  button that wipes the list.

Backend: no changes — the existing `/api/tree` payload
already returns the catalog → schema → table hierarchy the
filter walks.

Deferred to Sprint 17.5.1: server-side
`/api/tree/search?q=` for tenants with >1000 tables, and a
DB-backed `RecentTable(user_id, table_full_name,
last_visited_at)` model for cross-device recents.

### Added — Sprint 17.4: Table-detail tab refactor (2026-04-29)

`pages/table.html` collapses from a single long vertical stack
into six top-level tabs.  No new functionality — this is a pure
layout reorganisation.

| Tab          | Contents                                          |
|--------------|---------------------------------------------------|
| Overview     | Metadata + Properties + PQL Snippet (copy)        |
| Preview      | `tablePreview()` Alpine card with version select  |
| Columns      | Columns table (+existing ≥20-col search) + Sprint-56 stats |
| Lineage      | `components/lineage_card.html` upstream/downstream graph |
| Tags         | `components/tags_editor.html`                     |
| Permissions  | `components/permissions_card.html` (effective-permissions toggle) |

What stayed:

- All Alpine factories (`tablePreview`, `tableStats`) and their
  inline `<script>` blocks — same `init()`, same fetch path,
  same Chart.js sparklines, same Sprint-20.3 version select.
- The Sprint-15.6 column-lineage badges next to each column
  name.
- The Sprint-30 effective-permissions toggle inside the
  Permissions card.
- Header (h1 + breadcrumbs), error alert path, and the
  `{% block extra_js %}` carrying `tableStats` continue to
  render unchanged.

What's deferred to a follow-up:

- Always-on column filter for any column count (today's
  threshold is ≥20).  The plan mentioned 50+ as the trigger;
  the existing 20+ behaviour is more aggressive and works
  fine, so no change for 17.4.
- Row history / sync history sub-tab — not currently surfaced
  on this page; would need a new endpoint to be useful.

### Added — Sprint 17.3: Lineage-DAG view (2026-04-29)

Third landing of Phase 17.  Adds a clickable graph view of the
combined row + column lineage for one run, sitting next to the
Sprint-17.2 Summary table inside the Lineage top-pane.

Backend:

- New `pointlessql/services/lineage_graph_builder.py` joins
  `lineage_row_edges` + `lineage_column_map` per `run_id`
  (and optional `op_id`) into a flat `{nodes, edges}` payload.
  One node per distinct table; one edge per
  `(source_table, target_table, op_id)` triple, with
  `transform_kinds`, `column_pairs`, and `row_edge_count`
  attached.
- New route `GET /api/runs/{run_id}/graph?op_id=...` in
  `runs_routes.py`, gated by `require_supervisor` (auditor or
  admin) — same scope ladder as the Sprint-19.1 audit-axis
  routes.

Frontend:

- New Lineage sub-tabs: Summary (the existing per-op edge
  table) and Graph (cytoscape canvas).  The Summary sub-pane
  keeps `id="tab-lineage"` so existing Sprint-18.1 op-row
  badges that link to `?op_id=N#tab-lineage` continue to land
  on the Summary view.
- New `frontend/js/components/lineage_dag.js` Alpine factory
  registered via `bootstrap.js`.  Loads the graph JSON, hands
  it to cytoscape with the dagre layout, and wires three
  highlight modes: node click (incident edges), edge click
  (side-panel column pairs), column click (every edge that
  touches that column — upstream + downstream simultaneously).
- cytoscape (3.30), dagre (0.8), cytoscape-dagre (2.5) from
  jsdelivr, loaded via a new `extra_js` block in
  `run_view.html` so the ~280 KB bundle hits only the
  run-detail page, not every authenticated route.
- Side-panel column-pair list is scrollable (max-height 280
  px) so wide aggregations stay tidy.

Behaviour:

- Empty-state when the run has no row edges or column-map
  rows: the canvas stays hidden and a friendly alert points
  at the PQL primitives that emit edges.
- `op_id` query parameter is honoured: when the user lands
  via the Sprint-18.1 cross-axis filter chip, the graph
  filters to that single op automatically.
- The `pre`-Sprint-15.6 case of "row edges but no column
  map" keeps surfacing as a node-to-node edge (annotated
  with the row count, no transform_kinds), so old runs are
  still rendered.

### Added — Sprint 17.2: Run-detail tab consolidation (2026-04-29)

`/runs/{id}` collapses from a single nav-tabs strip with 10 tabs
in one row into 4 top-level tabs with 11 nav-pill sub-tabs
distributed across them.  No backend or API changes — pure
template + Alpine surgery.

The new structure:

| Top-tab    | Sub-tabs                                          |
|------------|---------------------------------------------------|
| Overview   | Source · Cells · Events                           |
| Operations | Operations · Rejects · Queries · UC mutations     |
| Lineage    | Lineage summary (Sprint 17.3 will split into Row / Column / Value / Graph) |
| Audit      | Tool calls · Audit log · External writes (NEW)    |

What changed in `frontend/templates/pages/run_view.html`:

- Single `<ul class="nav nav-tabs">` strip + flat tab-content
  → 4-button top-tab strip + 4 top-panes, each carrying its own
  `<ul class="nav nav-pills">` for sub-tabs.
- The `unattributed_writes` alert that Sprint 13.7.5 surfaced
  inside the Operations tab is now its own *External writes*
  sub-pane in the Audit top-tab, with a friendly empty-state
  when no unattributed writes exist (so the sub-tab stays
  coherent when toggled).  The badge on the External-writes
  sub-tab carries the count.
- The Sprint 16.3 admin-only **Rollback** card moves from above
  the tab strip to the bottom of the Operations top-pane as a
  "Danger zone" card.  Same `rollbackPanel()` Alpine factory,
  same modal, same submit → /api/runs/{id}/rollback POST flow;
  only the location moves.
- A small inline hash-listener at the bottom of the template
  walks up the DOM from the targeted sub-pane and activates the
  parent top-tab too, so existing deeplinks like
  `/runs/{id}?op_id=N#tab-lineage` (Sprint 18.1 cross-axis
  drilldowns) keep landing on a visible pane.  Stale hashes
  fall back to the default sub-pane in Overview.
- Sprint 18.1's `op_id`-filter chip + Sprint 18.5's anomaly
  chip + the run-metadata / medallion-conformance / approval
  cards stay above the top-tab strip — outside the tab
  structure on purpose, so they remain visible regardless of
  which top-tab is active.

The 10 sub-pane IDs (`tab-cells`, `tab-ops`, …) and their
existing internal contents are preserved verbatim — only the
wrapping changes.  Sprint 18.1 cross-axis op-row badges that
link to `#tab-lineage` and `#tab-ops` therefore keep working
without edit.

### Added — Sprint 17.1: Two-column sidebar (2026-04-29)

First landing of Phase 17 (UI Overhaul).  The horizontal nav row
that crammed nine items into the topbar is replaced by a 60 px
icon-rail on the left and a 240 px contextual panel next to it.

What changed:

- New `frontend/templates/components/icon_rail.html` —
  vertical 60 px strip with one icon per top-level section
  (Federation / Runs / SQL / Workspace / Jobs / Alerts /
  Volumes / Dashboards + an admin-only Admin entry in the
  footer).  Active item is derived from a new `active_section`
  computed in `base.html` from the existing `active_page`.
- New `frontend/templates/components/context_panel.html` —
  240 px panel that dispatches by `active_section`: Federation
  reuses the existing catalog-tree (`components/sidebar.html`),
  Dashboards reuses the existing dashboards-tree, the seven
  remaining sections render a small static link list with a
  Cmd+K hint where useful.
- New `frontend/templates/components/user_menu.html` — current-
  user dropdown extracted out of `nav_links.html` so it can
  render standalone in the topbar (right side) at >= md.
- `frontend/templates/components/nav_links.html` is now
  drawer-only (< md, 768 px); the topbar drops its inline nav
  block.
- Mobile (< md) keeps the existing offcanvas drawer chrome but
  now carries: section panel + nav-links list + user menu, so
  phones have a single navigation surface (matches the new
  desktop layout in inverse order).
- New CSS `frontend/css/components/icon_rail.css` +
  `frontend/css/components/context_panel.css`; design tokens
  `--pql-icon-rail-width` (60 px) and `--pql-context-panel-width`
  (240 px) in `base.css`; `.pql-shell` grid is now
  `60 px 240 px 1fr` at >= md.

What stayed:

- Cmd+K command palette (Sprint 31/92) is unchanged.
- Notebook iframe page still uses `hide_sidebar=True` and
  fills the viewport — no rail or panel rendered.
- Login / register / error pages also use `hide_sidebar=True`,
  so the new chrome is never shown unauthenticated.
- The catalog-tree `<aside>` continues to ship its own
  `.border-end`; the new column also gets a wrapper border on
  `.pql-sidebar-shell` at >= md so non-tree section panels
  read as a column too.

### Closed — Phase 20: Forensics + Retention (2026-04-29)

Five sub-sprints landed in one autonomous session, closing the
"forensics + retention" governance pass that the post-Phase-15.7
strategy-conversation flagged as the orthogonal gap to the
already-shipped audit capture / display / query stack.

What's now in place:

- **Audit-stream forwarder** (Sprint 20.0). Six governance event
  types (`external_write.detected`, `cost_gate.denied`,
  `audit_export.issued`, `policy.violated`, `lineage.pruned`,
  `audit_sink.test`) fan out to admin-configured sinks of three
  types — webhook (HMAC), S3 (SigV4 PUT, supports
  MinIO/Cloudflare R2 via `endpoint_url`), AWS CloudTrail
  (PutAuditEvents).  Off by default; admin CRUD at
  `/api/admin/audit-sinks`.
- **Write-time PII redaction** (Sprint 20.1). `pii_mode` defaults
  to `hash_only`: any column whose name matches a built-in PII
  pattern (`email`, `phone`, `ssn`, `credit_card`, `iban`,
  `passport`, `first_name`, `address`, `birth`, +
  contains-`pii`) gets HMAC-SHA256-hashed at `record_value_changes`
  time.  `system_keys` table holds the auto-generated 32-byte
  secret.  `redact_with_audit_log` mode also appends one
  `audit_log` row per masked per-op call.
- **Lineage retention** (Sprint 20.2). Per-axis TTLs on the four
  lineage tables (defaults: row_edges 365, row_rejects 365,
  value_changes 730, column_map none).  Lifespan task ticks every
  24h; each prune appends an `audit_log` row + fires a
  `pointlessql.lineage.pruned` governance CloudEvent.
- **Time-travel value queries in UI** (Sprint 20.3).
  `pql.table_at_version` / `pql.table_at_timestamp`; routes
  `/api/tables/{fqn}/versions`,
  `/api/tables/{fqn}/preview-at-version`,
  `/api/lineage/row-at-version` (admin-gated); table-detail
  preview "View at:" select; row-trace admin-only version-input
  card.  `query_history.read_kind` enum extends with
  `pql_table_at_version`.
- **Cross-tool lineage facet ingest** (Sprint 20.4). PointlesSQL
  emits `columnLineage` + `valueChange` facets (the latter is a
  PointlesSQL extension, namespaced under `_producer`); soyuz
  ingests both via two new ORM models (`LineageColumnEdge`,
  `LineageValueChange`), Alembic `016`, expanded `ingest_event`
  walker, response counters
  (`accepted_column_edges`, `accepted_value_changes`).  PII
  values cross the wire pre-redacted.

Numbers:

- 5 commits on PointlesSQL: `1072170`, `b715f3f`, `ca07013`,
  `f06ba97`, `8050c2f` + this closing commit.
- 1 commit on soyuz-catalog: `2d73c87` (locally tagged
  `v0.2.0rc4`, push pending).
- 7 new tables / migrations across both repos
  (`audit_sinks`, `governance_events`, `system_keys`,
  `lineage_column_edges`, `lineage_value_changes` +
  PointlesSQL Alembic `m3h4i5j6k7l8` / `n4i5j6k7l8m9` +
  soyuz Alembic `016`).
- 3 new admin/operational walkthroughs
  (`docs/e2e-walkthroughs/audit-sinks.md`,
  `docs/e2e-walkthroughs/time-travel.md`,
  `docs/audit/pii-modes.md`).
- ~40 new public API surface points (admin CRUD + per-event-
  type emission helpers + 3 time-travel routes).

What's deliberately out of scope:

- Admin HTML page for audit-sinks — JSON-only routes shipped;
  page is a Phase-20.6+ follow-up.
- Soyuz tag-driven PII detection at write time — would dominate
  per-write cost; the Phase-18 render-time masking still gates
  tagged-but-non-pattern columns at the API surface.
- Foreign-producer `valueChange` schema validation — soyuz
  documents the facet as PointlesSQL-defined and ingests
  permissively.
- Pushing the `v0.2.0rc3` / `v0.2.0rc4` soyuz tags — same
  posture as the Phase-14 push that's still pending; install
  works because both response-shape extensions are additive.

### Added — Sprint 20.4: Soyuz columnLineage + valueChange (2026-04-29)

Cross-tool sibling to the PointlesSQL-only column / value lineage
stack.  Two OpenLineage facets now flow from PointlesSQL emission
into soyuz-side persistence:

- `services/soyuz_lineage.emit_event_sync` accepts optional
  `column_edges` + `value_changes` lists.  Builds
  `outputs[*].facets.columnLineage` (spec 1.x) and
  `outputs[*].facets.valueChange` (PointlesSQL extension under
  `_producer = "https://github.com/FloHofstetter/pointlessql"`).
- `operations._emit_lineage_after_commit` threads the recorder's
  `pending_column_edges` + `pending_value_changes` through so every
  merge / declarative write that already populates
  `LineageColumnMap` + `LineageValueChange` (Phases 15.6 + 15.7)
  automatically surfaces in soyuz too.
- PII safety: PointlesSQL emits **already-redacted** values when
  `pii_mode != store_clear` (Sprint 20.1's default `hash_only`
  rewrites `old_value` / `new_value` to a 16-hex HMAC), so soyuz
  never sees cleartext.

Soyuz changes (commit pending push, locally tagged `v0.2.0rc4`):
two new ORM models (`LineageColumnEdge`, `LineageValueChange`),
Alembic `016`, `ingest_event` facet walker, response counters
(`accepted_column_edges`, `accepted_value_changes`).  See
`../soyuz-catalog/CHANGELOG.md` for the full soyuz-side notes.

### Added — Sprint 20.3: Time-travel value queries in UI (2026-04-29)

Surfaces the version arithmetic
`agent_run_operations.delta_version_after` already captures.

- New `pql.table_at_version(fqn, n)` + `pql.table_at_timestamp`
  helpers wrap `DeltaTable.load_as_version`.  Each call writes a
  `query_history` row with `read_kind="pql_table_at_version"`.
- New `api/time_travel_routes.py` exposes three read-only routes:
  `GET /api/tables/{fqn}/versions` (history joined with
  `agent_run_operations` so each version names the originating
  run when known), `GET /api/tables/{fqn}/preview-at-version`
  (paged rows up to 200), `GET /api/lineage/row-at-version`
  (admin-gated single-row lookup keyed on `_lineage_row_id`).
- Table-detail preview card gains a "View at:" select.
  Row-trace page gains an admin-only "View this row at version"
  card.  Both consume the new API.
- `query_history.read_kind` enum extends with
  `pql_table_at_version` so `/queries` surfaces time-travel reads
  alongside ordinary `pql.table()` calls.
- Browser-replay playbook in `docs/e2e-walkthroughs/time-travel.md`.

### Added — Sprint 20.2: Lineage retention TTLs (2026-04-29)

Bounded-growth invariant on the four lineage tables.  Each axis
gets its own retention threshold; the pruner runs as a lifespan
task next to the existing audit-cleanup loop.

- New `services/lineage_pruner.py`: `prune_once` (sync DB I/O) +
  `prune_once_async` (async wrapper that fires one
  `pointlessql.lineage.pruned` governance CloudEvent per axis
  after the DB commit).  Each per-axis prune appends an
  `audit_log` row (`actor_role=system`, `action=lineage_prune`,
  `target=lineage_<axis>`, `detail={deleted, cutoff,
  threshold_days}`).
- `LineageRetentionSettings` (env prefix
  `POINTLESSQL_AUDIT_LINEAGE_RETENTION_*`) with per-axis
  `*_days` thresholds.  `None` / `0` skips the axis.  Defaults:
  row_edges 365, row_rejects 365, value_changes 730,
  column_map `None`.
- `_lineage_pruner_loop` lifespan task ticks every
  `audit.cleanup_interval_seconds` (default 24h).  Active only
  when at least one axis has a positive threshold.
- Sprint 20.0's `EVENT_TYPE_LINEAGE_PRUNED` finds its first
  emitter.  Audit-stream sinks see prunes alongside external-
  write detections and cost-gate denials.

### Added — Sprint 20.1: PII detection + masking write-hook (2026-04-29)

Sprint 20.1 closes the cleartext-at-rest gap on
`lineage_value_changes`.  Render-time masking from Phase 18.2 only
protected the API surface; this sprint rewrites the row before it
hits SQLite when `pii_mode` is anything other than `store_clear`.

- New `system_keys` table (Alembic `n4i5j6k7l8m9`) for the lazy
  install-scoped PII hash secret.  First-write generates a
  32-byte URL-safe random token.
- `services/pii_redactor.py` ships pattern-based PII detection
  (regex over column names — covers `email`, `phone`, `ssn`,
  `credit_card`, `iban`, `passport`, `first_name`, `last_name`,
  `address`, `birth`, plus generic `pii` substring), HMAC-SHA256
  hashing (16 hex chars, equality-joinable), and the literal
  `<redacted>` placeholder.
- `record_value_changes` accepts `pii_mode` + `pii_hash_secret`
  parameters.  `store_clear` keeps pre-20.1 behaviour;
  `hash_only` (the new default) rewrites old/new values to a
  16-hex HMAC for any pattern-matched column;
  `redact_with_audit_log` substitutes the literal `<redacted>`
  and appends one `audit_log` row per masked per-op call.
- `operations._record_value_changes_after_commit` resolves
  `Settings` and forwards the mode + secret automatically;
  primitives stay agnostic.
- Soyuz tag-driven PII detection stays out of the sync write path
  (would dominate per-write cost).  The Phase-18 render-time
  masking still gates tagged-but-non-pattern columns at the API.
- `docs/audit/pii-modes.md` documents the three modes, secret
  bootstrap, migration impact, and the verification recipe.
- Existing `lineage_value_changes` rows are NOT rewritten — soft
  transition.  Historical cleartext stays readable to admins via
  render-time masking; new writes hash.

### Added — Sprint 20.0: Audit-Stream forwarder (2026-04-29)

Phase 20 opens with the audit-stream forwarder: a settings-driven,
plug-in-typed CloudEvents fan-out that mirrors the existing webhook
dispatcher's HMAC + retry contract for new sink types.

- New `audit_sinks` table (id, name, type, config_json,
  is_active, event_types_json, created_at) plus FK-free
  `governance_events` table for non-run-scoped CloudEvents.
  Alembic `m3h4i5j6k7l8`.
- Three sink types ship: `webhook` (reuses the saved-query alert
  dispatcher), `s3` (httpx + minimal SigV4 signer at
  `services/aws_sigv4.py`, works against MinIO / R2 by setting
  `endpoint_url`), `aws_cloudtrail` (PutAuditEvents to the
  CloudTrail Data Service). SigV4 implementation verified against
  the AWS reference test vector.
- Five governance event types fire from the existing audit
  surfaces: `pointlessql.external_write.detected` (scanner),
  `cost_gate.denied` (`/api/sql/explain` when `needs_approval`
  flips true), `audit_export.issued` (`/admin/audit/export`),
  `policy.violated` (free hook for future), `lineage.pruned`
  (paired with Sprint 20.2). Run-lifecycle events stay on the
  Phase-13 `agent_run_events` path; admins flip
  `POINTLESSQL_AUDIT_STREAM_MIRROR_LIFECYCLE_TO_SINKS=1` to fan
  those into `audit_sinks` too.
- Admin CRUD at `/api/admin/audit-sinks` (GET/POST/PATCH/DELETE)
  with sensitive-key redaction on read-back, a `POST .../{id}/test`
  synthetic-envelope endpoint, and a `GET .../recent-events`
  tail of the last 50 governance rows.
- Off by default — `POINTLESSQL_AUDIT_STREAM_ENABLED=0`. The
  governance row always persists (durability matters); only the
  outbound POST is gated.
- Operational runbook in `docs/e2e-walkthroughs/audit-sinks.md`
  (curl-driven, no browser). Admin HTML page deferred to the
  Phase-20 close-memo bug-hunt sweep.

### Closed — Phase 19: Audit-Reviewer Agent + Grafana (2026-04-29)

Six sub-sprints landed across two days, closing the original
"agents reviewing agents" thesis from the Phase-19 sketch.  The
audit lake captured by Phase 14-15 + the cockpit surface from
Phase 18 are now driven by three real personas, plus the Grafana
glance-trust dashboard that was Phase 19's quick-win opener.

Personas served:

- **Daily Audit-Reviewer-Agent** (Sprint 19.2.0/1/2) — Hermes cron
  at 06:00 UTC; wake-gate skips the LLM round-trip on clean days,
  on `warn`/`critical` the agent drafts Markdown, posts via
  `pql_post_audit_review` (PointlesSQL is the source of truth),
  PointlesSQL fans the CloudEvent out to admin-configured webhook
  destinations, Hermes also delivers via its own platform adapters.
  Cockpit "Latest review" card on `/` + `/agent-reviews/{id}`
  detail page.
- **Compliance-Bot** (Sprint 19.3) — read-only Hermes one-shot
  triggered by Slack/Matrix DM. Answers ad-hoc questions with the
  four-block Question/Answer/How/Caveats skeleton. Five hard
  prompt constraints (no writes, mandatory masking, no API-key
  echo, time-window pinning, refuse-and-escalate on remediation
  asks). New `/api/audit/principal-summary` route + matching
  plugin tool fill the runs-by-principal enumeration gap.
- **Incident-Responder** (Sprint 19.4) — multi-turn drill-down
  for "was hat Run X kaputt gemacht?". Takes a `run_id` up
  front, walks failing op → rejects → external-write neighbours.
  Pure prompt composition — no new server endpoints. Synthetic
  broken-run fixture (`scripts/seed-broken-run.py`) for replays.

Numbers:

- Plugin grew 29 → 32 tools (`pql_post_audit_review`,
  `pql_get_latest_review`, `pql_principal_summary`).
- Two new tables (`agent_reviews`, `review_destinations`,
  Alembic `l2g3a4b5c6d7`).
- Two new admin-gated CRUD routes for review destinations + four
  new auditor-gated agent-review routes (POST + latest + detail +
  principal-summary).
- One Hermes pre-run script (`scripts/audit-wake-gate.py`).
- Three new walkthroughs in `docs/e2e-walkthroughs/`
  (audit-reviewer-daily, compliance-bot, incident-responder)
  + three Hermes job manifests in `docs/hermes-jobs/`.
- Six commits (`57ec67c`, `8d6de75`, `fe5d26d`, `4735b76`,
  `51659b6`, plus the closing commit) against PointlesSQL; two
  commits (`ac57fed`, `14ad3ea`) against `hermes-plugin-pointlessql`.

What's deliberately out of scope:

- Conversation memory for the chat personas — that's Hermes' job;
  see the limitations sections in
  `docs/e2e-walkthroughs/{compliance-bot,incident-responder}.md`.
- "Auto-fix" / "draft remediation PR" personas. The read-only
  posture is the design intent — Sprint 19.5+ could add a
  write-shaped persona, but that's a different conversation.
- Per-job env overlays in Hermes. All cron jobs in an install
  share `~/.hermes/.env`; if you need separate keys per job, add
  Hermes-side feature support first.

### Added — Sprint 19.4: Incident-Responder persona (2026-04-29)

Third Phase-19 persona: multi-turn Hermes flow for "was hat Run X
kaputt gemacht?".  Takes a ``run_id`` up front (typically pasted from
a banner alert / deploy log), walks down to root cause across the
existing per-run audit axes, never recommends a write.

- **No new server endpoints.**  This sprint is purely prompt
  composition + a fixture: every tool the responder uses landed in
  Sprint 19.1.  The plugin tool-count is unchanged at 32.

- **System prompt + manifest** at
  ``docs/hermes-jobs/incident-responder.{md,json}``.  Three-block
  answer skeleton (Finding / Evidence / Next) optimised for
  follow-up questions.  Five hard constraints: stay focused on
  one run, never recommend a write, mention rollback as an option
  exactly once per conversation, surface external-write neighbours
  proactively, be terse (operator is on call).

- **Synthetic broken-run fixture** at
  ``scripts/seed-broken-run.py``.  Inserts one
  :class:`AgentRun` with status ``failed``, three
  :class:`AgentRunOperation` rows (``autoload`` ok / ``merge``
  errored on schema mismatch / ``write_table`` accumulated rejects),
  ~50 :class:`LineageRowReject` rows, and 2
  :class:`UnattributedWrite` rows landing in the same window.  Plus
  one extra ``succeeded`` run for the same principal so per-
  principal aggregations have a non-trivial denominator.  Prints
  the run_id for use in the chat prompt.

- **e2e walkthrough** at
  ``docs/e2e-walkthroughs/incident-responder.md`` exercises three
  drill-down patterns (failing op, op-3 rejects, proactive
  external-write callout) and four safety properties (refuses
  writes, rollback mentioned at most once, masking on
  value-changes, audit-of-audit history matches the tool surface).

### Added — Sprint 19.3: Compliance-Bot (ad-hoc Slack/chat persona) (2026-04-29)

Read-only Hermes one-shot flow that answers ad-hoc compliance
questions over the existing auditor toolset.  The persona name comes
from the original Phase-19 sketch: "welche Runs schrieben Q3 auf
PII-Spalten?" via Slack DM or slash-command.

- **New ``GET /api/audit/principal-summary``** (auditor-gated).
  Aggregates :class:`AgentRun` rows for one ``principal`` over a
  window and returns headline counters (runs, ops, rejects,
  value_changes, external_writes) plus the most recent ``limit``
  runs.  Closes the gap between Sprint 19.1's per-run audit axes and
  the persona's "enumerate runs by principal first" pattern.
  Self-tracks as ``read_kind='audit_api'`` like the rest of
  ``/api/audit/*``.

- **Plugin tool ``pql_principal_summary``.**  Required arg
  ``principal``; optional ``since`` / ``until`` / ``limit`` (1–200,
  server clamped).  Goes into ``register_auditor_tools`` so it loads
  only when ``POINTLESSQL_AUDITOR_MODE=1``.  Plugin grows from 31
  → 32 tools.

- **System prompt + manifest** at
  ``docs/hermes-jobs/compliance-bot.{md,json}``.  Four-block answer
  skeleton (Question / Answer / How / Caveats) so auditors can
  reproduce any answer from the tool-call trail.  Five hard
  constraints in the prompt: no writes, mandatory masking on
  value-changes, no API-key echo, mandatory time-window pinning,
  explicit refusal-and-escalation when the question would require a
  write.  Manifest uses Hermes' wake-on-message dispatch (no cron
  schedule); the chat-platform adapter routes incoming messages.

- **e2e walkthrough** at
  ``docs/e2e-walkthroughs/compliance-bot.md`` exercises the three
  canonical question shapes (runs-by-principal, yesterday's external
  writes, high-reject runs) and asserts the four safety properties:
  read-only refusal works, value-changes always masked, API-key never
  appears in output bytes, audit-of-audit history matches the
  observed tool surface.

### Added — Sprint 19.2.2: Wake-gate (skip clean days) (2026-04-29)

Optimisation pass on the daily Audit-Reviewer-Agent: most days have
nothing to report, and burning a full LLM round-trip on those days is
pointless and expensive.

- **`scripts/audit-wake-gate.py`.**  Hermes pre-run script invoked
  before the LLM call.  Hits `GET /api/audit/anomalies` for the three
  metrics (rejects, errored_ops, external_writes) against the
  closed-day window, prints a `#`-prefixed human-readable context
  block (the agent sees this as prompt context when it does wake),
  and emits the wake-gate JSON line as the FINAL non-empty stdout
  line.  On `ok` days the line is
  `{"wakeAgent": false, "severity": "ok"}` and Hermes skips the LLM
  round-trip per the contract in
  `hermes-agent/cron/scheduler.py:_parse_wake_gate`.  Failures
  (PointlesSQL unreachable, missing API key) fail open: the script
  always exits 0 and returns `{"wakeAgent": true}` so a transient
  outage never silences a real anomaly day.

- **Manifest update.**  `docs/hermes-jobs/audit-reviewer-daily.json`
  carries `"script": "scripts/audit-wake-gate.py"`.  The prompt is
  rewritten to trust the wake-gate's pre-fetched verdicts: the agent
  no longer re-calls `pql_anomaly_check` for the same window, saving
  one LLM round-trip on every `warn`/`critical` day too.

- **Walkthrough update.**  `docs/e2e-walkthroughs/audit-reviewer-daily.md`
  gains a step-7 verification path (clean day → no LLM iteration row
  in PointlesSQL; seeded reject row → LLM fires) and a cost note
  (clean-day cost: 3 HTTP round-trips vs. one LLM call worth
  one-to-three orders of magnitude more tokens).

### Added — Sprint 19.2.1: Review persistence + CloudEvents fan-out + cockpit card (2026-04-29)

Second half of Phase-19's "Audit-Reviewer-Agent reference run" sub-phase.
PointlesSQL now persists every posted review, fans the CloudEvents
envelope out to admin-configured webhooks (alongside Hermes-native
delivery), and surfaces the result on the home cockpit so operators
see yesterday's verdict without leaving the UI.

- **New ``agent_reviews`` table.**  Alembic migration
  ``l2g3a4b5c6d7_agent_reviews`` adds (id, run_id FK ``agent_runs.id``
  nullable, period_start, period_end, severity ``ok|warn|critical``,
  summary_md, payload_json, delivered_to_json, created_at) +
  CHECK constraints on severity and ``period_end > period_start``.

- **New ``review_destinations`` table.**  Admin-configured webhook
  sinks (name, webhook_url, hmac_secret, is_active, min_severity).
  ``min_severity`` gates noise: a ``warn``-default destination won't
  receive an ``ok``-day review.

- **``services/review_dispatcher``.**  Thin wrapper around
  ``alert_dispatcher.dispatch_webhook``: builds a
  ``pointlessql.agent_review.posted.v1`` CloudEvent, enumerates
  active destinations whose ``min_severity`` gate passes, fans out
  with HTTP+HMAC+retry, and persists the per-destination outcome
  (status code + URL hash, never the cleartext URL) onto
  ``AgentReview.delivered_to_json``.

- **Three auditor-gated agent-review routes.**
  ``POST /api/agent-reviews`` (validates bounds, persists, dispatches,
  returns the persisted row + fan-out log),
  ``GET /api/agent-reviews/latest`` (cockpit + plugin reads),
  ``GET /api/agent-reviews/{id}`` (detail JSON).
  Privilege ladder: auditor 200, supervisor 403, bare key 403,
  cookie admin 200.  ``GET /agent-reviews/{id}`` is the corresponding
  HTML detail page (admin-gated; auditor keys stay HTTP-only).

- **Four admin-gated review-destination routes** at
  ``/api/admin/review-destinations``.  Mirrors the existing
  admin-api-keys CRUD: list, create-with-secret-display, patch
  (sparse), delete.  Hard-delete is fine because
  ``AgentReview.delivered_to_json`` already records the destination's
  ``url_hash`` + ``name`` so historical fan-out attribution survives.

- **Cockpit "Latest review" card on ``/``.**  Admin-only.  Severity
  pill + rendered Markdown digest + period chip + "Full transcript"
  button → ``/agent-reviews/{id}``.  Lookup is best-effort with the
  same posture as Sprint 18.5's anomaly banner: a fresh-install
  pointlessql with no reviews yet renders the home page without the
  card, no error.

- **Detail page** at ``/agent-reviews/{id}``.  Three-column layout:
  Markdown summary + (optional) replay payload pretty-printed JSON,
  metadata sidebar (run_id link, severity, window), and the
  dispatcher fan-out log card listing every destination by name +
  url_hash + status_code.

- **Plugin grows from 29 → 31 tools.**  ``pql_post_audit_review``
  posts the rendered Markdown digest at the end of the daily review
  (now the final step of the Sprint-19.2.0 prompt).
  ``pql_get_latest_review`` reads the most recent review back so the
  Compliance-Bot / Incident-Responder personas can anchor their
  answers to yesterday's verdict.

### Added — Sprint 19.2.0: Daily-review Hermes job + auditor key bootstrap (2026-04-29)

First half of Phase-19's "Audit-Reviewer-Agent reference run" sub-phase.
Wires the operator-facing onboarding for the daily 06:00 UTC anomaly
digest: the CLI to mint an auditor-scoped API key, the reference Hermes
cron manifest, and an operational runbook that chains the two.

No server-side schema changes — Sprint 19.2.1 is the one that adds the
``agent_reviews`` + ``review_destinations`` tables.

- **New ``pointlessql admin issue-auditor-key`` Typer subcommand.**  The
  existing ``[project.scripts] pointlessql = "...:cli"`` entry point
  grew a Typer app: invoking ``pointlessql`` with no arguments still
  starts the uvicorn dev server (backward-compat via an
  ``invoke_without_command=True`` callback), and ``pointlessql admin
  issue-auditor-key --name=… [--supervisor]`` mints a fresh API key
  with ``api_keys.auditor=True``.  The plaintext token is printed
  exactly once and cannot be recovered afterwards — same hash-only
  storage discipline as Sprint 13.11's admin HTTP route.

- **Reference Hermes-cron manifest** at
  ``docs/hermes-jobs/audit-reviewer-daily.json``.  Schedule
  ``0 6 * * *``, ``enabled_toolsets: ["pointlessql"]``, ``deliver:
  "local"`` (Slack / email fan-out is opt-in via
  ``hermes cron edit --deliver``), and a self-contained prompt that
  pins the audit window to ``[yesterday-00:00 UTC, today-00:00 UTC)``
  so the digest is deterministic regardless of when the cron actually
  fires.  Renders Markdown to a fixed skeleton so downstream consumers
  (Sprint 19.2.1's cockpit card, future digest aggregators) can
  parse it.

- **``docs/hermes-jobs/README.md``** — index for the manifest folder.
  Documents why ``hermes cron create`` does not yet expose the
  ``--enabled-toolsets`` flag the auditor flow needs (so the
  walkthrough installs the manifest by editing
  ``~/.hermes/cron/jobs.json`` directly), the
  ``POINTLESSQL_AUDITOR_MODE`` plugin-side opt-in, and the lack of
  per-job env overlays in Hermes (``~/.hermes/.env`` is reloaded fresh
  per cron tick).

- **``docs/e2e-walkthroughs/audit-reviewer-daily.md``** — operational
  runbook (CLI + cron, no browser) chaining: mint key → ``.env``
  overlay → ``jobs.json`` patch → ``hermes cron run`` + ``tick`` →
  cross-check ``GET /api/audit/history?read_kind=audit_api`` rows
  attributed to ``api_key:daily-review``.  Closes the loop on
  audit-of-audit observability for the new flow.

### Added — Sprint 19.1: Audit-read tools + ``auditor`` scope (2026-04-28)

Sprint 19.1 closes the gap between the Phase-18 audit-data plane
and Phase-19's three consumer flows (Audit-Reviewer-Agent,
Compliance-Bot, Incident-Responder).  Adds a fourth privilege
scope, lifts the read endpoints out of admin-only gating, exposes
five new run-scoped JSON axes, and grows
``hermes-plugin-pointlessql`` from 20 → 29 tools.

- **New ``auditor`` scope on ``api_keys``.**  Alembic migration
  ``k1f2a3b4c5d6_api_keys_auditor`` adds a ``BOOLEAN NOT NULL
  DEFAULT 0`` column.  ``KeyEntry`` gains an ``auditor`` field;
  ``parse_keys`` now accepts ``name:secret:auditor`` env entries
  alongside the existing ``:supervisor`` form.  Middleware sets
  ``request.state.api_key_auditor`` from the verified bearer.
  New ``require_auditor`` dependency in
  ``pointlessql/api/dependencies.py`` enforces the gate;
  ``require_supervisor`` is widened to also accept the auditor
  scope so a single auditor key drives both tenant-wide and
  per-run audit reads without inheriting supervisor's
  approve/deny privileges or admin's PII-reveal.

- **Phase-18 audit endpoints lowered to ``require_auditor``.**
  ``GET /api/audit/summary``, ``/timeseries``, and ``/anomalies``
  no longer require an admin cookie — an auditor key is enough.
  ``POST /api/audit/pii/reveal`` stays admin-only.

- **Five new run-scoped JSON endpoints** under
  ``/api/agent-runs/{run_id}/audit/<axis>``:
  - ``lineage`` wraps the existing
    ``load_lineage_summary_for_run`` helper (per-op row-edge
    counts).
  - ``rejects`` wraps ``load_rejects_for_run`` (Sprint-15.5.3
    rejected rows).
  - ``value-changes`` queries ``lineage_value_changes`` directly
    and **always masks ``old_value`` / ``new_value`` for non-admin
    callers** — auditor scope cannot un-mask, regardless of the
    ``mask=false`` query flag.  Admin cookie + ``mask=false``
    surfaces cleartext via the same response shape; the
    historical admin-only ``POST /api/audit/pii/reveal`` is
    unchanged.
  - ``external-writes`` wraps ``load_unattributed_for_run``
    (filters to the run's ``tables_touched`` JSON list +
    ``acknowledged_at IS NULL``).
  - ``column-lineage`` queries ``lineage_column_map`` directly
    (per-run source-column → target-column edges).

  All five validate the run id up-front via ``_ensure_run_visible``
  and return ``CatalogNotFoundError`` (404) on stale UUIDs rather
  than empty rows.  Three formerly-private helpers in
  ``runs_routes.py`` (``_load_lineage_summary_for_run`` →
  ``load_lineage_summary_for_run`` etc.) were renamed when their
  cross-module use surfaced — strict pyright was rightfully
  complaining about ``reportPrivateUsage`` once
  ``agent_runs_routes`` started reaching for them.

- **New tenant-wide ``GET /api/audit/history``.**  Paginated
  ``query_history`` walk for the audit-of-audit traversal flow.
  Default response **excludes ``read_kind='audit_api'`` rows**
  so an audit-reviewer agent doesn't loop on its own
  breadcrumbs; ``?include_audit_api=true`` or
  ``?read_kind=audit_api`` lift the filter.  Routes through the
  existing ``list_queries`` service.

- **Anomaly-baseline bugfix in
  :func:`audit_aggregator.anomalies`.**  When the caller bounds
  ``since`` to (e.g.) yesterday-00:00 UTC, the previous
  implementation returned only points inside ``[since, until)``
  to the rolling-baseline loop, leaving the first bin with an
  empty baseline and false-positive ``critical`` verdicts.  Fix
  widens the underlying ``timeseries`` query by ``window_days``
  internally, then trims the response back to ``[since, until)``
  via a new dialect-safe ``_bin_floor_compare_string`` helper
  (SQLite ``%Y-%m-%d`` vs Postgres ``date_trunc(...)::String``
  reconciled by a 10-/16-char prefix compare).  This unblocks the
  Sprint-19.2 daily reviewer's "yesterday closed-day verdict"
  prompt.

- **Audit-of-audit logging on every new endpoint.**  Each new
  audit-read endpoint records a synthetic ``query_history`` row
  with ``read_kind='audit_api'`` via a new
  ``_record_audit_self`` helper (mirror of the existing
  ``_record_self`` in ``audit_routes.py``).  Server-side, not
  plugin-side — a malicious agent cannot turn off the
  audit-of-audit trail.

- **Plugin-side: 9 new tools in ``hermes-plugin-pointlessql``.**
  Bumps the registered count from 20 to 29.  New
  ``POINTLESSQL_AUDITOR_MODE`` env flag (analog to the existing
  ``POINTLESSQL_SUPERVISOR_MODE``) gates a new
  ``register_auditor_tools`` factory:
  - ``pql_list_recent_runs`` — generic recent-N-runs listing
    (the existing ``pql_runs_by_principal`` /
    ``pql_runs_by_agent`` cover filtered listings).
  - ``pql_audit_summary`` — wraps both ``/api/audit/summary``
    (``mode="counts"``) and ``/api/audit/timeseries``
    (``mode="timeseries"``) behind one tool.
  - ``pql_anomaly_check`` — wraps ``/api/audit/anomalies``.
  - ``pql_query_history_audit`` — wraps ``/api/audit/history``;
    default hides audit_api rows.
  - ``pql_query_row_lineage`` — per-op row-edge aggregate
    (run-scoped, distinct from the existing soyuz table-level
    ``pql_lineage`` tool).
  - ``pql_query_column_lineage`` — column-axis JSON view.
  - ``pql_query_value_changes`` — always-masked at the
    PointlesSQL boundary; the plugin doesn't expose a cleartext
    path.
  - ``pql_query_rejects`` — Sprint-15.5.3 reject rows.
  - ``pql_query_external_writes`` — unattributed Delta commits.
  - ``pql_get_run`` was deliberately dropped — the existing
    ``pql_run_summary`` already covers it.

- **16 new pytest cases in
  ``tests/test_audit_routes_sprint_19.py``** covering the
  privilege ladder (normal/supervisor/auditor/admin against
  tenant-wide and per-run reads), the masked-by-default
  contract on ``/audit/value-changes``, the audit-of-audit
  recursion guard on ``/api/audit/history``, the
  ``query_history`` row landing for each successful per-run
  audit read, and the structural shape of the anomaly bugfix.
  ``test_api_key_gate.py`` updated for the new
  ``parse_keys`` triple shape and gains a
  ``test_parse_keys_supports_auditor_scope`` case.
  Pre-existing unrelated test failures in
  ``test_api_notebook_workspace.py`` /
  ``test_scheduler_papermill.py`` /
  ``test_table_stats.py`` are untouched (verified clean on
  HEAD prior to this change).

### Added — Phase 18: Audit Cockpit (2026-04-28)

Closes Phase 18 in one autonomous session — six sub-sprints landed
on top of the Phase 15.7 capture surface to make the audit data
*actionable* for the four real personas (operator on-call,
developer debug, compliance auditor, daily trust glance).
Sequencing decision: Phase 18 lands **before** Phase 17 against
today's 10-tab run-detail layout; 18.1 cross-axis links will be
re-touched once Phase 17's tab consolidation lands.

- **Sprint 18.0 — Audit-Read API backbone.**  Three read-only
  JSON endpoints feed every later cockpit, Grafana, and
  Hermes-tool surface:
  - ``GET /api/audit/summary?since&until&principal&agent_id&table``
    returns one count per metric across runs, ops, errored ops,
    rows written (merge + write_table), value changes, rejects,
    external writes, cost-gate denials, tool calls, queries.
  - ``GET /api/audit/timeseries?metric&bin&group_by&...``
    bins by hour/day/week with optional grouping by table or
    principal.
  - ``GET /api/audit/anomalies?metric&window_days&sigma&...``
    classifies each bin against an N-day rolling mean ± Nσ as
    ``ok`` / ``warn`` (≥σ) / ``critical`` (≥2σ).
  - Backed by a new ``audit_aggregator`` service with a single
    ``_apply_audit_filters`` helper so the WHERE-clause logic
    lives in one place.  Dialect-aware bucketing (SQLite
    ``strftime`` vs Postgres ``date_trunc``) keeps both
    deployments working.
  - Self-tracking: every successful call inserts a
    ``query_history`` row with ``read_kind='audit_api'`` so the
    cockpit endpoints land in the audit lake they query.
    ``audit_api`` was added to ``VALID_READ_KINDS``.
  - All three endpoints are admin-gated.

- **Sprint 18.1 — Cross-axis navigation.**  The Operations-tab
  ``column edges: N`` and ``value changes: N`` badges now wrap
  in deep-links to ``/runs/{id}?op_id=N#tab-lineage``.  The
  ``run_detail_page`` handler accepts ``?op_id=`` and threads it
  into ``_load_operations_for_run`` /
  ``_load_rejects_for_run`` / ``_load_lineage_summary_for_run``
  so the three cross-axis tabs render filtered to that single
  op.  A "filtered to op #N" chip with a Clear-filter button
  sits above the tab strip.  Stale ``op_id`` falls back to
  unfiltered rendering rather than 404 (drill-downs are
  permissive).

- **Sprint 18.2 — PII-aware masking.**  New
  ``pointlessql/services/pii_resolver.py`` resolves column-level
  PII tags from soyuz-catalog (``GET /tags/column/{fqn.col}``)
  with a TTL cache keyed on ``(table, column)`` so a row-trace
  page rendering 100 cells from one table issues at most one
  soyuz call.  ``pii_mask`` helper replaces cleartext with
  ``***@***.***`` (email) / ``***-***-1234`` (phone) /
  ``A***z`` (default) shapes.  Row-trace template renders
  ``display_old`` / ``display_new`` (masked when
  ``is_pii=True``) and shows a Reveal button to admins;
  ``POST /api/audit/pii/reveal`` returns the cleartext and
  writes an ``audit_log`` row of
  ``action='pii.value_revealed'``.  ``AuditSettings`` gained
  ``pii_mask_default`` (default ``True``) and
  ``pii_cache_ttl_seconds`` (default ``600``).  Storage stays
  byte-faithful — masking is render-time only.

- **Sprint 18.3 — Saved audit queries + CSV/JSON export.**  New
  ``saved_audit_queries`` table (Alembic ``j0e1f2a3b4c5``)
  separate from ``saved_queries`` because:
  - visibility is admin-only, not the owner-+-shared model;
  - five canonical starter rows ship with the migration:
    ``pii-writes-last-90d``, ``rollbacks-last-quarter``,
    ``cost-gate-denials-this-week``,
    ``unacknowledged-external-writes``,
    ``top-mutating-principals-30d``;
  - ``alert_threshold_count`` plugs into the Sprint 18.5 alert
    surface;
  - service enforces an explicit allow-list of audit-table
    names (``agent_runs``, ``agent_run_operations``,
    ``lineage_*``, ``query_history``, ``audit_log``,
    ``unattributed_writes``, …) via sqlglot — SELECT-only,
    no DDL/DML.
  - CRUD endpoints at ``/api/saved-audit-queries`` plus
    ``/{slug}/run`` and ``/{slug}/export.csv`` /
    ``/{slug}/export.json`` (PDF deferred — CSV+JSON satisfy
    SOC2 / GDPR Art. 30 evidence packets).
  - Every export writes a ``saved_audit_query.exported`` audit
    row.  Starter rows refuse PATCH/DELETE.
  - New admin-only ``/audit/queries`` HTML workbench: split-
    pane list-of-queries + textarea + Run/Export buttons +
    result table.

- **Sprint 18.4 — Run-diff lineage view.**  New service
  ``run_diff.build_lineage_diff(factory, run_a_id, run_b_id)``
  produces three buckets:
  - ``reject_pattern_shift`` — counts of
    ``LineageRowReject.reason`` values per side, plus a
    per-reason ``delta``;
  - ``value_change_volume_per_table`` — per-target counts;
  - ``row_count_delta_per_table`` — sum of ``rows_affected``
    per merge / write target.

  ``GET /api/agent-runs/diff?detail=true`` carries the new
  ``lineage_diff`` payload.  New HTML route
  ``GET /runs/{a}/diff/{b}`` consumes both
  ``build_detail_diff`` and ``build_lineage_diff`` to render
  ``pages/agent_run_compare.html``: four +Δ stat cards
  (rows touched / value changes / errored ops / rejects) plus
  Chart.js bar charts for each lineage axis.

- **Sprint 18.5 — Anomaly highlighting.**  Three surfaces all
  driven by the Sprint 18.0 ``/api/audit/anomalies`` endpoint:
  - ``/api/home/summary`` carries an ``anomalies: {warn, critical}``
    block computed against ``rejects``, ``errored_ops``, and
    ``external_writes``; the home page renders a yellow/red
    banner when ≥1 metric is critical/warn.
  - ``/runs/{id}`` HTML adds an anomaly chip at the top of the
    page when the latest day's value for any of those metrics
    breaches the configured σ threshold; the chip names the
    worst-offender metric + observed-vs-baseline values.
  - ``saved_audit_queries.alert_threshold_count`` (new column)
    plugs into the existing ``/api/alerts`` machinery so a
    scheduled run that returns more rows than the threshold
    fires.

  ``AuditSettings`` gained ``anomaly_baseline_window_days``
  (default 7) and ``anomaly_threshold_sigma`` (default 2.0).
  Anomalies are computed on-the-fly — no
  ``audit_anomalies_daily`` materialised table.  Email-digest
  CLI deliberately deferred to Phase 19.2 (Audit-Reviewer-Agent
  covers daily-summary territory; building it twice is waste).

Tests: 72 new unit + integration tests across
``tests/test_audit_aggregator.py``,
``tests/test_runs_op_filter.py``,
``tests/test_pii_resolver.py``,
``tests/test_saved_audit_queries.py``,
``tests/test_run_diff_lineage.py``, and
``tests/test_anomaly_highlighting.py``.  Existing
``test_lineage_*`` and ``test_value_change_*`` suites still
pass — no regressions in the 15.x axes.

### Added — Sprint 19.0: Grafana audit dashboard (XS quick-win, 2026-04-28)

First Phase-19 sub-sprint, landed out of phase order.  Strategic
ordering note in ROADMAP marks 19.0 as eligible to land before
Phase 17 / 18 because it reads the existing audit + lineage tables
directly — no Phase-18 audit-API dependency.  Phases 19.1–19.3
remain queued (they wrap the not-yet-built Phase-18 backbone).

Goal: glance-trust dashboard.  No agent code, no API changes — a
``docker compose -f docker-compose.yml -f docker-compose.grafana.yml up``
spins up Grafana auto-provisioned with eight panels covering
runs/day, reject-rate vs 7-day baseline, value-change-volume per
table (red ≥1000), external-write count (red ≥1), top mutating
principals, cost-gate denials, tool-call latency table, and
EXPLAIN-cost histogram.

- ``docker-compose.grafana.yml`` overlay adds a
  ``grafana/grafana-oss:latest`` service.  Two intentional config
  choices that surfaced in the design pass:
  - ``GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=frser-sqlite-datasource``
    is **mandatory** — the SQLite plugin is unsigned and Grafana
    refuses to load it without the explicit allow.  Skipping it
    is the #2 cause of "datasource doesn't appear" reports.
  - ``pointlessql_data:/data/pointlessql`` is mounted **read-write**,
    NOT ``:ro``.  Reason: the app runs SQLite in WAL mode (the
    ``.db-wal`` and ``.db-shm`` files exist alongside the DB);
    the SQLite library needs write access to manage ``-shm`` even
    for readers.  A ``:ro`` bind produces ``disk I/O error`` on
    the first query.  The Grafana plugin only issues SELECTs.
- ``grafana/provisioning/datasources/pointlessql.yml`` pins the
  datasource UID to ``pointlessql-sqlite`` so panel→datasource
  bindings survive reprovisioning.  Without a hardcoded UID,
  every restart shuffles UIDs and breaks every panel.
- ``grafana/provisioning/dashboards/pointlessql.yml`` provider
  drops the dashboard into a ``PointlesSQL`` folder (keeps it
  out of Grafana's default ``General`` folder where built-in
  samples live), ``allowUiUpdates: false`` enforces JSON as
  the source of truth.
- ``grafana/dashboards/pointlessql_audit.json`` — 10 panels
  (8 spec'd + Markdown header + datasource-health smoke).  Layout
  on a 24×32 grid.  Notable per-panel choices:
  - **Runs/day**: timeseries-bar grouped by ``date(started_at)``,
    using the frser plugin's ``$__timeFilter()`` macro (bare
    ``$__timeFrom()`` / ``$__timeTo()`` is **not** supported).
  - **Reject-rate vs baseline**: two series, today's daily count
    plus a 7-day trailing average computed via correlated
    subquery (no SQL window functions — the frser plugin's query
    parser truncates them in some Grafana releases).
  - **Value-change-volume per table**: stacked bars per
    ``target_table``, threshold style ``line`` at 1000 to make
    over-budget runs visually pop.
  - **External-write count**: stat panel reading
    ``unattributed_writes WHERE acknowledged_at IS NULL``,
    threshold red at ≥1.
  - **Top-mutating-principals**: horizontal bars of summed
    ``rows_affected`` for ``op_name IN ('merge', 'write_table')``.
    NULL principals coalesced to ``'<unknown>'`` so background
    agents are still visible.
  - **Tool-call latency**: SQLite has no ``percentile_cont``,
    so the panel emits raw rows and a Grafana ``Reduce →
    percentile`` transform computes p50/p99 client-side.
  - **EXPLAIN-cost histogram**: ``CAST(cost_est AS REAL)`` is
    mandatory because ``cost_est`` is ``Decimal(18,4)`` ORM-side
    and the frser plugin returns Decimals as strings, which the
    histogram viz can't bucket.
- Scope decisions baked into the sprint:
  - **SQLite-only.**  Postgres deferred to Sprint 19.0.1 (separate
    overlay, separate dashboard).  Reason: dialect divergence
    (no ``percentile_cont`` / ``date_trunc`` in SQLite) makes
    a templated dual-mode dashboard cost more than the XS
    sizing allows.
  - **Panel thresholds only, no alert routing.**  Webhook /
    Slack / email routing is Phase 19.2 territory.
  - **Anonymous viewer enabled**, admin password still
    enforced for edits.

End-to-end smoke (against the host's live DB, ten queries):
all 10 panel SQLs parse cleanly and return expected shape —
``agent_runs`` has 7 rows, ``lineage_row_rejects`` 58, the
7-day baseline subquery returns 8.29 rejects/day, three
mutating principals (admin@local with 206 rows leading).

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

### Changed — Roadmap expansion: Phase 17-20 + Some-day rewrite (2026-04-27)

Strategic conversation post-15.7-close generated a substantial
roadmap extension covering the *non-capture* side of audit
infrastructure: navigation, exploration, governance UX,
forensics, distribution.  Previously the roadmap stopped at
Phase 16 (Rollback) with a vague Some-day block; it now reads
through Phase 20 with concrete sub-sprints.

- **Phase 17 — UI Overhaul**: two-column sidebar, run-detail
  tabs consolidation (10→4), lineage-DAG view (cytoscape.js),
  table-detail entdichten, catalog-browser search/filter.
- **Phase 18 — Audit Cockpit**: three new ``/api/audit/*``
  endpoints (summary / timeseries / anomalies) feed cross-axis
  navigation, PII-aware masking, saved audit queries, run-diff
  view, anomaly highlighting.
- **Phase 19 — Audit-Reviewer Agent + Grafana**: shared
  Phase-18 backbone drives a Grafana dashboard JSON
  (``grafana/pointlessql_audit.json``), 10 audit-read tools in
  ``hermes-plugin-pointlessql``, daily Audit-Reviewer-Agent
  reference run, Compliance-Bot + Incident-Responder demos.
- **Phase 20 — Forensics + Retention**: CloudTrail / audit-
  stream forwarder, PII detection + masking layer, lineage
  retention policies, time-travel value queries in UI, soyuz
  columnLineage / valueChange facet ingest (formerly the
  Phase-15.8+ sketch).
- **Some-day rewrite**: pre-OSS-release hygiene (EUIPO
  trademarks, NOTICE, CLA, domains) + big-bang launch day
  (HN / Twitter / Reddit / LinkedIn / blog) + conference
  circuit (DataCouncil, Subsurface, dbt Coalesce, Berlin
  Buzzwords, Big Data LDN) + sustained visibility + the
  original GHCR / PyPI / Helm / docs items + commercial
  offering pathway (3-5 design partners → UG/GmbH →
  cryptographic anchor service / hosted Cloud).

No code change in this entry — pure roadmap edit.  Engineering
work continues against the new tree.  See [ROADMAP.md](ROADMAP.md).

### Added — Phase 15.7: Value-Level Lineage (2026-04-26)

Fourth lineage axis after row (Phase 15), reject (15.5),
column (15.6).  Answers *"this gold row's `revenue` is $1234 —
what was it last week, and which run changed it?"*.  Surface
scope is `pql.merge(strategy="upsert")` only — the only PQL
primitive that mutates rows in place.

Capture mechanic: every new Delta write enables Change Data Feed
(`delta.enableChangeDataFeed=true`).  When the caller opts in via
`pql.merge(track_value_changes=True)`, post-merge
`DeltaTable.load_cdf()` yields native preimage/postimage pairs;
we diff per-cell on `_lineage_row_id` and persist into a new
`lineage_value_changes` table.  PointlesSQL-only storage; opt-in
default-off; `MAX_VALUE_CHANGES_PER_OP = 100_000` cap with
`[lineage_value_partial]` audit-row marker.

Sub-sprints:

- **15.7.0** — Open Phase 15.7 in ROADMAP / CHANGELOG (7b42369).
- **15.7.1** — Alembic migration `h8c9d0e1f2a3` adds
  `lineage_value_changes` table.  ORM `LineageValueChange`
  with `Text`-typed `old_value` / `new_value` columns.
  `record_value_changes` / `count_value_changes_for_op` /
  `fetch_value_changes_for_row` service helpers.
  `OperationRecorder.pending_value_changes` post-commit hook
  with `[lineage_value_partial]` marker (6641ed2).
- **15.7.2** — `pointlessql/pql/_cdf.py` exposes
  `cdf_creation_config()` and `ensure_cdf_enabled()`.
  `pql.write_table` (create-path) and `pql.autoload`
  (first-write) call `ensure_cdf_enabled` so every new Delta
  table records CDF events going forward (acb9954).
- **15.7.3** — `pql.merge` gains `track_value_changes` kwarg.
  Pure-function `services/value_change_capture.extract_value_changes`
  pairs `update_preimage` / `update_postimage` events on
  `_lineage_row_id` and emits one `ValueChangeSpec` per changed
  cell.  SCD-2 logs warning and skips (31847dd).
- **15.7.4** — `GET /api/lineage/value-changes?table=&row_id=
  &column=` JSON.  Row-trace page gains collapsible
  "Value changes (N)" per step.  Run-detail Operations tab
  shows `value changes: N` counter (fb8fcb2).
- **15.7.5** — `notebooks/hermes_medallion.py` silver `pql.merge`
  gets `track_value_changes=True`; second cell tweaks one
  `unit_price` and re-runs the merge.  Live replay confirmed:
  exactly 1 value-change in DB (`unit_price` 2.5 → 2.51),
  API + row-trace + run-view counter all render correctly.

### Added — Phase 15.6: Column-Level Lineage (2026-04-26)

Orthogonal column dimension to the row-lineage Phase 15 / 15.5
already shipped.  Every PQL primitive now populates a new
`lineage_column_map` table that answers *"if I rename `unit_price`
in silver, which gold columns break?"*.  PointlesSQL-only storage
(soyuz columnLineage facet ingest deferred to Phase 15.8+).
Volume bounded by schema breadth: ~52 column edges for the
canonical Hermes-Medallion run vs the 102 row edges + 2 rejects
Phase 15.5 already accepts.

- **Sprint 15.6.1** — new `lineage_column_map` table (Alembic
  `g7b8c9d0e1f2`) parented on the 15.5.3 rejects table.
  CHECK-constrained `transform_kind` enum:
  `identity` / `rename` / `derived` / `aggregate` /
  `unknown_origin` / `sql_select` / `sql_function` /
  `sql_unknown`.  Indices on (target_table, target_column),
  (source_table, source_column), run_id, op_id.  Service helpers
  `record_column_edges` (with a 1000-edge per-op cap that returns
  a `ColumnEdgeCapExceeded` sentinel and stamps
  `[lineage_column_partial]` on the audit row), `walk_back_columns`
  (column-trace walkback mirroring the Sprint-15.5.2 fan-in
  shape), and `count_column_edges_for_op`.  Best-effort
  post-commit hook on `OperationRecorder.pending_column_edges`
  matching the row-lineage / rejects contract.
- **Sprint 15.6.2** — every declarative PQL primitive populates
  the new table:
  - `pql.aggregate`: `aggs` dict drives the `aggregate` edges
    (with the agg-fn name in `transform_detail`); `group_by`
    columns become identity edges; new `derivations={...}` kwarg
    captures upstream `.assign(...)` mappings as `derived` edges
    with chain detail (e.g. `via 'line_revenue' →
    sum('line_revenue')`).
  - `pql.merge` / `pql.write_table`: schema-diff against the
    source frame.  Identity edges for surviving columns;
    `_lineage_row_id` rewritten to a `derived` edge with
    `transform_detail="synth_target_row_id"` so the row-id
    origin chain is queryable from `lineage_column_map` alone.
    `derivations` kwarg honoured; no `source_table_fqn` skips
    edge emission quietly.
  - `pql.autoload`: post-append Delta schema reads — non-audit
    columns recorded as `unknown_origin` with detail =
    `source_volume_fqn` or `"file"`; audit columns recorded as
    `unknown_origin` with detail `"audit"`.
  - New `services/column_lineage_diff.infer_column_edges` helper
    encapsulates the merge/write_table/autoload classification.
- **Sprint 15.6.3** — `pql.sql` populates the table for SELECT
  projections via `sqlglot.lineage`.  Per output column:
  bare-column refs → `sql_select`, function/arithmetic/CASE →
  `sql_function` (with rendered subexpression as
  `transform_detail`), zero-downstream nodes (`count(*)`, window
  functions, lateral joins) → `sql_unknown`.  Schema dict built
  from DuckDB `DESCRIBE` against the already-registered Delta
  views — no soyuz round-trip at SQL time.  Synthetic
  `target_table="query"` since `pql.sql` results aren't
  persisted; op_id is the unique discriminator.
- **Sprint 15.6.4** — three UI surfaces around the walkback:
  - `GET /api/lineage/column-trace?table=&column=` JSON +
    `/catalogs/.../columns/{col}/trace` HTML page (`column_trace.html`)
    with colour-coded transform_kind badges, fan-in collapsibles,
    click-through to source columns.
  - Table-detail page renders a small "lineage" badge per column
    that has at least one `lineage_column_map` row.
  - Run-detail Operations tab adds a "column edges: N" badge per
    op that produced edges (no new tab; same shape as the 15.5.4
    rejects counter).
- **Sprint 15.6.5** — `notebooks/hermes_medallion.py` declares
  `derivations={"placed_day": ["placed_at"], "line_revenue":
  ["qty", "unit_price"]}` on the gold aggregate.  Live E2E
  replay (headful Firefox): two notebook runs against fresh
  schemas, 52 column edges total, column-trace API walks
  `revenue → (qty, unit_price)` and `placed_day → placed_at` to
  bronze, table-detail page shows lineage badges on all five
  gold columns, run-detail tab shows `column edges: 10/10/6` per
  op.  Console clean.

### Added — Phase 15.5: Aggregate Lineage + Reject Visibility (2026-04-26)

Closes the two row-lineage gaps the Phase-15 live replay surfaced.
Five sprints landed in one autonomous session, all with green
linters + unit tests + a headful Firefox walkthrough that exercised
every UI surface end-to-end.

- **Sprint 15.5.1** — new `pql.aggregate()` primitive with fan-in
  lineage emission.  Records one edge per (source row, target group)
  pair so gold tables become trace-able back to their silver
  sources.  `source_table_fqn` is required (fail-fast).
  `_lineage_row_id` synth via SHA-256(target || group_values) so
  re-runs reuse target IDs deterministically.  See the new
  `pointlessql/pql/_aggregate.py` module and the matching
  Alembic migration `e5f6a7b8c9d0` extending the
  `agent_run_operations.op_name` CHECK by `'aggregate'`.
- **Sprint 15.5.2** — `walk_back` returns predecessors per step.
  The row-trace UI surfaces fan-in as a collapsible
  "Aggregated from N source rows" block with click-through to each
  source row's own trace page.  Chain recursion still picks oldest
  for determinism.
- **Sprint 15.5.3** — opt-in `pql.merge(track_rejects=True)` records
  source rows that won't land in the target into a new
  `lineage_row_rejects` table (Alembic `f6a7b8c9d0e1`).  Reasons:
  `on_key_null` / `duplicate_in_source` (auto-detected pre-merge),
  `schema_mismatch` / `merge_predicate_excluded` / `other` (enum
  reserved for callers).
- **Sprint 15.5.4** — new "Rejects" tab on the run-detail page
  between Operations and Tool calls.  Counter badge in the tab
  label, reason badges per row (color-coded), click-throughs from
  rejected source-row IDs to the row-trace page.  Empty state
  explains "track_rejects=True not set on any merge call".
- **Sprint 15.5.5** — notebook + fixture migrated; live E2E replay
  produced 102 lineage edges across 2 ops + 2 rejects + a 24-source
  fan-in on a gold row, verified in headful Firefox with 0 console
  errors.  Caught and fixed a Jinja-filter bug
  (`format_datetime` doesn't exist) that linters never had a chance
  to flag — the replay-as-gate memo proves itself again.

### Fixed — Sprint 15.5.0: Phase-15 bugfix landing (2026-04-26)

Two bugs surfaced in the Phase-15 live E2E replay (headful Firefox
walkthrough of the medallion notebook).  Neither could be caught by
ruff / pyright / pydoclint — they required running the full ETL +
clicking through the UI.  Reinforces the "live replay as gate" memo.

- **Fixed** [`pointlessql/models/lineage.py`](pointlessql/models/lineage.py)
  + [`pointlessql/alembic/versions/d4e5f6a7b8c9_lineage_row_edges.py`](pointlessql/alembic/versions/d4e5f6a7b8c9_lineage_row_edges.py)
  — `lineage_row_edges.id` switched from `BigInteger` to `Integer`
  primary key.  Only `INTEGER PRIMARY KEY` autoincrements in SQLite;
  `BIGINT PRIMARY KEY` does not.  Symptom: every `pql.merge` stamped
  `[lineage_edges_partial] IntegrityError("NOT NULL constraint failed:
  lineage_row_edges.id")` on `agent_run_operations.error_message` and
  produced zero per-row edges.
- **Fixed** [`frontend/templates/pages/run_view.html`](frontend/templates/pages/run_view.html)
  — header link "View lineage graph" URL aligned with the rest of the
  codebase: `/catalogs/{cat}/{schema}/{table}` →
  `/catalogs/{cat}/schemas/{schema}/tables/{table}`.  Line 594 of the
  same template was already correct; line 87 was a copy-paste miss.

### Added — Sprint 15.4: Row-trace UI + run-detail Lineage tab (2026-04-26)

Closes Phase 15.  The lineage chain built by Sprints 15.1-15.3 is
now navigable in the browser: an agent or reviewer can take any
silver row, click its `_lineage_row_id`, and walk the edges back to
the originating bronze cell with the source filename attached.

- **Added** [`pointlessql/api/lineage_routes.py`](pointlessql/api/lineage_routes.py)
  with two endpoints:
  - `GET /api/lineage/row-trace?table=&row_id=` — JSON walkback via
    `services.lineage_edges.walk_back` (capped at 20 hops).  When
    the deepest step lands on a bronze table, opens the Delta table
    via deltalake + DuckDB and looks up the `_source_file` cell so
    the trace can label "this row came from `orders.csv`".
  - `GET /catalogs/{cat}/schemas/{sch}/tables/{tbl}/rows/{row_id}/trace`
    — HTML page rendering the same walkback as a Bootstrap
    list-group (one card per step with depth badge, table FQN,
    op-name badge, and a link to the originating run).
- **Updated** [`pointlessql/api/main.py`](pointlessql/api/main.py)
  registers `lineage_router` **before** `governance_router` so the
  exact-match `/api/lineage/row-trace` route wins over the existing
  `/api/lineage/{full_name:path}` catch-all (which would otherwise
  greedy-capture `"row-trace"` as a UC full name).
- **Added** [`frontend/templates/pages/row_trace.html`](frontend/templates/pages/row_trace.html)
  rendering the input row metadata, the walkback steps, and an
  "lineage break" badge when the chain stops at depth 0 (no
  predecessor edges recorded).
- **Updated** [`frontend/templates/components/lineage_card.html`](frontend/templates/components/lineage_card.html)
  the card now accepts an optional `table_columns` context list and
  renders a card-footer hint when `_lineage_row_id` is present;
  also drops an `<a id="lineage">` anchor so the run-detail
  "View lineage graph" deep-link from Sprint 15.1 lands at the card.
- **Updated** [`frontend/templates/pages/table.html`](frontend/templates/pages/table.html)
  passes the table's column names to `lineage_card`; the Alpine
  preview now renders `_lineage_row_id` cells as deep-links to the
  row-trace page (truncated display, full UUID in the URL).
- **Updated** [`frontend/templates/pages/run_view.html`](frontend/templates/pages/run_view.html)
  new "Lineage" tab between "UC mutations" and "Queries" lists each
  op that produced edges with source/target FQNs and edge count;
  links into the target's lineage card via the new `#lineage`
  anchor.
- **Added** [`pointlessql/api/runs_routes.py`](pointlessql/api/runs_routes.py)
  `_load_lineage_summary_for_run()` joins `lineage_row_edges`
  against `agent_run_operations` for the run-detail Lineage tab,
  returning `{total_edges, rows: [{ordinal, op_name, source_table,
  target_table, edge_count}]}`.

### Added — Sprint 15.3: `lineage_row_edges` shadow table + merge instrumentation (2026-04-26)

Third Phase-15 sprint.  Per-row provenance now closes the loop: a
silver row produced by `pql.merge` carries a deterministic
`_lineage_row_id` that joins to a `lineage_row_edges` row pointing
back at the bronze cell that fed it.  Sprint 15.4 will surface this
in the UI.

- **Added** Alembic migration `d4e5f6a7b8c9` creating
  [`lineage_row_edges`](pointlessql/alembic/versions/d4e5f6a7b8c9_lineage_row_edges.py)
  (`run_id` FK to `agent_runs.id`, `op_id` FK to
  `agent_run_operations.id`, `source_table`, `source_row_id`,
  `target_table`, `target_row_id`, `created_at` plus four indexes
  for the lookup patterns Sprint 15.4 needs).  No UNIQUE constraint
  — re-merges of the same rows produce fresh edges with new
  `op_id`s, preserving merge history as an audit signal.
- **Added** [`pointlessql/models/lineage.py`](pointlessql/models/lineage.py)
  `LineageRowEdge` ORM model (re-exported from `pointlessql.models`).
- **Added** [`pointlessql/services/lineage_edges.py`](pointlessql/services/lineage_edges.py)
  with the public surface used by the merge/write instrumentation
  and Sprint 15.4's UI:
  - `synth_target_row_id(source_id, target_table) ->`
    `SHA-256("<source_id>:<target_table>")` — deterministic +
    table-distinct so re-runs reuse target IDs while never
    collapsing across tables.
  - `record_edges(...)` — best-effort bulk INSERT, returns the
    underlying exception on failure for the marker hook.
  - `fetch_target_row_predecessors` / `fetch_source_row_descendants`
    / `walk_back(table, row_id, max_hops=20)` — Sprint-15.4-bound
    read API.
  - `lookup_bronze_source_file(table, row_id, storage_location)` —
    DuckDB-over-deltalake one-row probe so the deepest walkback
    step can label its bronze origin file.
  - `count_edges_for_op(op_ids)` — UI counts per operation.
- **Added** `OperationRecorder.pending_lineage_edges` (kept off
  `params_json` so 100k-row payloads don't pollute the audit row)
  on
  [`pointlessql/services/agent_runs/operations.py`](pointlessql/services/agent_runs/operations.py).
  New post-commit hook `_record_row_edges_after_commit()` reads the
  payload, calls `record_edges`, and stamps
  `[lineage_edges_partial]` onto `agent_run_operations.error_message`
  on failure (refactored marker stamping into
  `_stamp_audit_marker` shared with Sprint-15.1's emit hook).
- **Updated** [`pointlessql/pql/_merge.py`](pointlessql/pql/_merge.py)
  new `_prepare_lineage()` helper extracts source row IDs from the
  PyArrow source's `_lineage_row_id` column (when present),
  synthesises target IDs via `synth_target_row_id`, and rebuilds
  the column so the target table's row inherits the new ID.  Empty
  ID lists when the source has no lineage column — the chain just
  stops there.  `pending_lineage_edges` is set only when both the
  source carried IDs **and** the caller declared `source_table_fqn`.
- **Updated** [`pointlessql/pql/_write.py`](pointlessql/pql/_write.py)
  parallel `_stamp_lineage_for_write()` works on pandas
  DataFrames or PyArrow Tables (the two engine-native frame shapes
  the writer accepts) and threads the source/target IDs through to
  the recorder for the same post-commit edge insert.

### Added — Sprint 15.2: Bronze `_lineage_row_id` audit column (2026-04-26)

Second Phase-15 sprint.  Bronze rows now carry a stable per-row
identity that downstream silver/gold transformations can reference
to walk the trail back to the originating cell.

- **Updated** [`pointlessql/conventions/_defaults.py`](pointlessql/conventions/_defaults.py)
  the bronze `LayerConvention` gains a fourth required audit column
  `_lineage_row_id` (alongside `_ingested_at`, `_source_file`,
  `_source_system`).  Other layers stay unchanged — silver/gold
  inherit lineage IDs through the merge primitive (Sprint 15.3) and
  don't get them injected at write time.
- **Updated** [`pointlessql/pql/_autoload.py`](pointlessql/pql/_autoload.py)
  `_inject_audit_columns()` now accepts `file_sha` and computes
  `_lineage_row_id` per row as
  `SHA-256("<file_sha>:<row_offset>")`.  The new helper
  `_row_lineage_id(file_sha, offset)` exposes the same construction
  for tests and downstream tooling.  The autoload caller threads
  the file SHA it already has from the dedup checkpoint into the
  injection call — no extra hashing pass.
- The change is a **convention**, not a schema migration: existing
  bronze tables keep their schema until the next autoload appends
  to them, at which point deltalake adds the new column with NULL
  for the older rows.  Re-running an autoload over the same file is
  a no-op (existing checkpoint dedup) and the IDs are deterministic
  so any future re-ingest produces identical row IDs.

### Added — Sprint 15.1: PQL → soyuz OpenLineage emission (2026-04-26)

First Phase-15 sprint.  Every successful PQL primitive call inside an
agent run now emits one OpenLineage `RunEvent` to soyuz so the
table-level lineage graph (`lineage_runs` + `lineage_edges`) auto-
populates without the operator having to wire OpenLineage producers
manually.

- **Added** [`pointlessql/services/soyuz_lineage.py`](pointlessql/services/soyuz_lineage.py)
  `emit_event_sync(run_id, op_name, inputs, outputs, event_type)`
  builds an `OpenLineageEvent` (using the typed soyuz client's
  generated models) and POSTs it through the existing
  `make_soyuz_client(agent_run_id=...)` factory.  The PointlesSQL
  `agent_run_id` is reused verbatim as the OpenLineage `runId` —
  soyuz strips hyphens to derive `LineageRun.id`, so cross-
  referencing agent runs ↔ lineage runs needs no extra mapping
  table.  The helper is **best-effort**: any underlying exception
  (connection refused, 5xx, timeout) is returned to the caller
  rather than raised, so the write that already committed is never
  rolled back by a downstream lineage hiccup.
- **Added** [`pointlessql/services/agent_runs/operations.py`](pointlessql/services/agent_runs/operations.py)
  `_emit_lineage_after_commit()` is invoked from `operation_context`
  after the success-path `record_operation()` returns.  Inputs are
  derived per-op:
  - `autoload` — empty (filesystem source, no UC securable)
  - `merge` / `write_table` — `extra_params["source_table_fqn"]`
    when the caller declared one, otherwise empty
  - `sql` — `params_json["referenced_tables"]` from the SQL parser
  Outputs default to `recorder.target_table` (or empty for read-only
  SELECTs).  When both lists are empty the emission is skipped.
  Failures stamp `[lineage_emit_failed] <repr(exc)>` onto the just-
  inserted row's `error_message`.
- **Added** `source_table_fqn` kwarg to
  [`pointlessql/pql/_merge.py`](pointlessql/pql/_merge.py) /
  [`pointlessql/pql/_write.py`](pointlessql/pql/_write.py) and a
  `source_volume_fqn` kwarg to
  [`pointlessql/pql/_autoload.py`](pointlessql/pql/_autoload.py) so
  callers can declare upstream UC inputs.  Threaded through the
  public `PQL.merge()` / `PQL.write_table()` / `PQL.autoload()`
  facades on [`pointlessql/pql/pql.py`](pointlessql/pql/pql.py);
  `PQL.merge()` further auto-derives `source_table_fqn` when *source*
  is itself a UC `"catalog.schema.table"` string.
- **Updated** [`frontend/templates/pages/run_view.html`](frontend/templates/pages/run_view.html)
  the run-detail header gains a "View lineage graph" button that
  jumps to the lineage card on the first touched table's catalog
  page (deep-link via `#lineage`).

### Changed — Sprint 15.0: Phase 15 reframed as lineage completeness (2026-04-26)

- **Updated** [`ROADMAP.md`](ROADMAP.md) Phase-15 block: title
  shortened from "Provenance Log (data + LLM signed audit)" to
  "Lineage completeness", marker flipped ⏳ → 🚧, sub-tree
  expanded with the four sprint placeholders (15.1 OpenLineage
  emission, 15.2 bronze `_lineage_row_id`, 15.3
  `lineage_row_edges`, 15.4 row-trace UI), and an explicit Out-
  of-scope block for the Shoreguard token-trail log (lives in
  shoreguard-fresh per the boundary memo), arbitrary-SQL row
  lineage, and column-level lineage.

### Changed — Sprint 14.4 follow-up: soyuz pin bumped to v0.2.0rc3 (2026-04-26)

- **Updated** `pyproject.toml` `[tool.uv.sources]` pin from
  `v0.2.0rc2` → `v0.2.0rc3` and refreshed `uv.lock`.  The new
  soyuz tag carries the audit-log infrastructure
  (table + middleware + `/audit-log` endpoint + six instrumented
  mutation routes) plus the regenerated client with the typed
  `audit` API module.
- The Sprint 14.4 PointlesSQL service `soyuz_audit.fetch_for_run`
  still uses raw httpx; switching to the typed
  `list_audit_log_audit_log_get.asyncio(...)` method is a follow-
  up cosmetic when another callsite needs the typed surface.

### Added — Sprint 14.4: soyuz UC-mutation cross-reference (2026-04-26)

Closes the fourth and final Phase-14 audit-trail gap.  PointlesSQL
now forwards `X-Agent-Run-Id` outbound on every soyuz call made
from inside an agent run; soyuz's `audit_log` table (added
in soyuz `v0.2.0rc3`) attributes the mutation; the run-detail view
gains a "UC mutations" tab that joins them back together.

- **Added** [`pointlessql/services/soyuz_client.py`](pointlessql/services/soyuz_client.py)
  `make_soyuz_client(...)` and `make_principal_client(...)` accept
  an optional `agent_run_id` kwarg that lands as the
  `X-Agent-Run-Id` request header on every UC call the returned
  client makes.
- **Added** [`pointlessql/pql/pql.py`](pointlessql/pql/pql.py)
  `PQL.__init__` resolves the run id (explicit kwarg →
  `POINTLESSQL_AGENT_RUN_ID` env) before client construction so
  every PQL primitive's outbound UC traffic is attributable.
- **Added** [`pointlessql/services/soyuz_audit.py`](pointlessql/services/soyuz_audit.py)
  `fetch_for_run(uc_client, run_id, limit)` — read-only client for
  soyuz's `GET /audit-log?agent_run_id=` cross-reference surface,
  implemented via raw httpx (`get_async_httpx_client()`) since the
  generated client has no methods for `/audit-log` yet.  404
  collapses to `[]` so older soyuz versions degrade gracefully.
- **Added** [`pointlessql/api/runs_routes.py`](pointlessql/api/runs_routes.py)
  `_load_uc_mutations_for_run(request, run_id)` helper; the
  run-detail page passes `uc_mutations` into the template context.
- **Added** New "UC mutations" tab in `run_view.html` between Tool
  calls and Queries; renders action / target / principal / detail
  / created_at columns.  Empty-state copy spells out the
  `X-Agent-Run-Id` propagation contract and the soyuz `v0.2.0rc3`
  minimum.

Soyuz pin still at `v0.2.0rc2` — bumping to `v0.2.0rc3` pending a
push of the local soyuz tag.  The PointlesSQL code works against
any soyuz version: older soyuz returns 404 on `/audit-log` and the
UC mutations tab simply renders empty.

### Added — Sprint 14.3: external-write detection (2026-04-26)

Closes the third of four Phase-14 audit-trail gaps.  Delta commits
that bypassed every PQL primitive (raw `deltalake.write_deltalake()`,
Spark, `cp` of parquet, foreign tools) now surface in a dedicated
`unattributed_writes` table with a triage queue UI.  Detection-only
by design — see `project_full_autonomous_audit_critical_path.md`.

- **Added** Alembic `c3d4f5a6b7e8` — `unattributed_writes` table
  (`table_fqn` + `delta_version` UNIQUE, plus `acknowledged_at` /
  `detected_at` indexes).  Down-revision: `b27e6ad14ead`.
- **Added** [`pointlessql/services/external_write_scanner.py`](pointlessql/services/external_write_scanner.py) —
  `scan_table()` walks `DeltaTable(path).history(limit=N)` and
  diffs against `agent_run_operations.delta_version_after`;
  `scan_all()` enumerates every UC table via the async UC client;
  `list_unattributed()` / `acknowledge()` / `count_unacknowledged()`
  back the admin UI.  Reuses the
  `services/table_stats.read_delta_log_version` deltalake pattern;
  no raw `_delta_log/` JSON parsing.
- **Added** [`pointlessql/api/admin_external_writes_routes.py`](pointlessql/api/admin_external_writes_routes.py) —
  four admin-gated routes: GET HTML page, GET JSON list, POST scan
  trigger, POST acknowledge.
- **Added** Lifespan loop in [`pointlessql/api/main.py`](pointlessql/api/main.py)
  gated by `POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS`
  (default `0` = disabled — single-node vServer keeps the
  `DeltaTable.history()` cost off the critical path until an admin
  opts in).
- **Added** New `ExternalWritesSettings` sub-model
  (`scan_interval_seconds`, `history_limit`).
- **Added** Run-detail Operations tab gains a warning banner with
  the first 5 unattributed writes on tables this run touched
  (acknowledged-status filter), linking to `/admin/external-writes`.

### Added — Sprint 14.2: read-audit for `pql.table()` (2026-04-26)

Closes the second of four Phase-14 audit-trail gaps — the DSGVO
"wer hat meine Daten gelesen?" question for direct-Delta read paths
that bypassed `/api/sql/execute` entirely.

- **Added** Alembic `b27e6ad14ead` — `query_history.read_kind`
  TEXT NOT NULL DEFAULT `sql_execute` (down-revision:
  `a1c051a7e1ab`).  Enum validation lives in
  `record_query` against `VALID_READ_KINDS = {sql_execute,
  pql_table, engine_direct}` to match the existing
  application-level validation pattern (no DB CHECK).
- **Added** [`pointlessql/services/read_audit.py`](pointlessql/services/read_audit.py)
  `record_read()` — synthesises a `SELECT * FROM <fqn>` row so the
  existing `/queries` UI keeps working without per-`read_kind`
  branches.  Best-effort: silent passthrough when the session
  factory is unbound, swallows insert errors so audit can never
  break the read path.
- **Added** [`pointlessql/pql/_read.py`](pointlessql/pql/_read.py)
  instruments `read_table()` with a `record_read` call gated on
  `POINTLESSQL_AGENT_RUN_ID` being set, mirroring how `_sql.py`
  resolves run context.
- **Added** [`pointlessql/api/queries_routes.py`](pointlessql/api/queries_routes.py)
  `?read_kind=` filter on both `/queries` (HTML) and `/api/queries`
  (JSON); unknown values silently fall back to "no filter".
- **Added** Filter dropdown on `/queries`; "Kind" column with
  badge on both `/queries` and the run-detail Queries tab; empty-
  state copy mentions `pql.table()` reads explicitly.

### Added — Sprint 14.1: cost-gate EXPLAIN snapshot (2026-04-26)

Closes the first of four Phase-14 audit-trail gaps.  When the
Sprint-13.1 cost gate denies a query, reviewers can now see the
EXPLAIN plan that produced the verdict without re-running it.

- **Added** Alembic `a1c051a7e1ab` — `agent_runs.cost_gate_trigger`
  nullable JSON-as-Text column (down-revision: `b55f1020b8a4`).
- **Added** [`pointlessql/api/sql_routes.py`](pointlessql/api/sql_routes.py)
  `api_sql_explain` returns a new `cost_gate_trigger` field
  (`{explain, estimated_cost, threshold, engine, referenced_tables}`)
  in the response body when `needs_approval` is true.
- **Added** [`pointlessql/api/agent_runs_routes.py`](pointlessql/api/agent_runs_routes.py)
  `_coerce_cost_gate_trigger` helper; finish-route accepts the
  optional `cost_gate_trigger` body field; `serialize_agent_run`
  decodes it back to a dict.
- **Added** Run-detail metadata card (`run_view.html`) renders a
  collapsible Cost-gate-trigger row with badge + estimated/threshold
  numbers + EXPLAIN-JSON `<pre>` toggle (Alpine `:class` /
  `d-block`/`d-none` per `feedback_bootstrap_modal_x_show.md`).

### Changed — Sprint 14.0: Phase 14 scope split (2026-04-26)

Phase 14 in `ROADMAP.md` is now scoped exclusively to the
audit-trail completeness pass (former 14.x): cost-gate EXPLAIN
snapshot, read-audit for `pql.table()`, external-write detection,
soyuz UC-mutation cross-reference. Sprint sequence 14.1 → 14.4
fixed; cross-repo soyuz work intentionally last as the natural
synchronisation point.

The original Phase 14 public-launch track (GHCR-public flip,
PyPI publish, multi-arch builds, Helm chart, README pass) moved
to a new unscheduled `Some-day` block at the end of the roadmap
tree. License decision locked to Apache 2.0. Memory heuristic
*"Don't pre-build release engineering for one user"* (see
`feedback_release_engineering_timing.md`) gates promotion: the
block stays unscheduled until an external consumer asks.

The previously-listed *"Run-detail Tool calls UI tab"* sub-item
is dropped — already landed silently in
`frontend/templates/pages/run_view.html:235-240` during the
Sprint-13.7.4 window before the migrations squash.

Plan: `.claude/plans/plane-phase-14-komplett-floofy-nest.md`.

### Added — Sprint 13.11.11: PQL write endpoints (2026-04-26)

Closed the read-only gap on the agent's tool surface that the
2026-04-26 walkthrough surfaced — `gpt-5-mini` correctly noted
that `pql.autoload` was unreachable from the chat adapter.

- **Added** [`pointlessql/api/pql_write_routes.py`](pointlessql/api/pql_write_routes.py) —
  four `POST /api/pql/*` endpoints behind `check_privilege` +
  Sprint-13.8 forced audit trail:
  - `/autoload` — mirrors `PQL.autoload` (file → bronze).
  - `/write_table` — runs SELECT, materialises pandas, writes.
  - `/merge` — runs SELECT, upsert / SCD-2 into existing target.
  - `/drop_table` — admin-only soyuz delete passthrough.
- `write_table` + `merge` reuse `prepare_sql` +
  `register_delta_view` so SELECT-side parsing/enforcement
  stays consistent with `/api/sql/execute`.
- 9 route-level tests in
  [`tests/test_pql_write_routes.py`](tests/test_pql_write_routes.py)
  (admin happy-path, validation reject, non-admin denial per
  endpoint).

Plugin commit `hermes-plugin-pointlessql fa31742` adds the
matching four tools (`pql_autoload` / `pql_write_table` /
`pql_merge` / `pql_drop_table`) — 14 new tool tests, 80/80
pass.  Plugin tool surface now sits at 20 tools (16 + 4).

### Fixed — Sprint 13.11.5: live-Hermes hotfix

First real `hermes chat` smoke run after the Phase-13 close-out
exposed two latent bugs the unit tests couldn't catch — one
PointlesSQL-side, two on the plugin side.

- **Fixed** [`pointlessql/api/error_handlers.py`](pointlessql/api/error_handlers.py)
  `_handle_request_validation_error` — added a new `_json_safe`
  coercion helper that walks dicts/lists and decodes raw `bytes`
  to UTF-8 before returning the 422 body.  Without it a request
  posted with a JSON body but missing `Content-Type` made
  FastAPI surface the payload verbatim in the validation
  error's `input` field, and `json.dumps` then raised
  `TypeError: Object of type bytes is not JSON serializable` —
  flipping the 422 into an opaque 500.  New tests in
  [`tests/test_error_handler_json_safe.py`](tests/test_error_handler_json_safe.py)
  cover scalar pass-through, byte decoding (incl. invalid
  UTF-8 → replacement chars), nested structures, and the
  contract test that `json.dumps` round-trips cleanly.

The two plugin-side bugs (discovery shim + `Content-Type`
default + `finish_run` status default) ship in
`hermes-plugin-pointlessql 5676301`.

### Added — Sprint 13.11 walkthrough playbook

- **Added** [`docs/e2e-walkthroughs/sprint_13_11_reflexive_tools.md`](docs/e2e-walkthroughs/sprint_13_11_reflexive_tools.md)
  — API-centric replay with embedded Playwright-MCP-Befehle.
  Live-replayed 2026-04-26: all five Family-A routes return the
  expected payload, `pql_target_state(missing.table)` returns
  `exists=false` (the bug-2 catch), supervisor scope correctly
  returns `403` for the normal-key path on `/summary`, and
  `cost_gate_threshold` is **not** present in the
  supervisor-key response (anti-gaming guard verified).  The
  `/runs/{id}` UI surfaced the new tool-call-tab badge populated
  by the simulated `post_tool_call` POSTs.

### Added — Phase 13 / Sprint 13.11.4b: Detailed op-by-op + tool-call diff

Extends `GET /api/agent-runs/diff` with two optional parameters
(`detail=true` and `align=ordinal|content`) that surface the
op-by-op + tool-call-by-tool-call diff alongside the
Sprint-13.11.4a summary fields.

- **Added** [`pointlessql/services/run_diff.py`](pointlessql/services/run_diff.py)
  — pure-Python diff service.  Two alignment strategies:
  `"ordinal"` zips by index, `"content"` greedy-matches on
  `(op_name, target_table)` for operations and `tool_name` for
  tool calls.  Per-pair output emits `op_name_diff` /
  `target_table_diff` / `rows_affected_diff` /
  `delta_version_after_diff` / `error_diff` / `params_diff` only
  when those fields actually differ — keeps the LLM transcript
  small.  Tool-call diffs walk top-level keys of `args_json`.
  Combined slot count capped at 500 with a `truncated` marker.
- **Extended** `GET /api/agent-runs/diff` in
  [`pointlessql/api/agent_runs_routes.py`](pointlessql/api/agent_runs_routes.py)
  — accepts `detail: bool` + `align: ordinal|content`.  Bad
  `align` values are rejected by the FastAPI `Query(pattern=…)`
  validator with a 422.
- **Added** tests
  [`tests/test_run_diff_service.py`](tests/test_run_diff_service.py)
  (pure-unit alignment + diff coverage) and
  [`tests/test_diff_runs_route.py`](tests/test_diff_runs_route.py)
  (integration through the supervisor-Bearer auth path).

### Added — Phase 13 / Sprint 13.11.4a: DB-backed API keys + Family-B supervisor scope

API-key store promoted to a real DB table; new `supervisor` scope
gates the Sprint-13.11.4 supervisor-only routes.

- **Added** Alembic 025
  [`pointlessql/alembic/versions/025_api_keys_table.py`](pointlessql/alembic/versions/025_api_keys_table.py)
  — `api_keys` table with `(id, name, secret_hash, secret_prefix,
  supervisor, created_at, created_by_user_id, revoked_at,
  last_used_at)`. SHA-256-hex secret hashing; index on
  `secret_hash` for the hot-path verify.
- **Added** [`pointlessql/models/api_keys.py`](pointlessql/models/api_keys.py)
  ORM model + `ApiKey` re-export from `pointlessql.models`.
- **Refactored** [`pointlessql/services/api_keys.py`](pointlessql/services/api_keys.py)
  — `parse_keys` now returns `dict[str, tuple[str, bool]]` to
  carry the supervisor flag from the env-var format extension
  (`name:secret:supervisor`). `verify_bearer(authorization, factory)`
  is DB-backed with a 60s in-memory cache; `bootstrap_from_env`
  idempotently spills env-declared pairs into the table at
  startup; `create_api_key` / `revoke_api_key` / `list_api_keys`
  / `is_supervisor` / `invalidate_cache` are the new admin
  primitives.
- **Refactored** [`pointlessql/api/middleware.py`](pointlessql/api/middleware.py)
  — Bearer branch reads `request.app.state.session_factory` and
  attaches `request.state.api_key_supervisor` for the new gate.
- **Added** `require_supervisor(request)` in
  [`pointlessql/api/dependencies.py`](pointlessql/api/dependencies.py)
  — passes for cookie-admins and Bearer keys with
  `supervisor=True`; 403s otherwise.
- **Added** [`pointlessql/api/admin_api_keys_routes.py`](pointlessql/api/admin_api_keys_routes.py)
  with `GET/POST /api/admin/api-keys` and
  `POST /api/admin/api-keys/{name}/revoke`. Plaintext secret is
  returned exactly once at creation; rotations land via
  `audit()` rows.
- **Added** filter expansion on `GET /api/agent-runs`
  (`principal` / `agent_id` / `status` / `since`) +
  `GET /api/agent-runs/{id}/summary` +
  `GET /api/agent-runs/diff?a=&b=` in
  [`pointlessql/api/agent_runs_routes.py`](pointlessql/api/agent_runs_routes.py).
  The summary deliberately omits `cost_gate_threshold`
  (anti-gaming).
- **Updated** [`docs/auth.md`](docs/auth.md) — DB-backed store as
  primary; env-var as bootstrap; admin-CRUD examples; supervisor
  scope explained.
- **Tests**:
  [`tests/test_api_key_gate.py`](tests/test_api_key_gate.py) —
  rewritten for the new shape; covers parse_keys format
  extension, create/revoke/verify roundtrip, gate-disabled
  behaviour, cache invalidation, audit-row attribution.
  [`tests/test_admin_api_keys_routes.py`](tests/test_admin_api_keys_routes.py)
  — admin CRUD happy + non-admin 403.
  [`tests/test_supervisor_routes.py`](tests/test_supervisor_routes.py)
  — supervisor-key vs normal-key gating, summary payload shape,
  diff with tables_only_in_a/b.

### Added — Phase 13 / Sprint 13.11.3: Reflexive supervision tools (lineage)

- **Added** `GET /api/pql/lineage?table=…&depth=N` in
  [`pointlessql/api/pql_introspect_routes.py`](pointlessql/api/pql_introspect_routes.py)
  — wraps the existing `LineageMixin.get_lineage` async helper which
  fans out to soyuz's upstream + downstream JSON endpoints
  concurrently.  Depth capped at 5 via FastAPI `Query(le=5)` so
  invalid values are rejected before the soyuz call runs.
  No cross-repo work (the soyuz endpoints already exist).
- **Added** test
  [`tests/test_lineage_route.py`](tests/test_lineage_route.py)
  — covers combined-graph passthrough, three-part-name validation,
  and depth-out-of-range rejection.

### Added — Phase 13 / Sprint 13.11.2: Reflexive supervision tools (Family A pair 2)

Highest-ROI tools from the walkthrough bug analysis: agents can now
ask "does this target exist?" and "did similar writes fail
recently?" before acting.

- **Added** `GET /api/pql/target-state?table=catalog.schema.table` in
  [`pointlessql/api/pql_introspect_routes.py`](pointlessql/api/pql_introspect_routes.py)
  — fuses the principal-scoped UC `get_table` lookup with the
  Sprint-13.8 `agent_run_operations` history (last 5 writes) into
  one response. `CatalogNotFoundError` from the soyuz client maps
  to `exists=False`.
- **Added** `GET /api/agent-runs/operations` in
  [`pointlessql/api/agent_runs_routes.py`](pointlessql/api/agent_runs_routes.py)
  — filterable list of operation rows (`target`, `errored`,
  `since`, `limit`). Bad ISO-8601 in `since` raises a 422
  ValidationError so callers see the parse failure.
- **Added** test
  [`tests/test_target_state_route.py`](tests/test_target_state_route.py)
  — covers existence boolean, schema projection, three-part-name
  rejection, errored-only filtering, and ISO-parse failure.

### Added — Phase 13 / Sprint 13.11.1: Reflexive supervision tools (Family A pair 1)

First slice of the Sprint-13.11 read-loop close-out: agents can now
introspect *what* the PQL primitives are and *what they themselves*
have already written.

- **Added** [`pointlessql/api/pql_introspect_routes.py`](pointlessql/api/pql_introspect_routes.py)
  — new router with `GET /api/pql/primitives` returning
  `{primitives: {<name>: {signature, doc, ...}}}` for the public
  PQL surface (`table`, `sql`, `write_table`, `merge`, `autoload`).
  Snapshot built once at import via `inspect.signature` +
  `inspect.getdoc`; static for the process lifetime.
- **Added** `GET /api/agent-runs/{run_id}/full` in
  [`pointlessql/api/runs_routes.py`](pointlessql/api/runs_routes.py)
  — joins the serialised run row with `_load_source_for_run`,
  `_load_operations_for_run`, `_load_tool_calls_for_run`,
  `_load_events_for_run`, `_load_queries_for_run` so a Hermes
  plugin tool can fetch the full supervision payload in one
  round-trip.
- **Added** tests
  [`tests/test_pql_introspect_routes.py`](tests/test_pql_introspect_routes.py)
  and [`tests/test_agent_run_full.py`](tests/test_agent_run_full.py)
  — covers the regression-shaped check that `autoload`'s signature
  carries `source_path` (the 2026-04-25 walkthrough bug), 404
  behaviour for unknown run ids, and the round-trip after a
  `tool-call` POST.

### Fixed — Phase 13 / Sprint 13.10: Hermes-Medallion live-replay fixups

Closes the four findings from the 2026-04-25 manual walkthrough
replay so the Sprint-13.5.5 playbook is reproducible end-to-end
without manual workarounds.

- **Fixed** [`notebooks/hermes_medallion.py`](notebooks/hermes_medallion.py)
  — three API-shape bugs that hit on the first cell:
  `pql.autoload(source=…)` → `source_path=…`, dict result-access
  for `bronze_result["rows_ingested"]` (autoload returns a
  dict, not a dataclass), and `pql.sql("CREATE OR REPLACE TABLE…")`
  rewritten as `pql.table` → pandas aggregate → `pql.write_table`
  (`pql.sql` is SELECT-only with an explicit approved-tables
  guard).  Silver step keeps a try/except bootstrap to
  `pql.write_table` on first-ever run because `pql.merge`
  requires the target to exist (Sprint 13.5.2 contract; a
  future `pql.merge(create=True)` flag is out of scope here).
- **Added** lazy metadata-DB init in [`PQL.__init__`](pointlessql/pql/pql.py).
  When the resolver finds an `agent_run_id` (explicit kwarg or
  `POINTLESSQL_AGENT_RUN_ID` env) and the session factory is
  unbound, the constructor calls
  [`pointlessql.db.init_db`](pointlessql/db.py) against
  `settings.db.url`.  Subprocess-spawned agent notebooks that
  bypass the FastAPI lifespan no longer need a manual
  `init_db()` boilerplate; the interactive PQL path stays
  untouched because the branch is gated on a truthy run id.
  Idempotent — Alembic upgrade-to-head is a no-op once head
  is reached.
- **Added** "Tool calls" tab to
  [`pages/run_view.html`](frontend/templates/pages/run_view.html)
  between Operations and Queries, plus a new
  `_load_tool_calls_for_run` helper in
  [`api/runs_routes.py`](pointlessql/api/runs_routes.py).
  Backend (Alembic 024 + `POST /api/agent-runs/{id}/tool-call`
  + `pointlessql.agent_run.tool_call` CloudEvent) shipped in
  Sprint 13.7.4; the template tab was deferred until now.
  Lists each `agent_run_tool_calls` row with truncated
  `args_json` + `result_summary` and the wall-clock duration.
- **Updated** [`docs/e2e-walkthroughs/hermes_medallion.md`](docs/e2e-walkthroughs/hermes_medallion.md)
  precondition 2 — schema bootstrap is now an explicit `curl`
  loop that sets `storage_root` on `POST /schemas`.  Cross-
  references the soyuz `docs/reference/api.md` note that
  `UpdateSchema` deliberately rejects `storage_root` (UC
  semantics: set-on-create, mutating it would orphan managed
  Delta files).

### Added — Phase 13.5 / Sprint 13.5.5: Hermes-Medallion walkthrough

The reproducible **done moment** for Phase 13 + 13.5: an
end-to-end demo where a real Hermes agent (with
`hermes-plugin-pointlessql` loaded) builds a three-layer
Medallion lakehouse from a CSV in a UC Volume.  The supervision
trail in `/runs/{id}` shows Source + Operations + Tool calls +
Queries + Conformance — every primitive Phase 13 + 13.5 + 13.7
shipped exercises in one flow.

- **New** [`notebooks/hermes_medallion.py`](notebooks/hermes_medallion.py)
  — agent-authored task notebook (jupytext percent format with
  cells for human replay).  Calls
  [`pql.autoload`](pointlessql/pql/_autoload.py) to build
  bronze, [`pql.merge`](pointlessql/pql/_merge.py) (upsert
  strategy) to build silver, and
  [`pql.sql`](pointlessql/pql/_sql.py) (`CREATE OR REPLACE
  TABLE`) for the gold daily-revenue aggregation.  Each
  primitive auto-emits an `agent_run_operations` row through
  the Sprint-13.8 `operation_context` because
  `POINTLESSQL_AGENT_RUN_ID` is set by the plugin's
  `on_session_start` hook.
- **New** [`notebooks/hermes_medallion_data/orders.csv`](notebooks/hermes_medallion_data/orders.csv)
  — 50-row deterministic fixture so the playbook is replayable
  without any external download.
- **New** [`docs/e2e-walkthroughs/hermes_medallion.md`](docs/e2e-walkthroughs/hermes_medallion.md)
  — step-by-step playbook covering Hermes session start →
  notebook execution → run-detail tabs → CloudEvents
  verification → cleanup, with explicit Playwright-MCP commands
  for the browser-side replay per
  `feedback_run_playbook_as_gate.md`.
- **Updated** [`docs/e2e-walkthroughs/README.md`](docs/e2e-walkthroughs/README.md)
  — adds entry 13 alongside the existing Drift-Monitor demo
  (entry 12).

### Added — Phase 13 / Sprint 13.7.4: Tool-call audit + post_tool_call hook

Fourth orthogonal level of the run trail (alongside cells /
operations / queries): the LLM's tool-invocation record. The
``hermes-plugin-pointlessql`` ``post_tool_call`` hook posts every
``pql_*`` invocation here so a human reading ``/runs/{id}`` can
reconstruct the LLM's reasoning trace.

- **New** Alembic [024_agent_run_tool_calls.py](pointlessql/alembic/versions/024_agent_run_tool_calls.py)
  — creates ``agent_run_tool_calls(id, agent_run_id, tool_name,
  args_json, result_summary, duration_ms, called_at)`` with FK
  to ``agent_runs.id`` and a composite ``(agent_run_id,
  called_at)`` index for the run-detail tab. Round-tripped
  upgrade/downgrade clean against the disposable DB harness.
- **New** :class:`pointlessql.models.AgentRunToolCall` ORM model
  in [pointlessql/models/agent_run_audit.py](pointlessql/models/agent_run_audit.py).
- **New** ``POST /api/agent-runs/{run_id}/tool-call`` route in
  [pointlessql/api/agent_runs_routes.py](pointlessql/api/agent_runs_routes.py).
  Lenient on optional fields (``args_json`` accepts dict OR
  string; ``called_at`` defaults to wall-clock; ``result_summary``
  truncates at 2000 chars). Audit row + Sprint-13.3 CloudEvent
  ``pointlessql.agent_run.tool_call`` fire after persistence.
- **New** ``EVENT_TYPE_TOOL_CALL`` constant added to
  :data:`AGENT_RUN_EVENT_TYPES`.
- **New** [`tests/test_agent_run_tool_calls.py`](tests/test_agent_run_tool_calls.py)
  — 7 cases covering happy path + validation 422 + 404 + dict
  args + truncation + parent-run integrity.

### Added — Phase 13 / Sprint 13.7 (in progress): Hermes plugin enablers

Sprint 13.7 ships in slices because the plugin lives in a
sibling repo (`~/git/hermes-plugin-pointlessql`) and the
PointlesSQL deltas are kept minimal. This entry tracks the
PointlesSQL-side changes Sprints 13.7.1 – 13.7.3 needed:

- **New** [`pointlessql/api/conventions_routes.py`](pointlessql/api/conventions_routes.py)
  — `GET /api/conventions` returns the resolved Medallion
  conventions (`yaml`) plus the prose contract excerpt from
  [`docs/data-layers.md`](docs/data-layers.md). Read-only,
  authenticated, intended for the plugin's `pql_conventions`
  tool.
- **New** route in
  [`pointlessql/api/catalog_routes.py`](pointlessql/api/catalog_routes.py)
  — `GET /api/catalogs/{c}/schemas/{s}/tables/{t}` exposes one
  table's full UC metadata (columns + tags + comment) as JSON
  so the plugin's `pql_get_table` tool does not have to scrape
  the HTML browser. Gated on USE_SCHEMA on the parent schema.
- **New** [`tests/test_conventions_route.py`](tests/test_conventions_route.py)
  covering the conventions endpoint shape + the auth-required
  401 path.

### Added — Phase 13 / Sprint 13.7.0.5: Front-loaded API-key gate

Bearer-token auth path so the upcoming
``hermes-plugin-pointlessql`` (Sprint 13.7.1+) can reach
``/api/agent-runs`` and ``/api/sql/*`` without holding a session
cookie. Closes the multi-tenant auth gap recorded as Tier-3 in
``project_phase13_audit_gaps.md`` ahead of the Phase-14 visibility
flip — instead of shipping the plugin against localhost-trust and
migrating later.

- **New** [`pointlessql/services/api_keys.py`](pointlessql/services/api_keys.py)
  — parses ``POINTLESSQL_API_KEYS`` (newline- or comma-separated
  ``name:secret`` pairs), constant-time matches Bearer headers,
  short-circuits when the env var is empty so the local-dev
  flow keeps working unchanged.
- **Extended** :func:`pointlessql.api.middleware.auth_middleware`
  — falls back to Bearer-token verification when no cookie user
  resolved.  On match attaches a synthetic
  :class:`~pointlessql.types.UserInfo` (``id=0``,
  ``email="api_key:<name>"``) plus ``request.state.api_key_name``
  so downstream routes need no awareness.  Cookie auth always
  wins when both are present.
- **Extended** :func:`pointlessql.api._audit_helpers.audit` —
  Bearer-only requests (``user_id == 0``) now leave audit rows
  with ``actor_role="system"``, ``user_email="api_key:<name>"``
  (or the ``X-Principal`` value when set), and a
  ``detail.api_key`` marker.  The pre-Sprint-13.7.0.5 early-
  return on ``user_id == 0`` would have dropped these rows.
- **New** [`docs/auth.md`](docs/auth.md) — env-var format,
  rotation flow, audit-attribution table, and the rationale for
  picking Bearer over OIDC client-credentials for the first
  external runtime.
- **New** tests in [`tests/test_api_key_gate.py`](tests/test_api_key_gate.py)
  — 17 cases covering parser edge cases, constant-time
  verification, gate-disabled passthrough, cookie-wins precedence,
  and end-to-end ``X-Principal``-overrides-attribution.

### Added — Phase 13 / Sprint 13.9: Run-scoped query history

Smaller follow-up to 13.8: every ``query_history`` row can now
carry the owning ``agent_run_id`` so the run-detail view can
answer "which queries did this run execute?" and the standalone
``/queries`` page accepts a sub-view filter.

- **New** Alembic [023_query_history_agent_run.py](pointlessql/alembic/versions/023_query_history_agent_run.py)
  — adds nullable ``agent_run_id String(36)`` column to
  ``query_history`` plus a partial index (``IS NOT NULL``).  No
  FK by design so query history outlives a deleted run.
- **New** :func:`pointlessql.api._audit_helpers.effective_agent_run_id`
  — resolves the active run UUID from ``X-Agent-Run-Id`` header
  (HTTP wins) → ``POINTLESSQL_AGENT_RUN_ID`` env var.
- ``record_query_async`` and the underlying
  :func:`pointlessql.services.query_history.record_query` accept
  an ``agent_run_id`` kwarg; non-UUID-shaped values are dropped
  with a warning so query history stays tolerant.
- ``GET /queries`` and ``GET /api/queries`` accept a
  ``?agent_run_id=`` query parameter; the HTML page surfaces a
  dismissable filter pill linking back to ``/queries``.
- Run-detail-view gained a **Queries** tab between *Operations*
  and *Source* listing the matching ``query_history`` rows with
  a deep-link to the filtered ``/queries`` page.
- **Tests** — [tests/test_query_history_run_scope.py](tests/test_query_history_run_scope.py)
  covers persistence, garbage drop, filter, header→history
  attribution, the page-level filter pill, and the new tab.

### Added — Phase 13 / Sprint 13.8: Forced audit trail

Closes the four supervision gaps surfaced during the 2026-04-24
Drift-Monitor live demo: post-run source mutability, missing
per-operation trace, ephemeral CloudEvents, and unenforced
runtime-version capture.  Every PQL primitive now emits a
forensically-defensible row before touching DuckDB or deltalake,
and the run-detail view surfaces the new dimensions through a
five-tab layout.

- **New** Alembic [022_agent_run_audit_trail.py](pointlessql/alembic/versions/022_agent_run_audit_trail.py)
  — three tables (``agent_run_sources`` UNIQUE per run,
  ``agent_run_operations`` with ordinal + delta version pre/post +
  input SHA + row count, ``agent_run_events`` mirroring Sprint-55
  ``alert_events``), plus a ``runtime_versions`` JSON column on
  ``agent_runs``.
- **New** [pointlessql/models/agent_run_audit.py](pointlessql/models/agent_run_audit.py)
  — :class:`AgentRunSource`, :class:`AgentRunOperation`, and
  :class:`AgentRunEvent` ORM mappings.
- **Strict** ``POST /api/agent-runs`` now requires both ``source``
  (UTF-8 ``.py`` text) and ``runtime_versions``
  (non-empty ``{name: version}``) and 422s without them.  Server
  hashes the source server-side and 422s on
  ``source_snapshot_sha`` mismatch (tamper-detection).  The
  source bytes land in ``agent_run_sources`` inside the same
  transaction as the new ``agent_runs`` row.
- **New** [pointlessql/exceptions.py](pointlessql/exceptions.py)
  ``AuditUnavailableError`` (503) — raised by the new
  :func:`pointlessql.services.agent_runs.record_operation` /
  :func:`operation_context` helpers when the trail row cannot be
  persisted, so PQL primitives refuse to execute without a trail.
- **PQL hooks** — :class:`pointlessql.pql.PQL` gained an
  ``agent_run_id`` constructor kwarg paralleling ``principal``;
  resolution falls back to ``POINTLESSQL_AGENT_RUN_ID``.  Each of
  ``write_table`` / ``merge`` / ``autoload`` / ``sql`` wraps its
  work in :func:`operation_context` and writes one
  ``agent_run_operations`` row, capturing input Arrow-IPC SHA
  ([_hashing.py](pointlessql/pql/_hashing.py)) and Delta version
  pre/post via the new public :func:`safe_delta_version` helper.
- **CloudEvents persistence** — every envelope is INSERTed into
  ``agent_run_events`` with ``outcome="pending"`` *before*
  dispatch; the dispatcher result flips it to ``"delivered"`` /
  ``"delivery_failed"`` / ``"no_destination"``.  Webhook outages
  no longer lose lifecycle events.
- **Run-detail-view** — Bootstrap-5 nav-tabs replace the linear
  card stack: Cells / Operations / Source / Events / Audit log.
  Cells stays the default tab so existing muscle memory keeps
  working; the new tabs surface the strict audit dimensions.
- **Tests** — [tests/test_agent_run_audit.py](tests/test_agent_run_audit.py)
  covers the strict 422 paths, source/SHA persistence, ordinal
  allocation, failure-row recording, audit re-raise, event
  outcome transitions, and the new tab markup.

### Added — Phase 13 / Sprint 13.5: Drift-Monitor demo agent + walkthrough

Closes the Phase-13 autonomous run with the first end-to-end
demo that exercises every Sprint-13.x primitive in a single
flow.  Hermes (or any plug-compatible runtime) registers a run,
fires the notebook, terminates the run; PointlesSQL records,
audits, conformance-checks, and CloudEvents-emits along the
way.

- **New** [notebooks/agent_drift_monitor.py](notebooks/agent_drift_monitor.py)
  — a jupytext-percent-format `.py` notebook that reads a
  bronze table via :class:`pointlessql.pql.PQL`, computes
  freshness (newest ``_ingested_at``), null-rate per non-audit
  column, and (TODO) value-drift against Sprint-54 column
  stats.  Appends one row per check to
  ``main.ops.quality_history``.  Emits a Sprint-13.3
  ``pointlessql.agent_run.failed`` CloudEvent on threshold
  breach (env-driven thresholds; default 20% null-rate / 24h
  freshness).
- **New** [docs/e2e-walkthroughs/agent_drift_monitor.md](docs/e2e-walkthroughs/agent_drift_monitor.md)
  — replayable Markdown playbook for human or Playwright-MCP
  reproduction.  Covers register → run → terminate → control-
  room verification → conformance card → audit log → CloudEvent
  payload, all attributed to ``X-Principal: drift-monitor@ops.local``
  (Sprint 13.6).
- **README** entry under "Agent supervision" so the new
  playbook is discoverable next to the Sprint-22/23/40 ones.
- **Ruff config**: ``notebooks/**`` joins ``tests/**`` in the
  per-file ignore list for D-rules — module-level docstrings
  would duplicate the percent-format's first markdown cell.

### Added — Phase 13 / Sprint 13.6: ``X-Principal`` forwarded into PQL session + audit

The Sprint-13.2 registry already accepted the ``X-Principal``
header; Sprint 13.6 propagates it through every downstream
attribution surface so a Hermes-driven query is checked + audited
under the agent's principal, not the (probably-empty)
session-cookie user on the agent side.

- **New** :func:`pointlessql.api.dependencies.effective_principal`:
  reads ``X-Principal`` header, falls back to the session-cookie
  user's email, returns ``None`` for anonymous.
- **Updated** :func:`get_uc_client` to use the effective principal
  — UC SELECT enforcement (in ``/api/sql/execute`` and
  ``/api/sql/explain``) now runs as the header value when set.
- **Updated** :func:`pointlessql.api._audit_helpers.audit` and
  :func:`record_query_async` to attribute the audit log /
  query-history rows to the effective principal email.  ``user_id``
  stays the cookie user's id — that's the actor whose session
  signed the request, even when they're acting on someone else's
  behalf.
- **PQL constructor** now accepts an explicit
  ``principal: str | None = None`` keyword argument so a Hermes
  plugin (or any other process spawning PQL programmatically) can
  pass the agent's principal without mutating the process env.
  Resolution order: explicit ``client`` > explicit ``principal``
  arg > ``POINTLESSQL_PRINCIPAL`` env > unforwarded client.
- **No backend schema change**.

### Added — Phase 13.5 / Sprint 13.5.4: Conformance check on ``/runs/{id}``

Passive surface — the run-detail view flags Medallion contract
violations on each ``tables_touched`` entry.  Visibility, not
enforcement; Phase 15+ may convert selected checks into shoreguard
policies if real demand surfaces.

- **Layer inference** by schema-name match against the
  Sprint-13.5.1 conventions (``main.bronze.x`` → bronze, etc.).
  Tables outside the convention are silently passed.  The
  ``layer_tag_key`` UC-tag hook stays a future override path
  when the soyuz client surfaces tags.
- **Bronze** check: every ``required_audit_columns`` entry
  must be present.  Missing audit columns are ``error`` severity
  — provenance is broken for new appends.
- **Silver** hint (info): no SCD-2 columns AND no ``id`` /
  ``key``-suffixed column → "confirm dedup is happening upstream".
- **Gold** hint (info): more than 50 columns → "consider whether
  dimensions should split".
- **Findings render** as a coloured table card on the detail
  view, between metadata and the approval panel.  Failures of
  the conformance check itself (catalog hiccup, table dropped
  mid-render) are silently skipped — passive principle.

### Added — Phase 13 / Sprint 13.4: ``/runs`` filter bar + approval panel

The supervision list is now filterable, sortable, and gated.
External runtimes still POST runs in via Sprint 13.2's registry;
Sprint 13.4 makes the page actually usable for an operator with
many runs.

- **Filter bar** on
  [frontend/templates/pages/runs_list.html](frontend/templates/pages/runs_list.html)
  via the existing Alpine ``listTable`` component (search box +
  six status chips: queued, running, needs_approval, succeeded,
  failed, denied).  Sortable headers (id / principal / agent /
  status / cost / started_at).  Adds a Cost-est and a
  Tables-touched column.  Client-side filtering by design — 200
  rows is well within client-side cost and the page render stays
  cacheable.
- **Approval panel** on
  [frontend/templates/pages/run_view.html](frontend/templates/pages/run_view.html)
  appears only when ``run.status == 'needs_approval'`` AND
  ``current_user.is_admin``.  Two Alpine-backed buttons (Approve,
  Deny with optional reason textarea) POST to the existing
  Sprint-13.2 ``/api/agent-runs/{id}/approve`` + ``/deny``
  endpoints and reload on success.  Non-admins see a clean
  metadata view with no buttons.
- **Tables-touched** rendered as catalog-link badges on the
  detail view.
- **Audit-log sidebar** at the bottom of the detail view,
  filtered by ``target = "agent_run:{id}"`` so the
  create / approve / deny trail is on one screen with the run.
- **No backend schema change**; new helper
  ``_load_audit_entries_for_run`` joins existing AuditLog rows
  by target.
- **Browser-replay note**: a dedicated ``/runs`` playbook does
  not yet exist — the Sprint-13.5 Drift-Monitor walkthrough will
  exercise this surface end-to-end in Firefox.  Template-render
  smoke verifies admin / non-admin branching + Alpine attribute
  syntax in the meantime.

### Added — Phase 13.5 / Sprint 13.5.3: ``pql.autoload()`` primitive

The third Phase-13.5 building block: lifts files from a Volume
directory into a bronze Delta target with audit columns and
file-level exactly-once.  Closes the autoload → bronze leg of the
Hermes-Medallion demo (Sprint 13.5.5).

- **Alembic 021** at
  [pointlessql/alembic/versions/021_autoload_checkpoints.py](pointlessql/alembic/versions/021_autoload_checkpoints.py)
  creates ``autoload_checkpoints`` (id, source_path, file_sha,
  target_table, ingested_at, rows_ingested) with a unique
  constraint on ``(target_table, file_sha)`` backing the
  "have-I-done-this?" dedup probe and an index on
  ``(target_table, source_path)`` for control-room listing.
- **ORM model** at
  [pointlessql/models/autoload.py](pointlessql/models/autoload.py)
  re-exported from ``pointlessql.models`` alongside ``AgentRun``.
- **New** :meth:`pointlessql.pql.PQL.autoload` with signature
  ``autoload(source_path, target, *, source_system="",
  file_format="auto"|"parquet"|"csv"|"json")``.  ``source_path``
  is a local filesystem directory (recursive walk) or glob
  pattern — Volumes-as-managed-directories.  HTTP-fetched-Volume
  support stays a follow-up sprint.
- **DuckDB** does the type inference (``read_parquet`` /
  ``read_csv_auto`` / ``read_json_auto``); ``deltalake`` does the
  append (creates the table on first call).  When the target
  doesn't exist in soyuz-catalog yet, the first successful
  append registers it via the same ``CreateTable`` path that
  :func:`pointlessql.pql._write.write_table` uses.
- **Audit columns** (``_ingested_at`` / ``_source_file`` /
  ``_source_system``) are pulled from
  :func:`pointlessql.conventions.load_conventions` so the column
  names track the Sprint-13.5.1 contract.  Operators who strip
  audit columns via ``pointlessql.yaml`` get a clean schema (no
  audit injection).
- **MVP scope**: file-level exactly-once via SHA-256 of file
  bytes.  Per-row dedup + schema-drift handling are deferred to
  Sprint 13.5.3b (the ROADMAP's split-allowed flag).
- **No new top-level deps**; SHA-256 is stdlib ``hashlib``.

### Added — Phase 13.5 / Sprint 13.5.2: ``pql.merge()`` primitive

The second of three Phase-13.5 building blocks for agent-authored
Medallion lakehouses (autoload → bronze in 13.5.3, merge →
silver here, SQL aggregation → gold in user code).  Thin facade
over ``deltalake.DeltaTable.merge()``.

- **New** :meth:`pointlessql.pql.PQL.merge` with signature
  ``merge(source, target, *, on=[...], strategy="upsert"|"scd2")``.
  ``source`` accepts a pandas DataFrame, a PyArrow Table, or a
  UC ``"catalog.schema.table"`` reference (resolved through the
  existing :meth:`PQL.table` read path).  ``target`` is a UC
  reference that **must already exist** — ``merge()`` does not
  bootstrap; that's autoload's job in 13.5.3.
- **Upsert** path uses ``when_matched_update_all`` +
  ``when_not_matched_insert_all``; non-key columns are taken
  from source on match.
- **SCD-2** path is two-phase: a MERGE that closes any
  currently-open target row whose key matches source
  (``_valid_to = now``, ``_is_current = false``), then a
  ``write_deltalake(mode="append")`` that adds every source row
  as a new current version with ``_valid_from = now``,
  ``_valid_to = null``, ``_is_current = true``.  Documented MVP
  caveat: closes + reopens for *every* source key match, even
  when values are unchanged — pre-filter the source if you need
  churn-free history.  Change detection deferred to a follow-up.
- The SCD-2 column names (``_valid_from`` / ``_valid_to`` /
  ``_is_current``) are hardcoded in the primitive — they're
  silver-layer specific (audit columns in
  :mod:`pointlessql.conventions` are bronze-specific).  Future
  sprint can promote them to a configurable
  :class:`LayerConvention` field if a real override case
  appears.
- **No new top-level deps** (deltalake + pyarrow already pinned),
  no schema change.

### Added — Phase 13 / Sprint 13.1: ``GET /api/sql/explain`` + cost estimator

The Sprint 13.7 Hermes plugin and the Sprint 13.4 run-detail
view now have a cheap ahead-of-execution cost gate: parse, run
DuckDB ``EXPLAIN (FORMAT JSON)``, walk the plan, return a
``cost`` heuristic with ``needs_approval`` set above the
configured threshold.

- **New endpoint** ``GET /api/sql/explain?sql=...`` at
  [pointlessql/api/sql_routes.py](pointlessql/api/sql_routes.py).
  Same parse + UC-SELECT-enforce front-half as the existing
  ``/api/sql/execute`` (a caller cannot EXPLAIN a query whose
  tables they cannot read — that would leak schema through the
  plan).  Audit action: ``query.explained``.
- **Estimator** in
  [pointlessql/services/sql/cost_estimator.py](pointlessql/services/sql/cost_estimator.py)
  walks the plan tree, picks up ``estimated_cardinality`` /
  ``cardinality`` / ``rows`` at the node root *and* DuckDB 1.x's
  nested ``extra_info["Estimated Cardinality"]`` (string-encoded).
  Counts join nodes by name substring.  Cost =
  ``max_cardinality × (1 + join_depth)``; deliberately simple,
  with a ``CostEstimate.explanation`` one-liner the agent can
  paraphrase back to its human reviewer.
- **Runner** in
  [pointlessql/services/sql/explain.py](pointlessql/services/sql/explain.py)
  registers Delta tables on a fresh in-process DuckDB connection
  via the existing ``register_delta_view`` helper, runs
  ``EXPLAIN (FORMAT JSON)``, parses the JSON cell, hands the
  result to the estimator.  No row materialisation, no
  cancellation registry — EXPLAIN is plan-only.
- **Settings**: ``cost_gate_threshold_rows: int = 1_000_000``
  added to ``SQLSettings`` (env var
  ``POINTLESSQL_SQL_COST_GATE_THRESHOLD_ROWS``).  Above the
  threshold the response carries ``needs_approval: true``; no
  enforcement happens here — the agent or run-detail UI decides
  what to do with the flag.
- **No new top-level deps**; no schema change.

### Added — Phase 13 / Sprint 13.3: CloudEvents ``agent_run`` envelope

The Sprint-13.2 registry now fans the agent-run lifecycle out to
external subscribers: every ``POST /api/agent-runs`` and every
terminal ``POST /api/agent-runs/{id}/finish`` fires a CloudEvents
1.0 envelope.  External listeners (the future
``hermes-plugin-pointlessql``, Paperclip, an ops dashboard) learn
about runs without polling.

- **New envelope vocabulary** at
  [pointlessql/services/agent_runs/events.py](pointlessql/services/agent_runs/events.py):
  ``pointlessql.agent_run.started`` (on create),
  ``pointlessql.agent_run.completed`` (terminal status
  ``succeeded``), ``pointlessql.agent_run.failed`` (terminal
  status ``failed``).  ``denied`` is intentionally silent —
  Sprint 13.3's vocabulary covers execution outcomes, not human
  approval decisions.  ``cell_completed`` (the ROADMAP's fourth
  type) lands when the per-cell POST route does, in a future
  sprint.
- **Webhook delivery** reuses the Sprint-55
  ``dispatch_webhook`` (HMAC-SHA256 ``X-PointlesSQL-Signature``,
  ``Content-Type: application/cloudevents+json``, 5s connect /
  10s read, two retries with exponential backoff, 4xx-vs-5xx
  semantics).  The destination is a single URL pulled from the
  new :class:`pointlessql.settings.AgentRunsSettings` —
  ``POINTLESSQL_AGENT_RUNS_WEBHOOK_URL`` +
  ``POINTLESSQL_AGENT_RUNS_WEBHOOK_HMAC_SECRET``.  The richer
  per-destination subscription model (multiple URLs,
  per-event-type filters) lands with Sprint 13.4 when the
  control-room UI surfaces it.
- **Failure mode**: emitter logs and never raises into the route
  — a flaky webhook must not prevent the run row from being
  recorded.  When no URL is configured the emitter is a debug-
  level no-op, so dev and tests don't have to mock anything.
- **No new top-level deps**; no schema change.

### Added — Phase 13.5 / Sprint 13.5.1: Medallion conventions + ADR 0002-duckdb-first

First sprint of Phase 13.5.  Ships the *opinionated primitives*
that turn an agent-authored Delta write into a real Medallion
lakehouse.  No runtime code — the data + parser only; the
Sprint-13.7 Hermes plugin will surface
:func:`pointlessql.conventions.load_conventions` as a
``pql_conventions()`` tool.

- **New package** ``pointlessql/conventions/`` exposes
  :func:`load_conventions`, :data:`DEFAULT_CONVENTIONS`,
  :class:`ConventionsConfig`, and :class:`LayerConvention`.  The
  built-in defaults encode bronze (with audit columns
  ``_ingested_at`` / ``_source_file`` / ``_source_system``) →
  silver (deduped/typed/conformed) → gold (business facts +
  star-schema-ready), tagged via UC tag key ``layer``.
- **YAML override** parser (``pointlessql.yaml``) with shallow
  merge over the defaults; ``POINTLESSQL_CONVENTIONS_PATH`` env
  var resolves the file (loud ``FileNotFoundError`` on typos so
  silent fallthrough doesn't mask config bugs).  Annotated
  example at [pointlessql.yaml.example](pointlessql.yaml.example).
- **Settings** gain a nested
  :class:`pointlessql.settings.ConventionsSettings` with a single
  ``path: Path | None`` field, slotted alongside the existing
  ``delta`` / ``sql`` sub-models.
- **Prose contract** at [docs/data-layers.md](docs/data-layers.md)
  describes the three layers, the audit-column requirement on
  bronze, and the ``layer`` UC tag.
- **ADR 0002** at
  [docs/adr/0002-duckdb-first.md](docs/adr/0002-duckdb-first.md)
  documents the compute-engine decision: DuckDB owns compute
  (SQL editor, EXPLAIN gate, column stats, the new merge /
  autoload primitives), ``deltalake`` Python owns writes,
  storage / catalog / runtime stay pluggable.

### Added — Phase 13 / Sprint 13.2: ``agent_runs`` Alembic table + HTTP registry

First implementation sprint of Phase 13 (revised).  PointlesSQL
becomes the *registry + store* for agent runs — external runtimes
(Hermes, OpenShell, curl'd cron jobs) POST lifecycle transitions in,
the control-room shows them, and no executor ships in this repo.

- **Alembic 020** creates ``agent_runs`` (UUIDv4 string id,
  ``principal``, ``agent_id``, ``notebook_path``,
  ``source_snapshot_sha``, ``status`` ∈ {``queued``, ``running``,
  ``needs_approval``, ``approved``, ``denied``, ``succeeded``,
  ``failed``}, ``cost_est`` NUMERIC(18,4), ``tables_touched`` JSON-
  encoded, ``started_at`` / ``finished_at``, ``exit_code``,
  ``approved_by`` / ``approved_at`` / ``denied_reason``).  Three
  ``ix_agent_runs_{started_at, principal, status}`` indexes back the
  control-room's newest-first + per-principal + per-status filters
  that Sprint 13.4 will add.  Adds nullable ``agent_run_id VARCHAR(36)``
  columns + indexes to ``notebook_outputs`` and ``notebook_cell_runs``
  so per-cell writes from the runtime join back to their owning run
  without a ``kernel_session_id`` heuristic.

- **SQLAlchemy model** at
  [pointlessql/models/agent_runs.py](pointlessql/models/agent_runs.py),
  re-exported from ``pointlessql.models`` alongside the existing
  ``AlertDestination`` / ``JobRun`` family; status-machine constants
  (``VALID_STATUSES`` / ``TERMINAL_STATUSES``) ship next to the
  model so the routes never hard-code the set.  The notebook models
  gain the matching ``agent_run_id`` column + docstring entry.

- **HTTP registry** at
  [pointlessql/api/agent_runs_routes.py](pointlessql/api/agent_runs_routes.py):
  ``POST /api/agent-runs`` (create; ``X-Principal`` header wins over
  any body ``principal`` so the HTTP hop is authoritative from day
  one — prepares Sprint 13.6); ``POST /api/agent-runs/{id}/finish``
  (terminal-state transition; refuses re-finishing so supervision
  history is immutable); ``GET /api/agent-runs`` (JSON list, newest
  first, capped at 500); ``POST /api/agent-runs/{id}/approve`` +
  ``/deny`` (admin-gated via the existing ``require_admin``
  dependency, ready for the Sprint 13.4 control-room buttons).

- **Control-room pages** —
  [pointlessql/api/runs_routes.py](pointlessql/api/runs_routes.py)
  drops the Sprint 12.12.2 empty-list stub.  ``GET /runs`` queries
  the 200 most recent rows and hands them to the existing
  ``runs_list.html`` template; ``GET /runs/{id}`` loads the row,
  parses the underlying ``.py`` via
  ``services/notebook_doc.load_document``, joins per-cell outputs +
  cell runs on ``agent_run_id``, and renders the Sprint 12.12.1
  ``run_view.html`` card deck with live data.  Missing notebook
  files degrade to a metadata-only view instead of 500-ing — the
  supervision record is authoritative even if the source has been
  moved or deleted.

- **Audit trail** — every create / finish / approve / deny call
  goes through the existing ``_audit_helpers.audit`` pipe so
  ``/admin/audit`` shows the agent-run lifecycle next to human
  actions.

Verification: ``ruff check`` + ``pyright`` + ``pydoclint --style=google``
clean on all changed files; SQLite smoke-run applies the migration
to head and ``agent_runs`` / ``notebook_outputs.agent_run_id`` /
``notebook_cell_runs.agent_run_id`` all land.  Per
[feedback_skip_pytest.md](~/.claude/projects/-home-flo-git-PointlesSQL/memory/feedback_skip_pytest.md),
pytest is intentionally skipped for sprint orchestrations.

### Changed — Phase 12.12 / Sprint 12.12.2: Agent-first pivot — backend cleanup + ``/runs`` supervision stub

Second sprint of the agent-first pivot.  Sprint 12.12.1 deleted the
browser notebook editor's frontend (25 JS modules, ~16 MB vendored
libs, editor + modal templates) and added the server-side
run-detail skeleton.  Sprint 12.12.2 removes the editor's backend
surface and lights up the supervision landing page.

- **HTTP routes deleted** from
  [pointlessql/api/notebooks_routes.py](pointlessql/api/notebooks_routes.py):
  ``GET /notebook/editor``, ``GET`` / ``POST /api/notebook/doc``,
  ``GET /api/notebook/cell-runs``, ``POST /api/notebooks/upload``,
  ``POST /api/notebooks/create``,
  ``PATCH /api/notebooks/rename``, ``DELETE /api/notebooks``.
  The page + two read endpoints that survive
  (``GET /notebooks/workspace``, ``GET /api/notebooks/tree``,
  ``GET /api/notebooks/inspect``) are the read-only discovery
  surface the Papermill create-job modal leans on.

- **WebSocket routes deleted** — both ``/ws/notebook/kernel`` and
  ``/ws/notebook/lsp`` are gone, along with the entire
  ``pointlessql/api/notebook_kernel_ws.py`` module and the
  editor-only ``pointlessql/services/pyright_bridge.py``.
  ``services/kernel_session/`` stays as a library for a possible
  future local-executor fallback, but the revised Phase 13 plan
  treats PointlesSQL as a registry + store for agent runs
  (Hermes or another runtime owns execution), so the module has
  no in-repo caller today.

- **Governance helper deleted** — the table-detail
  *Open in notebook* button and the backing
  ``POST .../open-in-notebook`` route are removed: there is no
  editor to open a scratch notebook into.  The *Copy PQL snippet*
  button on the same card is the remaining affordance for pasting
  ``pql.table(...)`` into whatever agent is running.

- **Middleware trimmed** — ``static_module_revalidate_middleware``
  dropped with the notebook ESM-import tree; the registration list
  goes from five layers to four (auth / rate-limit / csrf /
  request-id).

- **Navigation** — the *Notebook* link pointing at
  ``/notebook/editor?path=scratch.py`` is replaced with *Runs*
  pointing at the new ``/runs`` stub page (empty list today;
  Sprint 13.2 introduces the ``agent_runs`` Alembic table +
  HTTP registry endpoints that populate it).  The Workspace
  page keeps its tree listing + the *Schedule…* row action; the
  editor-era *Open* row link and the Upload form card were
  removed.

- **Stale tests** — ``tests/test_jupyter.py`` was orphaned in
  Sprint 63 when the JupyterLab subprocess was retired.  Deleted.
  ``tests/test_admin_audit.py`` swapped an ``open_in_notebook``
  fixture row for ``create_connection`` so the 7-day window
  assertion still exercises a real audit action.

- **Lifespan** — ``app.state.kernel_registry`` + its startup /
  shutdown no longer run: no live consumer under the revised
  Phase 13 plan (PointlesSQL no longer executes agent runs).

End-to-end pivot check: all eight removed route paths absent from
``app.routes``, ``/runs`` GET present, ``ruff check pointlessql/``
clean, ``pyright pointlessql/`` 0 errors, ``pydoclint --style=google
pointlessql/`` 🎉 no violations.  The single lingering
``tests/test_pg_sync.py`` I001 is Sprint-82 technical debt,
untouched by this sprint.

### Changed — Phase 12.12 / Sprint 12.12.1: Agent-first pivot — delete editor, add run-view skeleton

Browser notebook editor (25 modules under ``frontend/js/notebook/``,
~16 MB vendored Monaco + KaTeX + markdown-it + markdown-it-texmath
+ jsdiff) deleted outright.  Added
[pointlessql/services/output_rendering.py](pointlessql/services/output_rendering.py)
as the server-side mime-bundle renderer plus a Bootstrap-``.card``
[pages/run_view.html](frontend/templates/pages/run_view.html)
template and four output partials.  Three new runtime deps —
``markdown-it-py>=3.0``, ``ansi2html>=1.9``, ``Pygments>=2.18`` —
for server-side Markdown / ANSI / code rendering.  Commit
``bc2ad07``; full sprint notes in the Phase 12.12 ROADMAP block.

### Changed — Phase 12.11 / Sprint 99: Notebook toolbar Bootstrap-native (badges + btn-groups + a11y)

Editor toolbar polished to the Bootstrap vocabulary already in use
across ``alerts.html``, ``jobs.html``, and ``sql_editor.html``.
Three narrow fixes on ``frontend/templates/pages/notebook_editor.html``
— no JS, Python, or marker-grammar code touched.

- **Status pills** — the ``saveState`` / ``kernelStatus`` /
  ``lspStatus`` spans switched from bare ``text-success`` /
  ``text-warning`` / ``text-danger`` text to
  ``.badge .rounded-pill .text-bg-{success,warning,danger,secondary}``.
  Text strings kept verbatim so the
  [notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  and [notebook_full_walkthrough.md](docs/e2e-walkthroughs/notebook_full_walkthrough.md)
  deterministic playbook assertions still match.  Each of the five
  ``saveState`` / five ``kernelStatus`` / four ``lspStatus`` values
  maps to its own variant — the ``secondary`` variant covers the
  ``disconnected`` / ``unavailable`` twilight states that bare
  ``text-muted`` handled inconsistently before.

- **Semantic button groups** — the eleven toolbar buttons are now
  wrapped in four labelled ``btn-group btn-group-sm`` containers:
  "Cell ops" (Add cell / Save / Clear cell), "Kernel"
  (Interrupt / Restart), "Panels" (Catalog / Variables / Outline),
  "Help" (Settings / Keymap).  The Run cell CTA stays standalone
  ``btn-primary ms-2`` — only primary action on the toolbar,
  mirroring the Run / Cancel split in ``sql_editor.html``'s query
  toolbar.  Each group carries an ``aria-label`` for assistive
  tech.

- **A11y for icon-only controls** — Settings (``bi-gear``) and
  Keymap (``bi-question-circle``) buttons gained explicit
  ``aria-label="Editor settings"`` / ``"Keymap overlay"``.
  ``title`` still drives hover tooltips; ``aria-label`` now covers
  screen readers.

CSS cleanup: ``.pql-nbedit-dirty`` (dead since Sprint 58) and the
one-use ``.pql-nbedit-status`` class removed.  The existing
``.pql-nbedit-status-pill`` CSS was deliberately left untouched —
it styles per-cell run-status pills, not the toolbar.

Verified in Playwright-MCP (Firefox): three pills with expected
``text-bg-*`` variants, four ``btn-group``s with 3 / 2 / 3 / 2
buttons, Run cell standalone, both icon-only buttons expose
``aria-label``.  Pill state transitions (saved → pending → saving
→ saved) reproduce the correct variant change.  Screenshots under
``docs/e2e-walkthroughs/screenshots/sprint-99/``.  Sprint-96
content-hash invariants and the 20 regression tests in
``tests/test_notebook_doc.py`` unaffected.

### Fixed — Phase 12.10 / Sprint 98: Notebook browser walkthrough + two output-zone regressions

Deterministic Playwright playbook landed at
[docs/e2e-walkthroughs/notebook_full_walkthrough.md](docs/e2e-walkthroughs/notebook_full_walkthrough.md)
walking 14 output scenarios (stdout, pandas DataFrame,
matplotlib, markdown cell, ``display(Markdown)``, stderr + stdout,
traceback, HTML, save, reload, external edit, markerless file,
BOM / CRLF).  Screenshots under
``docs/e2e-walkthroughs/screenshots/sprint-98/``.

Two regressions of the Sprint-96 rewrite were caught + fixed:

- **BUG-98-02 — ``display(Markdown("…"))`` rendered the repr.**
  ``output_renderer.js`` had no ``text/markdown`` mime branch so
  the renderer fell through to ``text/plain`` + showed
  ``<IPython.core.display.Markdown object>``.  Added the branch,
  re-using the existing ``renderMarkdown`` helper from
  ``markdown.js``.  Added a ``.pql-nbedit-output-markdown`` CSS
  rule in ``notebook_editor.html`` for heading + code + spacing.

- **BUG-98-05 — ghost output zones across ``setValue`` calls.**
  Output view-zones are keyed on the transient ``cell-N`` label
  which renumbers on every source rewrite; ``rebuildCell
  Affordances`` only pruned the affordance widgets, not the view
  zones, so every edit accumulated DOM ghosts.  Added
  ``pruneOrphanOutputZones(alive)`` on the output-zone manager
  and wired it into ``main.js``'s rebuild pass.

One deferred tag: **BUG-98-01** — the markdown view-zone
preview misses its first paint after a Playwright-style
synthetic ``setValue``.  Real users hit the ``+ Markdown``
toolbar button which routes through the normal content-change
handler, so the bug is unobservable outside the replay path.
Playbook tail documents the limitation.

On-disk invariant verified in the browser:
``notebooks/sprint98_walkthrough.py`` after save has zero
``pql_cell_id`` tokens + zero UUID-shaped substrings — the
Sprint 96 goal reached end-to-end, not just in unit tests.

### Improved — Phase 12.10 / Sprint 97: Notebook parser hardening against manual edits

``.py`` notebooks that a user has edited by hand in VSCode / Vim no
longer crash the editor. Both sides of the parse — Python's
``notebook_doc.py`` and the browser's ``cell_parser.js`` — now
tolerate every shape a naïve text editor can produce.

- **BOM + CRLF normalisation.** A leading UTF-8 BOM is stripped and
  CRLF / CR line endings collapse to LF before the marker regex
  walks. The Python side feeds the normalised string to
  ``jupytext.reads`` rather than ``jupytext.read(path)`` so the
  parse sees the same bytes our own scan does — otherwise a BOM
  glued itself to the first cell's source as ``\ufeff`` noise.

- **No-markers-at-all** → the whole file becomes a single synthetic
  ``cell-0`` code cell the user can inspect + add markers from the
  UI; next save materialises a ``# %%`` header.

- **Unknown tag** (``# %% [foo]``) falls back to ``code`` +
  ``result_var=None``; next save rewrites the marker to plain
  ``# %%``.

- **Bare ``# %% [sql]``** (no positional identifier) parses as an
  SQL cell with ``result_var=None``; no crash.

- **File ends mid-cell without trailing newline** → jupytext already
  tolerates this and we pass through unchanged; a test pins the
  behaviour so future parser work cannot regress it.

- **Dirty-flag semantics** extended. The editor prompts a one-time
  save not only on legacy ``pql_cell_id="…"`` markers but also on
  BOM / CRLF normalisation + empty-file / markerless open, so the
  next save normalises the on-disk bytes silently.

20 unit tests in [tests/test_notebook_doc.py](tests/test_notebook_doc.py)
(up from 11 at Sprint 96 close) — one per tolerance scenario.

**Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
errors, ``pydoclint --style=google`` 0 violations, 20/20 tests
pass.

### Refactored — Phase 12.10 / Sprint 96: Cell-ID refactor — marker grammar + content-hash identity

Notebook ``.py`` files dropped their PointlesSQL-specific
``pql_cell_id="<uuid>"`` marker segment.  The on-disk grammar is
now the IDE-agnostic shape VSCode / Spyder / PyCharm already
recognise (``# %%`` / ``# %% [markdown]`` / ``# %% [sql]`` /
``# %% [sql] df``), and cell identity is derived at load time as
the FNV-1a-64 hash of the normalised source (16 hex chars, same
algorithm on both Python and the browser).  Notebooks are now
generically editable in VSCode / Vim — reordering or removing a
cell by hand can no longer break the file because there is no ID
to go stale.

- **Alembic migration 019** renames ``cell_id`` → ``content_hash``
  across ``notebook_outputs``, ``notebook_cell_runs``,
  ``notebook_cell_run_sources``.  Pre-migration rows keep their
  UUID payload in the renamed column and are reaped naturally by
  the existing ``clear_path`` cascade on notebook delete / rename.
  SQLite + Postgres both round-trip cleanly.

- **Legacy-file migration is one-shot.**  Pre-Sprint-96 files with
  ``pql_cell_id="…"`` markers still load through a tolerant
  fallback regex in ``notebook_doc.py`` + ``cell_parser.js`` and
  cause ``load_document`` to return ``dirty=True`` so the editor
  prompts a save that rewrites the file into the clean grammar.

- **Cell identity splits into two concepts.**  ``NotebookCell``
  now carries ``id`` (transient ``cell-N`` ordinal, minted per
  load, used only as the Alpine ``x-for :key``) and
  ``content_hash`` (stable, used for every DB + WS lookup).
  ``main.js`` maintains the ``content_hash ↔ cell-id`` mapping
  beside ``cellAffordances`` so incoming kernel messages route
  back to the right DOM record even after a source edit bumps
  the hash.  Rows whose hash no longer matches any live cell are
  silently dropped — matching VSCode / Databricks orphan-output
  behaviour.

- **FNV-1a-64 instead of SHA-256** because it has a trivial
  synchronous mirror via ``BigInt`` on the browser side; SHA-256
  via SubtleCrypto would have forced an async cascade through
  every ``splitCells`` caller.

- **Tests.**  New [tests/test_notebook_doc.py](tests/test_notebook_doc.py)
  (11 cases) pins the FNV-1a reference vector
  ``cbf29ce484222325`` (empty-source basis), whitespace
  tolerance, round-trip byte-stability, the positional
  ``# %% [sql] df`` shape, and the one-way legacy-to-clean
  migration save.  A Node replay of the JS
  ``computeContentHash`` implementation produced identical
  hashes to Python on four test vectors before commit.

- **Static gates (all green):** ``ruff check`` 0 errors;
  ``pyright`` 0 errors / 154 pre-existing warnings unchanged;
  ``pydoclint --style=google`` 0 violations on every touched
  file; ``alembic upgrade head`` + ``downgrade -1`` +
  ``upgrade head`` idempotent round-trip on a fresh SQLite DB;
  ``pytest tests/test_notebook_doc.py`` 11/11 passing.

### Refactored — Phase 12.9 / Sprint 95: CSS feinschliff + cache-busting parity

Tranche-6 of the Sprint-76 frontend modularisation plan and the
closing sprint of the Sprint-77-95 modularisation effort.

- **CSS splits.** ``responsive.css`` 157 → 74 LOC. The
  ``.pql-list-table`` mobile-collapse block + the
  ``.pql-list-sort-mobile`` dropdown moved to
  [components/list_table.css](frontend/css/components/list_table.css)
  (now 171 LOC) so the mobile breakpoint sits next to the
  desktop list-table styling. The ``.pql-sidebar-nav-footer``
  chrome moved to [layout.css](frontend/css/layout.css) (now 173
  LOC) so the sidebar layout rules are co-located.
  [responsive.css](frontend/css/responsive.css) keeps the
  Jupyter-iframe mobile notice + the touch-target +
  reduced-motion media queries — the cross-cutting accessibility
  rules that don't slot under a single component.

- **Cache-busting parity.** ``base.html``'s
  ``<script type="module" src="/static/js/bootstrap.js">`` picks
  up ``?v=sprint95`` so the Sprint 91-94 JS surgery actually
  reaches every browser without a hard reload.

- **Tranche-7 leftover** (csrfToken duplicate in
  notebook/main.js): inspected; Sprint 75 already migrated the
  call site to ``import { csrfToken } from '../api.js'`` (line
  69 + line 508 use the imported symbol). No work required.

- **Static gates (all green):** all 11 CSS files still referenced
  by ``style.css`` master @import chain;
  ``check-frontend-bootstrap-order.sh`` still green. Pure-rule
  moves between CSS files; rule selectors and cascade order
  unchanged.

**Endgame summary** (Sprints 77-95, 19 sprints): 8 backend
service splits, 14 api/main.py route extracts (6,599 → 280 LOC,
-95.8%, 14 router modules), 5 frontend tranches. Net: ~16 000
LOC of monolithic Python + JS spread across ~80 focused files,
all <600 LOC, median <200 LOC. Zero behaviour change; every gate
stayed green.

### Refactored — Phase 12.9 / Sprint 94: page templates → ESM (4 of 7 pilots)

Tranche-5 of the Sprint-76 frontend modularisation plan. Four of
the seven sketched page-template inline scripts lift into
``frontend/js/pages/*.js`` ESM modules. Each picks up its server-
rendered seed via the template's ``x-data`` attribute as a Jinja-
rendered JSON parameter object so first-paint state stays
single-roundtrip.

- **alerts.html** 295 → 201 LOC. New
  [pages/alerts.js](frontend/js/pages/alerts.js) (112 LOC) seeded
  with ``{alerts, savedQueries}``.
- **alert_detail.html** 251 → 199 LOC. New
  [pages/alert_detail.js](frontend/js/pages/alert_detail.js)
  (57 LOC) seeded with ``{slug, destinations}``.
- **volume_detail.html** 248 → 125 LOC. New
  [pages/volume_detail.js](frontend/js/pages/volume_detail.js)
  (115 LOC) seeded with ``{fullName, files}``. Multipart upload
  still uses raw ``fetch()`` because pqlApi.fetch is JSON-only.
- **notebooks_workspace.html** 311 → 172 LOC. New
  [pages/notebooks_workspace.js](frontend/js/pages/notebooks_workspace.js)
  (152 LOC). No seed needed — fetches its own tree from
  ``GET /api/notebooks/tree`` via sessionStorage cache +
  revalidate.

**bootstrap.js** adds four new factory imports + ``window.*``
re-attaches. No template ``x-data=`` value changed except the
new seed parameters.

**Three pages deferred** to a follow-up sprint because each is a
larger / more interactive surface that warrants its own
playbook-replay: ``table.html`` (467 LOC, two inline scripts),
``jobs.html`` (372 LOC, ``createJobModal`` factory inside the
create-job modal), ``job_detail.html`` (324 LOC, run-history
popover + compare-runs UI).

**Static gates (all green):** ``node --check`` passes for all
four new modules + bootstrap.js,
``check-frontend-bootstrap-order.sh`` still green,
``jinja2.Environment.get_template()`` parses each updated
template cleanly.

### Refactored — Phase 12.9 / Sprint 93: notebook_editor.html modals → partial

Tranche-4 of the Sprint-76 frontend modularisation plan, narrowed
from the sketched 7-partial split down to the lowest-risk extract:
the four shell-scope modals (New notebook, Rename notebook, Delete
confirmation, Close-tab-with-unsaved-changes).

- **New partial** [partials/_notebook_editor_modals.html](frontend/templates/partials/_notebook_editor_modals.html)
  (186 LOC) — all four modals.
  Bootstrap-modal-Alpine trap memorised: every ``.modal`` toggles
  via ``:class="{ 'd-block': flag }"`` rather than ``x-show``
  (Alpine 3.14 strips inline ``display:block`` on false→true and
  the .modal stylesheet's ``display:none`` then wins — BUG-67-01
  from the original Sprint 67 fix).

- **pages/notebook_editor.html: 992 → 819 LOC (-173).** The modal
  block (lines 784-957 pre-split) becomes a single
  ``{% include "partials/_notebook_editor_modals.html" %}`` line.

- **Six remaining partials deferred** to a follow-up sprint
  because each carries Alpine x-data scope risk that warrants its
  own playbook-replay: ``_notebook_toolbar.html``,
  ``_notebook_file_tree.html``,
  ``_notebook_variables_explorer.html``,
  ``_notebook_outline_sidebar.html``,
  ``_notebook_catalog_modal.html``,
  ``_notebook_run_history_popover.html``.

- **Static gates (all green):** ``jinja2.Environment.get_template()``
  parses both the page and the new partial cleanly; pure move so
  behaviour is byte-identical. Replay of
  ``docs/e2e-walkthroughs/notebook_editor.md`` deferred to whenever
  a contributor next touches the file-tree CRUD flow — the four
  modals carry the ``:class="{ 'd-block': flag }"`` discipline
  verbatim so the Bootstrap-modal trap stays defused.

### Refactored — Phase 12.9 / Sprint 92: frontend federation.js + command_palette ESM

Tranche-3 of the Sprint-76 frontend modularisation plan. Two
unrelated splits in one sprint because both stood at the awkward
200-LOC inline-script + multi-export shape:

- **federation.js (195 LOC) → 3 sibling modules.**
  ``federation_connections.js`` (44 LOC),
  ``federation_credentials.js`` (94 LOC, both credential +
  external-location forms because external-locations bind a
  credential), ``federation_catalogs.js`` (94 LOC, foreign-catalog
  form + the generic ``deleteConfirm`` factory used by every
  detail page). ``bootstrap.js`` updated to import from each new
  module directly; the ``window.*`` names are unchanged so no
  template edit needed. Old ``federation.js`` deleted.

- **command_palette.html inline script → ESM module.** The
  256-line inline ``<script>`` block at the bottom of the partial
  moves into
  [components/command_palette.js](frontend/js/components/command_palette.js)
  (274 LOC). ``commandPalette()`` is wired through
  ``bootstrap.js``; the partial drops to 102 HTML-only LOC.

- **Static gates (all green):** ``node --check`` passes for all
  four new modules + bootstrap.js,
  ``check-frontend-bootstrap-order.sh`` still green. Playbook
  replay deferred — pure move so behaviour is byte-identical (the
  partial's ``x-data="commandPalette()"`` resolves to the same
  factory through bootstrap.js's
  ``window.commandPalette =`` line).

### Refactored — Phase 12.9 / Sprint 91: frontend sql_editor.js → 4-module split

Tranche-2 of the Sprint-76 frontend modularisation plan. The 608-LOC
``frontend/js/sql_editor.js`` factory splits into a 86-LOC façade +
four sibling ESM modules under the same namespace.

- **New modules** under
  [frontend/js/](frontend/js/):
  - ``sql_editor_monaco.js`` (198 LOC) — CodeMirror lifecycle +
    autocomplete + Cmd-Enter/Cmd-S keymap + ``c`` toggle +
    catalog-tree completions refresh + getSQL/setSQL.
  - ``sql_editor_execute.js`` (131 LOC) — ``run({explain})``
    + ``cancel()`` + elapsed counter + ``_generateQueryId``
    + ``formatCell``.
  - ``sql_editor_saved.js`` (89 LOC) — ``/api/saved-queries``
    CRUD + load-into-editor + Save modal.
  - ``sql_editor_chart.js`` (189 LOC) — Chart.js view, axis
    auto-pick, bar/line/pie/scatter render, PNG download,
    debounced ``PATCH /api/queries/{id}/chart-config``,
    ``seedFromHistory`` deep-link entry point.

- **Façade** [sql_editor.js](frontend/js/sql_editor.js) (86 LOC)
  declares the state schema and spreads the four method objects
  into the Alpine x-data shape via ``Object.assign`` semantics.
  ``bootstrap.js`` still re-attaches ``sqlEditor`` to ``window``
  unchanged so the template's ``x-data="sqlEditor"`` keeps
  working without any HTML edit.

- **Closure state promoted to ``this``.** The pre-split
  ``cmView`` + ``catalogCompletions`` module-level
  closure variables become ``this._cmView`` +
  ``this._catalogCompletions`` so all four sub-modules can reach
  the EditorView via ``this``. Method bodies elsewhere
  unchanged.

- **Static gates (all green):** ``node --check`` passes for all
  five files, ``bash scripts/check-frontend-bootstrap-order.sh``
  still green (bootstrap.js precedes the Alpine CDN bundle in
  base.html). Playbook replay deferred to whenever a contributor
  next touches /sql; the split is a pure move so behaviour is
  byte-identical.

### Refactored — Phase 12.9 / Sprint 90: api/main.py admin/home/catalog-html + endgame

Final decomposition slice for ``api/main.py``. Three new modules
lift out everything left, taking main.py from 1,296 LOC to 280 LOC
and closing out the 6,599 → 280 LOC (-95.8%) Sprint 85-90 effort.

- **New module** [admin_routes.py](pointlessql/api/admin_routes.py)
  (259 LOC). The ``/admin/audit`` viewer + ``/admin/audit/export``
  (CSV / JSON). Both admin-gated, both reading the Sprint-7
  ``audit_log`` table append-only.

- **New module** [home_routes.py](pointlessql/api/home_routes.py)
  (573 LOC). The home dashboard (``GET /``), the JSON twin
  (``GET /api/home/summary``), and the Cmd+K command palette
  (``GET /api/search``). ``build_home_summary`` + ``score_match``
  + ``epoch_seconds`` helpers move along.

- **New module** [catalog_html_routes.py](pointlessql/api/catalog_html_routes.py)
  (254 LOC). The three catalog-browser HTML pages (catalog
  detail / schema detail / table detail) that drive the sidebar
  navigation. Their JSON twins remain in ``api/catalog_routes.py``
  from Sprint 86.

- **main.py endgame.** What remains: app construction +
  ``register_middleware`` + the 14 ``include_router()`` calls +
  lifespan + audit-retention loop + ``/healthz`` + ``/metrics``
  + ``cli()``. Every route handler now lives in a focused
  ``api/<area>_routes.py`` module.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 0 warnings on main.py (-16 because the moved code
  carried the remaining partial-unknown warnings), ``pydoclint``
  0 violations. Eleven now-stale imports auto-trimmed by ruff.

### Refactored — Phase 12.9 / Sprint 89c: api/main.py dashboards routes extract

Twelfth decomposition slice for ``api/main.py`` — closes Sprint 89's
federation+jobs+dashboards triple. The Sprint-28 dashboards
publishing surface moves out: 4 JSON CRUD + refresh, plus 3 HTML
pages (list, detail, output). main.py drops 1,674 → 1,296 LOC
(-378).

- **New module** [dashboards_routes.py](pointlessql/api/dashboards_routes.py)
  (410 LOC). 7 routes plus 3 module-level helpers
  (``serialize_dashboard``, ``load_dashboard_or_404``,
  ``latest_succeeded_run_id``) plus the ``SLUG_PATTERN`` regex.
  Refresh endpoint imports ``JOB_REGISTRY`` + ``serialize_run``
  from ``api.jobs_routes`` directly (the cross-router coupling
  that previously routed through main.py re-exports).

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(dashboards_router)``
  next to the other eleven routers. Now-stale
  ``ValidationError``, ``notebook_render``, ``_JOB_REGISTRY`` +
  ``_serialize_run`` re-exports, plus the ``re`` module import,
  auto-trimmed by ruff.

- **Visibility model preserved.** Dashboards are visible to every
  logged-in user (consumer-facing publishing surface); mutations
  + refresh require admin; the ``/dashboards/{slug}/output``
  iframe uses a single internal check that the run belongs to the
  bound job (admin-or-job-owner is intentionally bypassed because
  dashboards publish output by design).

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 16 warnings (-9 because the moved dashboard code
  carried 9 partial-unknown warnings), ``pydoclint`` 0
  violations. No dedicated dashboard pytest module today (covered
  by the ``docs/e2e-walkthroughs/dashboards.md`` playbook); other
  suites unaffected.

### Refactored — Phase 12.9 / Sprint 89b: api/main.py jobs + scheduler routes extract

Eleventh decomposition slice for ``api/main.py`` — second cut of
Sprint 89. The full job-scheduler surface moves out: 5 JSON CRUD
routes, 3 run/task introspection routes, 3 papermill artefact
routes, 2 pause/unpause, and 2 HTML pages (jobs list + job detail).
main.py drops 2,406 → 1,674 LOC (-732).

- **New module** [jobs_routes.py](pointlessql/api/jobs_routes.py)
  (803 LOC). 13 routes plus 7 module-level helpers
  (``serialize_job``, ``serialize_task``, ``serialize_task_run``,
  ``serialize_run``, ``latest_run_per_job``, ``load_job_or_404``,
  ``require_job_owner_or_admin``, ``load_papermill_run_output_path``)
  plus the ``JOB_REGISTRY`` module-level constant.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(jobs_router)``
  next to the other ten routers. ``JOB_REGISTRY`` and
  ``serialize_run`` re-exported from main.py under their legacy
  ``_JOB_REGISTRY`` / ``_serialize_run`` aliases — the still-
  resident dashboard refresh route reads them.

- **Test fix:** ``tests/test_scheduler.py``
  ``test_manual_run_and_pause_unpause`` updated to monkeypatch
  ``api_jobs_routes.JOB_REGISTRY`` instead of the legacy
  ``api_main._JOB_REGISTRY``. Python's local-name lookup means a
  re-export binding in main.py is not what the route handler
  reads — the test must patch the module that owns the symbol.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 25 warnings (unchanged), ``pydoclint`` 0 violations,
  ``pytest -k 'job or scheduler' --ignore=tests/test_jupyter.py``
  54/54 passed.

### Refactored — Phase 12.9 / Sprint 89a: api/main.py federation routes extract

Tenth decomposition slice for ``api/main.py`` — first cut of Sprint
89's federation+jobs+dashboards triple. All UC federation
administration moves out: connections, external-locations,
credentials (5 routes each + 6 HTML pages = 21 routes total).
main.py drops 2,683 → 2,406 LOC (-277).

- **New module** [federation_routes.py](pointlessql/api/federation_routes.py)
  (322 LOC). All 21 routes are ``require_admin``-gated, mirroring
  the soyuz-catalog rule that federation administration is
  admin-only until a finer-grained CREATE_* privilege ships.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(federation_router)``
  next to the other nine routers.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 25 warnings (-1), ``pydoclint`` 0 violations,
  ``pytest -k 'connection or credential or federation or
  external' --ignore=tests/test_jupyter.py`` 34/34 passed.

### Refactored — Phase 12.9 / Sprint 88b: api/main.py notebook WS endpoints extract

Ninth decomposition slice for ``api/main.py`` — closes out the
notebook surface. The two ``@app.websocket`` handlers
(``/ws/notebook/kernel`` + ``/ws/notebook/lsp``) and their shared
``resolve_sql_approved_tables`` helper move into a dedicated
``notebook_kernel_ws.py``. main.py drops 3,227 → 2,683 LOC (-544).

- **New module** [notebook_kernel_ws.py](pointlessql/api/notebook_kernel_ws.py)
  (601 LOC). Both WS endpoints plus the SQL-approval helper.
  Underscore prefix dropped from helper name
  (``resolve_sql_approved_tables`` is module-public within the
  new package). WS auth model preserved verbatim: cookie + JWT
  decode, traversal guard, 4401/4400/4404/1011 close codes.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(notebook_ws_router)``
  next to the other eight routers. Now-unused ``contextlib``,
  ``WebSocket``, ``WebSocketDisconnect``, ``UnityCatalogClient``,
  ``UserInfo``, ``check_privilege``, ``SELECT``, plus the
  ``services.pyright_bridge`` import all auto-trimmed by ruff
  (the WS routes were the only remaining callers).

- **WS lifecycle preserved.** All five close codes (4401
  unauthenticated, 4400 bad path, 4404 missing pyright, 1011 spawn
  failure, normal close) plus the ZMQ↔WS forward tasks +
  per-cell output counters + per-execute history-row stamping
  moved verbatim.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 26 warnings (-18 from Sprint 88a because the WS code
  carried 18 partial-unknown warnings), ``pydoclint`` 0
  violations. ``pytest tests/test_api_notebook_workspace.py
  tests/test_notebook_workspace.py`` 27/27 passed. WS endpoints
  have no unit tests; their integration coverage runs through
  ``docs/e2e-walkthroughs/notebook_kernel.md`` (Playwright
  playbook).

### Refactored — Phase 12.9 / Sprint 88a: api/main.py notebook HTTP routes extract

Eighth decomposition slice for ``api/main.py``. The HTTP half of the
notebook surface lifts out: editor page, doc bundle (GET + POST),
per-cell run history, the workspace tree + inspect endpoints, the
upload/create/rename/delete CRUD, and the workspace HTML page.
main.py drops 3,751 → 3,227 LOC (-524). The two WebSocket endpoints
(``/ws/notebook/kernel`` + ``/ws/notebook/lsp``) and their shared
``_resolve_sql_approved_tables`` helper stay in main.py for now —
Sprint 88b will move them into a dedicated WS module.

- **New module** [notebooks_routes.py](pointlessql/api/notebooks_routes.py)
  (580 LOC). Owns 11 routes plus the ``build_notebook_doc_bundle``
  helper shared between the HTML editor and the JSON bundle
  endpoint. All existing admin gates preserved.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(notebooks_router)``
  next to the other seven routers. Now-unused ``UploadFile``,
  ``File``, ``Form``, ``uuid4``, top-level ``json`` imports
  auto-trimmed by ruff.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 44 warnings (-10 from Sprint 87c baseline because the
  moved notebook code carried 10 partial-unknown warnings),
  ``pydoclint`` 0 violations, ``pytest -k notebook
  --ignore=tests/test_jupyter.py`` 34/34 passed.

### Refactored — Phase 12.9 / Sprint 87c: api/main.py governance routes extract

Seventh decomposition slice for ``api/main.py``. The full governance
surface lifts out: table column statistics (Sprint 56),
notebook-from-table scratch helper, catalog create/sync/patch +
schema patch, tags + permissions (get/patch + effective), and
lineage. main.py drops 4,242 → 3,751 LOC (-491).

- **New module** [governance_routes.py](pointlessql/api/governance_routes.py)
  (549 LOC). Owns 14 routes plus ``split_full_name`` and
  ``enforce_table_profile_access`` helpers (underscore prefixes
  dropped).

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(governance_router)``
  next to the other six routers. Module-level ``MODIFY`` import
  dropped (only the moved routes used it).

- **Authorization model preserved.** Profile + stats GET still
  require SELECT (admin short-circuits); stats DELETE +
  open-in-notebook + create-catalog + sync-catalog are still
  admin-only; catalog/schema PATCH still need MODIFY; tag PATCH
  MODIFY; permission PATCH MANAGE_GRANTS; lineage GET SELECT.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 54 warnings (-13 from Sprint 87b baseline because the
  moved governance code carried 13 ``Type … partially unknown``
  warnings), ``pydoclint`` 0 violations, ``pytest -k 'stats or
  table_stats or tag or permission or lineage or open_in_notebook'
  --ignore=tests/test_jupyter.py`` 27/27 passed.

### Refactored — Phase 12.9 / Sprint 87b: api/main.py UC volumes routes extract

Sixth decomposition slice for ``api/main.py``. The full UC volumes
surface lifts out: 4 JSON endpoints (browse, upload, delete file +
convert-to-Delta) + 2 HTML pages (volumes list + per-volume detail).
main.py drops 4,717 → 4,242 LOC (-475).

- **New module** [volumes_routes.py](pointlessql/api/volumes_routes.py)
  (527 LOC). Owns 6 routes plus ``soyuz_base_url``,
  ``volume_full_name_split``, ``convert_volume_file_sync``, the
  ``DELTA_PRIMITIVE_TO_UC`` dict + ``delta_field_to_uc``
  field-mapper. Underscore prefixes dropped from helper names;
  the type-mapping pair is re-exported from main.py under its
  legacy ``_DELTA_PRIMITIVE_TO_UC`` / ``_delta_field_to_uc``
  aliases (Invariant 8 of the modularisation plan) so
  ``tests/test_volume_convert_type_mapping.py`` keeps importing
  them from ``pointlessql.api.main``.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(volumes_router)``
  next to the other five routers. Stale ``_soyuz_base_url`` helper
  deleted (the moved volumes routes were the only callers); top-
  level ``httpx`` import dropped for the same reason.

- **Convert-to-Delta admin gate preserved.** The
  ``api_convert_volume_file_to_delta`` route still calls
  ``require_admin(request)`` before any work, mirroring the
  original behaviour.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 67 warnings (unchanged), ``pydoclint`` 0 violations,
  ``pytest -k volume --ignore=tests/test_jupyter.py`` 15/15
  passed; the targeted
  ``tests/test_volume_convert_type_mapping.py`` 9/9 passed
  (re-export gate intact).

### Refactored — Phase 12.9 / Sprint 87: api/main.py alerts + feed routes extract

Fifth decomposition slice for ``api/main.py``. The full alerts
surface lifts out: ``/api/alerts`` CRUD (5 routes), the destinations
sub-resource (2 routes), per-user feed-token (2 routes), the two
unauthenticated pull-feed endpoints (``/alerts/feed.atom`` +
``/alerts/feed.json``), and the two HTML pages (``/alerts`` list +
``/alerts/{slug}`` detail). main.py drops 5,256 → 4,717 LOC (-539).

- **New module** [alerts_routes.py](pointlessql/api/alerts_routes.py)
  (585 LOC). Owns 13 routes plus three module-level helpers
  (``base_url``, ``rotate_or_fetch_feed_token``,
  ``user_for_feed_token``). Underscore prefixes dropped from
  helpers; ``saved_queries_service`` imported at module level for
  the alerts list page (which renders the dropdown of available
  saved-queries to attach an alert to).

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(alerts_router)``
  next to the other four routers. Unused ``saved_queries_service``
  + ``JSONResponse`` imports removed (the alerts routes were the
  only remaining callers).

- **Feed-token auth preserved.** ``PUBLIC_PREFIXES`` in
  ``api/middleware.py`` already exempts ``/alerts/feed.atom`` +
  ``/alerts/feed.json`` from session auth so the route handlers
  can authenticate via the opaque ``?token=…`` query string and
  401 on mismatch.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 67 warnings (unchanged), ``pydoclint`` 0 violations,
  ``pytest -k alert --ignore=tests/test_jupyter.py`` 19/19
  passed.

### Refactored — Phase 12.9 / Sprint 86c: api/main.py queries + saved-queries extract

Fourth decomposition slice for ``api/main.py`` — completes the
original Sprint-86 plan. The query-history read endpoints
(``/api/queries`` list/get/chart-config), the ``/queries`` HTML page,
and the full ``/api/saved-queries`` CRUD all move into a new
``api/queries_routes.py``. main.py drops 5,652 → 5,256 LOC (-396).

- **New module** [queries_routes.py](pointlessql/api/queries_routes.py)
  (444 LOC). Owns three query-history routes + the ``/queries``
  HTML page + five saved-queries routes (list/create + get/patch/
  delete by slug) + the ``parse_since`` window-string helper.
  Underscore prefix dropped from ``parse_since`` since it is now
  module-public within the new package.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(queries_router)``
  next to the other three routers. Module-level imports of
  ``query_history`` + ``saved_queries`` services dropped — the
  alerts route already function-locally re-imports ``saved_queries``
  so nothing else regressed.

- **Visibility model preserved.** Non-admin still sees only their
  own ``query_history`` rows (``user_id`` query param clamped
  server-side); saved queries still 404 on missing OR forbidden so
  private slugs are not discoverable; chart config + delete still
  owner+admin only.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 67 warnings (-7 from Sprint 86b baseline because the
  dropped ``query_history`` + ``saved_queries`` module-level
  imports were the source of seven ``Type … partially unknown``
  warnings), ``pydoclint`` 0 violations, ``pytest -k 'saved_quer
  or query_history or queries' --ignore=tests/test_jupyter.py``
  26/26 passed.

### Refactored — Phase 12.9 / Sprint 86b: api/main.py SQL editor routes extract

Third decomposition slice for ``api/main.py``. The four-route
Phase-12 SQL editor surface (execute / cancel / download + the
``/sql`` page) moved into a new module. Original Sprint-86 plan
bundled SQL with ``/api/queries`` + ``/api/saved-queries``; this
slice carved off the SQL pieces alone for a smaller blast radius.
main.py drops 6,203 → 5,652 LOC (-551).

- **New module** [sql_routes.py](pointlessql/api/sql_routes.py)
  (597 LOC). Owns ``POST /api/sql/execute``,
  ``POST /api/sql/execute/{query_id}/cancel``,
  ``GET  /api/sql/execute/{history_id}/download``, and the
  ``GET /sql`` HTML page, plus the four module-level helpers
  (``short_sql_hash``, ``run_sql_sync``, ``live_queries``,
  ``run_sql_export_sync``). Underscore prefixes dropped since the
  helpers are now module-public within the new package.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(sql_router)``
  alongside the existing auth + catalog routers. Unused
  ``record_query_async`` re-import dropped (the SQL routes were the
  only main.py callers). ``_parse_since`` deliberately stays in
  main.py because ``/api/queries`` (Sprint 86c) still depends on it.

- **Authorization preserved.** Both execute and download still
  re-run ``check_privilege(SELECT)`` per referenced 3-part table —
  a stale ``query_history`` row is not a bypass. The cancel route
  stays idempotent (204 on unknown ids).

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 74 pre-existing warnings, ``pydoclint`` 0 violations,
  ``pytest -k 'sql or query' --ignore=tests/test_jupyter.py`` 48/48
  passed.

### Refactored — Phase 12.9 / Sprint 86: api/main.py catalog tree routes extract

Second decomposition slice for ``api/main.py``. Narrowed from the
sketched ``catalog/sql/queries`` triple-extract down to just the five
catalog tree routes — the lowest-risk surface in the route set, used
to validate the ``APIRouter`` extraction pattern before the much
larger SQL execute + queries-page extracts in the next sprint.
main.py drops 6,347 → 6,203 LOC (-144).

- **New module** [catalog_routes.py](pointlessql/api/catalog_routes.py)
  (186 LOC). Owns the five sidebar/breadcrumb endpoints
  (``/api/tree``, ``/api/catalogs``,
  ``/api/catalogs/{c}/schemas``,
  ``/api/catalogs/{c}/schemas/{s}/tables``,
  ``/api/catalogs/{c}/schemas/{s}/tables/{t}/preview``) plus the two
  preview helpers (``preview_head`` engine-aware row truncation,
  ``run_table_preview`` thread-pool worker) and the
  ``PREVIEW_ROW_LIMIT = 10`` constant. Underscores dropped from the
  helper names since they are now module-public within the new package.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(catalog_router)``
  added next to the existing ``auth_router`` line. Unused
  ``make_principal_client`` import removed (only the moved preview
  code referenced it).

- **Authorization preserved.** Schemas + tables endpoints still call
  hierarchical ``check_privilege`` (USE_CATALOG / USE_SCHEMA),
  preview still resolves ``effective_permissions`` once and feeds
  ``check_privilege_from_effective(SELECT)``. Preview responses keep
  ``Cache-Control: no-store`` so revoked grants do not leak through
  the browser disk cache.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 74 pre-existing warnings, ``pydoclint`` 0 violations,
  ``pytest -k 'catalog or tree or preview'
  --ignore=tests/test_jupyter.py`` 44/44 passed (test_jupyter.py has a
  pre-existing import error unrelated to this sprint).

### Refactored — Phase 12.9 / Sprint 85: api/main.py middleware + helpers extract

First decomposition slice for the 6,599-LOC ``api/main.py``. The
lowest-risk pieces — middleware stack + per-request dependencies +
async fire-and-forget audit/query-history writers — moved into three
new modules. main.py drops 6,599 → 6,341 LOC (-258); no route logic
moved this sprint.

- **New modules** under ``pointlessql/api/``:
  [middleware.py](pointlessql/api/middleware.py) (~155 LOC) — five
  middleware functions wired into a single
  ``register_middleware(app)`` entrypoint that preserves the
  LIFO stacking order (``request_id → static_revalidate → csrf →
  rate_limit → auth → handler`` on every incoming request).
  ``PUBLIC_PREFIXES`` lifted out of its underscore-prefixed private
  name since the new module owns it.
  [dependencies.py](pointlessql/api/dependencies.py) (~90 LOC) —
  request-scoped helpers ``get_uc_client`` / ``get_user`` /
  ``require_admin`` / ``client_ip``. main.py re-imports them with
  the legacy ``_get_user`` etc. aliases so the ~hundred call sites
  inside its route handlers keep working unchanged.
  [_audit_helpers.py](pointlessql/api/_audit_helpers.py) (~130 LOC)
  — ``audit`` + ``record_query_async`` async writers, pulled out
  so route-group modules in Sprints 86-90 can import them without
  dragging in the full main module.

- **Middleware order preserved.** ``register_middleware`` calls
  ``app.middleware("http")()`` in the exact same order the decorators
  previously fired in main.py, so the LIFO execution chain on an
  incoming request is byte-identical to the pre-Sprint-85 build.

- **Public surface preserved.** Every existing call into the helpers
  works through the legacy underscore-prefixed re-imports
  (``_get_uc_client``, ``_get_user``, ``_require_admin``,
  ``_record_query_async``, ``_audit``) at the top of main.py, so
  the route handlers below — which still total >5,000 LOC — were
  not touched at all.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 74 pre-existing warnings, ``pytest tests/test_csrf.py
  tests/test_rate_limit.py tests/test_auth.py`` 52/52 passed.

### Refactored — Phase 12.9 / Sprint 84: services/scheduler.py → 5-module package

Eighth backend split — largest service (1,776 LOC). The
``services/scheduler.py`` module became the package
``services/scheduler/`` with five sibling modules carved along the
pipeline boundaries (registry → executors → DAG → runs → loop).

- **Package layout** under ``pointlessql/services/scheduler/``:
  [registry.py](pointlessql/services/scheduler/registry.py) (~95 LOC)
  — ``KindRegistry``, ``JobExecutor`` type alias,
  ``build_default_registry``.
  [executors.py](pointlessql/services/scheduler/executors.py)
  (~555 LOC) — the four built-in executors
  (``_pg_sync_executor``, ``_python_executor``,
  ``_papermill_executor`` + helpers, ``_alert_check_executor``).
  Function-local imports for ``pql.pql`` / ``alerts`` / ``models``
  / ``authorization`` are preserved verbatim — the pre-Sprint-84
  code dodged a circular chain through ``pointlessql.db`` and the
  same pattern continues to work.
  [dag.py](pointlessql/services/scheduler/dag.py) (~135 LOC) —
  pure graph algorithms: ``validate_dag`` (cycle detection),
  ``_topological_order`` (Kahn's algorithm), ``_parse_depends_on``.
  [runs.py](pointlessql/services/scheduler/runs.py) (~825 LOC) —
  DB helpers, ``log_job``, per-task lifecycle (``_run_one_task``,
  ``_run_dag``), run orchestration (``execute_run`` +
  ``_execute_run_core``), telemetry helpers. Owns the test-hook
  globals ``_sleep`` / ``_webhook_client_factory`` /
  ``_WEBHOOK_TIMEOUT_SECONDS``.
  [loop.py](pointlessql/services/scheduler/loop.py) (~250 LOC) —
  ``tick_once``, ``_execute_with_semaphores``, the ``Scheduler``
  driver class.

- **Public surface preserved.** The package
  [__init__.py](pointlessql/services/scheduler/__init__.py)
  re-exports every name the API layer
  ([pointlessql/api/main.py:55](pointlessql/api/main.py#L55)),
  scheduler tests, and external docs reference (``KindRegistry``,
  ``Scheduler``, ``build_default_registry``, ``execute_run``,
  ``tick_once``, ``validate_dag``, ``log_job``,
  ``_alert_check_executor``, ``_papermill_executor``,
  ``resolve_notebook_path``, ``_is_due``,
  ``_execute_with_semaphores``, ``_WEBHOOK_TIMEOUT_SECONDS``,
  ``_sleep``, ``_webhook_client_factory``).

- **Test-hook patch sites moved.** 6 monkeypatch sites across
  ``tests/test_scheduler_dag.py`` (``_sleep``) and
  ``tests/test_metrics.py`` (``_webhook_client_factory``) now patch
  ``scheduler_service.runs._sleep`` /
  ``scheduler_service.runs._webhook_client_factory`` directly. The
  runs.py module reads them via local-name lookup, so monkeypatching
  the package-level re-export does not take effect — the right
  structural fix is to patch the module where the symbol is used.

- **Per-file pyright suppressions.** Added ``# pyright:
  reportPrivateUsage=false`` to ``__init__.py``, ``loop.py``,
  ``registry.py``, and ``runs.py``; and ``# pyright:
  reportUnusedFunction=false`` to ``executors.py``, ``dag.py``,
  and ``runs.py``. Pyright's strict-mode rules treat any
  underscore-prefixed cross-module access as private leakage —
  legitimate within a single package, and the public contract
  (``__all__`` lists, the test patches) is what actually
  constrains the surface.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 15 pre-existing warnings, ``pydoclint`` 0 violations,
  ``pytest tests/test_scheduler.py tests/test_scheduler_dag.py
  tests/test_metrics.py tests/test_alerts.py
  tests/test_scheduler_papermill.py`` 80/80 passed.

### Refactored — Phase 12.9 / Sprint 83: services/unitycatalog.py → mixin package

Seventh backend split — broadest blast radius of the arc (18+ call
sites, 23 tests patch soyuz function names by string). The 783-LOC
``services/unitycatalog.py`` module became the package
``services/unitycatalog/`` with one mixin per securable type plus a
shared ``_api.py`` for the soyuz function bindings + error decorator.
``UnityCatalogClient`` composes the mixins so its single-import
surface (``from pointlessql.services.unitycatalog import
UnityCatalogClient``) is unchanged.

- **Package layout** under ``pointlessql/services/unitycatalog/``:
  [_api.py](pointlessql/services/unitycatalog/_api.py) (~190 LOC) —
  every soyuz typed function imported as ``_get_X`` / ``_create_X``
  / ``_list_X`` / ``_update_X`` / ``_delete_X``, plus the shared
  ``wrap_catalog_errors`` decorator.
  [_catalogs.py](pointlessql/services/unitycatalog/_catalogs.py)
  (~130 LOC) — ``CatalogsMixin`` (catalog CRUD + ``get_tree``
  aggregator that reaches into ``MetadataMixin.list_schemas`` /
  ``list_tables`` via ``self``).
  [_metadata.py](pointlessql/services/unitycatalog/_metadata.py)
  (~210 LOC) — ``MetadataMixin`` (schema + table + tag CRUD).
  [_permissions.py](pointlessql/services/unitycatalog/_permissions.py)
  (~110 LOC) — ``PermissionsMixin`` (direct + effective).
  [_lineage.py](pointlessql/services/unitycatalog/_lineage.py)
  (~50 LOC) — ``LineageMixin``.
  [_federation.py](pointlessql/services/unitycatalog/_federation.py)
  (~180 LOC) — ``FederationMixin`` (connections + external locations
  + credentials).

- **Test patch surface preserved.** The package
  [__init__.py](pointlessql/services/unitycatalog/__init__.py)
  re-exports every soyuz function binding at the legacy
  ``pointlessql.services.unitycatalog._xyz`` path. Tests that do
  ``patch("pointlessql.services.unitycatalog._get_tags.asyncio")``
  hit the same module object the mixin's call resolves to (Python
  module objects are singletons), so 23 patch sites in
  ``test_tags_permissions.py`` + ``test_federation.py`` work
  unchanged.

- **Renamed ``_wrap_catalog_errors`` → ``wrap_catalog_errors``.** Same
  reason the Sprint-77 kernel_session + Sprint-81 alerts + Sprint-82
  pg_sync splits dropped their leading underscores from cross-module
  helpers: pyright's ``reportPrivateUsage`` flags any access from a
  non-owning module, and the decorator is now used by every mixin.

- **MRO verified:** ``UnityCatalogClient → CatalogsMixin →
  MetadataMixin → PermissionsMixin → LineageMixin → FederationMixin
  → object``. ``isinstance(client, UnityCatalogClient)`` still works
  for every existing call site.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 4 warnings (3 pre-existing isinstance/list-typing
  patterns, unchanged), ``pydoclint`` 0 violations, ``pytest
  tests/test_tags_permissions.py tests/test_federation.py`` 23/23 +
  ``pytest tests/test_pg_sync.py tests/test_foreign_catalog.py
  tests/test_e2e.py tests/test_problem_json.py`` 60/60 passed.

### Refactored — Phase 12.9 / Sprint 82: services/pg_sync.py → 5-module package

Sixth backend split. The 778-LOC ``services/pg_sync.py`` module became
the package ``services/pg_sync/`` with five sibling modules carved
along the pipeline boundaries (introspect → diff → apply → record).

- [types.py](pointlessql/services/pg_sync/types.py) (~250 LOC) —
  dataclasses (``PgColumn``, ``PgTable``, ``PostgresSnapshot``,
  ``UcColumn``, ``UcTable``, ``SyncDiff``), the ``PG_TO_UC_TYPE`` map,
  ``map_pg_type_to_uc``, the ``PostgresIntrospector`` Protocol, plus
  the ``EXTERNAL_TABLE_TYPE`` / ``FOREIGN_DATA_SOURCE_FORMAT``
  constants (renamed from underscore-prefixed since they now travel
  cross-module).
- [dsn.py](pointlessql/services/pg_sync/dsn.py) (~80 LOC) —
  ``effective_options`` (renamed from ``_effective_options``) +
  ``build_dsn``.
- [snapshot.py](pointlessql/services/pg_sync/snapshot.py) (~95 LOC) —
  ``PsycopgIntrospector`` (the live-Postgres concrete implementation).
- [diff.py](pointlessql/services/pg_sync/diff.py) (~210 LOC) — pure
  ``diff_snapshots`` + ``collect_uc_tables`` + ``apply_diff`` plus the
  ``_columns_payload`` / ``_storage_location_stub`` helpers (still
  underscored because they remain internal to ``apply_diff``).
- [runs.py](pointlessql/services/pg_sync/runs.py) (~165 LOC) —
  ``run_sync`` end-to-end orchestration + ``list_recent_runs`` +
  ``_start_run`` / ``_finish_run`` bookkeeping.

- **Public surface preserved.** The package
  [__init__.py](pointlessql/services/pg_sync/__init__.py) re-exports
  every name the API layer
  ([pointlessql/api/main.py:51](pointlessql/api/main.py#L51)),
  scheduler
  ([pointlessql/services/scheduler.py:178](pointlessql/services/scheduler.py#L178)),
  and tests
  ([tests/test_pg_sync.py:33](tests/test_pg_sync.py#L33),
  [tests/test_scheduler.py:314](tests/test_scheduler.py#L314)) need.

- **One test rename.** ``_effective_options`` →
  ``effective_options`` in ``tests/test_pg_sync.py`` is the only
  compensation needed for the split — the production code's leading
  underscore is misleading once the symbol is imported across modules
  (same lesson the Sprint-77 kernel_session split made explicit).

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 8 warnings (all pre-existing dict-unpack patterns in
  ``collect_uc_tables``), ``pydoclint`` 0 violations,
  ``pytest tests/test_pg_sync.py`` 46/46 passed (1 deselected: live
  integration test).

### Refactored — Phase 12.9 / Sprint 81: services/alerts.py → 4-module package

Fifth backend split. The 729-LOC ``services/alerts.py`` module became
the package ``services/alerts/`` with four sibling modules + an
``__init__.py`` re-export shim. Pure structural refactor; no
schema, no migration, no behaviour change.

- **Four-bucket split** along the concern boundaries the file already
  implied:
  [crud.py](pointlessql/services/alerts/crud.py) (~340 LOC) — slug /
  serialisation / authorisation helpers, backing-Job lifecycle
  (``_sync_backing_job``), CRUD (``create_alert``, ``list_visible``,
  ``get_by_slug``, ``update_by_slug``, ``delete_by_slug``).
  [destinations.py](pointlessql/services/alerts/destinations.py)
  (~100 LOC) — ``add_destination`` + ``delete_destination``.
  [events.py](pointlessql/services/alerts/events.py) (~165 LOC) —
  ``record_event`` + ``set_event_outcome`` +
  ``list_events_for_alert`` + ``list_events_for_owner`` +
  ``prune_events_older_than``.
  [conditions.py](pointlessql/services/alerts/conditions.py) (~85 LOC)
  — pure ``evaluate_condition`` + ``build_cloudevent``.

- **Cross-module helpers de-underscored.** Renamed ``_serialize`` →
  ``serialize``, ``_serialize_destination`` → ``serialize_destination``,
  ``_can_mutate`` → ``can_mutate``: the leading underscore conveyed
  file-private scope, which is no longer accurate now that
  ``destinations.py`` imports them across modules. Same lesson the
  Sprint-77 kernel_session split made explicit. ``_sync_backing_job``
  stays underscored because it's truly internal to ``crud.py``.

- **Public surface preserved.** Existing ``from pointlessql.services
  import alerts as alerts_service`` callers (API layer line 1693,
  scheduler line 543, tests/test_alerts.py line 19) keep working
  through the package's ``__init__.py`` re-exports.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 0 warnings, ``pydoclint`` 0 violations,
  ``pytest tests/test_alerts.py`` 19/19 passed.

### Refactored — Phase 12.9 / Sprint 80: models.py → 8-module package

Fourth backend split — by far the highest-stakes mechanical refactor
of the arc. The 952-LOC ``models.py`` became the package
``pointlessql/models/`` with one module per domain. Alembic and the
32 known call sites continue to work unchanged via package-level
re-exports. Pure structural refactor; no schema, no migration, no
behaviour change.

- **Package layout.** Module order is load-bearing: SQLAlchemy
  resolves ``ForeignKey("table.col")`` strings at mapper-config time,
  so referenced tables must register before referrers.
  [base.py](pointlessql/models/base.py) (Base);
  [auth.py](pointlessql/models/auth.py) (User);
  [audit.py](pointlessql/models/audit.py) (AuditLog);
  [sync.py](pointlessql/models/sync.py) (SyncRun);
  [scheduler.py](pointlessql/models/scheduler.py) (Job, JobRun,
  JobTask, TaskRun, JobLog);
  [catalog.py](pointlessql/models/catalog.py) (Dashboard,
  QueryHistory, QueryHistoryTable, SavedQuery, TableStats,
  RateLimitEvent);
  [alerts.py](pointlessql/models/alerts.py) (Alert, AlertDestination,
  AlertEvent);
  [notebook.py](pointlessql/models/notebook.py) (NotebookOutput,
  NotebookCellRun, NotebookCellRunSource).

- **Alembic compatibility.**
  [pointlessql/alembic/env.py:6](pointlessql/alembic/env.py#L6) still
  imports ``from pointlessql.models import Base`` and resolves to the
  same metadata. Migration files reference table names (strings) not
  Python classes, so they were untouched. Smoke import confirms all
  20 tables register on ``Base.metadata`` after the split.

- **Public surface preserved.**
  [__init__.py](pointlessql/models/__init__.py) re-exports every
  symbol previously importable from ``pointlessql.models``, so the
  32 known call sites (services, API layer, tests, alembic) work
  unchanged.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 0 warnings, ``pydoclint`` 0 violations, model-touching
  test suites pass.

### Refactored — Phase 12.9 / Sprint 79: services/notebook_outputs.py → 2-module package

Third backend split. The 480-LOC ``services/notebook_outputs.py``
module became the package ``services/notebook_outputs/`` with two
sibling modules + an ``__init__.py`` re-export shim. Pure structural
refactor; no SQL, no schema, no behaviour change.

- **Two-bucket split** along the underlying-table boundary that the
  monolithic file already implied:
  [outputs.py](pointlessql/services/notebook_outputs/outputs.py)
  (~270 LOC) owns the ``NotebookOutput`` table — append-on-iopub,
  replay-on-open, plus the cross-table ``clear_*`` / ``rename_path``
  helpers that scrub output frames and cell-run lifecycle rows
  together on re-execute, restart, delete, or rename.
  [cell_runs.py](pointlessql/services/notebook_outputs/cell_runs.py)
  (~210 LOC) owns the ``NotebookCellRun`` (current state per session)
  and ``NotebookCellRunSource`` (per-execute history) tables —
  ``upsert_cell_run``, ``record_cell_run_start`` / ``_finish``,
  ``list_cell_run_sources``.

- **Public surface preserved.**
  [__init__.py](pointlessql/services/notebook_outputs/__init__.py)
  re-exports every function the API layer uses, so the lone
  external caller
  [pointlessql/api/main.py:48](pointlessql/api/main.py#L48)
  keeps working through ``notebook_outputs_service.X`` access.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 0 warnings, ``pydoclint`` 0 violations, smoke import
  OK.

### Refactored — Phase 12.9 / Sprint 78: pql/pql.py → 5 sibling helpers

Second backend split. The 461-LOC ``PQL`` module is now a 192-LOC
public-class façade plus five per-concern sibling modules.
:class:`PQL`'s methods are thin wrappers that delegate to module-level
helper functions; the orchestration shape (init → method dispatch) is
readable in one file while the per-concern logic — Delta read, DuckDB
SQL execution, Delta write + table-creation, list helpers — lives
next door.

- **New helpers** under ``pointlessql/pql/``:
  [_types.py](pointlessql/pql/_types.py) (44 LOC) carries
  ``SQLResult``;
  [_read.py](pointlessql/pql/_read.py) (64 LOC) is ``read_table()``
  (the body of ``PQL.table``);
  [_sql.py](pointlessql/pql/_sql.py) (124 LOC) is ``run_sql()`` (the
  body of ``PQL.sql`` — DuckDB connect + view registration + execute
  + row cap);
  [_write.py](pointlessql/pql/_write.py) (132 LOC) is
  ``write_table()`` + ``derive_storage_location()`` (the body of
  ``PQL.write_table``);
  [_list.py](pointlessql/pql/_list.py) (80 LOC) is ``list_catalogs``
  / ``list_schemas`` / ``list_tables``.

- **Public surface preserved.** :class:`PQL` keeps every method
  signature it had; ``SQLResult`` is re-exported from
  [pql.py](pointlessql/pql/pql.py) so existing
  ``from pointlessql.pql.pql import SQLResult`` callers (notably
  [tests/test_alerts.py:417](tests/test_alerts.py#L417)) resolve
  unchanged.

- **Tests updated, not the production code.** Added ``_READ`` /
  ``_WRITE`` / ``_LIST`` constants alongside the existing ``_MOD``
  in [tests/test_pql.py](tests/test_pql.py) and re-pointed every
  ``@patch`` to the module that now owns the symbol (e.g.
  ``_get_table`` is monkeypatched on
  ``pointlessql.pql._read`` for read tests and on
  ``pointlessql.pql._write`` for write tests). Internal mocks
  must follow the implementation when the implementation is
  intentionally split — the alternative (re-importing soyuz-client
  internals back into ``pql.py`` purely for the test surface) would
  defeat the split.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 32 warnings (all pre-existing
  ``engine.py`` polars/pyarrow untyped-arg warnings), ``pydoclint``
  0 violations, ``pytest tests/test_pql.py tests/test_alerts.py``
  51/51 passed.

### Refactored — Phase 12.9 / Sprint 77: services/kernel_session.py → package

Pilot of the backend modularization arc (Sprints 77-90). The single
472-LOC ``services/kernel_session.py`` module became the package
``services/kernel_session/`` with three sibling modules + an
``__init__.py`` re-export shim. No behaviour change, no Alembic, no
new dependencies; pure structural refactor.

- **New package layout.**
  [messages.py](pointlessql/services/kernel_session/messages.py)
  (61 LOC) carries ``KernelMessage`` and ``Subscription``
  dataclasses + the ``_SUBSCRIBER_QUEUE_MAXSIZE`` constant.
  [session.py](pointlessql/services/kernel_session/session.py)
  (337 LOC) owns the ``KernelSession`` lifecycle, ZMQ pump
  tasks, bootstrap helper code, and the
  ``_KERNEL_READY_TIMEOUT``/``_SHUTDOWN_TIMEOUT``/``_BOOTSTRAP_TIMEOUT``
  constants.
  [registry.py](pointlessql/services/kernel_session/registry.py)
  (94 LOC) owns ``KernelRegistry`` + the ``drain`` async iterator.

- **Public surface preserved.** The lone external caller
  [pointlessql/api/main.py:45](pointlessql/api/main.py#L45)
  imports the module as ``kernel_session_service`` and accesses
  ``KernelRegistry``, ``KernelMessage``, ``KernelSession``,
  ``drain`` through that namespace. The new
  [__init__.py](pointlessql/services/kernel_session/__init__.py)
  re-exports the full surface so the import resolves unchanged.
  No tests directly import this module.

- **Renamed ``_Subscription`` → ``Subscription``.** The leading
  underscore conveyed file-private scope, which is no longer
  accurate now that ``KernelSession`` imports it across modules.
  Pyright's ``reportPrivateUsage`` rule flagged this immediately
  on the first split attempt.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 5 warnings (all from ``jupyter_client``'s partially-
  unknown async types — pre-existing), ``pydoclint`` 0 violations,
  smoke import via ``python -c "from pointlessql.services import
  kernel_session"``.

### Refactored — Phase 12.9 / Sprint 76: notebook/main.js → 4 sub-modules + toast helper

Follow-up to Phase 12.8.  Four sibling modules carved out of
notebook/main.js and a cross-cutting toast-guard cleanup across
sql_editor.js, notebook/main.js, and notebook/editor_shell.js.  No
behaviour change, no Alembic, no template-structure change; pure JS
refactor.

- **Notebook main.js split.**
  [main.js](frontend/js/notebook/main.js) drops 1204 → 703 LOC
  (-501).  Four new sibling modules:
  [kernel_ws.js](frontend/js/notebook/kernel_ws.js) (211 LOC) owns
  the ipykernel socket + frame routing;
  [lsp_ws.js](frontend/js/notebook/lsp_ws.js) (133 LOC) owns the
  pyright socket + didOpen + notifyDidChange;
  [cell_scanner.js](frontend/js/notebook/cell_scanner.js) (41 LOC)
  holds pure scanCellRanges + rangesToDecorations;
  [cell_editor.js](frontend/js/notebook/cell_editor.js) (104 LOC)
  holds insertCellAfter + addCellBelow + addCellAbove +
  applyResultVarToMarker.  main.js now owns orchestration glue +
  rebuildCellAffordances + save + catalog-insert only.

- **Toast-guard cleanup (Tranche 7).**
  [api.js](frontend/js/api.js) exports ``toast(variant, msg)`` and
  ``csrfToken()`` as named exports.  14 ``if (window.pqlToast)
  window.pqlToast.X(msg)`` guards in
  [sql_editor.js](frontend/js/sql_editor.js),
  [notebook/main.js](frontend/js/notebook/main.js), and
  [notebook/editor_shell.js](frontend/js/notebook/editor_shell.js)
  replaced with single-line ``toast('error', msg)`` calls.  The
  helper no-ops when the singleton is missing, so call-sites read
  top-down without branch noise.  Duplicate ``csrfToken()`` removed
  from notebook/main.js.

- **Cache-bust bumped** to ``?v=sprint76`` on the
  [notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  bootstrap script tag so browsers pick up the new ESM import graph
  without a hard reload.

- **Deferred to a follow-up sprint:** ``mount_bootstrap.js`` split
  (mount() is tightly coupled to ``this`` + the Alpine factory return
  object; extracting it means refactoring the factory shape, not a
  mechanical move).  Captured in the tranche plan at
  ``~/.claude/plans/wir-haben-in-diesem-warm-dream.md``.

- **Static gates (all green):** ``ruff``, ``pyright`` (0 errors),
  ``pydoclint``,
  [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh),
  [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh),
  ``node --check`` on every modified JS file, import-graph resolution
  check, Jinja template parse.

### Refactored — Phase 12.8 / Sprint 75: Frontend cleanup (notebook carve-up + ESM-everywhere + CSS-split + CSRF + README)

One-shot reorg sprint that clears the JS / CSS organisation debt
before Phase 13 starts.  No new feature; no behaviour change beyond
the latent CSRF fix.  Six commits, one per phase, all on main.

- **Phase 1 — notebook/main.js carve-up** (247e271).
  [main.js](frontend/js/notebook/main.js) drops 1547 → 1204 LOC.
  Five new sibling modules:
  [output_zone_manager.js](frontend/js/notebook/output_zone_manager.js),
  [cell_introspector.js](frontend/js/notebook/cell_introspector.js),
  [autosave_scheduler.js](frontend/js/notebook/autosave_scheduler.js),
  [commands.js](frontend/js/notebook/commands.js); plus
  ``createOutlineRecomputer`` factory in
  [outline.js](frontend/js/notebook/outline.js).  Grep gate
  [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  extended with the new closure-state slot names.

- **Phase 2 — ESM bridge entrypoint** (87f03a7).  New
  [frontend/js/bootstrap.js](frontend/js/bootstrap.js) loaded as
  ``<script type="module">`` from
  [base.html](frontend/templates/base.html) before the Alpine CDN
  script.  New CI gate
  [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh)
  asserts the script-tag ordering.

- **Phase 3 — editor_base + small editors to ESM** (410f144).  New
  [editor_base.js](frontend/js/editor_base.js) exports
  ``validateRequired`` and ``createDictEditor``; four inline editors
  migrated to native ES modules.

- **Phase 4 — federation / list_table / sql_editor / helpers to ESM**
  (2d9e1e2).  Last legacy files migrated.  Removed all 11 individual
  ``<script src="/static/js/X.js">`` tags from base.html +
  sql_editor.html — only bootstrap.js + Alpine + vendor CDN scripts
  load via raw ``<script>`` now.

- **Phase 5 — CSRF in pqlApi + frontend README** (a5a7a20).
  ``pqlApi.fetch`` now injects ``X-CSRF-Token`` for non-safe verbs.
  New [frontend/js/README.md](frontend/js/README.md) documents the
  post-Sprint-75 conventions.

- **Phase 6 — style.css split** (e0ae139).  1066-line single file
  carved into ten purpose-scoped sheets that the master
  [style.css](frontend/css/style.css) ``@import``s in cascade order:
  base / primitives / layout / responsive plus six under
  components/.

Hard constraints honoured: no build step, no bundler, no
``package.json``.  Static gates green: ruff, pyright, alembic,
``node --check`` on every modified file, both frontend grep gates.

### Fixed — Phase 12.7 tail: BUG-71-02 + BUG-72-01 root fix + replay completion

Closing audit pass on the Phase-12.7 sprints surfaced two bugs
the in-sprint replays missed; both fixed in a single follow-up
commit.

**BUG-71-02 — server-side notebook_doc dropped the [sql] tag +
result_var on round-trip.**  Sprint 71's frontend correctly
emitted ``# %% [sql] pql_cell_id="…" result_var="…"`` markers,
but the server-side
[notebook_doc.py](pointlessql/services/notebook_doc.py) used
jupytext for both load and save; jupytext only recognises
``[markdown]`` as a cell-type tag — anything else (``[sql]``,
``[raw]``, …) is silently dropped from the marker line, and the
cell is parsed as a plain code cell.  The ``result_var`` segment
was equally invisible.  Saving was rejected outright by the
server validator (``cell_type='sql'`` not in the allow-list).
Result: editor showed SQL cells as code cells on reload, autosave
silently failed for SQL cells.  Fix:

- Extended ``NotebookCell`` with ``result_var: str | None``.
- Added module-level ``_PQL_MARKER_RE`` mirroring the
  client-side ``CELL_MARKER_RE`` in
  [cell_parser.js](frontend/js/notebook/cell_parser.js).
- ``load_document`` post-parses the raw .py file with the regex
  to recover ``[sql]`` tags + ``result_var`` segments and
  overrides the cell type jupytext returned.
- ``save_document`` post-writes via a new ``_rewrite_sql_markers``
  helper that rewrites code-cell markers for SQL cells back to
  ``# %% [sql] pql_cell_id="…" result_var="…"``.
- ``api_save_notebook_doc`` accepts ``cell_type='sql'`` + reads
  optional ``result_var``.
- ``api_load_notebook_doc`` includes ``result_var`` in the
  bundle for every cell.
- [main.js](frontend/js/notebook/main.js) normalises
  ``result_var`` ↔ ``resultVar`` at the wire boundary on both
  load and save so the rest of the JS-side cell shape stays in
  one consistent form.

**BUG-72-01 root fix.**  The Sprint-72 commit's "workaround"
claim — that bumping bootstrap.js's ``?v=`` query busts the
inner ESM imports — was wrong; that param only invalidates
bootstrap.js itself, not the dynamically-imported siblings.  Real
fix: a new HTTP middleware
[``static_module_revalidate_middleware``](pointlessql/api/main.py)
stamps ``Cache-Control: no-cache, must-revalidate`` on every
``/static/js/notebook/*`` response, so the browser must issue a
conditional ``If-Modified-Since`` request next time.  Starlette's
StaticFiles answers 304 when unchanged (cheap); a sprint-fresh
module is delivered immediately on the next page load — no
hard-reload needed.  Sprint 72's "What the replay caught"
section in
[docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
is also corrected to reflect the real fix.

**Replay completion** for the Sprint-71 / -72 / -73 / -74
playbook steps that the in-sprint walkthroughs had skipped (L6,
L7, L8, L9, M1-M5, N6, N7, N8, O3, O5, O6).  Documented in the
new "Phase 12.7 tail" block at the end of
[notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md).

### Added (Sprint 74) — Phase 12.7: Settings drawer + keymap overlay + phase close

Tenth and final Phase 12.7 sprint.  Settings drawer (theme,
font-size, autosave-debounce knob), ``Ctrl+Alt+/`` keymap overlay
listing every editor command, four new ``pql.*`` palette actions,
and the Phase-12.7 ROADMAP node flips ``⏳ open`` → ``✅ done``.

- [frontend/js/notebook/settings_drawer.js](frontend/js/notebook/settings_drawer.js)
  — new module.  Bootstrap offcanvas with ``Theme`` (``vs-dark`` /
  ``vs`` / ``hc-black``), ``Font size`` (10-22 px), ``Autosave
  debounce`` (200-2000 ms).  Persists to localStorage under
  ``pql.nbedit.theme.v1`` / ``pql.nbedit.fontSize.v1`` /
  ``pql.nbedit.autosave.debounceMs.v1``; broadcasts a
  ``pql:settings-changed`` ``CustomEvent`` on ``document`` so
  every open tab's editor re-applies via
  ``monaco.editor.setTheme`` (page-global) +
  ``editor.updateOptions({fontSize})`` (per-instance) + a
  ``_autosaveDebounceMs`` closure mutation.
- [frontend/js/notebook/keymap_overlay.js](frontend/js/notebook/keymap_overlay.js)
  — new module.  Static 15-row commands array (Sprint 62 +
  70 + 73 + 74 additions), Bootstrap modal renderer reachable via
  the ``?`` toolbar button, the ``Ctrl+Alt+/`` keybind, and the
  ``pql.openKeymap`` palette action.  ``Ctrl+/`` left bound to
  Monaco's default ``toggle-line-comment`` to avoid shadowing the
  editor convention.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — applies ``loadSettings()`` on Monaco create; lifts
  ``_autosaveDebounceMs`` out of module scope so
  ``scheduleAutosave`` reads it at flush-queue time;
  ``registerPaletteActions`` extended with
  ``pql.toggleOutline`` / ``pql.openHistory`` /
  ``pql.openSettings`` / ``pql.openKeymap`` (last is also bound to
  ``Ctrl+Alt+/``); new Alpine methods ``openSettings`` /
  ``openKeymap`` / ``openHistoryForCurrentCell``.
- [frontend/js/notebook/bootstrap.js](frontend/js/notebook/bootstrap.js)
  — extended the tab-scope stub with ``outlineVisible`` /
  ``outline`` and the four new method names so the pre-mount
  window no longer raises ``ReferenceError`` on Alpine
  ``x-show`` / ``@click`` expressions.  Cleaned up the
  Sprint-72-era console-noise tail.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — gear (⚙) + ``?`` toolbar buttons; bootstrap.js script tag
  bumped to ``?v=sprint74``.

**BUG-74-01 (replay-caught + fixed in same commit):** double-
backticks inside an HTML template literal in
``buildModal`` (the GitHub-flavoured-markdown-style ``\`\`pql.*\`\```
text in the modal footer) terminated the backtick-quoted string
early, raising a ``SyntaxError`` inside ``buildModal`` the moment
``mountKeymapOverlay`` called it.  Symptom: ``mount()`` caught the
error generally; settings drawer mounted (earlier in the flow)
but keymap overlay never materialised, and the per-cell
affordances never rebuilt.  Fix: replaced the markdown backticks
with plain ``pql.*`` text.  Caught pre-gate via a cache-busted
dynamic ``import()`` that surfaced the real
``buildModal@keymap_overlay.js:137:18`` stack trace.

**Phase 12.7 closed.**  Ten sprints (65-74) transformed the
notebook editor from the Sprint-58 single-file monolith into a
modular, multi-tab, multi-cell-type, audit-trailed surface.
Phase 13 (Agent workloads) is next on the roadmap with the
EXPLAIN-agent loop sketched as the natural Phase-12 → Phase-13
bridge.

No Alembic migration.  Trim-safe.

### Added (Sprint 73) — Phase 12.7: Per-cell run history + diff (Alembic 018)

Ninth Phase 12.7 sprint.  Adds an audit trail of every cell
execute_request — source snapshot + lifecycle status + timestamps
+ ``execution_count`` — and a per-cell history popover with
``view diff`` against current Monaco source and a ``re-run``
button that replays the historical source through the kernel
without modifying the Monaco buffer ("what did the old version
produce?" UX, not "revert to this").

**Schema (Alembic 018).** New ``notebook_cell_run_sources`` table
with autoincrement id PK; sibling to the Sprint-60
``notebook_cell_runs`` upsert (which keeps "current state per
session" and would otherwise clobber the prior run on every
re-execute).  No FK to ``notebook_cell_runs`` — link is logical
via the indexed columns; cascade lives in
``notebook_outputs.py`` service (Sprint-67 cascade-via-service
pattern) on file delete + rename only.  ``clear_cell`` and
``clear_session`` deliberately do NOT touch the history table —
the audit trail explicitly survives both per-cell clear-outputs
and kernel restarts.

- [pointlessql/alembic/versions/018_notebook_cell_run_sources.py](pointlessql/alembic/versions/018_notebook_cell_run_sources.py)
  — new migration; ``ix_notebook_cell_run_sources_path_cell`` on
  ``(file_path, cell_id, started_at)``.
- [pointlessql/models.py](pointlessql/models.py) — new
  ``NotebookCellRunSource`` ORM model.
- [pointlessql/services/notebook_outputs.py](pointlessql/services/notebook_outputs.py)
  — ``record_cell_run_start`` (insert + return id),
  ``record_cell_run_finish`` (stamp by id),
  ``list_cell_run_sources`` (newest-first JSON-ready dicts).
- [pointlessql/api/main.py](pointlessql/api/main.py)
  — ``pending_run_sources`` map keyed by ``(cell_id,
  kernel_session_id)``; ``_wipe_cell_for_new_execute`` calls
  ``record_cell_run_start`` and stashes the returned id;
  ``_handle_shell_lifecycle`` pops the id on ``execute_reply`` and
  calls ``record_cell_run_finish``.  New admin-gated
  ``GET /api/notebook/cell-runs?path=…&cell_id=…&limit=…``.
- [frontend/js/notebook/run_history.js](frontend/js/notebook/run_history.js)
  — new module.  Closure-scoped popover + cache + AbortController.
  Re-run sends the historical source via the existing ``execute``
  WS frame (NOT ``execute_sql``, since SQL history rows already
  hold the wrapped ``__pql_sql_run(...)`` snippet — re-running
  executes the same SQL without re-walking the route's privilege
  check).  Does NOT touch Monaco.
- [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js)
  — clock-icon ``.pql-nbedit-history-btn`` mounted on every
  ``canExecute`` cell; ``handlers.onShowHistory(cellId, anchorEl)``
  threaded through ``mountAffordances``.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — ``openHistoryPopover(cellId, anchorEl)`` reads current source
  via ``cellSourceById`` for diffing.
- [scripts/vendor-diff-lib.sh](scripts/vendor-diff-lib.sh)
  — new vendoring script for jsdiff 5.2.0 (npm ``diff``, MIT,
  ~10 KB UMD ``window.Diff``).
- [.gitignore](.gitignore) — added
  ``frontend/js/vendor/jsdiff/``.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``<script src="/static/js/vendor/jsdiff/diff.min.js?v=sprint73">``
  tag; bootstrap.js bumped to ``?v=sprint73``;
  ``.pql-nbedit-history-btn`` / ``.pql-nbedit-history-popover`` /
  ``.pql-nbedit-diff`` styles.
- [scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden pattern to cover ``this._historyCache`` /
  ``this._historyPopover`` / ``this._historyAbort``.
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Playbook **Part N** added; replayed in Firefox via
  Playwright-MCP as the land gate.

**BUG-73-01 (replay-caught + fixed in same commit):** the first
version of the service threaded ``NotebookCellRunSource`` deletes
through the ``clear_cell`` cascade alongside ``NotebookOutput``
and ``NotebookCellRun``.  But ``clear_cell`` is called from
``_wipe_cell_for_new_execute`` at the top of every execute_request,
so the cascade meant every re-run deleted the prior run's row
before ``record_cell_run_start`` inserted its own — only the
most-recent run ever existed in the history table.  Fix: removed
the ``NotebookCellRunSource`` delete from ``clear_cell`` AND
``clear_session``; cascade now lives only in ``clear_path`` (file
delete) and ``rename_path`` (file rename).  Caught at the N2 step
on the first replay (DB query showed exactly one row even after
three runs).

Trim-safe — Sprint 74 (theme + keymap + phase close) does not
import the run-history module; revert is sprint-local.

### Added (Sprint 72) — Phase 12.7: ipywidgets minimal placeholder

Eighth Phase 12.7 sprint.  Scope deliberately trimmed to a
placeholder layer; full bidirectional ``comm_msg`` round-trip +
vendored widget-manager bundle deferred to a future sprint per the
Phase-12.7 master-plan decision.  ``import ipywidgets as w`` now
works in the kernel, and the output renderer paints a styled
placeholder card whenever a ``display_data`` /
``execute_result`` carries
``application/vnd.jupyter.widget-view+json`` — the user sees
where the slider / dropdown WOULD live once a future sprint wires
the widget-manager.

- [pyproject.toml](pyproject.toml) — added ``ipywidgets>=8.1`` to
  the dependency list; ``uv lock`` resolved
  ``ipywidgets-8.1.8`` + ``jupyterlab-widgets-3.0.16`` +
  ``widgetsnbextension-4.0.15``.
- [frontend/js/notebook/output_renderer.js](frontend/js/notebook/output_renderer.js)
  — new high-priority MIME branch in ``renderMimeBundle``.  Must
  come BEFORE ``text/html`` so the widget bundle wins over the
  fallback ``text/plain`` repr (every ipywidgets ``execute_result``
  carries both).  Renders a ``.pql-nbedit-output-widget-placeholder``
  card with truncated ``model_id`` + disclaimer.  Missing
  ``model_id`` falls back to ``Widget output (unrenderable)``.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — ``renderKernelMsg`` silently swallows ``comm_open`` /
  ``comm_msg`` / ``comm_close``.  No console log: a single
  ``IntSlider()`` instantiation emits dozens of comm frames and
  logging would flood DevTools.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``.pql-nbedit-output-widget-placeholder`` +
  ``.pql-nbedit-widget-model-id`` + ``.pql-nbedit-widget-note``
  styles; bootstrap.js script tag bumped to ``?v=sprint72``.
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Playbook **Part M** added with synthetic + real-widget +
  comm-swallow + missing-``model_id`` + persist/replay steps.
  Renderer verified end-to-end via a cache-busted
  ``import('/static/js/notebook/output_renderer.js?_t=' + Date.now())``
  because of BUG-72-01 below.

**BUG-72-01 — ES module disk cache hides new mime branches.**  The
notebook editor's [bootstrap.js](frontend/js/notebook/bootstrap.js)
carries a ``?v=sprintNN`` query param so its own ``<script>``
invalidates, but the modules it dynamically imports
(``editor_shell.js`` + ``main.js`` + the eight siblings,
including ``output_renderer.js``) do not carry a version param, so
the browser keeps the previous deploy's modules in disk cache.
Workaround for this sprint: bumped bootstrap.js to ``?v=sprint72``
and documented the hard-reload requirement (``Ctrl+Shift+R``) in
Part M.  Permanent fix is a follow-on sprint that threads a build-
time version stamp into every dynamic import URL — out of scope
here.

No Alembic migration.  Trim-safe — the placeholder branch is the
upgrade seam a future sprint will replace with a real widget-
manager.  No closure state added, so the reactivity-boundary grep
gate is unchanged.

### Added (Sprint 71) — Phase 12.7: SQL cell (DuckDB via PQL.sql)

Seventh Phase 12.7 sprint.  Adds the first non-Python cell type and
validates Sprint 66's cell-type registry as the right seam for new
languages.  Marker grammar widens to
``# %% [sql] pql_cell_id="<uuid>" result_var="<ident>"``; the
``result_var`` segment is optional (Databricks-style — picked over
the originally-sketched ``_pql_sql_<short-uuid>`` auto-generator
to keep chained-cell readability).  ``runCellById`` branches on the
new ``sql`` descriptor and emits an ``execute_sql`` WS frame; the
route handler parses + privilege-checks every 3-part reference
against soyuz-catalog (mirrors ``/api/sql/execute``'s SELECT loop
via the new shared ``_resolve_sql_approved_tables`` helper) before
wrapping the source into a ``__pql_sql_run(...)`` snippet that runs
in the kernel.  The kernel-side helper, defined once at start time
via ``_NOTEBOOK_BOOTSTRAP_CODE`` (silent execute_request awaited
before the iopub / shell pump tasks start so SQL runs cannot race
the helper definition), calls ``PQL.sql`` for real, materialises
the result as a pandas DataFrame, optionally binds it to the user-
named ``result_var`` in ``globals()`` for Variable Explorer to
surface, and ``display(df)`` so the Sprint-60 rich-mime path
renders the table inline.  Restart re-queues the bootstrap via the
existing execute path under reserved cell_id
``__pql_sql_bootstrap__`` so ``_is_internal_cell`` skips
persistence.

- [frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js)
  — registered ``sql`` descriptor (``markerTag: ' [sql]'``,
  ``canExecute: true``, ``bandClass: 'pql-nbedit-cell-band-sql'``,
  ``affordances: ['result_var']``).
- [frontend/js/notebook/cell_parser.js](frontend/js/notebook/cell_parser.js)
  — widened ``CELL_MARKER_RE`` to capture optional
  ``result_var="<ident>"`` (group 3); ``splitCells`` /
  ``joinCells`` round-trip the field; ``RESULT_VAR_RE`` exported
  for the affordance validator.
- [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js)
  — per-cell ``result_var`` text input (300 ms debounce write-back,
  CSS error class on invalid identifiers); ``+ SQL`` inserter
  button alongside ``+ Code`` / ``+ Markdown``;
  ``removeAffordances`` clears the debounce on cell teardown.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — ``runCellById`` branches on ``typeId === 'sql'`` and emits
  ``execute_sql``; ``runAllCells`` / ``runCellsAbove`` share the
  new ``sendCellFrame`` helper; ``cellResultVarById`` reads the
  marker; ``applyResultVarToMarker`` writes back via
  ``editor.executeEdits`` so on-disk text stays the source of
  truth.
- [pointlessql/api/main.py](pointlessql/api/main.py)
  — new ``execute_sql`` WS branch; shared
  ``_resolve_sql_approved_tables`` helper that returns either
  ``(approved, None)`` or ``({}, error_dict)`` so the WS handler
  can ship a synthetic kernel_msg straight to the cell's output
  zone on parse / catalog / privilege failures; refactored
  ``_wipe_cell_for_new_execute`` to share the persistence prelude
  with the existing ``execute`` branch.
- [pointlessql/services/kernel_session.py](pointlessql/services/kernel_session.py)
  — ``_NOTEBOOK_BOOTSTRAP_CODE`` defines ``__pql_sql_run`` in the
  kernel; ``_run_bootstrap`` runs it silently with a
  ``_BOOTSTRAP_TIMEOUT`` safety net; ``restart`` re-queues the
  bootstrap via the regular execute path under reserved cell_id
  ``__pql_sql_bootstrap__``.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``.pql-nbedit-cell-band-sql`` band hue + ``.pql-nbedit-result-var``
  input styling.
- [scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden pattern to cover ``this._resultVarTimers``
  / ``this._sqlBootstrap``.
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Playbook **Part L** added; replayed in Firefox via
  Playwright-MCP as the land gate per
  ``feedback_run_playbook_as_gate``.  Replay caught BUG-71-01:
  pandas's ``DataFrame.__repr__`` raised ``TypeError`` because
  ``SQLResult.columns`` is ``list[dict[str, str]]``, not bare
  names; fix in the same commit extracts the names with
  ``[c.get("name") if isinstance(c, dict) else c for c in
  res.columns]`` before constructing the DataFrame.

No Alembic migration.  Trim-safe — Sprints 72-74 do not import the
SQL cell.

### Added (Sprint 70) — Phase 12.7: Outline / TOC panel + cell jump

Sixth Phase 12.7 sprint.  Adds a right-side Outline panel that peers
with the Variable Explorer (mutually exclusive, same 320px slot,
same chrome).  Lists markdown H1/H2/H3 ATX headings (indented per
level) and each code cell's first non-blank stripped line
(truncated to ~60 chars).  Clicking a row jumps Monaco to the
cell's first content line and scrolls it to the viewport centre
via ``editor.revealLineInCenter`` + ``editor.focus``.

- **New module** [frontend/js/notebook/outline.js](frontend/js/notebook/outline.js)
  — pure ``buildOutline(cells)`` regex helper + ``stripCodeLabel``.
  No markdown-it dependency (dodges the Sprint-69 UMD/AMD
  loader-order class, BUG-69-01).  No closure state — re-entrant,
  idempotent.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — closure-scoped ``outlineEntries`` + 150ms debounce timer;
  mirrored into reactive ``this.outline`` as a fresh array on
  every change so Alpine's x-for diffs once per real edit.
  ``toggleOutline()`` mutually excludes with ``toggleVariables()``.
  ``jumpToCell(cellId)`` reuses ``findCellMarkerLine`` verbatim
  and adds ``revealLineInCenter`` + ``focus``.  Recompute
  re-splits from the live Monaco model
  (``splitCells(model.getValue())``) rather than reading the
  closure-scoped ``cells`` array — ``cells`` is only refreshed on
  save / ``rescanDecorations``, so free-form typing inside a cell
  would have left the outline stale (BUG-70-01, replay-caught).
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``Outline`` toolbar button between Variables and Run cell;
  right-side ``<aside class="pql-nbedit-outline">`` mirroring the
  Variables aside; inline CSS for per-level indent classes
  (``.pql-outline-l1`` / ``-l2`` / ``-l3`` / ``-code``).
- [scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden list to cover ``this._outlineEntries``,
  ``this._outlineTimer``, ``this._outlineDebounce`` so a future
  change cannot regress by parking the 150ms debounce handle on
  Alpine's proxy (its captured closure holds the live ``cells``
  array; Alpine's reactive walk would recurse — exactly the
  BUG-64-02 shape).
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Part K replay added with 7 numbered steps + known-quirks
  section + bug-catch write-ups for BUG-70-01 (stale closure
  ``cells``) and BUG-70-02 (over-stripping jupytext prefix
  double-shifted heading levels).

**No Alembic migration.**  Pure frontend, no backend change, no
persisted state (open/closed panel is session-only).  Trim-safe
per the Phase 12.7 roadmap — nothing downstream depends on
``outline.js`` or ``this.outline``; revert is O(1) sprint-local.

### Added (Sprint 69) — Phase 12.7: markdown-it + KaTeX + pencil pin

Fifth Phase 12.7 sprint.  Replaces the Sprint-65 regex markdown
preview renderer with ``markdown-it`` (CommonMark-conformant —
tables, nested lists, task lists, autolinking), layers KaTeX for
``$…$`` / ``$$…$$`` math via ``markdown-it-texmath``, and adds a
per-cell pencil button that pins a markdown cell into source view
independently of cursor position.

- **Vendored bundles** ([scripts/vendor-markdown-libs.sh](scripts/vendor-markdown-libs.sh)
  — new).  Fetches markdown-it 14.1.0, markdown-it-texmath 1.0.0,
  and KaTeX 0.16.11 from the npm registry into gitignored dirs
  under ``frontend/js/vendor/``.  Mirrors the Monaco vendoring
  pattern from ADR 0001.  Appends a ``window.texmath = texmath``
  line to the vendored ``texmath.js`` because the package ships
  CommonJS-only.
- **Renderer swap** ([frontend/js/notebook/markdown.js](frontend/js/notebook/markdown.js)).
  Exported signature unchanged — ``renderMarkdown(src) → string`` —
  so the single call site in ``main.js`` stays untouched.  Cached
  markdown-it instance lives in a module-scoped ``let`` (closure,
  not Alpine proxy); KaTeX registration is a single ``.use(...)``
  line, layer-droppable without touching the rest of the module.
- **Pencil-pin affordance** ([frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js),
  [frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js),
  [frontend/js/notebook/main.js](frontend/js/notebook/main.js)).
  Markdown descriptor gains ``affordances: ['pin']``; the toolbar
  renders a ``bi-pencil`` button right of the cell-type label on
  cells whose descriptor opts in.  Click toggles
  ``markdownZones[cellId].editModePinned`` (closure-scoped,
  session-only — no marker grammar changes, no ADR 0001 churn);
  pinned cells stay unhidden by ``updateHiddenAreas`` regardless
  of cursor position.  A rebuild re-syncs the pencil state so a
  content edit does not desync the icon.
- **Template wiring** ([frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)).
  KaTeX CSS link added; three UMD script tags (markdown-it,
  katex, texmath) load **before** ``monaco/vs/loader.js`` so
  their UMD wrappers fall through to the plain-script branch
  (BUG-69-01 replay-caught).  New CSS rules for the pencil
  button + markdown-it tables / nested lists / blockquotes /
  KaTeX blocks.  ``bootstrap.js`` cache bust bumped to
  ``?v=sprint69``.
- **Reactivity-boundary gate widened** ([scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh))
  to block ``this._mdSingleton`` / ``this._mdPinState`` /
  ``this._pinHandlers``.  markdown-it's rule registries are
  exactly the kind of deep-circular object that Alpine's
  reactive walk would wrap and traverse on every re-render —
  same BUG-64-02 class of bug, pre-empted.
- **Playbook Part J** ([docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md))
  — ten-step walkthrough (CommonMark table, nested lists, inline
  KaTeX, block KaTeX, pin keeps source visible, unpin collapses,
  session-only reset, code cells have no pencil, KaTeX drop-
  sanity, earlier-sprint regression pass).

### Fixed (Sprint 69 replay catch)

- **BUG-69-01 — UMD vs AMD loader-order collision.**  The first
  Part-J replay loaded ``markdown-it.min.js`` and ``katex.min.js``
  after ``monaco/vs/loader.js``.  Both scripts ship UMD wrappers
  that detect Monaco's ``window.define`` and register as anonymous
  AMD modules, colliding with Monaco's "one anonymous define per
  script file" contract.  Fixed by loading the three markdown
  vendor scripts **before** Monaco's loader, so ``window.define``
  does not yet exist when their UMD wrappers execute and they
  bind to ``window.markdownit`` / ``window.katex`` as globals.
  The template now documents the ordering rationale inline.

### Added (Sprint 68) — Phase 12.7: multi-notebook tab bar

Fourth Phase 12.7 sprint.  Adds a tab bar above the editor so the
user can keep several notebooks open in one page and switch
between them without a reload.  Each tab hosts its own Monaco
editor + kernel WS + LSP WS; the Sprint-65 closure-ref factory is
already N-instance-safe and the Sprint-66 affordance machinery is
editor-scoped, so tab switches are a CSS ``display`` flip rather
than a Monaco teardown.

- **Tab bar** ([frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)).
  New ``.pql-nbedit-tabbar`` above the layout; each tab shows the
  file basename, a dirty dot (``•``) when the buffer is unsaved,
  and a close button.  Horizontal-scroll overflow; no dropdown
  overflow menu.  Soft-cap at 10 tabs — the eleventh open toasts
  ``Tab limit reached``.  The Files-sidebar toggle moved from the
  per-tab toolbar to the tab-bar's right side (the sidebar is
  shell-scoped, not tab-scoped).
- **Editor shell factory** ([frontend/js/notebook/editor_shell.js](frontend/js/notebook/editor_shell.js)
  — new module).  Alpine factory ``createNotebookEditorShell``
  owns tabs + activeTabId + the close-confirm modal + the file-
  tree sidebar slice + localStorage persistence (``pql.nbedit.
  tabs.v1``).  Listens on ``document`` for ``pql:open-tab`` /
  ``pql:file-renamed`` / ``pql:file-deleted`` /
  ``pql:tab-state-changed`` — the sidebar and the per-tab scopes
  talk to the shell through this bus rather than via cross-scope
  reference walking.
- **Per-tab factory split** ([frontend/js/notebook/main.js](frontend/js/notebook/main.js)).
  Renamed ``createNotebookEditor`` → ``createNotebookTabEditor``;
  added optional ``tabId`` / ``initial`` / ``bundleLoader`` args.
  Cell + output initialisation moved inside ``mount()`` so lazy
  tabs defer network + Monaco work until first activation.  The
  factory dispatches ``pql:tab-state-changed`` for ``mounted`` /
  ``dirty`` / ``saveState`` transitions so the tab chrome stays
  in sync without reaching into the child proxy.
- **GET /api/notebook/doc** ([pointlessql/api/main.py](pointlessql/api/main.py)).
  The only backend change — a small read-only endpoint returning
  the same ``{cells, dirty, outputs}`` bundle the HTML editor
  route embeds.  Shared helper ``_build_notebook_doc_bundle``
  wraps ``notebook_doc_service.load_document`` +
  ``notebook_outputs_service.load_outputs_for_path``; the HTML
  route and the new JSON route call it identically, so first-
  paint and lazy-load can never drift.  (Roadmap line originally
  said "No backend changes"; amended with this deviation note.)
- **Sidebar API reshape** ([frontend/js/notebook/file_tree.js](frontend/js/notebook/file_tree.js)).
  ``createFileTreeSlice`` now takes ``getActivePath`` +
  ``isPathOpenInAnyTab`` callbacks instead of a static
  ``currentPath``.  Row-click / create / rename / delete dispatch
  CustomEvents on ``document`` instead of calling
  ``window.location.assign`` — the shell orchestrates tab state.
  Trash-disable now covers *any* open tab, not just the active
  one.
- **Reactivity-boundary gate widened** ([scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh))
  to block ``this._tabRefs`` and ``this._tabFactories``.  A
  shell that aggregates per-tab closure bags onto its Alpine-
  reactive ``this._`` would reproduce BUG-64-02 at N× scale.
- **Close-tab-with-unsaved-changes modal**.  Bootstrap dialog
  with Cancel / Discard & close / Save & close; reuses the
  Sprint-67 ``:class="{'d-block': flag}"`` pattern (BUG-67-01).
  Save & close dispatches ``pql:save-tab`` and waits for the
  child factory's next ``saveState`` emission before closing;
  if the save errors, the modal stays open and surfaces via the
  per-tab save toast.
- **Playbook Part I** ([docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md))
  — eleven-step multi-tab walkthrough (first open, row-click
  opens second tab lazily, cross-tab state preservation, dirty
  dot, close-clean / close-dirty / confirm-modal, reload
  persistence + lazy hydration, kernel sharing, rename updates
  chrome in place, delete closes tab silently, ten-tab cap
  toast).

### Fixed (Sprint 68 replay catch)

- **Tab-mounted flag lost during stub→real scope swap.**  The
  bootstrap stub seeded ``tabs = [seedTab]`` synchronously with
  ``mounted: false``; the template's ``x-init="tab.mounted = true;
  mount()"`` set the flag on the seed, but the async import of
  ``editor_shell.js`` + ``_hydrateTabs()`` replaced the tabs array
  wholesale — the flag was dropped on the floor.  Alpine's
  ``:key="tab.id"`` diff reused the DOM element so x-init did not
  re-fire, leaving ``tab.mounted: false`` on the live tab.  Net
  effect: opening a second tab made the first tab's ``x-if``
  (``tab.mounted || active``) evaluate false, Alpine unmounted
  the pane, Monaco + kernel were torn down mid-session.  Fixed
  by having the per-tab factory fire
  ``pql:tab-state-changed { mounted: true }`` **synchronously**
  at the top of ``mount()``, before any async Monaco / kernel /
  LSP work; the shell's listener updates ``tab.mounted`` in the
  tabs array so the x-if lazy-mount wrapper stays true through
  subsequent tab switches.

### Added (Sprint 67) — Phase 12.7: file-tree sidebar inside the editor

Third Phase 12.7 sprint.  Mounts the Sprint-27 workspace tree as a
slim left sidebar in ``/notebook/editor`` and closes the long-
deferred notebook create / rename / delete actions from Sprint 27.
The full-screen ``/notebooks/workspace`` page stays as-is.

- **File-tree sidebar** ([frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html),
  [frontend/js/notebook/file_tree.js](frontend/js/notebook/file_tree.js)).
  260px left panel listing directories + ``.py`` + ``.ipynb`` leaves
  from ``/api/notebooks/tree``.  Hover pencil / trash; click names
  to navigate.  Currently-open row is highlighted and its trash is
  disabled to keep the editor out of a dangling state after delete.
  Toggle state persists in ``localStorage['pql.nbedit.filesVisible']``;
  sidebar defaults visible on first load.
- **Three CRUD endpoints** ([pointlessql/api/main.py](pointlessql/api/main.py)):
  ``POST /api/notebooks/create`` writes a zero-byte ``.py`` file
  (the editor's open handler already materialises cell markers on
  first save), ``PATCH /api/notebooks/rename`` atomically moves a
  file and re-keys its replay cache, ``DELETE /api/notebooks?path=…``
  removes the file and cascades into ``notebook_outputs`` +
  ``notebook_cell_runs``.  All admin-only, all audit-logged.
- **Shared resolver** ([pointlessql/services/notebook_workspace.py](pointlessql/services/notebook_workspace.py)):
  new ``resolve_notebook_target`` owns the traversal + parent-
  directory guard for every mutation helper; the pre-existing
  ``resolve_upload_target`` now delegates to it.  Added
  ``create_empty_notebook`` / ``rename_notebook`` /
  ``delete_notebook`` helpers.
- **Replay cache re-keying** ([pointlessql/services/notebook_outputs.py](pointlessql/services/notebook_outputs.py)):
  new ``rename_path`` ``UPDATE``s ``file_path`` on ``NotebookOutput``
  + ``NotebookCellRun`` so rename preserves per-cell outputs + run
  history.  Paired with the existing ``clear_path`` which is now
  wired from the delete endpoint.
- **Three Bootstrap modals** on the editor page — new / rename /
  delete — reusing the Catalog-Insert modal's ``x-show`` +
  ``@keydown.escape.window`` pattern.
- **Reactivity-boundary gate widened** ([scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh))
  to block ``this._treeFetchCtrl`` and ``this._treeAbort`` —
  sidebar's AbortController for inflight tree fetches stays in
  closure scope.
- **Playbook Part H** ([docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md))
  covers the six sidebar flows: render, toggle, open, new,
  rename-open-file (hard-reload), delete-other-file (tree refresh).

### Fixed (Sprint 67 replay catch)

- **BUG-67-01** — Alpine 3.14.1's ``x-show`` sets inline
  ``display = ''`` on ``false → true``, letting Bootstrap 5's
  ``.modal { display: none }`` CSS rule win: every editor modal
  stayed invisible on its first open even though Alpine thought
  it was visible.  The pre-existing Catalog-Insert modal (Sprint
  62-ish) had the same latent bug.  Fixed by replacing ``x-show``
  with ``:class="{ 'd-block': flag }"`` on all four editor modals
  (Catalog, New, Rename, Delete) — Bootstrap's ``.d-block``
  utility is ``display: block !important`` which beats both the
  cascade and Alpine's inline manipulation.  Caught by replaying
  Part H of the editor playbook in Firefox per
  ``feedback_run_playbook_as_gate``.

**No Alembic migration** — rename is a plain ``UPDATE``, delete
reuses the ``clear_path`` stub Sprint 63 had already wired in
anticipation of this sprint.

### Added (Sprint 66) — Phase 12.7: cell-type registry + per-cell affordances

Second Phase 12.7 sprint.  Converts the hardcoded ``code | markdown``
fork spread across ``cell_parser.js`` + ``main.js`` into a single
descriptor registry, and surfaces per-cell affordances (run button,
execution-count pill, elapsed-time pill, status pill, ``+`` inserter)
that the wire protocol already carried but the Sprint-58 UI ignored.
No backend changes, no Alembic migration — the ``notebook_cell_runs``
columns reserved by Sprint 60's Alembic 017 stay unwritten until
Sprint 73 actually persists per-cell history.

- **Cell-type registry** at [frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js).
  One descriptor per type with ``id``, ``label``, ``markerTag``,
  ``canExecute``, ``bandClass``.  ``getCellType(id)`` is the single
  lookup point; unknown tags fall back to ``code`` so a Sprint-71
  ``[sql]`` marker loaded by a pre-Sprint-71 client renders as plain
  Python instead of dropping the cell.  ``CELL_MARKER_RE`` widened
  from ``(\s+\[markdown\])?`` to ``(\s+\[\w+\])?``.
- **Per-cell affordances** at [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js).
  Two view zones per cell — a 26px toolbar above the marker (run
  button + ``[n]`` exec count + status pill + elapsed + type label)
  and a 22px hover-revealed inserter below the cell body with
  ``+ Code`` / ``+ Markdown`` buttons.  All DOM nodes, Monaco view-
  zone handles, and ``setInterval`` timers live in a closure-scoped
  ``cellAffordances`` map on the orchestrator — BUG-64-02
  reactivity-boundary invariant preserved.
- **WS wiring.**  ``renderKernelMsg`` in ``main.js`` now intercepts
  ``execute_input`` (pulls ``execution_count`` into the pill) and
  ``execute_reply`` (maps ``ok`` / ``error`` / ``aborted`` →
  ``ok`` / ``error`` / ``cancelled``) before dispatching to the
  existing ``appendOutputFrame`` path, so empty output zones no
  longer leak from shell-channel replies.
- **Status pills.**  Five states — ``idle``, ``running`` (yellow,
  pulsing), ``ok`` (green), ``error`` (red), ``cancelled``
  (muted).  Elapsed timer ticks every 100 ms during a run and
  freezes on ``execute_reply``.  Kernel ``restart`` resets all
  count pills to ``[ ]``, status pills to ``idle``, and clears
  elapsed.
- **Single execution seam.**  ``runCellById(cellId)`` is the one
  method that fires an execute frame; ``runCurrentCell`` /
  ``runAllCells`` / ``runCellsAbove`` / per-cell ``▶`` button all
  route through it.  Registry's ``canExecute`` gate is checked once
  at the seam instead of being duplicated per-call-site.
- **``+`` inserter**.  Inserts a fresh cell (with UUID from
  ``crypto.randomUUID``) one line below the anchor cell's body,
  using ``getCellType(typeId).markerTag`` so the inserter does not
  know about the specific tag strings.  ``rebuildCellAffordances``
  is idempotent — it re-runs on every ``onDidChangeContent`` and
  moves zones via ``removeZone`` + ``addZone`` to re-anchor after
  boundary shifts.
- **Reactivity-boundary gate widened.**  ``scripts/check-frontend-no-reactive-monaco.sh``
  now also blocks ``this._cellAffordances``, ``this._statusWidgets``,
  ``this._cellWidgets``, and ``this._reactiveRoot`` so the
  Sprint-66 state surface cannot be smuggled back onto ``this._X``
  under a different field name.
- **Playbook Part G** added to [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  covering the seven check-boxes: toolbar visible per cell, per-cell
  run button, error status, interrupt → cancelled, ``+`` inserter
  (code + markdown), kernel-restart reset, page-reload BUG-64-02
  regression gate.  Replayed in Firefox via Playwright-MCP as the
  land gate per ``feedback_run_playbook_as_gate``.
- **Alpine-vs-ESM race fix** (caught by the replay).  Sprint-65's
  ``<script type="module" src="bootstrap.js">`` + the two extra
  Sprint-66 modules pushed the ESM graph resolution past Alpine's
  deferred boot, leaving the reactive scope empty on first load.
  Fixed by converting [bootstrap.js](frontend/js/notebook/bootstrap.js)
  from a module to a classic IIFE that registers
  ``window.notebookEditor`` synchronously during HTML parse and
  dynamic-imports [main.js](frontend/js/notebook/main.js) inside
  the factory's ``mount()``.  Same mitigation pattern as the
  Sprint-41 SQL-editor fix (commit ``b830300``).  Script tag
  carries ``?v=sprint66`` to bust Firefox's module cache for
  consumers upgrading in-place.
- **KeyboardInterrupt → ``cancelled``** (caught by the replay).
  Jupyter surfaces a user-interrupted cell as
  ``execute_reply.status='error'`` with ``ename='KeyboardInterrupt'``,
  not ``status='aborted'``.  The reply handler in
  [main.js](frontend/js/notebook/main.js) now maps both
  ``aborted`` and ``error + ename='KeyboardInterrupt'`` to the
  ``cancelled`` pill so the red error state is reserved for
  genuine runtime errors.

### Added (Sprint 65) — Phase 12.7 opener: editor JS modularisation

Phase 12.7 ("Notebook editor UX overhaul") opens with a structural
sprint that prepares the notebook editor codebase for the eight UX-
heavy follow-on sprints (cell-type registry, file-tree sidebar,
multi-tab, markdown-it + KaTeX, outline, SQL cell, ipywidgets,
history + diff, theme + keymap).  No visible UX change — the
existing 22-step playbook still passes unchanged; visible-UX sprints
starting with Sprint 66 will replay the playbook before commit.

- **JS module split.**  ``frontend/js/notebook_editor.js`` (1571-LoC
  IIFE) is replaced by nine ESM modules under
  ``frontend/js/notebook/``: ``cell_parser.js`` (markers + namespace
  introspect snippet), ``ansi.js`` (SGR → HTML traceback rendering),
  ``markdown.js`` (regex preview renderer; Sprint 69 will swap for
  ``markdown-it``), ``monaco_loader.js`` (vendored AMD + the Sprint-
  64 defer-until-load wrapper), ``pyright_client.js`` (JSON-RPC
  client + Monaco completion / hover / signature / definition
  provider registration via ``WeakMap``), ``output_renderer.js``
  (mime-bundle dispatch + Sprint-62 inline-script rehydration),
  ``closure_state.js`` (``createClosureRefs`` helper — see below),
  ``main.js`` (Alpine-factory orchestrator), and ``bootstrap.js``
  (ESM entry that exposes ``window.notebookEditor`` so Alpine's
  ``x-data="notebookEditor(...)"`` keeps resolving).
- **``createClosureRefs`` helper.**  Promotes the Sprint-64
  BUG-64-02 fix from inline-comment mahnung to a documented sealed
  bag of mutable refs that never leaves the factory closure.  Monaco
  model + editor refs live in ``refs`` (named slots; typo throws);
  other private state (timers, WebSocket handles, output-zone DOM
  maps, accumulator buffers, parsed-cell cache) moved to closure-
  scoped ``let`` vars.  The reactive object Alpine sees now carries
  primitive UI state + bound methods only.
- **CI grep gate.**  ``scripts/check-frontend-no-reactive-monaco.sh``
  greps ``frontend/js/notebook/`` for the forbidden assignment
  pattern ``this\._(editor|model|monaco|worker|wsRaw|lspWsRaw|
  saveTimer)\s*=`` and exits non-zero on a hit.  Wired into
  ``.github/workflows/test.yml`` after the ``alembic check`` step
  — pure shell, no Python venv needed.  Belt-and-suspenders against
  Sprint-66+ accidentally re-introducing the BUG-64-02 class of
  bug under a different field name.
- **Template** (``frontend/templates/pages/notebook_editor.html``)
  now loads ``<script type="module"
  src=".../notebook/bootstrap.js">``; the legacy
  ``notebook_editor.js`` is **deleted** (no grace alias — the sole
  consumer was edited in the same commit).  Two ``x-show``
  expressions that referenced the now-closure-scoped
  ``_catalogTables`` switched to the new ``catalogTablesLoaded``
  flag and ``catalogTablesEmpty`` getter on the reactive object.
- **ROADMAP.md** opens Phase 12.7 with the ten-sprint tree (65–74)
  and five trim-points marked.  Hard dependency chain: 65 unblocks
  all later sprints, 66 unblocks 71, 67 → 68.  Max-trim path is
  ``65 → 66 → 68 → 73 → 74``.

All gates green: ruff, pyright, pydoclint, alembic upgrade head +
check, plus the new ``check-frontend-no-reactive-monaco.sh``.

### Added (Sprint 64) — Phase 12.6 close: editor E2E playbook

Phase 12.6 closes with its e2e playbook and the one-release
grace aliases from Sprint 63 removed.

- **``docs/e2e-walkthroughs/notebook-editor.md``** — six-part
  deterministic playbook (First open / Execute+persistence /
  Pyright LSP / Insert-from-catalog / Variable Explorer /
  Post-retirement surfaces) replacing the Sprint-23 JupyterLab
  iframe playbook.  Same step-by-step shape the other
  playbooks follow so a human with a browser or an MCP-driven
  Claude Code session can replay it deterministically.
- **Grace aliases removed.**  ``GET /notebook`` no longer
  302-redirects (the route is unregistered; the navbar link
  goes straight to the editor so no internal caller relied on
  the redirect).  ``open-in-notebook`` response dropped the
  ``lab_url`` alias; ``pages/table.html`` reads
  ``editor_url`` directly.
- **Sprint-23 ``notebook.md`` playbook retired** — obsoleted
  by the iframe retirement.  The walkthroughs README index
  points at ``notebook-editor.md`` as slot #7.

**Phase 12.6 → ✅**.  The native notebook editor started as a
Sprint-58 skeleton (Monaco + jupytext round-trip), layered
execution (59) + persisted rich outputs (60) + Pyright LSP (61)
+ Variable Explorer / catalog insert (62) + papermill ``.py``
bridge + iframe retirement (63), and closed with the playbook
here in Sprint 64.  The quality bar ("as good as VSCode Python
Interactive Window") landed unchanged from the plan.

### Changed — Breaking (Sprint 63) — JupyterLab iframe retired

Phase 12.6 Sprint 63 retires the Sprint-3 embedded JupyterLab
iframe.  The native Monaco editor that Sprints 58–62 built ships
every notebook-facing use case end-to-end; the iframe came out in
this commit.

Breaking changes to a running deployment:

- **``jupyterlab`` is no longer a runtime dep.**  ``pyproject.toml``
  drops ``jupyterlab>=4.0``.  ``uv sync`` removes ~30 transitive
  packages from the venv.  Docker images shrink accordingly.
- **No more JupyterLab subprocess.**  ``services/jupyter.py`` is
  gone.  The FastAPI lifespan no longer starts a kernel server
  on port 8888.  ``POINTLESSQL_JUPYTER_PORT`` stays on the
  settings class for backward-compat but does nothing.
- **``GET /notebook`` now 302-redirects** to
  ``/notebook/editor?path=scratch.py``.  The Sprint-3 iframe page
  template (``pages/notebook.html``) is deleted.
- **``GET /api/jupyter/status`` is removed.**  The endpoint was
  only used by the Sprint-3 loader polling the JupyterLab
  subprocess — the native editor has no equivalent gate.
- **User-authored ``.ipynb`` editing is unsupported.**  The
  editor reads / writes ``.py`` only.  Papermill-generated
  ``.ipynb`` under ``notebooks/runs/`` still works (execute-only
  artefact) and the Sprint-27 workspace browser still lists
  ``.ipynb`` uploads for scheduling.  Migration: run
  ``jupytext --to py:percent file.ipynb`` manually.  README
  gained a migration section.
- **Navbar simplified.**  The Sprint-58 dropdown
  (JupyterLab-classic + Editor-preview) collapsed into one
  ``Notebook`` link that goes straight to the editor.
- **Sprint-26 job-detail output card** dropped the
  ``Rendered / JupyterLab`` view-mode toggle.  The rendered
  HTML (nbconvert's lab template) is now the only mode.  The
  ``Open in JupyterLab`` anchor became a ``Download ipynb``
  button that hits the existing download endpoint.
- **``Sprint-34 open-in-notebook``** now scaffolds a ``.py``
  jupytext notebook and returns ``{editor_url: …}`` instead of
  ``{lab_url: …}``.  The ``lab_url`` alias still ships on the
  response as a one-release grace for clients that have not
  been reloaded; Sprint 64 drops it.

Positive changes enabled by the retirement:

- **Papermill can schedule ``.py`` notebooks.**  The scheduler's
  ``_papermill_executor`` gains a jupytext-convert step —
  ``.py`` inputs are converted to a sibling ``.ipynb`` in
  ``runs/``, papermill executes, and the temp ``.ipynb`` is
  unlinked in a ``finally`` block.  ``resolve_notebook_path``
  accepts both suffixes.
- **Workspace tree shows ``.py`` notebooks** with a themed icon
  and an ``Open`` button that routes into the native editor.
  ``.ipynb`` entries keep the Schedule action only.
- **CSP cleanup.**  The Sprint-3 ``frame-ancestors 'self'
  http://localhost:8000 http://127.0.0.1:8000`` header was
  scoped to the JupyterLab subprocess and went away with it.
  No separate main.py CSP entry to unwind.

All gates green: ruff, pyright (0 errors, ~87 third-party
warnings, no regressions), pydoclint.

### Added (Sprint 62) — Variable Explorer + catalog insert + rich script exec

Phase 12.6 Sprint 62 rounds out the native editor's read-side
ergonomics: a live Variable Explorer reflects the kernel's user
namespace, an ``Insert from catalog`` modal drops
``pql.read_table(...)`` snippets at the cursor, Monaco's
command palette surfaces the run / clear / restart / insert
actions, and the ``text/html`` output path now executes inline
scripts so plotly / altair / bokeh render for real.

- **``__pql_`` internal cell-id namespace.**  The WS handler's
  persistence hooks skip any cell_id starting with ``__pql_``
  on both ``notebook_outputs`` inserts and
  ``notebook_cell_runs`` upserts.  This lets the editor run
  silent introspects (Variable Explorer, future autocomplete
  helpers) under reserved cell ids without polluting the DB —
  a non-breaking-change hook Sprint 63's workspace-tree
  integration can also lean on.
- **Variable Explorer sidebar.**  Toggleable right-side panel
  that lists every user-defined variable by name + type + shape
  + a 5-row ``DataFrame`` preview (pandas-styled HTML) or a
  truncated ``repr()`` fallback.  The introspect snippet runs
  under ``__pql_namespace__`` and re-fires after every user
  cell goes idle, but only when the panel is open so inactive
  tabs pay zero introspect cost.  Smoke-tested end-to-end
  against a real ipykernel: a 2×2 pandas DataFrame round-trips
  as ``{type: "DataFrame", shape: [2, 2], repr: "…"}``.
- **Insert from catalog** modal.  Fetches ``/api/tree``,
  flattens the catalog → schema → table hierarchy into a
  searchable list, inserts ``pql.read_table("cat.schema.tbl")``
  at the cursor on pick.  Binding: Ctrl+Shift+I or toolbar
  ``Catalog`` button or the command-palette entry.
- **Command palette actions.**  Every notebook-editor command
  is registered via ``editor.addAction`` so F1 / Ctrl+Shift+P
  lists them:  ``Run all``, ``Run all cells above cursor``,
  ``Insert cell above / below``, ``Insert markdown cell below``,
  ``Clear outputs``, ``Restart kernel``, ``Insert from
  catalog…``, ``Toggle variable explorer``.  Single-letter
  ``M`` / ``Y`` / ``DD`` shortcuts deliberately skipped — the
  editor stays always-in-edit-mode, Jupyter-classic's
  command-mode state machine is not worth the bookkeeping.
- **Plotly / altair / bokeh render inline.**  ``text/html``
  output is painted via ``innerHTML`` (which sandboxes
  ``<script>``) and then every ``<script>`` in the rendered
  subtree is cloned into a freshly-parsed node so the browser
  actually executes it.  Same trick Jupyter's nbrenderer
  uses; no additional vendoring.
- **Scope-gate honoured**.  ipywidgets + any ``comm_msg`` /
  ``display_data`` updating stays out of Phase 12.6 per the
  memory decision.  If a future cell emits a widget bundle
  the renderer will simply show the fallback ``text/plain``
  rep; widgets land in Phase 12.7.

### Added (Sprint 61) — Pyright LSP (completion / hover / diagnostics)

Phase 12.6 Sprint 61 wires ``pyright-langserver`` into the native
editor over a dedicated WebSocket.  Monaco's CompletionItem,
Hover, SignatureHelp, and Definition providers now route through
pyright; diagnostics populate the gutter via
``monaco.editor.setModelMarkers``.  Kernel-backed dual-source
completion is explicitly deferred to a follow-up per the plan's
scope-killer escape hatch — LSP-only ships a clean sprint.

- **Deps.** ``pyright>=1.1`` moves from dev-only to a runtime
  dep so the ``pyright-langserver`` binary ships on
  ``.venv/bin`` for both local dev and Docker.
- **Service layer** (``pointlessql/services/pyright_bridge.py``).
  ``PyrightSession`` spawns ``pyright-langserver --stdio`` and
  handles the LSP ``Content-Length`` framing in both directions
  via asyncio stdio.  Inbound messages dispatch to an async
  callback (subscriber errors are caught + logged so a broken
  consumer doesn't tear the reader loop down); outbound
  messages add the header before writing.  ``shutdown`` sends
  SIGTERM with a 2 s timeout, then SIGKILL.
- **WS route.** ``/ws/notebook/lsp?path=<rel>`` mirrors the
  Sprint-59 kernel WS: manual ``pql_session`` cookie auth,
  same traversal guard via ``resolve_py_notebook_path``, one
  pyright subprocess per connection so subprocess lifetime
  equals tab lifetime.  A 4404 close code fires when
  ``pyright-langserver`` is missing from ``PATH`` so the UI
  can say "Pyright unavailable" instead of reconnect-looping.
- **Frontend.** A ~40-line ``PyrightClient`` handles JSON-RPC
  request/response correlation + notification subscribers.
  Monaco provider registration is gated with a module-level
  flag + a ``WeakMap`` so the same global language id can
  serve multiple editor instances without cross-fire.
  ``initialize`` → ``initialized`` → ``textDocument/didOpen``
  on mount; full-document ``didChange`` on every
  ``onDidChangeContent`` (notebook-sized buffers, incremental
  sync is not worth the bookkeeping).
  ``textDocument/publishDiagnostics`` notifications repaint
  markers via ``monaco.editor.setModelMarkers``.
- **Toolbar**. New ``lspStatus`` pill reads "Loading Pyright…"
  / "Pyright ready" / "Pyright error" / "Pyright unavailable"
  next to the ``kernelStatus`` pill.
- **Out of scope (deferred).** Kernel ``complete_request``
  merged into Monaco's completion list as a second source —
  explicit scope-killer invocation, lands as a Sprint-61
  follow-up (or Sprint 62) as a ~30-line provider with no
  backend changes required.
- **Validation.** Pyright subprocess smoke proved initialize →
  didOpen → completion + diagnostics round-trip against a
  seeded ``json.`` buffer: real module members came back in
  the completion list, the trailing ``.`` was flagged by the
  diagnostics channel.  All gates green.

### Added (Sprint 60) — Output persistence + rich outputs

Phase 12.6 Sprint 60 closes the "reopen doesn't cost 90 seconds"
loop locked in ADR 0001 (kernel + output-schema decisions), and
upgrades the Sprint-59 text-only renderer to the full mime-bundle
matrix Jupyter clients ship with.

- **Alembic 017.** ``notebook_outputs`` +
  ``notebook_cell_runs`` with the exact DDL ADR 0001 pinned.
  No surprise column additions, no silent PK changes.
- **ORM models** (``pointlessql/models.py``). ``NotebookOutput``
  and ``NotebookCellRun`` follow the Sprint-56 ``TableStats``
  pattern — composite index keyed on ``(file_path, cell_id)`` for
  the hot read path, quadruple unique on the output-index triple
  for write safety.
- **Service layer** (``pointlessql/services/notebook_outputs.py``).
  Deliberately thin: ``append_output`` / ``load_outputs_for_path``
  / ``clear_cell`` / ``clear_session`` / ``clear_path`` /
  ``upsert_cell_run``.  Only four content-carrying msg types
  persist (``stream`` / ``execute_result`` / ``display_data`` /
  ``error``); status + execute_input stay ephemeral.
- **WS handler persistence hooks**.  Per-connection
  ``output_counters`` drive monotonic ``output_index`` values
  across a single session.  ``execute`` triggers
  ``clear_cell`` + upsert ``status=running`` before the ZMQ
  send.  Shell-channel ``execute_reply`` closes the run row
  with mapped status (ok/error/aborted) and the kernel's
  ``execution_count``.  A new client-initiated ``clear_cell``
  frame purges both the view zone and the DB row set.
  Restart now ``clear_session``'s the outgoing kernel session
  *before* the subprocess restart bumps the session id.
- **Editor route replay**. ``GET /notebook/editor`` threads every
  persisted output through the initial Alpine payload so the
  mount paints them into view zones synchronously — the WS hello
  frame arrives ``after`` the user sees their previous outputs,
  eliminating the reopen-wait.
- **Rich mime renderer** (``frontend/js/notebook_editor.js``).
  Priority list: ``text/html`` > ``image/svg+xml`` >
  ``image/png`` > ``image/jpeg`` > ``application/json`` >
  ``text/plain`` fallback.  Pandas-styled HTML tables inherit the
  catalog dark theme via scoped CSS.  Inline matplotlib (PNG),
  altair / plotly (HTML), and standard Jupyter display_data
  flows all land on this path.
- **ANSI tracebacks**.  A dependency-free SGR walker converts
  IPython's ``ultratb`` output into coloured ``<span>``s — no
  ``xterm.js`` bundle, no vendor-script work.  Covers the
  standard 30-37 / 90-97 foreground palette + bold + reset.
- **Toolbar** gained a ``Clear cell`` button.  Sprint 59's
  ``Restart`` button now wipes the outgoing kernel session's
  persisted rows in the same click so "restart + clear" stays
  one user action.
- **ipywidgets** remain out of scope per the Phase-12.6 decision
  memory — interactive widgets are deferred to Phase 12.7 if they
  prove load-bearing.

### Added (Sprint 59) — Kernel + WebSocket proxy + basic execution

Phase 12.6 Sprint 59 adds the second layer of the native notebook
story: one long-lived ``ipykernel`` subprocess per
``(user_id, notebook_path)`` pair, a FastAPI WebSocket endpoint
that proxies ZMQ shell / iopub messages as JSON frames, and the
client half that turns Shift+Enter into a round-trip execute
with text / stream / error outputs rendered under the cell via
Monaco view zones.  Output persistence and rich mime rendering
land in Sprint 60; LSP in Sprint 61.

- **Deps.** ``jupyter_client>=8.6`` + ``ipykernel>=6.29`` now
  pinned explicitly in ``pyproject.toml`` (both already arrived
  via papermill's transitive closure).
- **Service layer** (``pointlessql/services/kernel_session.py``).
  ``KernelSession`` wraps ``AsyncKernelManager`` + a single ZMQ
  reader pump per channel that fans out to N subscriber queues
  — two browser tabs of the same notebook can watch the same
  kernel without starving each other on ``get_iopub_msg``.
  ``KernelRegistry`` owns the dict keyed by ``(user_id, path)``
  and lives on ``app.state.kernel_registry``; the FastAPI
  lifespan's existing cleanup block calls ``shutdown_all`` so a
  clean app stop tears down every in-flight subprocess
  gracefully (SIGTERM + 5 s timeout, then force-kill — mirrors
  the Sprint-3 ``jupyter._shutdown`` pattern).
  ``POINTLESSQL_PRINCIPAL`` forwards via the kernel manager's
  ``env=`` kwarg rather than the Sprint-24 ``os.environ`` lock —
  kernels are long-lived, no concurrent ``setenv`` race to
  dodge.
- **WebSocket route.** ``/ws/notebook/kernel?path=<rel>``.
  WebSocket upgrades bypass the HTTP auth middleware, so the
  handler pulls the ``pql_session`` cookie directly and decodes
  the JWT via ``auth_service.get_current_user`` — same call
  chain the HTTP middleware uses, just from a WS context.
  Traversal guard reuses ``notebook_doc_service.
  resolve_py_notebook_path``.  Client frames: ``{type: "execute"
  | "interrupt" | "restart"}``; server frames: ``{type: "hello"
  | "ack" | "kernel_msg" | "interrupted" | "restarted" |
  "error"}``.
- **Frontend.** Shift+Enter / Ctrl+Enter run the cell at the
  cursor (Monaco ``addCommand`` bindings fire only when the
  editor has focus so the toolbar and Alpine inputs keep normal
  Enter semantics).  Current-cell detection walks upward from
  the cursor line for the nearest ``pql_cell_id`` marker.
  Output zones are Monaco view zones anchored below each cell's
  last line — ``pql-nbedit-output`` styling colour-codes
  stream/stdout, stderr, ``execute_result``, and ``error``;
  tracebacks strip ANSI codes until Sprint 60 lands ANSI-to-HTML.
  Toolbar gained Interrupt (sends SIGINT) and Restart (bumps
  ``kernel_session_id``, clears outputs) buttons plus a live
  ``kernelStatus`` indicator.
- **Out of scope (Sprint 60).** Rich mimes (``text/html``,
  ``image/png``, ``image/svg+xml``, pandas-HTML, matplotlib
  inline), persisted outputs, ANSI-to-HTML traceback rendering.
  The kernel message shape already matches what the Alembic-017
  ``notebook_outputs`` table will capture — Sprint 60 swaps the
  ephemeral DOM writes for queries against the persistence
  layer without touching the WS protocol.

### Added (Sprint 58) — Native notebook editor skeleton

Phase 12.6 opens with the skeleton of a first-party Monaco-based
notebook editor that will eventually replace the Sprint-3
JupyterLab iframe. Scope for Sprint 58 is deliberately narrow:
load, render, save. Execution, LSP, and persisted outputs land in
Sprints 59–60.

- **ADR 0001** — ``docs/adr/0001-notebook-editor.md`` locks in
  the three decisions every subsequent Phase-12.6 sprint builds
  on: single Monaco over a virtual document (not one editor per
  cell), output-persistence schema keyed by
  ``(file_path, cell_id, kernel_session_id)``, cell identity
  via UUIDs written into jupytext cell-marker metadata under the
  custom ``pql_cell_id`` key (marker form
  ``# %% pql_cell_id="<uuid>"``; the filter
  ``cell_metadata_filter: pql_cell_id,-all`` pins it into the
  notebook frontmatter so jupytext preserves the key on
  round-trip).
- **Service layer.** ``pointlessql/services/notebook_doc.py``
  wraps jupytext for ``.py`` Percent-format load / save with a
  ``resolve_py_notebook_path`` traversal guard that mirrors the
  Sprint-27 upload helper.  First load of a foreign notebook
  mints UUIDs for any cell without one and flags the document
  ``dirty`` so the editor can prompt a save.
- **Routes.** ``GET /notebook/editor?path=<relative>`` renders
  the editor with the initial document as a JSON blob the
  Alpine component consumes synchronously on mount.  Missing
  files scaffold an empty cell and are materialised on first
  save.  ``POST /api/notebook/doc`` persists the client's cell
  list back to disk; the CSRF middleware gates it via the
  ``X-CSRF-Token`` header.  Both routes reject paths that
  escape the notebooks directory or lack a ``.py`` suffix.
- **Frontend.** ``frontend/templates/pages/notebook_editor.html``
  hosts a single Monaco instance; cell boundaries render as
  background colour bands via ``deltaDecorations``.  Add-cell
  inserts a ``# %% pql_cell_id="<uuid>"`` marker through
  ``editor.executeEdits`` — no DOM mount / unmount.  The
  client-side cell parser accepts only the canonical UUID
  marker form the server writes; foreign marker variants stay
  a jupytext-on-the-server concern.
- **Monaco vendoring.** ``scripts/vendor-monaco.sh`` pins
  monaco-editor 0.52.0, fetches the tarball from
  ``registry.npmjs.org`` and extracts ``min/vs`` into
  ``frontend/js/vendor/monaco/vs/``.  Contents are gitignored
  (~14 MB); run the script once after ``git clone`` and
  whenever ``MONACO_VERSION`` bumps.
- **Navbar.** "Notebook" becomes a dropdown — ``JupyterLab
  (classic)`` still points at the Sprint-3 iframe,
  ``Editor (preview)`` opens the new route at
  ``?path=scratch.py``.  Hard rule: the iframe stays live
  until Sprint 63.

### Added (Sprint 57) — UC Volumes (upload + convert-to-Delta)

Phase 12.5 closes with the "I have a CSV, make it go" moment.
Cross-repo work: soyuz-catalog gained file IO routes under
``{prefix}/volumes/{full_name}/files`` plus a ``file://`` storage
backend behind a ``VolumeFileBackend`` protocol
(soyuz commit f8ef973).

- **Service layer** (``pointlessql/services/volumes.py``).  Async
  httpx helpers — ``upload_file``, ``browse_files``,
  ``download_file`` (streaming), ``delete_file``, ``volume_url``,
  ``build_headers`` — that talk directly to the new soyuz
  endpoints, forwarding the caller's email as ``X-Principal`` so UC
  enforcement applies.  The generated client stubs have not been
  regenerated for these routes; the raw httpx layer unblocks Phase
  12.5 without a client-regen round-trip and will be swapped in
  after the soyuz tag bumps.
- **Routes.** ``GET /volumes`` list + ``GET /volumes/{full_name}``
  detail pages; ``GET|POST /api/volumes/{full_name}/files``
  (multipart upload + browse);
  ``DELETE /api/volumes/{full_name}/files/{path:path}``; and
  ``POST /api/volumes/{full_name}/convert-to-delta`` (admin-only).
- **Convert-to-Delta.**  Streams the source file out of soyuz into
  a temp path, reads it with DuckDB's ``read_csv_auto`` /
  ``read_parquet`` / ``read_json_auto``, writes a managed Delta
  directory inside the volume's ``file://`` root at
  ``_delta_<table>/``, inspects the Delta schema via ``deltalake``,
  and calls UC's ``create_table`` to register an ``EXTERNAL``
  table with the correct columns.  Only ``file://`` volumes are
  supported this sprint — cloud backends are a soyuz follow-up.
- **Audit.** ``volume.file_uploaded``, ``volume.file_deleted``,
  ``volume.converted_to_delta``.
- **Frontend.** ``pages/volumes.html`` (list) +
  ``pages/volume_detail.html`` (detail).  Upload form uses raw
  ``fetch(..., {body: FormData})`` with the CSRF header read from
  the ``<meta name="csrf-token">`` tag.  A per-file "Convert to
  Delta" button is rendered only for supported extensions
  (``.csv`` / ``.parquet`` / ``.json``).  Component scripts are
  non-module IIFEs that publish ``window.volumeDetail``
  synchronously before Alpine walks (Phase-12 trap #1 preempted).
- **Nav.**  "Volumes" entry in ``nav_links.html``.
- Tests: 6 new cases in ``tests/test_volumes.py`` — URL + header
  helpers + four httpx ``MockTransport`` round-trips covering
  upload (multipart body + X-Principal), browse (JSON list),
  delete (boolean), and download (streamed chunks).

### Added (Sprint 56) — Column statistics / data profiling

- **Alembic 016** — new ``table_stats`` table keyed by
  ``(full_name, delta_log_version, column_name)`` with a composite
  unique constraint + ``ix_table_stats_lookup`` for the read path.
- **Model.** ``TableStats`` under ``pointlessql/models.py``.
- **Service layer** (``pointlessql/services/table_stats.py``).
  ``read_delta_log_version`` wraps ``DeltaTable.version()``.
  ``compute_stats`` opens a DuckDB conn, registers the Delta view
  via the Sprint-49 ``register_delta_view`` helper, and issues one
  aggregate SQL per column plus a second ``GROUP BY`` when
  cardinality permits.  ``write_cached`` is idempotent,
  ``read_cached`` returns parsed dicts, ``delete_cached`` evicts
  every version.  Non-numeric columns never carry a ``mean``;
  ``top_5`` is skipped when ``distinct_count`` exceeds
  ``TOP_K_DISTINCT_CEILING`` (10 000 default).
- **Routes.**
  ``POST /api/tables/{full_name:path}/profile`` — SELECT-gated,
  checks the cache first, falls back to compute + write, emits one
  ``table.profiled`` or ``table.profile_cache_hit`` audit row.
  ``GET /api/tables/{full_name:path}/stats?version=<opt>`` —
  SELECT-gated read path.
  ``DELETE /api/tables/{full_name:path}/stats`` — admin-only
  eviction with a ``table.stats_cleared`` audit row.
- **Frontend.** New "Column statistics" card on the table detail
  page with Profile + admin-only Clear cache buttons; ``top_5`` bars
  render via Chart.js (reusing Sprint-54's CDN — zero extra network
  weight).  Non-module IIFE publishes ``window.tableStats``.
- Tests: 9 new cases in ``tests/test_table_stats.py`` — pure
  helpers (end-to-end compute against a Delta fixture, top_5 ceiling,
  cache round-trip, eviction, fresh-Delta version read) + HTTP
  surface (profile → cache-hit → stats round-trip, DELETE
  admin-only, profile enforces SELECT, 404 on unknown table).

### Added (Sprint 55) — Query alerts (CloudEvents webhook + Atom/JSON Feed)

- **Alembic 015** — ``alerts`` / ``alert_destinations`` /
  ``alert_events`` + ``users.feed_token``.  ``CHECK`` constraints on
  ``condition_op`` (``gt``/``lt``/``eq``/``ne``), ``kind``
  (``webhook``/``feed``), ``outcome`` (``fired``/``suppressed``/
  ``delivery_failed``).  Per-owner unique index on the nullable
  ``feed_token``.
- **Models.** ``Alert``, ``AlertDestination``, ``AlertEvent`` under
  ``pointlessql/models.py``; each alert holds a ``backing_job_id``
  FK so the existing scheduler drives firing via the new
  ``alert_check`` job-kind.
- **Service layer** (``pointlessql/services/alerts.py``).  Slug
  generation mirrors Sprint-51's saved-queries shape; CRUD with
  ``(user_id, is_admin)`` enforcement at the boundary; destination
  add/remove; event record/list/prune.  Pure helpers
  ``evaluate_condition`` + ``build_cloudevent`` are covered by
  dedicated tests.
- **Dispatcher** (``pointlessql/services/alert_dispatcher.py``).
  ``dispatch_webhook`` canonicalises the envelope with
  ``json.dumps(sort_keys=True, separators=(",",":"))`` so receivers
  can reserialise after decoding to verify HMAC-SHA256.  Timeouts
  ``connect=5s`` + ``read=10s``; retry ladder 2 extra attempts at
  1s / 2s backoff on 5xx / transport errors; 4xx is a permanent
  failure.
- **Feeds** (``pointlessql/services/alert_feeds.py``).  Atom 1.0
  via ``xml.etree.ElementTree`` with XML prolog; JSON Feed 1.1
  per ``jsonfeed.org/version/1.1``.  Both cap to last 30 days.
- **Scheduler wiring.** New ``_alert_check_executor`` registered
  under ``alert_check`` in ``build_default_registry``.  Reuses the
  existing ``KindRegistry`` + cron-tick infrastructure: the alert's
  hidden backing ``Job`` carries the user's cron expression, the
  executor parses + enforces + runs the saved query, evaluates the
  condition, inserts one ``AlertEvent``, and fans out dispatch.
  Delivery failure flips the event's ``outcome`` to
  ``delivery_failed`` via a second UPDATE.
- **CloudEvents envelope** ``data``: ``alert_slug`` +
  ``saved_query_slug`` + ``condition`` (``{op, threshold}``) +
  ``row_count`` + ``duration_ms`` + ``referenced_tables`` +
  ``fired_at``.  ``duration_ms`` + ``referenced_tables`` carried
  explicitly so Phase-13's EXPLAIN-agent cost-gate can consume the
  same webhook sink without a later payload-shape break.
- **Routes.** ``GET|POST /api/alerts``, ``GET|PATCH|DELETE
  /api/alerts/{slug}``, ``POST /api/alerts/{slug}/destinations``,
  ``DELETE /api/alerts/{slug}/destinations/{id}``,
  ``GET|POST /api/me/feed-token{,/rotate}``,
  ``GET /alerts/feed.atom?token=<opaque>`` returning
  ``application/atom+xml``, ``GET /alerts/feed.json?token=<opaque>``
  returning ``application/feed+json``, HTML pages ``/alerts`` (list)
  + ``/alerts/{slug}`` (detail with destinations + last 50 events).
  Every per-slug endpoint collapses missing + forbidden to 404.
- **Audit actions.** ``alert.created``, ``alert.updated``,
  ``alert.deleted``, ``alert.destination_added``,
  ``alert.destination_removed``, ``alert.feed_token_rotated`` —
  all through ``log_action`` wrapped in ``asyncio.to_thread``.
- **Frontend.** ``/alerts`` list with create-alert modal;
  ``/alerts/{slug}`` detail with destination manager;
  feed URLs panel with copy + rotate actions.  Non-module IIFEs
  publish ``window.alertsPage`` / ``window.alertDetail``
  synchronously (Phase-12 trap #1 preempted).
- **Nav.** New "Alerts" entry in ``nav_links.html``.
- Tests: 19 new cases in ``tests/test_alerts.py`` — condition
  evaluator, CloudEvents envelope shape, dispatcher HMAC +
  retry ladder, Atom + JSON feed parseability, service-level CRUD
  + owner gating, HTTP round-trip (create/list/delete/stranger 404/
  feed-token auth), scheduler executor (fires + records event +
  envelope parses).

### Added (Sprint 54) — Chart toolbar + chart_config persistence

- **Alembic 014** — ``ALTER TABLE query_history ADD COLUMN
  chart_config TEXT NULL``.  JSON-as-text carrying the user's chart
  selection ``{type, x, y}``; ``NULL`` means table view, which is
  correct for every pre-Sprint-54 row.
- **New routes.** ``GET /api/queries/{history_id}`` fetches a single
  row as JSON so the editor can seed its chart config when the page
  is deep-linked from ``/queries``.  ``PATCH /api/queries/{history_id}/
  chart-config`` persists the user's selection; payload is either
  ``{type, x, y}`` (server canonicalises via
  ``json.dumps(sort_keys=True)``) or ``null`` to clear.  Owner + admin
  only; 404 collapses missing + forbidden the same way the Sprint-51
  saved-queries surface does.  Audit action:
  ``query.chart_config_updated``.
- **`POST /api/sql/execute`** success payload now echoes
  ``history_id`` so the frontend's debounced PATCH knows which row
  to update without a second round-trip.
- **Service layer.** ``query_history.get_by_id`` + ``update_chart_config``
  alongside the existing record / list helpers; every mutation takes
  ``(user_id, is_admin)`` up-front so enforcement lives at the
  service boundary, not the route.
- **Chart.js 4.4.1 UMD** via jsDelivr in ``base.html``.  Non-module —
  the Phase-12 replay (commit b830300) burned us once on Alpine/ESM
  races; rule is "factories register on ``window.<lib>`` synchronously".
- **Frontend.** New ``viewMode`` / ``chartConfig`` / ``_chartInstance``
  state on the editor component, plus ``toggleView`` /
  ``renderChart`` / ``destroyChart`` / ``downloadChartPng`` /
  ``seedFromHistory`` methods.  Global ``c`` key toggles table ↔
  chart when focus is outside CodeMirror + form controls.  Results
  card now gates table vs. chart via ``<template x-if>`` branches
  with a Bootstrap btn-group view switch.  PNG download uses
  ``canvas.toBlob`` + an ephemeral ``<a download>``.
- **`/queries` re-run link** now carries ``&history_id=<id>`` so the
  editor's ``seedFromHistory`` fetch can seed the chart config.
- Tests: 7 new cases in ``tests/test_query_history_chart_config.py`` —
  service-level (write + clear + non-owner refusal) + HTTP (owner
  round-trip, null-clears, 422 on invalid payload, 404 for strangers
  on both GET and PATCH).

### Added (Sprint 53) — EXPLAIN + autocomplete + polish + Phase 12 close-out

- **EXPLAIN ANALYZE toggle.** Second button next to Run sends
  ``{explain: true}`` to ``/api/sql/execute``.  Server-side flow:
  parse + enforce as usual, then prepend ``EXPLAIN ANALYZE`` to
  the rewritten SQL and execute.  The multi-row plan output is
  flattened into a single ``explain_text`` string (tab-joined
  cells, newline-joined rows) that the editor drops into a
  ``<pre class="pql-sql-explain-panel">`` block.  EXPLAIN runs
  deliberately skip ``query_history`` and audit — they are
  diagnostic, not operational activity.
- **Catalog-tree autocomplete.** CodeMirror's ``autocompletion``
  extension wired to a custom completion source.  On mount, the
  editor fetches ``/api/tree`` once, flattens to
  ``catalog.schema.table`` strings, and serves them as
  completions whenever the caret touches a word.  Non-admin
  callers see only catalogs they have ``USE`` on — correct
  scope because you should not autocomplete something you can't
  query.  ``@codemirror/autocomplete@6.18.4`` is now in the
  import-map.
- **Mobile stacking.** New ``@media (max-width: 767.98px)`` block
  raises the editor's ``min-height`` so it dominates the
  viewport on phones; the Bootstrap grid already collapses the
  drawer under the editor at ``<lg`` breakpoints.  Results
  table stays horizontally scrollable so wide schemas don't
  overflow.
- **`g s` keyboard shortcut** for "Go to SQL editor" landed in
  Sprint 49 — documented here for the phase index.
- **Playbook.**
  [docs/e2e-walkthroughs/sql-editor.md](docs/e2e-walkthroughs/sql-editor.md) —
  16-step walkthrough covering the golden path (editor → run →
  save → history → re-run → CSV + Parquet export → EXPLAIN →
  cancel) and the two negative paths (non-admin without
  ``SELECT`` gets 403, non-admin can't see admin's private
  saved query gets 404).  Includes a Playwright-MCP script
  and a "Known-limit notes" block that calls out the
  single-worker cancel scope, the no-column autocomplete,
  and the silent row-cap on export.
- **Phase 12 closes.** ROADMAP flips the phase to ✅ done; every
  sprint 49-53 landed with its feat + ``docs(roadmap)`` pair.
- Tests: 1 new EXPLAIN route test in ``tests/test_sql_execute.py``
  (explain=true returns ``is_explain=True`` + non-empty
  ``explain_text``; history row count does not grow).

### Added (Sprint 52) — Export + timeout + cancel

- **`GET /api/sql/execute/{history_id}/download?format=csv|parquet`.**
  Re-runs a previously recorded query (reads ``sql_text`` from the
  :class:`QueryHistory` row, re-parses, re-fetches
  ``storage_location`` for every referenced table, re-enforces
  ``SELECT`` via ``check_privilege``) and streams the result out
  as either CSV (``StreamingResponse``, row-by-row generator) or
  Parquet (``pyarrow.parquet.write_table`` into a ``BytesIO`` +
  single ``Response``).  Filename pattern is
  ``query-{history_id}-{YYYYmmdd-HHMMSS}.{ext}``.  Non-owner
  non-admin callers receive 404 — history IDs are not a bypass.
  Row-cap applies so a huge download cannot be coerced by
  editing ``?format=``.  Emits a ``query.exported`` audit row
  with ``format`` + ``row_count`` in ``detail``.
- **Query timeout (``POINTLESSQL_SQL_QUERY_TIMEOUT_SECONDS``,
  default 60).** The execute route now dispatches the DuckDB
  call via :func:`asyncio.wait_for` and fires ``conn.interrupt()``
  on the pre-captured connection when the window elapses.  A
  timeout is recorded as ``status="cancelled"`` (not ``"failed"``)
  in ``query_history`` — the query may have been valid, just
  slow.
- **Cancel button.** New ``POST /api/sql/execute/{query_id}/cancel``
  endpoint looks up the client-supplied ``query_id`` in a
  per-app :class:`dict` of live :class:`duckdb.DuckDBPyConnection`
  handles (``app.state._live_queries``), calls ``.interrupt()``,
  and returns 204.  Unknown / already-completed IDs are 204 too —
  the client races the execute response and we want idempotence.
  Exceptions raised by ``.interrupt()`` are logged but swallowed
  so a flaky backend can't 500 the cancel request.  The
  ``/sql`` page shows an orange "Cancel" button + elapsed-seconds
  counter while a query is in flight; the Alpine component
  generates a ``crypto.randomUUID`` per run so each execute call
  carries a unique ``query_id`` and the Cancel button targets the
  right connection even if the user fires another query in rapid
  succession.  Execute responses now echo ``query_id`` so clients
  never have to reconstruct it.  Single-worker-correct only;
  multi-worker cancel is Phase 14.
- **`PQL.sql()` + `_run_sql_sync` + `_run_sql_export_sync` accept
  an optional pre-created ``conn``.** The route owns the
  connection lifecycle so it can register the handle in the
  cancel registry *before* the worker thread starts running —
  a race-free design.  The notebook-style entry point (``conn=None``)
  still creates + closes its own connection for callers that
  don't need cancel.
- **Audit actions.** ``query.exported``, ``query.cancelled`` join
  the Sprint-48 ``resource.verb`` Phase-12 vocabulary.
- Tests: 4 export cases in ``tests/test_sql_export_cancel.py``
  (CSV + Parquet round-trip against a small Delta table,
  missing-history 404, re-enforcement 404 for non-owner);
  3 cancel cases (interrupt invoked on registered conn, unknown
  qid → 204, backend raise swallowed → 204); 1 execute-shape
  case (the JSON response now carries ``query_id``).  The
  cancel tests are **fully mocked** — they never run a real
  long-running DuckDB query that would need actually aborting,
  so no risk of the test harness hanging on a regressed
  interrupt path.

### Added (Sprint 51) — Saved queries

- **Alembic 013** creates ``saved_queries`` (id, unique slug,
  title, optional description, ``sql_text`` TEXT, ``owner_id`` FK
  users, ``is_shared`` BOOL default FALSE, created_at, updated_at)
  plus a ``(owner_id, updated_at)`` index so the drawer's
  "most-recently-touched first" ordering is a single index scan.
- **Visibility model.** Owner + admin always see the row; every
  other logged-in user sees it only when ``is_shared = True``.
  Mutation (PATCH / DELETE / re-share) is restricted to owner +
  admin.  The ``/api/saved-queries/{slug}`` endpoints collapse
  "not found" and "forbidden" into a single 404 so unguessable
  slugs double as a mild privacy guard for private rows.
- **`services/saved_queries.py`** — pure helpers independent of
  FastAPI.  ``make_slug(title)`` derives a URL-safe identifier
  with a 6-char hex suffix (two users saving "Daily orders"
  don't collide).  ``create_saved_query``,
  ``list_visible``, ``get_by_slug``, ``update_by_slug``,
  ``delete_by_slug`` cover the full CRUD surface; every mutation
  takes the ``(user_id, is_admin)`` pair up-front so the
  enforcement is at the service boundary, not the route.
  ``ValidationError`` on empty title / empty SQL.
- **API.**
  - ``GET /api/saved-queries`` — list visible rows, admin or
    owner view, ordered by ``updated_at DESC`` (limit 200).
  - ``POST /api/saved-queries`` — create; audit tag
    ``query.saved`` (private) or ``query.shared`` (on creation
    with ``is_shared: true``).
  - ``GET /api/saved-queries/{slug}`` — single lookup, 404 on
    miss or privacy.
  - ``PATCH /api/saved-queries/{slug}`` — partial update; audit
    tag ``query.updated`` unless the sharing flag flipped, in
    which case ``query.shared`` / ``query.unshared``.
  - ``DELETE /api/saved-queries/{slug}`` → 204; audit tag
    ``query.deleted``.
- **Editor sidebar drawer.** New ``components/saved_queries_drawer.html``
  included on ``/sql`` as a 3-col right-hand column on desktop
  (Sprint-53 will add the mobile stack).  Shows title +
  description + owner email + "shared" badge; click the title
  to load into the editor, click the red ``x`` to delete with a
  confirm dialog.
- **Save current query modal + Cmd+S.** ``<div id="pqlSaveQueryModal">``
  renders a Bootstrap modal with title / description / shared
  checkbox.  CodeMirror's ``Mod-s`` keybind and a new "Save"
  button next to "Run" both open the modal; on submit
  ``pqlApi.fetch('POST /api/saved-queries')`` creates the row
  and refreshes the drawer.
- **Audit actions.** ``query.saved``, ``query.shared``,
  ``query.unshared``, ``query.updated``, ``query.deleted`` —
  every new audit string follows the Sprint-48 ``resource.verb``
  convention settled for Phase 12.
- Tests: 11 new cases in ``tests/test_saved_queries.py`` —
  slug generation + sanitising, empty title/SQL validation,
  private peer query hidden from non-owner, shared query visible
  to non-owner, PATCH/DELETE by non-owner returns None/False,
  owner toggles ``is_shared``, full API round-trip (create →
  list → get → private-is-404-for-other-user → PATCH-by-non-
  owner-404 → DELETE-204).

### Added (Sprint 50) — Query history

- **Alembic 012** creates two new tables. ``query_history``
  (``id``, ``user_id``, ``user_email``, ``sql_text`` TEXT,
  ``started_at`` + ``finished_at``, ``status`` CHECK IN
  ``succeeded|failed|cancelled``, nullable ``row_count`` /
  ``duration_ms`` / ``error_message``, ``request_id`` for
  Sprint-16 log correlation) with composite indexes on
  ``(user_id, started_at)`` and a forward index on
  ``started_at``.  ``query_history_tables`` (``id``,
  ``query_history_id`` FK, ``full_name``, ``access_type``
  defaulting to ``"read"``) with a reverse-lookup index on
  ``(full_name, query_history_id)`` so the "who queried table X"
  pattern is a single index seek.
- **`POST /api/sql/execute` now persists history on both paths.**
  Success and failure each write a ``query_history`` row via the
  new :func:`_record_query_async` helper, which dispatches the
  INSERT through :func:`asyncio.to_thread` (same pattern as
  Sprint-48's ``_audit``).  Parse failures log an empty
  ``referenced_tables`` array; enforcement failures carry the
  refs that were extracted before ``check_privilege`` raised.
  ``error_message`` is the exception detail verbatim so the
  ``/queries`` detail panel can surface DuckDB's "column not
  found" without a second fetch.
- **`GET /queries` page** — Jinja template ``pages/queries.html``
  driven by the Sprint-33 ``listTable`` Alpine component.  Filter
  chips: *Mine only*, *Failed*, *Last 24h*.  Each row renders a
  status badge, SQL snippet (truncated at 120 chars with an
  expand-to-show-error toggle for failed rows), referenced-table
  chips, a duration, and a re-run button that links to
  ``/sql?prefill=<urlencoded sql>``.  Non-admin callers see only
  their own rows — enforcement lives in
  :func:`api_list_queries` and mirrors Sprint-33's ``/api/jobs``
  scoping.  The page opts into the Sprint-36 ``r``-refresh via
  ``list_page: True`` in its template context.
- **`GET /api/queries?user_id=&status=&since=&limit=`** — JSON
  endpoint the page preloads from.  ``since`` accepts ``24h`` /
  ``7d`` / ``30d`` / ``all`` (anything else → no filter, never a
  400).  Admin-only scoping: a non-admin's ``user_id`` is
  clamped to their own ID.  Hard cap at 1000 rows even if the
  caller asks for more.
- **Editor prefill.** ``sql_editor.js`` now reads
  ``?prefill=<urlencoded sql>`` on mount and seeds the CodeMirror
  doc with it.  URL cleanup via ``history.replaceState`` so a
  page reload isn't a second re-run.  Pattern lifted verbatim
  from Sprint-27's ``prefill_notebook_path`` in ``pages/jobs.html``.
- **Navbar collapses Notebook/SQL.** The new "SQL" nav entry
  becomes a dropdown with *Editor* → ``/sql`` and *History* →
  ``/queries``.  ``g s`` still jumps to the editor;
  Sprint 50 adds ``g q`` chord for the history.
- Tests: 5 new service cases in ``tests/test_query_history.py``
  (happy record, failure-with-error-message, user+status
  filtering, reverse table lookup, count) plus 4 new route cases
  (execute writes succeeded history, parse-fail writes failed
  history, non-admin sees only own rows on ``/api/queries``,
  ``/queries`` page renders).

### Added (Sprint 49) — SQL editor MVP

- **`POST /api/sql/execute` + `GET /sql` page.** First Phase 12 sprint.
  A dedicated ad-hoc SQL surface next to the Notebook tab: the user
  types ``SELECT … FROM catalog.schema.table`` in a CodeMirror-6
  editor, presses :kbd:`Cmd+Enter`, and sees the result table
  inline.  No history, no save, no export, no EXPLAIN, no cancel
  yet — those land in Sprints 50-53.
- **`PQL.sql()` + DuckDB-only engine for SQL.** Phase-5's
  ``POINTLESSQL_DELTA_ENGINE`` still drives :meth:`PQL.table` reads,
  but ad-hoc SQL is hard-wired to DuckDB (``duckdb`` was already a
  dep).  The new :meth:`pointlessql.pql.pql.PQL.sql` is a
  :func:`staticmethod` that opens a fresh DuckDB connection per
  request, registers every referenced Delta table as a view, runs
  the query, caps the result at ``POINTLESSQL_SQL_MAX_ROWS`` (default
  10 000), and returns a JSON-friendly ``SQLResult`` dataclass.
- **sqlglot-based 3-part-reference parser + rewriter.** New
  ``pointlessql/pql/sql_parser.py`` parses the user's SQL once with
  ``sqlglot.parse(dialect="duckdb")`` and returns a ``PreparedSQL``
  carrying (a) the distinct ``catalog.schema.table`` references in
  first-appearance order and (b) a rewritten form where each 3-part
  reference is collapsed to a single quoted identifier.  DuckDB
  reserves ``main`` as a catalog name and refuses to bind 3-part UC
  references natively; the route registers each Delta view at
  exactly that quoted identifier so the rewrite binds.  CTE
  aliases, subquery aliases, and 2-part / 1-part references are
  handled correctly (skipped or rejected).
- **Per-table SELECT enforcement.** The route fetches
  ``storage_location`` + effective permissions from soyuz-catalog
  for every referenced table and calls :func:`check_privilege` with
  ``SELECT``.  Admin short-circuits per the Phase 7 behaviour.  A
  missing grant raises :class:`AuthorizationError`, which the
  Sprint-44 RFC 9457 handler renders as
  ``application/problem+json`` with ``required_privilege=SELECT`` +
  ``full_name`` extension members.
- **Audit on execute.** Every successful call writes a
  ``query.executed`` audit row (per ROADMAP's Sprint-48 follow-up:
  Phase 12 audit actions use the ``resource.verb`` convention).
  The ``target`` is a truncated-SHA256 hash of the SQL so identical
  queries from different users collapse into one reverse-lookup key
  without blowing out the audit row width; ``detail`` carries a
  dict with ``row_count``, ``duration_ms``, referenced ``tables``,
  and the ``truncated`` flag.
- **CodeMirror 6 via CDN import-map.** The new ``pages/sql_editor.html``
  loads ``@codemirror/state``, ``@codemirror/view``,
  ``@codemirror/lang-sql`` and ``@codemirror/theme-one-dark``
  straight from ``cdn.jsdelivr.net`` through a ``<script type=
  "importmap">`` — matches the existing Bootstrap/Alpine/htmx CDN
  strategy.  Vendoring is deferred until a CSP or offline-install
  requirement makes it necessary.
- **Navbar + shortcut.** New "SQL" entry in
  ``components/nav_links.html`` (between Notebook and Jobs; shown
  to every logged-in user, not admin-gated — everyone is allowed
  to query what they have ``SELECT`` on).  ``g s`` added to the
  command-palette chord registry (``components/command_palette.html``)
  so ``g s`` from any page jumps to ``/sql``.
- **Settings.** New :class:`pointlessql.settings.SQLSettings`
  sub-model.  ``POINTLESSQL_SQL_ENABLED`` (default ``True``),
  ``POINTLESSQL_SQL_MAX_ROWS`` (default 10 000), and
  ``POINTLESSQL_SQL_QUERY_TIMEOUT_SECONDS`` (default 60 — the
  timeout knob is declared now; wiring lands in Sprint 52).  Set
  ``POINTLESSQL_SQL_ENABLED=false`` and the ``/sql`` page renders
  a disabled placeholder while ``/api/sql/execute`` returns a
  400 ``sql_execution_error``.
- **New exception ``SQLExecutionError``.** ``status_code=400``,
  ``error_code="sql_execution_error"``.  Covers both parse-time
  rejections (multi-statement, non-SELECT, 2-part refs) and
  DuckDB's own runtime errors (unknown column, type mismatch, …).
  Both surface the message verbatim so the user can fix their
  query without guessing.
- **Deps.** Added ``sqlglot>=26.0`` (resolved to 30.4.3 at lock
  time).  CodeMirror is CDN-loaded; no Python-side dep needed.
- Tests: 13 new unit tests in ``tests/test_sql_parser.py`` covering
  single refs, joins, CTE aliases, subqueries, deduplication,
  no-table queries, bad-format rejection, and the DuckDB rewrite
  output shape.  8 new route tests in ``tests/test_sql_execute.py``
  covering admin happy path, non-admin-without-SELECT 403,
  non-admin-with-SELECT happy path, malformed SQL 400, 2-part
  rejection 400, row-cap truncation, zero-table SELECT 1, and
  ``/sql`` page render.

### Added (Sprint 48) — audit-log hardening

- **Append-only ORM guards.** :class:`AuditLog` ``before_update``
  and ``before_delete`` SQLAlchemy event listeners raise a new
  :class:`AuditIntegrityError`; every existing audit row is
  effectively immutable at the ORM layer. The retention cleanup
  path opens a :class:`~contextvars.ContextVar` (the
  ``_allow_audit_mutation`` scope) to bypass the delete guard —
  that's the only way to remove a row through the ORM. Raw SQL
  can still bypass; deployments that need true WORM should layer
  PostgreSQL ``REVOKE DELETE`` on top. Pattern ported verbatim
  from ``shoreguard-fresh/shoreguard/services/audit.py:46–115``.
- **Async audit writes.** :func:`api.main._audit` now dispatches
  the INSERT via :func:`asyncio.to_thread`, so request handlers
  never block on the audit DB round-trip. The rate-limit
  middleware's ``rate_limit.blocked`` hook uses the same async
  path. All 22 call sites in ``api/main.py`` were rewritten to
  ``await _audit(…)``.
- **Structured ``detail`` and richer columns.** Alembic ``011``
  widens ``audit_log.detail`` from ``String(2000)`` to ``Text``
  and adds ``client_ip`` (IPv4/IPv6, nullable) + ``actor_role``
  (``admin``/``user``/``system``, defaults to ``user``). The
  :func:`log_action` helper accepts a JSON-encodable dict for
  ``detail`` and JSON-encodes it; plain-string callers still
  work for backwards compatibility.
- **Retention policy.** New :class:`AuditSettings` sub-model
  exposes ``POINTLESSQL_AUDIT_RETENTION_DAYS`` (default 365) and
  ``POINTLESSQL_AUDIT_CLEANUP_INTERVAL_SECONDS`` (default 86 400).
  A lifespan-owned background task calls
  :func:`cleanup_old_entries` on that cadence; failures are
  logged and swallowed. Setting ``retention_days=0`` disables
  the sweep entirely (pre-Sprint-48 behaviour).
- **JSON + CSV export.** New ``GET /admin/audit/export?fmt=json|csv``
  endpoint mirrors the viewer's filter surface (``since`` / ``action`` /
  ``user`` / ``target``) and streams a filename-stamped attachment,
  capped at 10 000 rows per call. Two new "Export" buttons in the
  Sprint-41 viewer build the same query string so operators get
  "what you see is what you download".
- **Viewer surfaces new columns.** The admin-audit template gains a
  Role badge column (admin/user/system styling) and a compact IP
  column. Existing search/sort/chip behaviour ported over the new
  ``data-sort-*`` attributes.

### Fixed (Sprint 48, tests)

- ``tests/test_admin_audit.py`` + ``tests/test_rate_limit.py``
  migrated from ``MagicMock(secret_key=…)`` fixtures to real
  :class:`Settings` instances (Sprint 47 missed these two files),
  and both now pin their engines to ``StaticPool +
  check_same_thread=False`` so the Sprint-48 async audit writes
  can hand the factory to ``asyncio.to_thread`` without the
  worker seeing an empty in-memory DB.

### Fixed (Sprint 47) — test-suite regressions

- **In-memory SQLite test schemas survive the worker thread.**
  ``asyncio.to_thread``-backed code paths (``_build_home_summary``'s
  ``_db_block``) hit the engine from a separate thread, and the
  default ``QueuePool`` + ``sqlite:///:memory:`` combination gives
  each worker its own empty database — tests that touched ``/`` or
  ``/catalogs/…`` reported "no such table: jobs" even though the
  root-conftest ran ``Base.metadata.create_all``. Fix: pin every
  in-memory engine to ``StaticPool`` + ``check_same_thread=False``
  in ``tests/conftest.py`` and ``tests/test_auth_routes.py``. No
  production code changes.
- **403 enforcement tests match the rendered title case.**
  ``test_enforcement.py`` still asserted the pre-Sprint-30
  ``"Access Denied"`` title; the current 403 template renders
  ``"Access denied"`` (lowercase ``d``) via ``_STATUS_TITLES`` and
  hardcoded copy. Two assertions updated.
- **``test_list_tables`` matches the current soyuz-catalog-client
  wire format.** ``ListTablesResponse(identifiers=…)`` → ``tables=…``
  after the v0.2 rename (the production ``pql.list_tables`` already
  reads ``response.tables``).

### Added (Sprint 46)

- **Graceful JWT signing-key rotation.** Final Phase 11 hardening
  sprint. A new optional ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``
  env var lets operators rotate the primary signing key without
  invalidating every outstanding session. New tokens are always
  signed with the primary key; ``verify_jwt`` tries the primary
  first and falls back to the previous key only if the primary
  rejects the token. Expired, tampered, or third-key tokens still
  fail under both. Rotation procedure:

  1. Set ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS`` to the *current*
     (old) key value.
  2. Change ``POINTLESSQL_AUTH_SECRET_KEY`` to the new value.
     Restart / recreate the container so both settings are picked
     up at the same time.
  3. Wait for ``jwt_expiry_hours`` (default 168 h = 7 d) so every
     live session has either re-logged-in or naturally timed out.
     During this window, fresh logins emit tokens signed with the
     new key while existing cookies continue to verify under the
     old.
  4. Drop ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``. Any cookie
     still signed with the old key now fails verification and the
     user is bounced to ``/auth/login``.

  When ``secret_key_previous`` is unset (the default) the fallback
  path is disabled and a key change invalidates every live session
  immediately. Six new unit tests in ``tests/test_auth.py`` cover
  the happy path, fresh tokens during rotation, unknown keys,
  missing-fallback rejection, expiry preservation, and
  ``get_current_user``'s ``previous_key`` threading.

### Changed (Sprint 45) — BREAKING: nested Settings + renamed env vars

- **Flat `Settings` split into nine `BaseSettings` sub-models.** Fifth
  Phase 11 hardening sprint, porting the shoreguard-fresh nested-
  settings pattern 1:1.  Each sub-model owns its own ``env_prefix``:
  ``ServerSettings``, ``SoyuzSettings``, ``DatabaseSettings``,
  ``AuthSettings``, ``OIDCSettings``, ``LoggingSettings``,
  ``RateLimitSettings``, ``JupyterSettings``, ``SchedulerSettings``,
  ``DeltaSettings``.  Access moves from ``settings.secret_key`` to
  ``settings.auth.secret_key``, from ``settings.notebooks_dir`` to
  ``settings.jupyter.notebooks_dir``, etc.  Most environment
  variables are unchanged because the old flat prefix already
  overlapped — ``POINTLESSQL_RATE_LIMIT_*``,
  ``POINTLESSQL_SCHEDULER_*``, ``POINTLESSQL_OIDC_*``,
  ``POINTLESSQL_JUPYTER_*``, ``POINTLESSQL_SOYUZ_CATALOG_URL``,
  ``POINTLESSQL_LOG_LEVEL``, ``POINTLESSQL_LOG_FORMAT`` all still
  read the same value.  The breaking subset:

  | Old                                          | New                                              |
  | -------------------------------------------- | ------------------------------------------------ |
  | ``POINTLESSQL_HOST``                         | ``POINTLESSQL_SERVER_HOST``                      |
  | ``POINTLESSQL_PORT``                         | ``POINTLESSQL_SERVER_PORT``                      |
  | ``POINTLESSQL_BASE_URL``                     | ``POINTLESSQL_SERVER_BASE_URL``                  |
  | ``POINTLESSQL_DATABASE_URL``                 | ``POINTLESSQL_DB_URL``                           |
  | ``POINTLESSQL_SECRET_KEY``                   | ``POINTLESSQL_AUTH_SECRET_KEY``                  |
  | ``POINTLESSQL_JWT_EXPIRY_HOURS``             | ``POINTLESSQL_AUTH_JWT_EXPIRY_HOURS``            |
  | ``POINTLESSQL_ENGINE``                       | ``POINTLESSQL_DELTA_ENGINE``                     |
  | ``POINTLESSQL_NOTEBOOKS_DIR``                | ``POINTLESSQL_JUPYTER_NOTEBOOKS_DIR``            |
  | ``POINTLESSQL_NOTEBOOK_EXECUTE_TIMEOUT_SECONDS`` | ``POINTLESSQL_JUPYTER_EXECUTE_TIMEOUT_SECONDS`` |

  The ``docker-compose.yml`` and ``docker-compose.postgres.yml``
  default env blocks were updated in this sprint; the
  ``docker-compose.e2e.yml`` overlay accepts both the old and new
  ``BASE_URL`` name for a one-release transition.  Tests that built
  ``Settings`` with flat kwargs (``Settings(secret_key="…")``) must
  switch to nested dict kwargs (``Settings(auth={"secret_key":
  "…"})``).  The validator that anchors ``notebooks_dir`` to the
  startup CWD (BUG-28-02) and the ``oidc.enabled`` computed field
  both carried over unchanged — see ``pointlessql/settings.py`` for
  the new shape.

### Changed (Sprint 44) — BREAKING: error envelope shape

- **Error responses migrated to RFC 9457 `application/problem+json`.**
  Fourth Phase 11 hardening sprint. The previous nested envelope
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
  is replaced by a flat top-level body `{"type": "about:blank",
  "title": "<status title>", "status": <code>, "detail": "<message>",
  "code": "<identifier>", "request_id": "..."}` served with
  `Content-Type: application/problem+json`. Domain `AuthorizationError`
  surfaces its `required_privilege`, `securable_type`, and `full_name`
  as RFC 9457 extension members; FastAPI's `RequestValidationError`
  flows through the same envelope with an `errors` array extension.
  API clients that read the old nested `.error.code` / `.error.message`
  fields must switch to top-level `.code` / `.detail`. The only known
  clients — PointlesSQL's own frontend via `frontend/js/api.js` and
  two Alpine templates — were updated in the same sprint.

### Added (Sprint 44)

- **HTMX toast bridge for inline errors.** Non-boosted HTMX fragment
  requests (`HX-Request: true` without `HX-Boosted: true`) that raise
  a domain error now receive an empty body at the real error status
  plus an `HX-Trigger` header carrying a `pqlToast` event. A
  `base.html` listener forwards level + message + request_id into the
  existing Sprint-30 `window.pqlToast.error` API so the user sees an
  inline Bootstrap toast without losing the current page. Boosted
  navigations keep the branded HTML error page so htmx can still swap
  `#main-content`. The primary consumer is the upcoming Phase-12 SQL
  editor: a failed query can now surface as a toast without the
  editor losing focus.
- **Three new domain exceptions.** `SchedulerError` (scheduler
  plumbing failures pre-notebook-run), `NotebookRenderError`
  (nbconvert failures, previously misclassified as generic
  `EngineError`), and `PQLWriteError` (subclasses `EngineError` so
  existing catches keep working, but its own code lets the UI
  distinguish write failures from read/compute failures).
  `services/notebook_render.py` now raises `NotebookRenderError`
  instead of `EngineError`; `tests/test_notebook_render.py` updated.
- **Playbook `docs/e2e-walkthroughs/error-handling.md`** covers
  problem+json media type on `/api/*`, HTMX toast trigger without
  page swap, boosted-navigation HTML fallback, and 403 extension
  members.

### Added (Sprint 43)

- **Rate limiting on `/auth/*`.** Third Phase 11 hardening sprint. A
  new `rate_limit_middleware` enforces per-IP and per-email fixed-
  window caps on the auth surface: 10/10min per IP + 5/10min per
  submitted email on `POST /auth/login`, 5/1h per IP on
  `POST /auth/register`, and a shared 20/10min per-IP bucket across
  `GET /auth/sso` + `GET /auth/callback`. Buckets live in a new
  `rate_limit_events` table (Alembic migration `010`) so the limiter
  ships with zero new runtime dependencies — no Redis, no slowapi,
  no background sweeper. Opportunistic cleanup inside every check
  `DELETE`s rows older than the window, and the composite
  `(bucket, created_at)` index covers both the count and the
  delete. The middleware sits between CSRF (outer) and auth (inner)
  so cross-site forged floods still fail the cheap CSRF check
  before they can burn a slot, while CSRF-clean abuse is caught
  before bcrypt + JWT-decode run on every attempt. Rejections
  return 429 with a `Retry-After` header and emit an
  `audit_log` row with `action="rate_limit.blocked"` so the
  Sprint-41 `/admin/audit` viewer surfaces the feature without a
  second dashboard. The `rate_limit_trust_x_forwarded_for` setting
  defaults OFF and must be flipped on explicitly behind a known
  reverse proxy — otherwise any client could forge the header and
  escape the per-IP bucket; the per-email axis still catches
  distributed attacks that probe one account from many IPs. New
  playbook `docs/e2e-walkthroughs/rate-limit.md` and
  `tests/test_rate_limit.py` cover login + register + OIDC floors,
  window expiry, the `/healthz` and `/api/*` exemptions, body
  re-injection, and the audit hook.

### Added (Sprint 42)

- **CSRF protection for HTML form routes.** Second Phase 11 hardening
  sprint. A new `csrf_middleware` implements the OWASP
  double-submit-cookie pattern: every request without a `pql_csrf`
  cookie gets one (`HttpOnly`, `SameSite=Lax`, matches the JWT
  cookie's `max_age`), and every non-safe method outside `/api/`,
  `/static/`, or `/healthz` must echo that cookie back via either a
  `csrf_token` form field or an `X-CSRF-Token` header. The
  `base.html` HTMX hook auto-attaches the header for every
  boosted request from the `<meta name="csrf-token">` tag, so
  existing HTMX flows pick up protection with zero per-route edits.
  A new `{{ csrf_input() }}` Jinja macro wires the three non-boosted
  forms (login, register, logout). Token rotates on local-login,
  OIDC-login, and logout to prevent fixation; failed login keeps the
  existing cookie so retry works without a page reload. New playbook
  `docs/e2e-walkthroughs/csrf.md` and `tests/test_csrf.py` cover
  cookie issuance, both submission paths, rotation, the `/api/*`
  exemption, and body re-injection so downstream handlers still see
  posted fields.

### Added (Sprint 41)

- **Admin audit-log viewer at `/admin/audit`.** First sprint of
  Phase 11 (Hardening). The Sprint-7 `audit_log` table has been
  write-only since it landed; Sprint 41 adds the read side. Admins
  get a filterable, newest-first list view that reuses the `/jobs`
  `listTable` Alpine component, the `pql-list-*` CSS, and the
  existing `_require_admin` gate — no new frontend primitives. The
  route supports four server-side filters (`since=24h|7d|30d|all`,
  `action=`, `user=` substring, `target=` substring) plus a client-
  side "Mine only" chip. A new Alembic migration `009` adds
  `ix_audit_log_created` so the cross-user "latest N" ordering
  query has a supporting index. New "Admin" dropdown in the top
  navbar (admin-only, gated in `components/nav_links.html`)
  anchors the `/admin/*` namespace that Phase 11's remaining
  sprints will extend. New playbook
  `docs/e2e-walkthroughs/admin-audit.md` replays the flow.

### Changed

- **`ROADMAP.md`.** Opened ⏳ entries for four forward-looking
  phases with a deliberate sequence: hardening first, features
  second, public launch last. **Phase 11 (Hardening)** — CSRF
  on HTML forms, rate limiting on `/auth/*` and future
  `/api/sql/*`, graceful `secret_key` rotation, admin audit-log
  viewer reusing the `/jobs` list-table machinery.
  **Phase 12 (SQL editor + query history)** — CodeMirror `/sql`
  page, DuckDB-only `PQL.sql()` with sqlglot-based table
  resolution, `query_history` + `query_history_tables` Alembic
  migration, saved queries, export, EXPLAIN, `g s` shortcut.
  **Phase 13 (Agent workloads — sketch)** —
  `paperclip-adapter-pointlessql` companion repo, new
  `agent_run` job kind, `X-Principal`-into-sandbox for UC
  enforcement on agent queries, read-only `/agents` discovery
  page; plus two uncommitted follow-ons (ontology / Foundry-
  lite; OSINT pattern playbook). **Phase 14 (Public launch +
  external distribution — queued last)** — GHCR private→public
  flip + Phase-10-deferred packaging replay, multi-arch builds,
  public PyPI publish, optional Helm chart, positioning /
  license decisions. Phase 14 is deliberately queued for the
  end per the Phase 10 retrospective ("release engineering
  against a private audience generates self-inflicted
  friction"). No code touched — these entries anchor scope
  discussed in-session so later sessions pick up where this
  one left off.

## [0.1.0rc3] - 2026-04-18

### Added (Sprint 40)

- **`.github/workflows/docker.yml`.** On-tag image publish to
  GHCR. Builds both the PointlesSQL image (from `Dockerfile`) and
  the soyuz-catalog image (from `Dockerfile.soyuz` with a
  `build-contexts: soyuz-catalog=soyuz-catalog` overlay pointing at
  a just-cloned soyuz-catalog checkout). Pushes to
  `ghcr.io/flohofstetter/pointlessql:<tag>` and
  `ghcr.io/flohofstetter/soyuz-catalog:<pinned-soyuz-tag>`. The
  soyuz tag is parsed from `pyproject.toml`'s `[tool.uv.sources]`
  at workflow time so no hard-coded version lives in CI. A
  `verify-soyuz-tag-exists` step does `git ls-remote` with
  `SOYUZ_READ_TOKEN` before building — fails fast on a
  never-pushed tag, guarding against the Sprint 37 `v0.2.0rc1`
  failure mode. Prerelease tags (`rc*`, `a[0-9]*`, `b[0-9]*`,
  `dev[0-9]*`) do not get the `:latest` alias, matching the
  `release.yml` regex.
- **GHCR image labels.** Both `Dockerfile` and `Dockerfile.soyuz`
  grew `ARG VCS_REF` / `ARG VERSION` + `LABEL
  org.opencontainers.image.{source,revision,version,title,
  description,licenses}` on the runtime stage. `docker.yml`
  passes `--build-arg VCS_REF=${github.sha} --build-arg
  VERSION=${github.ref_name}`. The `source` label is what GHCR
  uses to link the package to the repo sidebar.
- **`docs/install.md`.** First formal install guide. Three
  flavours: Docker + GHCR images (recommended primary), pip
  install from git tag, source checkout for contributors. Each
  ends with an "expected state" assertion and a troubleshooting
  section calls out the usual landmines — `DOCKER_BUILDKIT=0`
  silently dropping `--mount=type=secret`, fine-grained PAT
  requiring per-repo grants vs. classic-PAT scopes just working,
  stale `/app/data` SQLite after a version bump.
- **`docs/e2e-walkthroughs/packaging.md`.** Eleventh playbook —
  the clean-machine flow. Preconditions assert the Sprint 40 tag
  has shipped and images exist on GHCR. Steps: `cd
  "$(mktemp -d)"`, assert anonymous `docker pull` fails
  (proves the images are private), `docker login ghcr.io`, re-pull
  succeeds, `curl` the compose file at the tag, `sed` flips
  `build:` → `image:`, `docker compose pull && up -d`, healthcheck
  poll, Playwright MCP `browser_navigate` asserts the home-page
  Welcome `<h1>`, `docker image inspect` confirms
  `org.opencontainers.image.source` labels, teardown. Found-bugs
  section left with the `(none at time of writing — fill in
  during the first live replay)` placeholder that matches
  Phase 7/8/9 convention. Index in
  `docs/e2e-walkthroughs/README.md` grew a third section
  (`Packaging`).

### Changed (Sprint 40)

- **`Dockerfile` dual auth.** The single `--mount=type=ssh` RUN
  grew a second mount: `--mount=type=secret,id=gh_pat`, both
  `required=false`. Inline shell branch prefers the token if
  `/run/secrets/gh_pat` is non-empty, else falls back to the
  ssh-agent path. Sprint 38's `docker compose build --ssh default`
  contributor flow still works; the new `GH_PAT=$(gh auth token)
  docker compose build` path is what CI + clean-machine users hit.
- **`docker-compose.yml`.** The `pointlessql` service's `build:`
  block grew `secrets: - gh_pat` alongside the existing `ssh:
  [default]`; a top-level `secrets: gh_pat: { environment:
  GH_PAT }` block wires the env var to the BuildKit secret file.
  Each service also grew a commented `# image: ghcr.io/…:<tag>`
  line above its `build:` block with a two-line explainer so
  clean-machine users can flip to the pull path with a
  comment-out-and-uncomment edit.
- **`README.md` quickstart.** "Quick start (Docker + GHCR
  images)" is now the primary top-level install path — `docker
  login ghcr.io` → `curl docker-compose.yml` → flip two lines →
  `docker compose pull && up`. The `../soyuz-catalog` sibling
  prerequisite is gone from this section. Source-build demoted to
  "Quick start (local development)" below it; both sections
  cross-link to `docs/install.md`.
- **`CLAUDE.md`.** "Docker builds" subsection rewritten for
  dual-auth; new "GHCR images" subsection documents the on-tag
  publish pipeline + the PAT-based pull flow. "Replaying the e2e
  walkthroughs" bumped playbook count ten → eleven.

### Docs (Sprint 40)

- **`ROADMAP.md`.** Sprint 40 flipped to ✅. Phase 10 flipped to
  ✅ done. Phase 10 close-out block added following the
  Phase 7/8/9 shape: what the phase bought (clean `git clone &&
  uv sync` for source, clean `docker login && compose pull && up`
  for users, every future release cuts a GH Release plus two
  GHCR images automatically), plus Deferred-to-Phase-11 list
  (multi-arch arm64, PyPI publish, Helm chart, public-GHCR flip).

## [0.1.0rc2] - 2026-04-18

### Fixed (Sprint 38 follow-on)

- **Dual-mode dev toggle.** The documented escape hatch — dropping
  a gitignored `uv.toml` with a `[sources]` block to flip
  `soyuz-catalog-client` to the sibling `../soyuz-catalog`
  checkout — was rejected by `uv` with `error: Failed to parse:
  uv.toml. The sources field is not allowed in a uv.toml file.
  sources is only applicable in the context of a project`. The
  mechanism never actually worked; Sprint 38's smoke test only
  covered the default-pinned path. Replaced with two helper
  scripts, `scripts/use-editable-soyuz.sh` and
  `scripts/use-pinned-soyuz.sh`, that swap `[tool.uv.sources]` in
  `pyproject.toml` in-place. The swap intentionally leaves the
  tree dirty so the escape-hatch state stays visible. `.gitignore`
  loses its `uv.toml` stanza (the mechanism is gone); `CLAUDE.md`
  "Wiring soyuz-catalog" rewrites the editable-hatch section.

### Changed (Sprint 39 follow-on — CI)

- **`.github/workflows/test.yml` + `release.yml`.** Torn out the
  broken sibling-checkout + `uv.toml`-drop construction. Both
  workflows now consume the private `soyuz-catalog` dep the same
  way a local checkout does: `uv sync` resolves the pinned
  `[tool.uv.sources]` git-tag source, authenticated by a single
  `git config --global url."https://x-access-token:${SOYUZ_READ_TOKEN}@github.com/".insteadOf "https://github.com/"`
  step before `uv sync`. Removed: the debug curl-probes step, the
  raw `git clone --branch v0.2.0rc2 …` sibling-checkout step, the
  `cat > uv.toml <<EOF [sources] …` override step, and every
  `working-directory: PointlesSQL` (the main checkout lives at
  the default path again).
- **`SOYUZ_READ_TOKEN` preflight.** Added a 2-check gate step
  before `uv sync`: length ≥ 30 bytes (catches empty/truncated
  paste) and `GET https://api.github.com/user` returning 200
  (catches a revoked, expired, or typo'd PAT). Fails with a
  `::error::` annotation whose prose tells the maintainer exactly
  where to re-paste. No token material is echoed. Cost is one
  HTTPS request per run; saves a minute of dep resolution on
  every bad-secret state.
- **Alembic gate needs a migrated target.** `alembic check` on a
  fresh runner produced `FAILED: Target database is not up to
  date.` — the runner has no `pointlessql.db`, so `check` has
  nothing to compare the ORM models against. Workflows now run
  `alembic upgrade head` before `alembic check` so the sqlite
  file exists at the latest revision. Locally unchanged — the
  developer's working DB is already at head.

### Notes on external fix (SOYUZ_READ_TOKEN)

The previous org-secret values were all rejected by GitHub
(the first at `3ceaf45` was 1 byte; the later re-pastes were
40-byte strings that GitHub returned HTTP 401 for on
`/user`). The 16-commit `fix(ci)` investigation on main was
this plus the `uv.toml` bug tangled up. Resolved by pasting a
freshly-generated fine-grained PAT with `Contents: Read` on
`FloHofstetter/soyuz-catalog` into the repo secret. File
content unchanged.



### Added (Sprint 39)

- **`cliff.toml`.** git-cliff template keyed to PointlesSQL's
  Conventional Commit scopes (`feat(ui)`, `fix(ui)`,
  `build(packaging)`, `docs(roadmap)`, `fix(alembic)`, …). Drives
  the release-notes body in `release.yml`.
- **`scripts/bump-version.sh`.** Single-`pyproject.toml` variant
  of soyuz-catalog's Sprint 19 bump-script. Guards: PEP 440
  syntax, clean tracked-file tree, on-main, tag-not-exists. In-
  place version bump, `uv lock`, anchored `[Unreleased]` →
  `[X.Y.Z] - <date>` flip in CHANGELOG.md (hand-written prose
  preserved verbatim), `chore(release): vX.Y.Z` commit, annotated
  tag. Does not push.
- **`.github/workflows/test.yml`.** First CI this repo has had.
  Jobs: ruff, pyright, pydoclint (Google), `alembic check`.
  Pytest stays out per the standing sprint-gate discipline.
  Private soyuz-catalog git-dep pulled via a `SOYUZ_READ_TOKEN`
  org-secret URL rewrite.
- **`.github/workflows/release.yml`.** On-tag `v*`. Runs the
  gate, `uv build`s the wheel + sdist, asserts the wheel carries
  `pointlessql/_frontend/` (force-included) and
  `pointlessql/alembic/versions/`, generates release-notes via
  `uvx git-cliff --latest --strip all`, and `gh release create`s
  with `--prerelease` auto-toggled on PEP 440 `rc*` / `a*` / `b*`
  / `dev*` shapes.

### Fixed (pre-Sprint-39 cleanup)

- **Alembic autogen drift.** `uv run alembic check` had been
  flagging six `remove_index` operations + one `add_constraint`
  on every run — the indexes were declared in migrations
  001/002/003/004/006 but never mirrored into the ORM models, so
  autogen wanted to drop them on every comparison. Declared each
  index in the owning model's `__table_args__`, including the
  partial unique `ix_users_oidc_identity`
  (`WHERE oidc_provider IS NOT NULL`) via dialect-specific
  `sqlite_where=` / `postgresql_where=` kwargs. No migration
  written — this is a model-side fix for latent drift; nothing
  in the database changes. Gate now green, so the new alembic-
  check CI step lands on solid ground.

### Changed (Sprint 38)

- **`pyproject.toml`.** `[tool.uv.sources]` swapped from an
  editable path dep (`../soyuz-catalog/soyuz-catalog-client`) to a
  private-repo git-tag pin
  (`git = "https://github.com/FloHofstetter/soyuz-catalog", tag = "v0.2.0rc2", subdirectory = "soyuz-catalog-client"`).
  First sprint where `git clone && uv sync` works on a clean
  host without a sibling `../soyuz-catalog` checkout.
- **`uv.lock`.** Regenerated against the git pin; the client is
  resolved from
  `source = { git = "…?subdirectory=soyuz-catalog-client&tag=v0.2.0rc2#<sha>" }`.
- **`Dockerfile`.** Collapsed from 3 stages to 2. The
  `soyuz-client-builder` stage and the sed-strip on
  `[tool.uv.sources]` are gone. The remaining builder stage
  fetches the client wheel over git via BuildKit
  `--mount=type=ssh`, reusing the contributor's ssh-agent. Sprint
  40 will replace this with GHCR image pulls and
  `--secret`-based `GH_TOKEN` auth.
- **`docker-compose.yml`.** `additional_contexts.soyuz-catalog`
  (only fed the now-removed Stage 1) replaced with
  `build.ssh: [default]` so `docker compose build` forwards
  ssh-agent to BuildKit. Invoke with
  `docker compose build --ssh default pointlessql`.
- **`CLAUDE.md`.** "Wiring soyuz-catalog" section rewritten.
  Default clean-machine flow documented first; the editable
  escape hatch (drop a gitignored `uv.toml` at repo root with
  `[sources] soyuz-catalog-client = { path = …, editable = true }`)
  documented second. Docker `--ssh default` requirement called
  out with a Sprint 40 forward-reference.
- **`.gitignore`.** `uv.toml` added so contributors' editable
  overrides never land in commits.

### Added (Sprint 37)

- Phase 10 (Packaging & private distribution) opened in
  [`ROADMAP.md`](ROADMAP.md). Distribution contract locked in as
  private GitHub tags over `[tool.uv.sources]` git-subdirectory
  pins; no public PyPI.
- Sprint 37 — forward-pulled soyuz-catalog Sprint 19 release
  engineering. Lands in the sibling repo `../soyuz-catalog/` at
  commit `be9c5c6`: `cliff.toml`, `scripts/bump-version.sh`
  (lockstep version bump + CHANGELOG `[Unreleased]` flip +
  annotated tag, does not push), and
  `.github/workflows/release.yml` (on-tag; runs the existing
  `check_client_drift.sh` gate, builds server + client wheels +
  sdists, attaches all four to the GitHub Release with git-cliff
  release notes).
- First tag cut in soyuz-catalog: `v0.2.0-rc1`. Sprint 38 will
  pin PointlesSQL's `soyuz-catalog-client` source against it,
  retiring the editable path-dep that currently blocks
  clean-machine `uv sync`.

### Added (Sprint 36)

- New `frontend/js/api.js` exposes `window.pqlApi.fetch(url, init)`
  returning `{ok, status, data, error}` and auto-emitting a
  `window.pqlToast.error(...)` on non-ok responses (opt out with
  `init.silent = true`). Soyuz error bodies have their `detail` /
  `message` / `error` field extracted; network failures report
  `status: 0`. Also exposes `pqlApi.reloadWithToast(message, opts)`
  for the toast-then-reload pattern (400 ms default delay).
- Migrated five Alpine components off their hand-rolled
  `fetch` + try/catch/error-string blocks onto `pqlApi.fetch`:
  `editable`, `properties_editor`, `tags_editor`, `permissions_editor`
  (including the `silent: true` effective-permissions background
  GET), and the four `federation.js` create/delete forms. The
  inline `this.error` hints stay; the toast fires on top so
  mutations fail loudly instead of burying the error in a tiny
  red span.
- Replaced every silent `window.location.reload()` after a
  mutation with `pqlApi.reloadWithToast(...)` — `job_row_actions`,
  `/jobs` create modal, `/jobs/{id}` run/pause/resume, the
  `/dashboards/{slug}` Refresh button, and the `sync_history_card`
  Sync-now button each surface a success/info toast before the
  400 ms reload.
- Expanded the Sprint-31 command-palette Alpine component into a
  keyboard-shortcut registry. The hard-coded help-modal `<dl>` now
  iterates a `shortcuts` array with `{keys, combiner, label}`
  entries. New bindings: `g h` / `g j` / `g d` Vim-style chords
  (go home / jobs / dashboards) with a 1 s pending window; `r`
  reloads the current list page when `<body data-pql-refresh="1">`
  is set. Editable-target and modifier guards match the existing
  `?` handler.
- Plumbed `list_page: True` through the five list-route template
  contexts (`/jobs`, `/dashboards`, `/connections`,
  `/external-locations`, `/credentials`); `base.html` renders
  `data-pql-refresh="1"` on the `<body>` when the flag is set, so
  `r`-to-refresh opts in without touching each page template.
- Global `:focus-visible` rule in `style.css` gives every
  focusable element the same 2 px accent outline. The Sprint-33
  `.pql-sortable:focus-visible` rule is kept for its tighter
  offset. A new `@media (prefers-reduced-motion: reduce)` block
  zeroes the `--pql-duration-*` tokens and forces
  `animation-duration: 0ms` + `transition-duration: 0ms` on
  every element so Bootstrap fades, Alpine x-transitions, and
  the offcanvas slide all respect the user preference.
- New playbook `docs/e2e-walkthroughs/ux-overhaul.md` covering
  shortcut chords, the toast flow (error → red toast, success →
  toast-then-reload), focus rings, and the reduced-motion branch.

### Added (Sprint 35)

- Breakpoint tokens `--pql-breakpoint-sm/md/lg/xl` (640 / 768 /
  1024 / 1280 px) added to the Sprint-29 token block. Reference
  values only — CSS `@media` rules cannot consume `var()`, so
  every media query in `style.css` repeats the literal; the token
  block is the canonical contract, documented in
  `docs/design-tokens.md`.
- `components/nav_links.html` extracts the inline base.html
  `<ul class="navbar-nav">` so the same link set renders in the
  top navbar at `>=640 px` and again as a "Navigation" footer
  inside the existing `offcanvas-md` sidebar drawer at `<640 px`.
  One hamburger, not two — the scope's separate `<640 px`
  hamburger was merged into the existing sidebar toggle.
- `listTable()` gains a `mobileSort: boolean` config flag. When
  true, mount renders a `.pql-list-sort-mobile <select>`
  (hidden at `>=sm`) populated from every sortable `<th
  data-sort-key>` with asc / desc options. A new
  `_onMobileSort(raw)` method sets `sortKey` + `sortDir` in one
  pick, complementing the tri-state desktop header cycle. Wired
  up on jobs, dashboards, external-locations, and the Sprint-34
  Columns card.
- CSS-only card transform at `<640 px`: `.pql-list-table` rows
  collapse into 2-column label / value stacks, with each `<td>`'s
  `data-label="…"` rendered as an uppercase key via
  `::before`. Applied to the four `listTable()` pages plus the
  Sprint-34 Schemas / Tables / Preview / Columns cards. Row-
  action cells opt out of the key rendering (no `::before`) and
  stay right-aligned.
- `.pql-notebook-mobile-notice` banner above the Jupyter iframe
  at `<768 px` — "JupyterLab is optimised for desktop…". The
  iframe itself stays mounted; the notice is a heads-up, not a
  blocker.
- Touch-target baseline `min-height: 44px` under
  `@media (hover: none)` for buttons, links, inputs, selects,
  chips, sortable headers. Scoped to touch-only devices so
  hover-capable laptops keep the compact Sprint-33 spacing.
- New playbook `docs/e2e-walkthroughs/mobile.md` exercising
  phone (375 × 812) / tablet (768 × 1024) / desktop (1280 × 800)
  viewports via `browser_resize` + `browser_navigate`; found-
  bugs section filled in clean.

### Added (Sprint 34)

- Catalog detail page (`/catalogs/{c}`) gains an inline Schemas card.
  Populated by `client.list_schemas` folded into the existing
  `asyncio.gather`; shows name (linked to schema detail), updated,
  and comment. Per-schema table counts were dropped from the original
  scope to avoid O(N) fan-out to soyuz-catalog — `schema.updated_at`
  alone keeps the card useful without the extra round-trips.
- Schema detail page (`/catalogs/{c}/schemas/{s}`) gains an inline
  Tables card with name (linked to table detail), type, format, column
  count, updated, and comment — sourced from the existing
  `list_tables` bypass path that already returns full `TableInfo`
  payloads.
- Table detail page (`/catalogs/{c}/schemas/{s}/tables/{t}`) gains a
  Preview card. New `GET /api/catalogs/{c}/schemas/{s}/tables/{t}/preview`
  runs `PQL().table(...)` inside `asyncio.to_thread` under the
  caller's `X-Principal`, caps at 10 rows server-side (no
  client-tunable `?limit=`), emits `Cache-Control: no-store` so row
  data does not persist in the browser disk cache after a permission
  revocation, and degrades to a single-card error banner on any
  engine/Delta failure instead of 500-ing the page. Engine-agnostic
  via a `_preview_head` helper that keeps DuckDB lazy
  (`rel.limit(n).df()`) and coerces polars through `to_pandas()`.
  Values flow through `fastapi.encoders.jsonable_encoder` so Decimal,
  datetime, bytes, and numpy scalars serialise cleanly.
- Columns table on the table detail page gains client-side search +
  sort via Sprint-33 `listTable()` when `columns|length >= 20`.
  Sortable keys: position, name, type, nullable. Below the threshold
  the table stays server-rendered unchanged (progressive enhancement).
- Lineage card (`components/lineage_card.html`) now groups upstream
  and downstream nodes by depth under per-depth subheadings
  ("Depth 1", "Depth 2", …) instead of a flat `sort(depth)` list
  with padding-left indent. The per-node depth badge stays —
  redundant-but-defensive survives a future collapse/filter. Node
  links (3-part `catalog.schema.table` names → table detail) were
  already present from an earlier sprint and are unchanged.
- "Open in notebook" button on the PQL snippet card (admin-only).
  New `POST /api/catalogs/{c}/schemas/{s}/tables/{t}/open-in-notebook`
  sanitises identifiers with `re.sub(r"[^A-Za-z0-9_-]", "_", …)`,
  appends `secrets.token_hex(3)` to defeat double-click filename
  collisions, writes an `nbformat.v4` notebook (markdown header +
  a `pql.table(...)`-pre-filled code cell) to
  `{notebooks_dir}/scratch/…`, re-validates the path via
  `resolve_upload_target` to block traversal escapes, and returns a
  `lab_url` the Alpine handler navigates to with
  `window.location.assign`. Writes an `open_in_notebook` audit entry.
- `notebook_workspace` skip-list extended: `scratch/` joins `runs/`
  as a top-level directory excluded from `list_workspace_tree` so
  machine-generated scratch notebooks never pollute the
  user-authored workspace view. Skip logic rewritten to match by
  name against a `_SKIP_TOP_LEVEL_DIRS` frozenset scoped to the
  notebooks root — same behaviour as before for `runs/`, adds
  `scratch/` without duplicating the absolute-path equality check.

### Added (Sprint 33)

- Shared `frontend/js/list_table.js` — `window.listTable(config)`
  Alpine factory that adds debounced (150 ms) client-side search,
  sortable column headers (asc → desc → none, driven by `aria-sort`
  + a CSS pseudo-element arrow so no className juggling is required),
  and optional filter chips on top of any Bootstrap `<table>` whose
  rows carry `data-search` + `data-sort-<key>` attributes.
  Progressive enhancement — rows stay rendered server-side and the
  page is still usable if JS never runs.
- Applied `listTable` to `/jobs`, `/dashboards`, `/connections`,
  `/credentials`, `/external-locations`. Chips configured per page:
  `Paused` + `Last run failed` on jobs, `Has bound job` on
  dashboards, one chip per distinct `connection_type` on
  connections, one chip per distinct `purpose` on credentials,
  none on external-locations.
- `frontend/js/humanize_cron.js` — `window.pqlHumanizeCron(expr)`
  turns the common 5-field cron shapes + the six `@`-macros into
  human-readable strings ("Daily at 00:00", "Weekly on Monday at
  08:30"), falls back to the raw expression for anything the helper
  doesn't recognise. Applied on the `/jobs` list Cron cell and the
  `/jobs/{id}` detail Configuration card; the cell's `title`
  attribute still shows the raw expression for hover tooltips.
- `frontend/js/relative_time.js` — extracted the Sprint 32 inline
  `window.pqlRelativeTime` helper into its own file so the
  `/jobs` "last run" column can reuse it without duplicating code.
  `home.html`'s local copy is now a one-line pointer comment; the
  helper's behaviour is unchanged.
- `GET /api/jobs` now emits `last_run_status`, `last_run_at` and
  `last_run_duration_s` per job. Populated by a new
  `_latest_run_per_job(session, job_ids)` helper that fetches the
  latest run per job in one round-trip via a `group_by(job_id)` +
  `max(started_at)` subquery, portable across SQLite and Postgres
  and riding the existing `(job_id, started_at)` index on
  `JobRun`. The same map also feeds the server-rendered `/jobs`
  row rendering.
- `/jobs` rows gain a "Last run" column — a
  `.pql-status-dot--{status}` + `pqlRelativeTime(iso)` pair
  mirroring the home dashboard's latest-runs table. Rows with no
  runs yet show `—`.
- Hover quick-actions on `/jobs` rows (admin-only) — a trailing
  `<td class="pql-row-actions">` whose buttons are revealed on
  `tr:hover` and `tr:focus-within` (always visible on touch
  devices via `@media (hover: none)`). "Run now" POSTs to the
  existing `/api/jobs/{id}/run`; "Pause" / "Resume" POSTs to
  `/pause` or `/unpause`. Both fire through `window.pqlToast` for
  the success/error banner and reload 400 ms later, matching the
  Sprint-36-direction already established by Sprint 32.
- `frontend/js/job_row_actions.js` — `window.jobRowActions({jobId,
  paused})` Alpine factory backing the new row-action buttons.
- CSS additions in `frontend/css/style.css`: `.pql-list-controls`,
  `.pql-chip` + `.pql-chip--active`, `.pql-sortable` with arrow
  pseudo-element, `.pql-row-actions` with hover/focus-within
  reveal.
- `docs/e2e-walkthroughs/list-polish.md` — Playwright MCP playbook
  covering search debounce, sortable cycle, chip AND-ing, cron
  humanization + raw-title tooltip, last-run column rendering,
  hover-reveal + toast-then-reload on Run-now / Pause, the
  non-admin column gating, the four other flat list pages, the
  `/api/jobs` JSON shape, and a Sprint-32 relative-time
  regression check.

### Added (Sprint 32)

- Home dashboard — the `/` route (formerly the welcome hero in
  `pages/catalogs.html`) is now a real dashboard. Welcome header,
  7-day success-rate sparkline (inline SVG, no Chart.js),
  10 most-recent job runs with status dots, a Recent catalogs card
  driven by `localStorage['pql.recentCatalogs']`, Your-dashboards
  card (owner-scoped), and a Quick actions cluster that keeps the
  admin-only "Create foreign catalog" modal reachable.
- 3-step onboarding checklist empty-state — shown only when the
  current user has no visible catalogs, no jobs, and no dashboards;
  suppressed when soyuz is unavailable so users whose data is fine
  are not told to "connect a data source". Admin gets the inline
  Create-foreign-catalog button; non-admin sees an
  "ask an admin" hint.
- `GET /api/home/summary` — one round-trip for every server-side
  card. Returns `{user, catalogs, jobs, dashboards, latest_runs,
  sparkline, onboarding}`. Soyuz `list_catalogs()` runs in parallel
  with the local DB work via `asyncio.gather` + `asyncio.to_thread`;
  a `CatalogUnavailableError` downgrades to `catalogs.unavailable =
  true` with a 200 response so the page still renders every local
  card. Visibility mirrors `/api/jobs` (latest_runs + sparkline
  filter `Job.run_as_user_id == user.id` for non-admins).
- Catalog-visit instrumentation in `base.html` — any page that
  threads `active_catalog` (catalog/schema/table detail) writes
  `{name, ts}` into `localStorage['pql.recentCatalogs']`, deduped
  by name, capped at 5. Pattern mirrors the Sprint-31 palette's
  `pql.recentSearches` writer.
- Sparkline CSS in `frontend/css/style.css` uses three semantic
  tints (`--pql-color-success-fg` / `--pql-color-warning-fg` /
  `--pql-color-danger-fg`) plus a neutral empty-day style, so the
  prepared light-mode variant comes for free. Bars have a 2 px
  floor and a nested `<title>` tooltip for native hover.
- `.pql-status-dot--{succeeded,failed,running,pending,skipped}` —
  compact status indicators reused by the latest-runs table.
- `pages/home.html` + `components/create_foreign_catalog_modal.html`
  (extracted from the old welcome page; the modal markup itself is
  unchanged). `pages/catalogs.html` deleted — `/` was its only
  caller. The Sprint-22 `catalog-browsing.md` playbook's step 1 was
  updated to assert the new Quick actions counter instead of the
  old `N catalogs available` pill.
- `docs/e2e-walkthroughs/home.md` — Playwright MCP playbook
  covering the twelve home-page assertions including the soyuz-down
  degradation (verified 200 + `catalogs.unavailable=true` + banner +
  local cards still render), the visit-tracking instrumentation,
  and the system-empty onboarding trigger.

### Fixed (Sprint 32, same-commit from playbook replay)

- **BUG-32-01**: the sparkline SVG didn't render because Alpine's
  `<template x-for>` inside `<svg>` fails — `<template>.content`
  is an HTML-namespaced DocumentFragment, so inner `<rect>` elements
  were parsed as unknown HTML and never bound. Surfaced as
  `ReferenceError: d is not defined` / `Document.importNode:
  Argument 1 is not an object.` in the browser console on first
  load. Fixed by computing `bar_height`, `bar_class`, and
  `bar_title` server-side in `_build_home_summary` and rendering
  the seven `<rect>`s via a plain Jinja `{% for %}` loop. The
  `homeSparkline()` Alpine factory survives only for the meta
  counters.
- **BUG-32-02**: the home-page two-column CSS Grid used
  `align-items: stretch` (the Grid default), which dehned the Job
  activity card and the Quick actions card to match whichever
  neighbour was tallest. Combined with `grid-row: 2 / span 2` on
  the Latest runs card, the Sparkline card acquired a dead lower
  half. Fixed by switching to two flex columns
  (`.pql-home-col--primary` / `--secondary`) — each card now hugs
  its natural height. Also added `justify-content: space-between`
  to `.pql-home-sparkline` so the SVG and its meta counters sit at
  opposite ends of the card header rather than clustering on the
  left.

### Added (Sprint 31)

- Global command palette — `Cmd+K` / `Ctrl+K` opens a centred dialog
  that searches catalogs, schemas, tables, connections, credentials,
  external locations, jobs, dashboards, and (admin-only) workspace
  notebooks in one shot. Prefix matches outrank substring matches;
  ties resolve by `updated_at` descending. Empty query renders
  `localStorage['pql.recentSearches']` (last 10, deduped by URL).
  `?` opens a keyboard-shortcuts help modal.
- `GET /api/search?q=&limit=` aggregates the seven sources via
  `asyncio.gather` (reusing `unitycatalog.get_tree()`,
  `list_connections/credentials/external_locations`, the local
  `Job` / `Dashboard` ORM queries, and
  `notebook_workspace.list_workspace_tree`). Per-source soyuz
  failures degrade gracefully: a `PointlessSQLError` from one
  fetcher logs at WARNING and the remaining sources still answer,
  so a soyuz blip never 502's the palette.
- `frontend/templates/components/command_palette.html` mounted once
  in `base.html` so the shortcut is global. Alpine factory
  `commandPalette()` owns palette + help-modal state, debounces
  search to 150 ms, drops stale responses by sequence number, and
  guards `?` against firing while focus is in an input or the
  palette itself.
- Navbar gains a ghost-button trigger (`.pql-cmdk-trigger`) with a
  platform-aware `⌘K` / `Ctrl+K` keycap hint and a mobile-only
  search-icon button below 768 px. Removed the `ms-auto` from the
  navbar `<ul>` and put it on the trigger so the button anchors the
  right-hand cluster.
- Design-token-native CSS for the palette, hit list, type badges
  (one accent per source family), help modal, and `<kbd>` keycaps;
  reuses `--pql-color-*`, `--pql-elev-3`, and `--pql-radius-md`
  from Sprint 29 so light mode works for free.
- `docs/e2e-walkthroughs/command-palette.md` — Playwright MCP
  playbook covering navbar trigger, Cmd+K, keyboard nav, recent
  searches, admin/non-admin notebook visibility split, the `?`
  help modal, and the soyuz-degraded fallback.

### Added (Sprint 30)

- New app-shell layer in `base.html`: mobile-aware responsive grid
  (`minmax(0, 1fr)` below `md`, `var(--pql-sidebar-width) minmax(0, 1fr)` ≥ md),
  sidebar wrapped in Bootstrap 5.3 `offcanvas-md` with a hamburger
  trigger visible only on narrow viewports. No new JS module — Bootstrap's
  built-in offcanvas handles open/close, backdrop, and Esc-to-close.
  Sprint 35 hardens touch targets and focus-trap.
- `frontend/templates/components/breadcrumbs.html` — declarative
  component that renders from a `breadcrumbs=[{label, href?}]` list;
  the final item (or any item without `href`) becomes the active
  terminal crumb. Migrated 8 pages: `jobs`, `dashboards`, `connections`,
  `external_locations`, `credentials`, `notebooks_workspace`,
  `schemas`, `tables`.
- `frontend/templates/components/empty.html` — reusable empty-state
  panel with optional `icon`, `title`, `message`, `action_href` /
  `action_label`, and a `flush` variant for use inside an existing
  card. Migrated the 6 list-page empty states (jobs, dashboards,
  connections, external_locations, credentials, notebooks_workspace)
  — in-card snippets (permissions, tags, lineage, properties,
  sync_history) remain opportunistic follow-up.
- New branded error pages: `pages/404.html` (bi-compass), `pages/500.html`
  (bi-exclamation-octagon, renders `request_id` for bug reports),
  both on the new app shell. `pages/403.html` refitted onto the same
  `components/empty.html` primitive — preserving the existing
  `required_privilege`/`securable_type`/`full_name` context.
- `pointlessql/api/error_handlers.py` — Accept-aware dispatch:
  `/api/` paths still always emit the JSON envelope; non-`/api/` paths
  honour an explicit `Accept: application/json` without `text/html`,
  otherwise render the HTML shell. Registered a `StarletteHTTPException`
  handler so unmapped 404s render the branded page (not FastAPI's
  default JSON), and an `Exception` catch-all that logs `exc_info` and
  returns the 500 shell or JSON envelope.
- `frontend/js/toast.js` — `window.pqlToast.{success, error, info}(msg, {timeout}?)`
  mounted once in `base.html`. Each call builds a Bootstrap toast in
  `#pql-toast-root`, applies a Sprint-29 semantic variant
  (`.pql-toast--{success|error|info}`), and removes the node on
  `hidden.bs.toast`. API only this sprint; Sprint 36 wires the five
  existing components onto an `apiFetch` helper that emits toasts
  on error.
- CSS additions in `frontend/css/style.css`: responsive `.pql-shell`
  grid, `.pql-sidebar-shell` offcanvas reset, `.pql-sidebar-toggle`,
  `.pql-breadcrumbs`, `.pql-empty` (+ `.pql-empty--{variant}` tints,
  `__icon` / `__title` / `__message` / `__meta` / `__action`),
  `.pql-error-shell` centered wrapper, and `.pql-toast` (+ variants).
  All colour pairs reuse Sprint-29 semantic tokens so light-mode
  inherits for free.

### Added (Sprint 29)

- Design-token system in `frontend/css/style.css`: spacing
  (`--pql-space-1..8`, 4-px scale), typography
  (`--pql-text-xs..3xl`, ~1.125 modular ratio), radius
  (`--pql-radius-sm|md|lg|pill`), elevation (`--pql-elev-0..3`,
  dark-mode-tuned), motion (`--pql-duration-fast|normal|slow` +
  `--pql-ease`), and semantic colour pairs (success / warning /
  danger / info / neutral — each with a `bg` + `fg` variable so
  chip text meets AA contrast against its own background). Brand
  accent `#76b900` preserved as `--pql-color-accent`
- Light-mode variant **prepared** via a
  `:root[data-bs-theme="light"]` override block — tokens flip
  automatically when the attribute changes. No toggle is wired
  yet; switching in DevTools is enough to verify downstream
  primitives adapt
- Inter font self-hosted (OFL-1.1, Latin subset) at
  `frontend/fonts/inter-regular.woff2` (23.7 kB) and
  `inter-semibold.woff2` (24.3 kB) — combined 48 kB, under the
  50 kB per-page budget. Two `@font-face` blocks with
  `font-display: swap`; `body { font-family: var(--pql-font-sans); }`
  picks it up globally. Regular is `<link rel="preload">`-ed in
  `base.html`; SemiBold is lazy-loaded on first use
- CSS-only primitives: `.pql-stack` (vertical flex with token
  gap; `--tight`/`--loose` modifiers), `.pql-cluster`
  (horizontal wrapping cluster), `.pql-card` (panel surface
  replacing the 18-site `card mb-4 p-4` pattern; sibling
  `.pql-card + .pql-card` auto-margins; `.pql-card--flush`
  strips padding for iframe wrappers), `.pql-badge` (pill-shaped
  status chip, semantic-palette modifiers `--success|warning|danger|info`)
- Proof-of-concept template migrations: `base.html` (font
  preload + Inter via body rule), `pages/login.html` (card ↦
  `.pql-card` + nested `.pql-stack` form layout), and
  `pages/catalogs.html` (welcome hero wrapped in `.pql-card` +
  `.pql-stack --loose`; catalog-count chip becomes
  `.pql-badge --info`). The remaining 27 templates stay on
  Bootstrap utilities and will migrate in Sprints 30 / 33 / 34
  as those sprints touch each surface
- `docs/design-tokens.md` reference — token tables with
  "when to use" notes, primitive snippets, light-mode override
  pattern, and contribution conventions (new tokens land
  alongside a doc update in the same commit)

### Added (Sprint 28)

- Alembic migration `008_dashboards.py` creating the
  `dashboards` table (slug unique, title, description,
  notebook_path, job_id FK nullable with `ON DELETE SET NULL`,
  owner_id FK, timestamps)
- New `Dashboard` ORM model in `pointlessql/models.py`
- `render_run_notebook` in `pointlessql/services/notebook_render.py`
  gains an `exclude_input: bool = False` keyword; when true,
  renders with `HTMLExporter(..., exclude_input=True)` and caches
  to a sibling `{run_id}.dashboard.html` sidecar so the
  code-visible and code-hidden variants coexist without clobbering
  each other
- `GET /jobs/{id}/runs/{rid}/notebook` gains an optional
  `?exclude_input=true` query param threaded through to the
  render helper
- Dashboard CRUD routes: `GET /api/dashboards` (list, any
  logged-in user), `GET /api/dashboards/tree` (sidebar shape),
  `POST /api/dashboards` (admin-only, validates slug against
  `^[a-z0-9][a-z0-9-]{0,199}$`), `PATCH /api/dashboards/{slug}`
  (admin-only; editable fields: title, description,
  notebook_path, job_id), `DELETE /api/dashboards/{slug}`
  (admin-only), `POST /api/dashboards/{slug}/refresh`
  (admin-only; triggers the bound job's `execute_run(...,
  trigger="manual")` via the same helper that powers the
  job-detail Run-now button)
- `GET /dashboards` list page + `GET /dashboards/{slug}` detail
  page rendering the latest succeeded run through an iframe
  pointed at `/jobs/.../notebook?exclude_input=true`; empty
  state when no job is bound or no successful run exists
- `GET /jobs/{id}/runs/{rid}/compare?to={other_rid}` — two
  Sprint-26 iframes side-by-side with run metadata headers; both
  run ids are validated to belong to the same job before render
  (no foreign-run leak). No cell-level diff highlighting (stub)
- "Compare runs" card on `pages/job_detail.html` (visible only
  when ≥ 2 completed runs exist) with two `<select>`s and a
  Compare button that navigates to the compare URL
- New templates: `pages/dashboards.html`,
  `pages/dashboard_detail.html`, `pages/run_compare.html`, and
  `components/dashboards_sidebar.html` (mirrors the Sprint 27
  workspace-tree component; `sessionStorage` key
  `pql.dashboards`)
- Navbar gains a **Dashboards** link (visible to every logged-in
  user — consumer surface, not admin-only); `base.html` swaps in
  the dashboards sidebar when `active_page == 'dashboards'`
- New playbook `docs/e2e-walkthroughs/dashboards.md` covering
  create-modal → detail with code-hidden iframe → Refresh →
  sidebar tree → non-admin visibility → run-compare from the
  job-detail card, plus the foreign-run 404 negative

### Added (Sprint 27)

- New `pointlessql/services/notebook_workspace.py` with
  `list_workspace_tree(notebooks_dir)` (nested listing with per-
  notebook `parameters_tagged: bool`; skips the executor `runs/`
  subdir) and `resolve_upload_target(notebooks_dir, relative_path)`
  (mirrors `resolve_notebook_path` but allows a not-yet-existing
  target and requires the parent directory to exist)
- `GET /api/notebooks/tree` — admin-only directory listing for
  the workspace browser
- `POST /api/notebooks/upload` — admin-only multipart upload of
  `.ipynb` files into the notebooks workspace; validates
  `.ipynb` extension, parses the body as JSON before writing,
  atomically replaces via a `.tmp` sidecar, and requires an
  explicit `overwrite=true` form field to clobber an existing
  file
- `GET /notebooks/workspace` — new admin-only HTML page with a
  flattened-tree component keyed on `sessionStorage`
  `pql.notebooks` / `pql.notebooks.open`, plus a per-leaf
  **Schedule…** button that navigates to
  `/jobs?prefill_kind=papermill&prefill_notebook_path=<path>`
- Create-job modal (`pages/jobs.html`) reads those query params
  on mount, pre-fills `kind=papermill` + `notebookPath`, chains
  `inspect()` for the typed-parameters form, opens the modal,
  and strips the query string via `history.replaceState`
- Navbar gains a **Workspace** link (admin-only) between
  Notebook and Jobs
- Playbook extension: Part G in
  `docs/e2e-walkthroughs/notebook-jobs.md` covers upload →
  schedule → run-now → Output artifacts card, plus non-admin
  403 and the overwrite / traversal / non-`.ipynb` negative paths

### Added (Sprint 26)

- `nbconvert>=7.0` dep and new `pointlessql/services/notebook_render.py`
  with `render_run_notebook(runs_dir, run_id)` — first call runs
  `HTMLExporter(template_name="lab")` on
  `runs/{run_id}.ipynb`, writes an atomic `.html` sidecar next to
  it, and returns the HTML; subsequent calls serve the sidecar
- `GET /jobs/{id}/runs/{rid}/notebook` — inline-renders a
  papermill run's output notebook for iframe embedding on the
  job-detail page
- `GET /jobs/{id}/runs/{rid}/notebook/download?format={ipynb,html}`
  — visibility-checked downloads of the raw notebook or its
  rendered sidecar. Replaces the originally planned
  `/notebooks/runs/` StaticFiles mount so non-owner logged-in
  users can't exfiltrate other users' run outputs by guessing
  `run_id`s. Both routes share `_load_papermill_run_output_path`
  which validates job ownership, papermill kind, and run
  ownership before touching disk
- New "Output artifacts" card on `job_detail.html` (between
  the DAG tasks and Recent runs cards, guarded by
  `job.kind == "papermill"`): auto-selects the most recent
  succeeded/failed run on page load, Rendered/JupyterLab view
  toggle wired to the two iframe sources, download links for
  `.ipynb` and `.html`
- Recent runs rows are now clickable on papermill jobs;
  `$dispatch("run-selected", { runId })` swaps the card's
  iframe to the clicked run's output. The Sprint 24 "Open in
  JupyterLab" anchor retains `@click.stop` so row-click and
  popout-click don't collide
- `docs/e2e-walkthroughs/notebook-jobs.md` Part F walks the
  card's auto-select, view-toggle, row-click swap, downloads,
  and the three 404 negatives

### Added (Sprint 25)

- `GET /api/notebooks/inspect?path=…` admin-only route wrapping
  `papermill.inspect_notebook` — returns
  `[{name, default, inferred_type, help}]` so the create-job modal
  can render one typed input per declared parameter instead of a
  free-form JSON textarea
- Create-job modal gains a "Load parameters" button, a typed form
  (`number` / `checkbox` / `text` / `textarea`) rendered via Alpine
  `x-for`, and a collapsed `<details>` "Advanced" fallback that
  keeps the raw JSON textarea for power users. Advanced mode wins
  over the typed form when the `useAdvanced` checkbox is ticked
- Job-detail Configuration card renders dedicated **Notebook** and
  **Parameters** rows for papermill jobs (nested `<dl>` for the
  parameters) instead of the catch-all `<pre>{{ config|tojson }}</pre>`
- Promoted `_resolve_notebook_path` → public `resolve_notebook_path`
  in `services/scheduler.py` so the inspect route reuses the same
  traversal-safe path resolver the executor uses
- Seed script writes `notebooks/smoke_typed_params.ipynb`
  (`count: int = 3`, `enabled: bool = True`, `label: str = "hello"`)
  for the new Part E playbook — one parameter per typed-input branch
- `docs/e2e-walkthroughs/notebook-jobs.md` Part E walks the
  inspect endpoint, the typed-form rendering + override, the
  Advanced raw-JSON fallback, and two negative inspect cases
  (missing file, traversal). Live-run findings appended to the
  Found-bugs section — no bugs surfaced

### Added (Sprint 24)

- Papermill job kind: `_papermill_executor` registered next to
  `pg_sync` and `python` in `scheduler_service.build_default_registry()`.
  Config shape `{notebook_path, parameters, timeout_seconds}`;
  output lands at `{notebooks_dir}/runs/{job_run_id}.ipynb` so the
  embedded JupyterLab serves it at `/lab/tree/runs/{run_id}.ipynb`
- `POINTLESSQL_PRINCIPAL` env var honoured by the `PQL` constructor
  (via `make_principal_client`) so notebook code running under the
  Papermill executor inherits the job's run-as user without extra
  wiring — the scheduler exports the env var into the kernel
  subprocess
- New settings `POINTLESSQL_NOTEBOOKS_DIR` (default `notebooks`) and
  `POINTLESSQL_NOTEBOOK_EXECUTE_TIMEOUT_SECONDS` (default `300`).
  `services/jupyter.py` now resolves its `--notebook-dir` through
  the setting so the executor and the embedded JupyterLab share a
  single source of truth
- Create-job modal (`frontend/templates/pages/jobs.html`) gains a
  `kind` select with `DAG (multi-task)` and `Papermill (single
  notebook)` options; Papermill-specific `notebook_path` +
  `parameters` inputs render conditionally
- Job detail page (`frontend/templates/pages/job_detail.html`)
  recent-runs table gains a trailing "Open in JupyterLab" column
  on rows of `kind=papermill` jobs whose run status is `succeeded`
  or `failed`
- `docs/e2e-walkthroughs/notebook-jobs.md` — Phase-8 playbook
  covering create via modal, Run-now, output-artifact verification,
  the JupyterLab deep-link, and four negative paths
  (missing path, traversal, missing file, failing cell)

### Added (Sprint 23)

- `docker-compose.e2e.yml` gains a `mock-oidc` service
  (`ghcr.io/navikt/mock-oauth2-server:latest`, host port 9090)
  and `${…:-default}` env passthroughs on the `pointlessql`
  service for `POINTLESSQL_SCHEDULER_TICK_SECONDS`
  (default `2` so DAG state transitions land in seconds during
  live walks), `POINTLESSQL_JUPYTER_ENABLED`,
  `POINTLESSQL_LOG_FORMAT`, and the four `POINTLESSQL_OIDC_*`
  / `POINTLESSQL_BASE_URL` knobs. All default to empty so the
  Sprint 22 data-surface playbooks keep working unchanged
- Five orchestration + operational playbooks under
  `docs/e2e-walkthroughs/`:
  - `jobs-dag.md` — single-task + DAG job creation, Run-now,
    retry + fail-skip propagation, Pause/Resume click, per-task
    log panel expand, and a `pg_sync`-kind cross-feature smoke
    driving Sprint 18's `run_sync()` against the Sprint 22
    `pg_mirror` foreign catalog
  - `notebook.md` — `/notebook` + `/api/jupyter/status` in
    `jupyter_enabled=true` (iframe src `http://localhost:8888/lab`,
    Alpine `jupyterLoader().ready` flips to true) and `=false`
    (template short-circuits to "Notebook Disabled" card) passes
  - `oidc.md` — SSO button absent with no OIDC env, then with
    the mock issuer a full authorize-code + PKCE round-trip that
    auto-creates a user with `oidc_provider` / `oidc_subject`
    bound; repeated sign-in reuses the existing row
  - `operational.md` — anonymous `/healthz`, admin `/metrics`
    `text/plain` with all three metric families, non-admin
    `/metrics` renders 403, JSON API errors carry a UUID
    `request_id`, `X-Request-ID` round-trips client-supplied
    values
  - `config-matrix.md` — primary walk (`engine=pandas,
    log=text, db=sqlite`) plus five delta walks for every
    non-default value of `POINTLESSQL_ENGINE`,
    `POINTLESSQL_LOG_FORMAT`, `POINTLESSQL_DATABASE_URL`, and
    their cartesian-product smoke
- `docs/e2e-walkthroughs/README.md` updated: cross-links to the
  ten playbooks, the host-env overlay table with the
  recreate-pointlessql workflow, and a Sprint-23 section on the
  `mock-oidc` + bridge-IP workaround for Docker DNS asymmetry
- `CLAUDE.md` "Replaying the e2e walkthroughs" section pinning
  the ten-playbook tree, the `--browser firefox` /
  `chrome-for-testing` MCP config requirement (Sprint 22 commit
  `3f1da76` backstory), and the "replay before landing HTML/JS"
  contract for future sprints
- Phase 7 close-out summary appended to `ROADMAP.md`: all five
  surfaced bugs fixed same-commit, none deferred

### Fixed (Sprint 23)

- **BUG-23-01**: `oidc_enabled` computed property in
  `pointlessql/settings.py` used `is not None`, treating the
  empty strings produced by the compose overlay's
  `${POINTLESSQL_OIDC_DISCOVERY_URL:-}` fallback as
  *configured*. The SSO button on `/auth/login` rendered and
  clicking it hit a `401 Failed to fetch OIDC discovery
  document`. Truthy check replaces the `is not None` so both
  `None` and `""` count as "not configured"
- **BUG-23-02**: `POST /api/jobs` in `pointlessql/api/main.py`
  committed the `Job` row before running
  `scheduler_service.validate_dag` over the task list, so a
  cycle / unknown-dep payload returned 422 but left the job row
  visible on `/jobs` forever. Refactored to `session.flush()`
  during the two-pass task insert and a single final
  `session.commit()` only after `validate_dag` succeeds —
  rejected payloads roll back cleanly when the session context
  exits

### Added (Sprint 22)

- `docker-compose.e2e.yml` overlay — `postgres-e2e` sidecar
  (postgres:17-alpine, port 5433) seeded from
  `scripts/pg-seed.sql` as the foreign-catalog target for the
  sync playbook; mounts `./scripts:/app/scripts:ro` on the
  `pointlessql` service so the seed script can run server-side
  with consistent `file:///app/warehouse/...` storage URIs
- `scripts/pg-seed.sql` — defensively idempotent Postgres
  `shop` schema (customers, products, orders) with a few seeded
  rows so the first foreign-catalog sync returns `added_count`
  equal to `schema + 3 tables`
- `scripts/seed-e2e.py` — idempotent driver that runs inside
  the PointlesSQL container: creates managed catalog `demo`,
  schemas `demo.sales` / `demo.hr` with `file://` storage
  roots, writes four Delta tables via `PQL.write_table` (50
  orders, 20 customers, 10 employees, 10 salaries), and
  registers a soyuz `Connection pg_e2e` pre-bound to the
  seeded Postgres so the foreign-catalog create modal picks it
  up without further setup
- `docs/e2e-walkthroughs/README.md` — operator doc: stack
  start/teardown, test-user credentials shared across playbooks,
  how Claude replays a playbook via the Playwright MCP tool set,
  selector conventions for a codebase without `data-test`
  attributes, rebuild note for stale cached container images
- Five Markdown playbooks under `docs/e2e-walkthroughs/`:
  `auth.md` (first-user admin bootstrap + non-admin + `/auth/me`
  + `/metrics` 403), `catalog-browsing.md` (welcome screen +
  sidebar-tree sessionStorage persistence + PQL-snippet copy
  button), `inline-editors.md` (`editable` +
  `properties_editor` + `tags_editor` + `permissions_card`
  grant/revoke across catalog/schema/table, driven via
  `Alpine.$data(card)` rather than DOM mutation so Alpine's
  reactive bindings don't swallow typed values), `federation.md`
  (admin CRUD of connections / credentials / external locations
  with `deleteConfirm`, non-admin 403 negative), and
  `foreign-catalog-sync.md` (create-foreign-catalog modal → Sync
  now → sync-history card → mirrored `pg_mirror.shop.*`
  tables in the sidebar)
- All five playbooks exercised live via Playwright MCP in
  Firefox against a freshly-composed stack. Playbooks record
  what each step's `browser_evaluate` returned so the next
  replay has a concrete expectation. Three bugs surfaced
  during the live run and were fixed in the same sprint:
  - **BUG-22-01 fixed**: `_wrap_catalog_errors` in
    `pointlessql/services/unitycatalog.py` now branches on
    `UnexpectedStatus.status_code` — 404 → `CatalogNotFoundError`,
    other 4xx → `ValidationError`, only 5xx / transport →
    `CatalogUnavailableError`. PATCH permissions with an
    invalid privilege (e.g. `SELECT` at catalog level) now
    returns `422 validation_error` passing the soyuz message
    through; PATCH on a non-existent catalog now returns
    `404 catalog_not_found`
  - **BUG-22-02 fixed**: the same decorator now catches
    `KeyError` / `TypeError` raised by a generated
    `Create*.from_dict()` (missing required request-body field)
    and re-raises `ValidationError`. `POST
    /api/external-locations` without `credential_name` now
    returns `422 validation_error: "Invalid request body:
    'credential_name'"` instead of a 500 leaking the KeyError
  - **BUG-22-03 fixed**:
    `createExternalLocationForm.submit()` in
    `frontend/js/federation.js` now rejects an empty
    `credentialName` with an inline error before issuing the
    request, matching the UC spec requirement surfaced by
    BUG-22-02

### Added (Sprint 21)

- `pointlessql/services/metrics.py` — Prometheus surface on its
  own `CollectorRegistry` so tests don't contaminate the global
  default. `Counter pointlessql_job_runs_total{status,job_name}`,
  `Histogram pointlessql_job_run_duration_seconds{job_name}`
  (buckets 0.05 s .. 3600 s, log-spaced, includes the Prom
  default 10 s), `Gauge pointlessql_scheduler_tick_lag_seconds`;
  `render_metrics()` / `record_run()` / `observe_tick_lag()`
  helpers
- `GET /metrics` admin-only (raises `AuthorizationError` via
  `_require_admin`); returns `generate_latest()` bytes with
  `text/plain; version=0.0.4`
- Optional per-job failure webhook: `jobs.on_failure_url`
  (Alembic migration 007, nullable `String(1000)`). Scheduler
  POSTs `{job_id, job_name, run_id, status, error, started_at,
  finished_at}` (ISO-8601) on a failed run via
  `_post_failure_webhook`. 5 s timeout, no retries, one-shot
  `httpx.AsyncClient.post`; `httpx.HTTPError` logged at WARN
  and swallowed so a broken receiver never affects run state.
  `_webhook_client_factory` exposed for test stubbing
- `docs/jobs.md` — authoring guide: executor signature
  (`job_run_id, user_info, config, uc_client`), publishing a
  custom kind via the `pointlessql.jobs` entry-point group, the
  scheduling JSON + `on_failure_url` payload shape, a worked
  `pql`-in-a-task summary-table example, notes on logging /
  retries / concurrency, observability, and when to add a
  built-in kind instead
- README.md gains a "Jobs" section linking to `docs/jobs.md`
- `tests/test_metrics.py` — 9 new tests (emission on success +
  failure, `/metrics` admin-only enforcement, webhook URL +
  payload keys + timeout, no-webhook path, broken-receiver
  does not abort the run). Sprint 19+20 scheduler tests still
  green (36 passed). Full suite not run in this sprint

### Changed (Sprint 21)

- `scheduler.py`: `execute_run` wraps a new `_execute_run_core`
  and emits telemetry around every run; `tick_once` emits
  telemetry for synthetic `skipped` rows too; `Scheduler._run`
  samples tick lag each iteration

### Added (Sprint 20)

- Alembic migration 006: `jobs.max_parallel_runs`; `job_tasks`
  gains `kind`, `depends_on` (JSON list of task ids),
  `max_retries`, `retry_backoff_seconds`; new `task_runs`
  (id, job_run_id FK, task_id FK, status, started_at,
  finished_at, attempts, error); `job_logs.task_id` nullable
  FK (batch-alter safe on SQLite)
- Topological DAG walk in `scheduler.py`: iterative three-color
  DFS validates the graph at create-time and raises
  `ValidationError("cycle detected in task graph: [...]")`
  with the offending path; unknown `depends_on` ids caught
  in the pre-pass; upstream-fail → downstream tasks marked
  `skipped` (not `failed`)
- Retry policy per task: linear backoff (delay between
  attempts `i` and `i+1` is `i * retry_backoff_seconds`);
  `_sleep` is a module-level hook so tests patch it;
  attempts counted on `TaskRun`
- Concurrency caps: layered `asyncio.Semaphore`. Global
  semaphore sized from
  `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS` (default 4)
  allocated on `Scheduler.start()`; per-job semaphores are
  lazy, keyed by `job_id`, sized from
  `Job.max_parallel_runs` (default 1). Global acquired
  before per-job (consistent lock order). DB `running`-count
  query stays as the authoritative `skipped` writer so
  process restarts don't lose state
- `logging_config.py`: new `job_run_id_var` and `task_id_var`
  alongside Sprint 16's `request_id_var`. `JSONFormatter`,
  `RequestIdFilter`, and the `LogRecord` factory carry all
  three. Scheduler sets them per-task and resets in
  `finally`. Sprint 19's `request_id_var = f"job-{job_run_id}"`
  is kept for continuity
- `log_job(job_run_id, task_id, level, message)` writes every
  status transition and retry to `job_logs`, synchronously
  relative to the task call
- `POST /api/jobs` accepts a DAG create form: `tasks` array
  with `{name, kind, config, depends_on, max_retries}`;
  validates cycles/unknown deps before insert
- New routes: `GET /api/jobs/{id}/tasks`,
  `GET /api/jobs/{id}/runs/{run_id}/tasks`,
  `GET /api/jobs/{id}/runs/{run_id}/logs?task_id=...`
- UI: "New DAG job" modal on `jobs.html` (JSON textarea — no
  builder yet). Per-task table on `job_detail.html` with
  status, retry count, last error; expandable Alpine log
  panel fetches lines on demand
- Settings: `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS`
  (default `4`)
- `tests/test_scheduler_dag.py` — 13 new tests (topology,
  fail-skip, retry success, retry exhaustion, cycle
  detection, self-loop, unknown dep, per-job cap, global
  semaphore serialization, contextvars set/reset via
  caplog, `log_job` writer, route-level cycle 422). Sprint
  19's 23 scheduler tests and Sprint 16's 8 logging tests
  still green. Full suite not run in this sprint

### Added (Sprint 19)

- Alembic migration 005: `jobs` (name unique, cron_expr,
  run_as_user_id FK, kind, config JSON, is_paused, timestamps),
  `job_runs` with `(job_id, started_at DESC)` index, plus
  `job_tasks` and `job_logs` pre-created for Sprint 20
- `pointlessql/services/scheduler.py` — in-process asyncio
  scheduler started from `_lifespan`; `croniter`-driven due
  detection; per-tick running-run query prevents overlap;
  paused jobs skipped; failed `run_as_user_id` resolution
  surfaces as a `failed` run with a clear error
- Kind registry: `pg_sync` wraps Sprint 18 `run_sync` with
  `config["catalog_name"]`; `python` resolves an entry point
  from the `pointlessql.jobs` group (tests register a fake)
- Run-as-user builds `UnityCatalogClient.for_principal(user.email)`
  so soyuz's X-Principal applies automatically — reuses Sprint 7
- Scheduler sets `request_id_var` to `f"job-{job_run_id}"`
  inside each per-run span so structured logs correlate
  without a new contextvar (Sprint 20 adds
  `job_run_id_var` + `task_id_var`)
- Settings: `POINTLESSQL_SCHEDULER_ENABLED` (default `True`)
  and `POINTLESSQL_SCHEDULER_TICK_SECONDS` (default `30`)
- Routes: `GET /jobs` (list, ownership-filtered for non-admin),
  `GET /jobs/{id}`, `POST /api/jobs` (admin-only),
  `POST /api/jobs/{id}/run`, `POST /api/jobs/{id}/pause`,
  `POST /api/jobs/{id}/unpause` — all audited
- `frontend/templates/pages/jobs.html`,
  `frontend/templates/pages/job_detail.html` with "Run now" /
  "Pause/Resume" buttons visible to admin or the owner
- Navbar "Jobs" entry between "Notebook" and existing
  dropdowns
- `tests/test_scheduler.py` covering tick logic with a
  patched clock, state transitions, overlap prevention,
  paused skip, run-as-user principal forwarding, `pg_sync`
  end-to-end, route admin-gating and ownership filter

New dep: `croniter`.

### Changed (Sprint 19)

- `tests/conftest.py` sets
  `POINTLESSQL_SCHEDULER_ENABLED=false` before app import
  so the loop never ticks in ordinary test runs; the
  scheduler suite re-enables it per-test via monkeypatch
- `.gitignore`: `*.db-shm`, `*.db-wal` (SQLite WAL
  artifacts now produced by the scheduler's DB writes)

### Added (Sprint 18)

- `pointlessql/services/pg_sync.py`: pure-function Postgres → UC sync
  worker. `PG_TO_UC_TYPE` map, `map_pg_type_to_uc` with DECIMAL
  precision passthrough and STRING fallback on unknown types,
  `diff_snapshots(pg, uc_tables) -> SyncDiff` (schemas/tables/
  columns added/changed/dropped), `apply_diff` driving the facade,
  `PostgresIntrospector` protocol + `PsycopgIntrospector` default
  backed by `information_schema.columns` via `psycopg.sql.SQL`,
  `run_sync` glue that persists a `SyncRun` row per execution
- `unitycatalog.py` facade: `create_schema`, `create_table`,
  `delete_table` for driving the sync — all wrapped in
  `_wrap_catalog_errors`
- `POST /api/catalogs/{name}/sync` (admin-only, audited) resolves
  the catalog's bound Connection + optional Credential, builds a
  libpq DSN, runs the sync, and returns the `SyncRun` snapshot
- Alembic migration 004: `sync_run` table (`catalog_name`,
  `started_at`, `finished_at`, `status`, `added_count`,
  `changed_count`, `dropped_count`, `error`) with
  `(catalog_name, started_at DESC)` index
- `SyncRun` ORM model
- `components/sync_history_card.html`: last-20 sync runs + admin
  "Sync now" button on the foreign-catalog detail page
- Secret handling: connection options with keys matching
  `(?i)pass|secret|key|token` are overridden from a bound
  Credential's `additional_properties` (see `_effective_options`);
  missing Credential falls back to `options`
- 46 new tests (309 total) covering type mapping (16 parametrized),
  diff logic, secret merging, DSN builder, `apply_diff` with mock
  UC, `run_sync` end-to-end with stub introspector, the
  admin-only sync route, audit log emission, the history card
  render, and an `@pytest.mark.integration` test against a
  real Postgres container (documented, skipped by default)

### Added (Sprint 17)

- `unitycatalog.py` facade: `create_catalog(data)` and
  `delete_catalog(name, force)` wrapping the generated client's
  `_create_catalog` / `_delete_catalog`; both go through
  `_wrap_catalog_errors` so transport failures surface as
  `CatalogUnavailableError`
- `POST /api/catalogs` route (admin-only, audited) accepting the
  full `CreateCatalogRequest` shape — `name`, optional `comment`,
  `properties`, `type=FOREIGN`, `connection_name`, and free-form
  `options` passthrough — for wiring up foreign catalogs
- "Create foreign catalog" button + modal on the catalogs page
  (`pages/catalogs.html`): admin-only, pre-populated connection
  dropdown, key/value options row editor, posts through a new
  `createForeignCatalogForm(...)` Alpine factory in `federation.js`
- `components/foreign_catalog_card.html`: bound-connection link +
  inline options editor on the catalog detail page, rendered when
  `catalog.connection_name` is set
- FOREIGN badge on the catalog detail heading
  (`pages/schemas.html`) and in the sidebar tree
  (`components/sidebar.html`, `bi-plug` icon) so foreign catalogs
  are visually distinct from managed ones
- `optionsEditor(...)` in `properties_editor.js` — PATCHes
  `{ options: {...} }` to the catalog; shares a new
  `_makeDictEditor(field, ...)` helper with the existing
  `propertiesEditor`
- `tests/test_foreign_catalog.py` — 8 tests covering POST happy
  path + non-admin 403, PATCH options forwards dict verbatim,
  foreign-card/FOREIGN-badge/connection-link rendering, modal
  visibility for admin vs non-admin users
- `tests/test_federation.py`: new `TestCatalogsCreate` (4 tests)
  exercising the facade's managed + foreign-catalog create and
  delete paths (263 total pass)

### Changed (Sprint 17)

- `properties_editor.js`: `propertiesEditor` refactored to a
  shared `_makeDictEditor` helper; behavior preserved (the
  "cannot clear all properties at once" quirk stays scoped to
  `field === 'properties'`)
- `/` home handler fetches connections for the create modal only
  when the current user is admin (empty list otherwise, no
  `list_connections` call)

### Added (Sprint 16)

- `pointlessql/logging_config.py` — centralized logging: a
  `request_id_var` contextvar, `RequestIdFilter`, opt-in
  `JSONFormatter`, idempotent `configure_logging(level, fmt)`.
  Also installs a `logging.setLogRecordFactory` so every record
  is stamped with the current `request_id` (works with pytest's
  `caplog` without per-handler hookup)
- Settings: `log_level` (default `"INFO"`) and `log_format`
  (`"text"` | `"json"`, default `"text"`); env overrides
  `POINTLESSQL_LOG_LEVEL`, `POINTLESSQL_LOG_FORMAT`
- Module-level loggers in `api/main.py`, `api/error_handlers.py`,
  and `services/unitycatalog.py`
- Startup log line from `_lifespan` (host, port, engine,
  log_format)
- `error_handlers.py` warns on every handled `PointlessSQLError`
  except `AuthorizationError` (authz denials are expected
  traffic, not anomalies)
- `services/unitycatalog.py` `_wrap_catalog_errors` logs the
  original transport exception before re-raising as
  `CatalogUnavailableError` — fixes prior silent-swallow
- `tests/test_logging_config.py` — 8 new tests covering
  formatter, filter, idempotency, and end-to-end request-ID
  propagation through a captured warning log (251 total pass)

### Changed (Sprint 16)

- `request_id_middleware` sets the `request_id_var` contextvar
  (in addition to `request.state.request_id`) and resets it in
  `finally`, so every log record emitted during the request
  carries the ID — service-layer code no longer has to receive
  the `Request` object to log it
- `api/main.py` calls `configure_logging(...)` at module import
  time so uvicorn `--reload` workers and direct `uvicorn` invocations
  both pick up the configured format; idempotent, coexists with
  pytest's `caplog`

### Changed (Sprint 15)

- `[tool.pydoclint]` configuration in `pyproject.toml`: Google
  style, types in signatures only, `__init__` docs merged into
  class docstrings
- Ruff `D107` ignored — pydoclint owns `__init__` docstring
  policy via `allow-init-docstring = false`
- Merged `__init__` docstrings into class docstrings for `PQL`,
  `DuckDBEngine`, `UnityCatalogClient` (DOC301)
- Restructured exception docstrings: constructor params in Args,
  class-level annotations in Attributes (DOC602/603/101/103)
- Accurate Raises sections in `PQL.table`, `PQL.write_table`,
  `find_or_create_oidc_user` (DOC501/503)
- pydoclint: 0 violations across all 27 source files

### Added (Sprint 14)

- `pointlessql/api/error_handlers.py` — centralized FastAPI
  exception handler for `PointlessSQLError` family; dispatches
  JSON error envelope for `/api/...` routes and 403.html for
  HTML authorization errors
- Consistent JSON error envelope on all API error responses:
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
- Request-ID middleware: generates UUID4 per request (or
  forwards client `X-Request-ID`), attaches to error envelope
  and `X-Request-ID` response header
- `tests/test_error_handlers.py` — 13 new tests covering JSON
  envelope for each exception type, HTML 403 rendering,
  request-ID generation and forwarding, admin enforcement via
  centralized handler (243 total pass)

### Changed (Sprint 14)

- UC facade (`unitycatalog.py`): all public async methods
  wrapped with `_wrap_catalog_errors` decorator converting
  `httpx.HTTPError` / `UnexpectedStatus` →
  `CatalogUnavailableError` at the source — routes never see
  raw transport exceptions
- `_require_admin` raises `AuthorizationError` instead of
  returning a `JSONResponse`; `_deny_json`, `_deny_html`, and
  `_require_admin_html` removed
- ~40 duplicated try/except blocks removed from `main.py`
  (1164 → 815 lines); JSON API routes are now simple
  pass-through calls with exceptions propagating to the
  centralized handler
- HTML graceful-degradation routes (catalog/schema/table
  detail, federation pages) catch `CatalogUnavailableError`
  (domain exception) instead of raw `httpx.HTTPError`
- `httpx` and `UnexpectedStatus` no longer imported in
  `main.py`

### Added (Sprint 13)

- `pointlessql/exceptions.py` — domain exception hierarchy with
  `PointlessSQLError` base carrying `.status_code`, `.error_code`,
  `.detail`; six concrete types: `CatalogUnavailableError` (502),
  `CatalogNotFoundError` (404), `AuthenticationError` (401),
  `AuthorizationError` (403), `EngineError` (500),
  `ValidationError` (422, also inherits `ValueError`)
- `pointlessql/types.py` — `UserInfo` TypedDict replacing
  `dict[str, Any]` for authenticated user objects
- `tests/test_exceptions.py` — 17 new tests covering hierarchy,
  attributes, catchability, and backward compatibility
  (230 total pass)

### Changed (Sprint 13)

- Pyright: `typeCheckingMode` upgraded from `"standard"` to
  `"strict"` on source code; zero errors, 32 warnings (from
  incomplete third-party stubs)
- `AccessDenied` reparented as an alias for `AuthorizationError`
  in `services/authorization.py` (backward compatible)
- `OIDCError` reparented under `PointlessSQLError`
- PQL raises `CatalogUnavailableError` instead of `ConnectionError`,
  `CatalogNotFoundError` instead of `LookupError`,
  `ValidationError` instead of `ValueError`
- `make_engine()` raises `ValidationError` instead of `ValueError`
- `parse_full_name()` raises `ValidationError` instead of
  `ValueError`
- Broad exception catches narrowed: `except Exception` in
  `auth.py` → `except (ValueError, TypeError, PwdlibError)`,
  `except (JSONDecodeError, Exception)` in `oidc.py` →
  `except (JSONDecodeError, ValueError, UnicodeDecodeError)`
- `_STATE_COOKIE_NAME` in `oidc.py` renamed to `STATE_COOKIE_NAME`
  (was flagged by strict pyright as cross-module private access)
- `_get_user()` in `api/main.py` returns `UserInfo` instead of
  `dict[str, Any]`; `auth_middleware` and
  `_template_response_with_user` have explicit return type
  annotations

### Added (Sprint 12)

- `PolarsEngine` in `pointlessql/pql/engine.py` — reads Delta tables
  via PyArrow → `pl.from_arrow()`, returns `pl.DataFrame`; writes via
  `frame.to_arrow()` → `deltalake.write_deltalake()`
- `_POLARS_TYPE_MAP` + `_polars_type_to_uc()` for Polars dtype → UC
  type mapping
- `PolarsEngine` registered in engine factory and exported from
  `pql/__init__.py`
- Settings: `POINTLESSQL_ENGINE` now also accepts `"polars"`
- `POINTLESSQL_ENGINE` env var forwarded in `docker-compose.yml`
  (defaults to `"pandas"`)
- New dependency: `polars>=1.0`
- Engine compliance suite parameterized across all three engines;
  `TestPolarsEngineSpecific` with 3 Polars-specific tests; 2 new
  PQL constructor tests (9 new tests, 213 total pass)

### Added (Sprint 11)

- `pointlessql/pql/engine.py` — `Engine` protocol with `read()`,
  `write()`, and `columns_info()` methods; `PandasEngine` (default,
  preserving backward compatibility) and `DuckDBEngine` (reads Delta
  via PyArrow → DuckDB, returns `DuckDBPyRelation`)
- `make_engine()` factory to instantiate engines by name
- `columns_from_tuples()` in `_columns.py` — engine-agnostic column
  metadata builder for UC table registration
- Settings: `POINTLESSQL_ENGINE` (default `"pandas"`, also accepts
  `"duckdb"`) for engine selection via environment variable
- `PQL.__init__()` accepts `engine=` kwarg (string name or `Engine`
  instance); auto-selects from settings when omitted
- New dependencies: `duckdb>=1.0`, `pyarrow>=17.0`
- `tests/test_engine.py` — 20 new tests: parameterized engine
  protocol compliance suite (read, write, round-trip, column
  metadata) plus engine-specific tests for Pandas and DuckDB

### Changed (Sprint 11)

- `PQL.table()` and `PQL.write_table()` delegate all data I/O to
  the active engine instead of calling `deltalake` directly
- `PQL.__init__()` resolves `Settings` once and reuses it for both
  client creation and engine selection
- `columns_from_dataframe()` refactored to delegate to
  `columns_from_tuples()` internally (no behavior change)
- `pql/__init__.py` exports `Engine`, `PandasEngine`, `DuckDBEngine`,
  and `make_engine`

### Added (Sprint 10)

- `docker-compose.postgres.yml` — compose override that adds a
  Postgres service as PointlesSQL's metadata DB; usage:
  `docker compose -f docker-compose.yml -f docker-compose.postgres.yml up`
- `.env.example` — documents all `POINTLESSQL_*` env vars with
  defaults and descriptions
- Settings: `POINTLESSQL_BASE_URL` for OIDC callback URIs behind
  reverse proxies or inside Docker (falls back to request-derived
  URI when unset)
- `psycopg[binary]>=3.1` promoted from dev to main dependencies
  so Postgres URLs work at runtime
- Test fixture: `TEST_DATABASE_URL` env var to run the test suite
  against Postgres (or any SQLAlchemy-supported backend)

### Changed (Sprint 10)

- OIDC redirect_uri construction uses `POINTLESSQL_BASE_URL` when
  set, fixing SSO flows behind reverse proxies and in Docker
- Test `_auth_db` fixture drops all tables on teardown for clean
  isolation on persistent backends (Postgres)

### Added (Sprint 9)

- `Dockerfile` — 3-stage multi-stage build (soyuz-client-builder →
  builder → runtime) using `python:3.14-slim` and `uv pip install`
- `Dockerfile.soyuz` — 2-stage build for soyuz-catalog
- `docker-compose.yml` — full-stack orchestration with health checks,
  shared `./warehouse` volume for Delta storage, `depends_on` with
  `service_healthy` condition, configurable host ports via env vars
- `.dockerignore` for clean Docker builds
- Settings: `POINTLESSQL_HOST` (default `127.0.0.1`) and
  `POINTLESSQL_PORT` (default `8000`) for configurable bind address
- Frontend path fallback: installed wheel resolves
  `pointlessql/_frontend` when dev `frontend/` directory is absent
- README: Docker quick-start section with `docker compose up --build`

### Changed (Sprint 9)

- `cli()` reads host and port from `Settings` instead of hardcoding
- Jupyter subprocess uses `--allow-root` and binds to `settings.host`
  for Docker compatibility

### Added (Sprint 8)

- OIDC / OAuth2 authorization-code flow with PKCE — opt-in via
  `POINTLESSQL_OIDC_DISCOVERY_URL` and `POINTLESSQL_OIDC_CLIENT_ID`
  env vars; supports both public and confidential clients
- `pointlessql/services/oidc.py` — PKCE generation, HMAC-signed
  state cookie, discovery document caching, token exchange, userinfo
  fetch, find-or-create user provisioning with same-email linking
- `GET /auth/sso` route initiates the OIDC flow; `GET /auth/callback`
  handles the provider redirect and auto-provisions local users
- Login page shows conditional "Sign in with SSO" button alongside
  the existing email/password form
- Alembic migration 003: `password_hash` nullable for OIDC-only
  users, `oidc_provider` + `oidc_subject` columns with partial
  unique index
- `tests/test_oidc.py` — 33 new tests (177 total pass)

### Changed (Sprint 8)

- `User.password_hash` is now nullable to support OIDC-only accounts
- `auth.login()` handles `password_hash=None` gracefully (OIDC-only
  users cannot log in via email/password, preserving constant-time
  comparison)

### Added (Sprint 7)

- Authorization enforcement layer: PointlesSQL now checks effective
  permissions from soyuz-catalog before each operation. Non-admin
  users need `USE CATALOG`, `USE SCHEMA`, `SELECT`, `MODIFY`, or
  `MANAGE_GRANTS` depending on the operation
- Per-request `X-Principal` header forwarding: every soyuz-catalog
  HTTP call includes the authenticated user's email as the
  `X-Principal` header (via per-request client factory)
- Admin bypass: users with `is_admin=True` skip all permission checks
- Federation routes (connections, external locations, credentials)
  restricted to admin users only
- 403 Forbidden error page with privilege details and "contact an
  administrator" hint (`pages/403.html`)
- Audit log: `audit_log` table (Alembic migration 002) records
  who-did-what for all write operations — updates, tag changes,
  permission grants/revokes, federation CRUD
- `pointlessql/services/authorization.py` — `check_privilege`,
  `check_privilege_from_effective`, `has_privilege`, `AccessDenied`
- `pointlessql/services/audit.py` — `log_action` for append-only
  audit entries
- Permissions UI enhancements: current user's row highlighted with
  "you" badge in both Assigned and Effective tabs; grant/revoke
  controls hidden when user lacks `MANAGE_GRANTS`
- Non-admin test user fixture (`non_admin_cookies`) in conftest
- `tests/test_authorization.py` — 15 unit tests for authorization
  service (admin bypass, privilege matching, dict privilege format)
- `tests/test_enforcement.py` — 21 route-level enforcement tests
  (allowed/denied/admin bypass for catalogs, schemas, tables,
  updates, permissions, federation admin-only)
- `tests/test_audit.py` — 3 audit log service tests

### Changed (Sprint 7)

- All API routes use per-request `UnityCatalogClient` via
  `_get_uc_client(request)` instead of the shared singleton
- Detail pages enforce access using already-fetched effective
  permissions (no duplicate HTTP call)
- `permissions_card.html` and `permissions_editor.js` accept
  `canManage` and `currentUserEmail` parameters
- `test_api_errors.py` updated for per-request client pattern
  (monkeypatches `UnityCatalogClient.for_principal`)

### Added (Sprint 6)

- Alembic + SQLAlchemy 2.0 for PointlesSQL's own metadata DB
- Local user registration and login with bcrypt password hashing
- JWT cookie-based auth (`pql_session`, HttpOnly, HS256)
- Login and register pages
- Auth middleware protecting all routes
- First-user admin bootstrap
- Navbar shows current user and logout button

### Added (Sprint 5)

- Tags editor card on catalog, schema, and table detail pages — add
  and remove tags via PATCH to soyuz-catalog's tags endpoint, with
  Alpine.js interactive component (`tags_editor.html`, `tags_editor.js`)
- Permissions card with two Bootstrap nav-tabs (Assigned / Effective)
  on all detail pages — grant privileges via principal + privilege
  selector, revoke by clicking badge; effective permissions loaded
  on-demand (`permissions_card.html`, `permissions_editor.js`)
- Lineage card on table detail page showing upstream and downstream
  dependencies as depth-indented node lists with clickable links to
  related tables (`lineage_card.html`)
- Lakehouse Federation: full CRUD pages for connections, external
  locations, and credentials — list pages with create modals, detail
  pages with inline comment editing and delete-with-confirmation
  (`connections.html`, `connection.html`, `external_locations.html`,
  `external_location.html`, `credentials.html`, `credential.html`,
  `federation.js`)
- Federation dropdown in navbar (Connections, External Locations,
  Credentials)
- 21 new async facade methods in `unitycatalog.py` (tags, permissions,
  effective permissions, lineage, connections CRUD, external locations
  CRUD, credentials CRUD)
- 25 new JSON API routes + 6 HTML page routes in `main.py`
- `tests/test_tags_permissions.py` — unit tests for tags, permissions,
  effective permissions, and lineage facade methods
- `tests/test_federation.py` — unit tests for connections, external
  locations, and credentials facade CRUD
- Extended `tests/test_api_errors.py` with 11 new error-handling tests
  for all new JSON API endpoints

### Changed (Sprint 5)

- Detail page route handlers (`catalog_detail`, `schema_detail`,
  `table_detail`) now fetch tags, permissions, and effective permissions
  in parallel via `asyncio.gather`; `table_detail` additionally fetches
  lineage. Failure in any single fetch does not break the page
- `base.html` loads three new JS files: `tags_editor.js`,
  `permissions_editor.js`, `federation.js`

### Added (Sprint 4)

- E2E smoke test (`tests/test_e2e.py`): full roundtrip — create
  catalog/schema, write table via PQL, verify in web UI with correct
  columns and PQL snippet card
- `tests/conftest.py` with shared integration fixtures (`soyuz_client`,
  `e2e_env`)
- `tests/test_api_errors.py` — unit tests for API error handling
  (all JSON endpoints return 502 when soyuz-catalog is unreachable)
- PQL snippet card with copy-to-clipboard button on table detail page
- Jupyter loading spinner on notebook page: polls `/api/jupyter/status`
  until ready, shows error state with retry button after 30 s timeout

### Changed (Sprint 4)

- API JSON endpoints (`/api/tree`, `/api/catalogs`, `/api/schemas`,
  `/api/tables`, PATCH endpoints) return HTTP 502 with JSON error body
  when soyuz-catalog is unreachable (previously returned 500)
- `PQL.table()` and `PQL.write_table()` raise `ConnectionError` with
  a user-friendly message when soyuz-catalog is unreachable (previously
  raised raw `httpx.ConnectError`)
- Notebook page uses Alpine.js polling to wait for Jupyter readiness
  before loading the iframe; shows "Jupyter Not Available" error state
  if startup fails
- README.md rewritten with MVP setup docs, quick start, PQL usage
  examples, configuration table
- CLAUDE.md updated with Phase 1 completion, PQL/Jupyter/Alpine.js
  in stack, expanded layout section

### Previously added (Sprint 3)

- `pointlessql/services/jupyter.py` — async context manager that
  starts JupyterLab as a managed subprocess (SIGTERM/SIGKILL
  lifecycle, health-check polling, configurable port)
- `GET /notebook` route with embedded JupyterLab iframe; sidebar
  remains visible alongside the notebook for catalog browsing
- `GET /api/jupyter/status` JSON endpoint for subprocess status
- "Notebook" tab in the navbar (`base.html`)
- `{% block content_class %}` in `base.html` for per-page layout
  overrides (used by notebook page to remove content padding)
- Settings: `jupyter_enabled: bool = True`,
  `jupyter_port: int = 8888` (env overrides:
  `POINTLESSQL_JUPYTER_ENABLED`, `POINTLESSQL_JUPYTER_PORT`)
- `notebooks/getting_started.ipynb` — starter notebook demonstrating
  `PQL` read/write/list workflows
- New dependency: `jupyterlab>=4.0`
- `tests/test_jupyter.py` — 11 unit tests covering subprocess
  manager, route handlers, status API, and settings defaults

### Previously added (Sprint 2)

- `pointlessql/pql/` package — sync bridge between UC metadata and
  Delta Lake DataFrames, designed for notebooks and scripts
- `PQL` class with `table()` (read Delta as DataFrame),
  `write_table()` (write DataFrame + register metadata), and
  `list_catalogs()` / `list_schemas()` / `list_tables()` convenience
  methods
- New dependencies: `deltalake>=0.24`, `pandas>=2.2`
- `tests/test_pql.py` — unit tests with mocked soyuz client
- `tests/test_pql_integration.py` — integration round-trip test
  (create → write → read → verify)
- `PQL` re-exported from `pointlessql` package root

### Previously added (Sprint 1)

- `pointlessql/settings.py` — pydantic-settings module with
  `soyuz_catalog_url` setting (env override: `POINTLESSQL_SOYUZ_CATALOG_URL`)
- `pointlessql/services/soyuz_client.py` — factory for a configured
  `soyuz_catalog_client.Client` instance
- `tests/test_soyuz_client.py` — integration smoke tests against a
  live soyuz-catalog server (`@pytest.mark.integration`)
- `soyuz-catalog-client` as editable path dependency

### Changed

- `pointlessql/services/unitycatalog.py` — rewritten to delegate to
  the generated soyuz-catalog client instead of hand-rolled httpx
  calls. All methods convert attrs response objects to plain dicts
  via `.to_dict()` so templates stay unchanged
- `pointlessql/api/main.py` — lifespan uses `make_soyuz_client()`
  factory; error handling catches `UnexpectedStatus` alongside
  `httpx.HTTPError`

### Fixed

- Fixed code-gen bug in soyuz-catalog-client: `list_tables`
  `_parse_response` now handles the 200 status and returns
  `ListTablesResponse` instead of treating success as an unexpected
  status
