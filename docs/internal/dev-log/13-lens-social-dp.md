---
title: "Cluster 13 — Phase 70–77 Lens + Social + Data products (dev-log)"
audience: contributor
cluster_id: "13"
phases: "70-77"
closed: "2026-05-15"
---

# Cluster 13 — Phase 70–77 Lens + Social + Data products (dev-log)

> Phase 70 (member-access + 5-submodule JS-split), Phase 71-72 (Session B closures), Phase 73 (agent-authored data products), Phase 74-75 (social network primitives), Phase 76 (Full Social Network for Data Products), Phase 77 (workspace landing + pin CRUD + 11 sub-sprints).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Notes**)

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

> from CHANGELOG.md (bucket: **Notes**)

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

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 74.2 — Hermes-cron alt runner (2026-05-15).**
  New ``GET /api/active-reviewer/queue`` (admin/steward) lists
  DPs with ``runner='hermes_cron'`` so a Hermes-cron job can
  enumerate work.  The plugin H.3 batch (out-of-tree in
  ``hermes-plugin-pointlessql``) ships ``pql_dp_activity`` /
  ``pql_dp_post_comment`` / ``pql_dp_endorse`` so the cron
  job can render context + post comment + write endorsement
  end-to-end via plugin tools.

> from CHANGELOG.md (bucket: **Notes**)

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

> from CHANGELOG.md (bucket: **Notes**)

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

> from CHANGELOG.md (bucket: **Notes**)

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

> from CHANGELOG.md (bucket: **Notes**)

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
