---
title: "Cluster 14 — Phase 78–81 (Hygiene + Phase 81 feed/launchpad) (dev-log)"
audience: contributor
cluster_id: "14"
phases: "78-81"
closed: "2026-05-16"
---

# Cluster 14 — Phase 78–81 (Hygiene + Phase 81 feed/launchpad) (dev-log)

> Phase 78-79 (stale-comment + broad-except sweep), Phase 80 (phase-80.9 close-out), Phase 81 (large feed/launchpad wave: 81.G inline-edit, 81.H /new launchpad, 81.K Activity/Discover tabs, 81.L /help reference, 81.M entity action menus).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Added**)

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

> from CHANGELOG.md (bucket: **Changed**)

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

> from CHANGELOG.md (bucket: **Added**)

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
