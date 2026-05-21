# Roadmap

Single source of truth for *what is done*, *what is in progress*, and
*what is next* in PointlesSQL. Read this before starting work so you
pick up where the previous session left off.

The phases below break the project down into milestones (`M0`) and
sprints (`Sprint N`). When a sprint lands, flip it to ✅ and append
the short commit hash. When the scope of a planned sprint becomes
clearer, expand its bullet list in place — do not create a separate
planning document. This mirrors the roadmap discipline established
in [`soyuz-catalog/ROADMAP.md`](../soyuz-catalog/ROADMAP.md).

Older closed phases that are no longer load-bearing for follow-up
conversations are *collapsed*: a one-line summary stays in this
file (in tabular form), and the full per-sprint detail moves to
[`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md).  See "How to update
this file" at the bottom for the collapse trigger.  Phase numbers
are preserved across the collapse so cross-references in
`CHANGELOG.md`, memory entries, and commit messages remain valid.

Status legend: ✅ done · 🟦 backbone shipped (deferred UI/wiring follow-ups) · 🔜 next · ⏳ planned · ⏳ partial · 🧊 on ice

## Current state

```text
PointlesSQL
│
├── Phases 0–47 — completed, collapsed                    ✅ done
│   │
│   │   Full per-sprint detail in
│   │   [`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md).  Phases 0-12.8
│   │   were collapsed in commit `3a90354` (2026-04-27); Phases
│   │   12.10-13.5 in the same commit; Phases 12.9 + 14-47 rolled
│   │   2026-05-12 to bring this file back under 2500 lines.
│   │
│   │   ```
│   │   Phase  Closed       Sprint range  What shipped
│   │   ─────  ───────────  ────────────  ─────────────────────────────────────
│   │     0    2026-01      M0–M1         Repo skeleton, hand-rolled httpx UC client, catalog browser prototype
│   │     1    2026-02      S1–S4         MVP: catalog UI + Notebook tab + pql Pandas/Delta helper
│   │     2    2026-02      S5            Catalog UI cards: tags, permissions, lineage, federation
│   │     3    2026-02      S6–S8         Auth: login, JWT sessions, grant enforcement (PointlesSQL = enforcement layer)
│   │     4    2026-03      S9–S10        `docker compose up` packaging, soyuz-client wheel, single-image flow
│   │     5    2026-03      S11–S12       Pluggable compute engines (DuckDB + Polars alongside Pandas)
│   │     5.5  2026-03      S13–S15       Quality pass: strict pyright, exception hierarchy, structured logs
│   │     6    2026-03      S16–S20       Foreign Postgres mirror, scheduler/jobs, cron mgmt UI
│   │     7    2026-03      S21–S22       Playwright-MCP live UI walkthroughs (every HTML route exercised)
│   │     8    2026-03      S23–S30       Notebook-as-job: Papermill execution, schedule, params, output
│   │     9    2026-03      S31–S40       UX overhaul: nav, search, toasts, breadcrumbs, dark mode, empty states
│   │    10    2026-03      S41–S43       Private GHCR + git-tag pinning, dual-auth Dockerfile
│   │    11    2026-03      S44–S47       CSRF, rate-limiting, JWT key rotation, in-app audit viewer, OIDC
│   │    12    2026-04      S48–S53       SQL editor (CodeMirror) + query history + audit-log hardening
│   │    12.5  2026-04      S54–S57       Charts, alerts (HMAC/CloudEvents/Atom/JSON-Feed), column stats, UC Volumes
│   │    12.6  2026-04      S58–S64       Native Monaco notebook editor (replaces JupyterLab iframe)
│   │    12.7  2026-04      S65–S80       Notebook editor UX overhaul (variable explorer, Marimo-grade)
│   │    12.8  2026-04      S81–S86       Frontend cleanup: ESM modules, CSS split, `pqlApi.fetch` CSRF wrapper
│   │    12.9  2026-05-05   S76–S95       LLM-friendly modularization (frontend 99.3% ESM, 28 modules / 5852 LOC)
│   │   12.10  2026-04      S96–S98       Notebook format hardening (UUID-free percent grammar, FNV-1a-64 hash)
│   │   12.11  2026-04      S99           Notebook visual polish (toolbar+badges only; S100–S102 cancelled)
│   │   12.12  2026-04-24   S103–S106     Agent-first pivot: delete browser editor, build read-only run-view
│   │    13    2026-04-26   S107–S128     Agent-run supervision + analytical memory; 13.11 = 10 reflexive tools
│   │    13.5  2026-04-26   S129–S140     Medallion + DuckDB-first opinion: pql.autoload/merge/aggregate
│   │    14    2026-04-26   —             Audit-trail completeness: cost-gate EXPLAIN + read-audit + soyuz cross-ref
│   │    15    2026-04-26   —             Lineage completeness: PQL→soyuz OpenLineage + lineage_row_edges + row-trace UI
│   │    15.5  2026-04-26   —             Aggregate Lineage + Rejects (walk_back tree + lineage_row_rejects + Rejects tab)
│   │    15.6  2026-04-26   —             Column-Level Lineage (lineage_column_map + sqlglot AST + column-trace UI)
│   │    15.7  2026-04-26   —             Value-Level Lineage (lineage_value_changes + CDF bootstrap + value-changes API)
│   │    15.8  2026-04-30   —             Lineage Wiring Audit (1 root cause: silver SELECT drops _lineage_row_id)
│   │    16    2026-04-27   —             First-Class Rollback (pql.rollback + RollbackError + /runs/{id}/rollback UI)
│   │    16.5  2026-04-29   —             Delta-Branching (tags + pql.branch/discard/promote/preview + control-room)
│   │    17    2026-04-29   —             UI Overhaul: icon-rail sidebar + 4-tab run-detail + cytoscape DAG + 6-tab table
│   │    18    2026-04-29   —             Audit Cockpit: inbox+badge + FTS + reverse-index + deeper-diff
│   │    19    2026-04-29   —             Audit-Reviewer Agent + Grafana: 3 personas + agent_reviews + 5 audit routes
│   │    20    2026-04-29   —             Forensics + Retention: stream-fwd (webhook/S3/CloudTrail) + PII hash + TTLs
│   │    21    2026-04-30   —             ML Registry: MLflow subprocess + UC MODEL securable + 5-tab + autolog
│   │    22    2026-04-30   —             Documentation site (mkdocs-material, ~30 pages, ADR-0004 launch-flip)
│   │    23    2026-05-05   23.0–23.5     Contextual help-popovers (5 hero + models/runs/branches/audit anchors)
│   │    28    2026-05-05   —             Workspace isolation (Databricks-style soft, per-workspace audit-sink)
│   │    29    2026-05-05   —             Workspace polish: OIDC group→workspace mapping + Grafana $workspace var
│   │    30    2026-05-05   —             Postgres production-readiness (PG FTS + sqlite→pg migration CLI + pool tune)
│   │    31    2026-05-05   31.0–31.4     Test-suite speed: SQLite 30min→68s (bcrypt rounds=4 + session-scope schema)
│   │    32    2026-05-05   —             PG test quality: 45 failures → 0 (session.flush adds + dialect-aware seeds)
│   │    33    2026-05-05   —             Admin Console: /admin/{audit-sinks,review-destinations,api-keys,system-info}
│   │    34    2026-05-05   —             Cross-Workspace Observability: 8 new Grafana panels
│   │    35    2026-05-06   —             Targeted modularization: _branch 1310→branch/, lineage_edges 1137→lineage/
│   │    36    2026-05-06   —             Declarative Pipelines + Expectations
│   │    37    2026-05-06   —             Playwright coverage refresh (44→48 walkthroughs, 6 BUG-37 fixed in 37.1)
│   │   37.1   2026-05-06   —             Phase-37 BUG sweep (HTMX 2.0.6, dbt chrome, admin x-data escape)
│   │    38    2026-05-06   —             Sprint-Sweep: 35.4 (run_view→8 partials) + 36.7 unblocked via mashumaro 3.17
│   │    39    2026-05-06   —             Agent EXPLAIN-driven self-rewrite loop (structured envelope rewrite)
│   │    40    2026-05-06   —             Lakehouse Federation reads (OpenLineage POST + table-detail merged graph)
│   │   40.5   2026-05-06   —             Foreign-Delta CDF tail (pull-modell, deferred from 40.2 at plan time)
│   │   40.6   2026-05-06   —             CDF Tail UI integration
│   │   40.7   2026-05-06   —             Row-Trace fold-in of CDF events
│   │    41    2026-05-07   —             Sprint 17.6 promoted: 3 lineage sub-pills (Row/Column/Value) in run-detail
│   │    42    2026-05-07   —             Anomaly-Inbox System-Errors band
│   │    43    2026-05-07   —             Error envelope + exception hierarchy unification
│   │    44    2026-05-07   —             Structured logging + traceback preservation
│   │    45    2026-05-07   —             Pyright Hot-Spot Cleanup (559→497 warnings)
│   │    46    2026-05-07   —             Test-Auth-Fixture Centralization (admin_client/non_admin_client/anonymous_client)
│   │    47    2026-05-07   —             NewType ID Hardening (RunId/OpId/QueryHistoryId, ~36 consumer signatures)
│   │   ```
│   │
│
├── Phase 71 — Data-Product Marketplace polish              ✅ done 2026-05-12
│   │
│   │   Catch-up to enterprise-catalog collaboration table stakes
│   │   (Atlan, Collibra, Alation, Snowflake Marketplace).
│   │   Phase 50 already gives us the Data-Product contracts +
│   │   freshness + dependency-graph; Phase 71 layers the social
│   │   affordances analysts already expect from a modern catalog
│   │   so PointlesSQL doesn't read as "no comments / no follow /
│   │   no reviews" against the incumbents at trial time.
│   │
│   │   Scope is deliberately narrowed to well-trodden patterns
│   │   (comment threads, star ratings + reviews, follow + email
│   │   webhook, wiki README, browse-page rework).  The
│   │   AI-native differentiation lives in Phase 72; the two
│   │   phases are independent and can land in either order.
│   │
│   │   Cross-cutting picks (TBD at plan time):
│   │   - threaded vs flat comments (recommend threaded with a
│   │     2-level cap to avoid Reddit-depth UX);
│   │   - markdown rendering reuses the existing `markdown-it`
│   │     bundle (Phases 12.5/56);
│   │   - rating widget = Bootstrap 5-star; one review per user
│   │     per DP (upsert);
│   │   - notifications fan out via the Phase-20 audit-stream
│   │     forwarder (webhook + email sinks) — no new pub-sub
│   │     plumbing.
│   │
│   ├── Sprint 71.1 — Comment threads per data product         ✅ done 2026-05-12
│   │   ├── New model: `DataProductComment` (id, dp_slug,
│   │   │   parent_comment_id, author_user_id, body_md,
│   │   │   created_at, deleted_at, workspace_id) + Alembic.
│   │   ├── Soft-delete via `deleted_at` so audit-trail integrity
│   │   │   holds; threading via parent_comment_id capped at
│   │   │   depth 2.
│   │   ├── `/api/data-products/{slug}/comments` GET (list) +
│   │   │   POST (create) + DELETE (soft, author or
│   │   │   workspace admin).
│   │   ├── `@mention` resolution against OIDC users; resolved
│   │   │   mentions feed into Sprint 71.4 notifications.
│   │   ├── New "Discussion" tab on `/data-products/{slug}`.
│   │   └── ~15 pytest cases (CRUD + soft-delete + auth +
│   │       cross-workspace isolation).
│   │
│   ├── Sprint 71.2 — Star ratings + review text               ✅ done 2026-05-12
│   │   ├── New model: `DataProductReview` (id, dp_slug,
│   │   │   author_user_id, stars 1-5, body_md, created_at,
│   │   │   updated_at, dp_semver_at_review, workspace_id) +
│   │   │   Alembic.
│   │   ├── One review per (user, DP); idempotent upsert via
│   │   │   `/api/data-products/{slug}/reviews` PUT.
│   │   ├── Average-rating + count badge on
│   │   │   `/data-products/{slug}` header + browse cards.
│   │   ├── Reviews tab on the DP page with sorting (recent vs
│   │   │   stars-desc).
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 71.3 — Follow / subscribe                       ✅ done 2026-05-12
│   │   ├── New model: `DataProductFollow` (user_id, dp_slug,
│   │   │   workspace_id, created_at) — composite PK + Alembic.
│   │   ├── `/api/data-products/{slug}/follow` POST/DELETE for
│   │   │   self; followers-count exposed via `/api/data-
│   │   │   products/{slug}` (full list only to steward, for
│   │   │   privacy).
│   │   ├── "Follow / Unfollow" button on the DP header.
│   │   ├── New page `/data-products/followed` listing the
│   │   │   current user's followed DPs.
│   │   └── ~8 pytest cases.
│   │
│   ├── Sprint 71.4 — Notification fanout                      ✅ done 2026-05-12
│   │   ├── Wire follow + comment + review events into the
│   │   │   Phase-20 audit-stream forwarder so existing
│   │   │   webhook/S3/CloudTrail sinks receive them — no new
│   │   │   pub-sub plumbing.
│   │   ├── New event types: `pql.dataproduct.commented`,
│   │   │   `pql.dataproduct.reviewed`,
│   │   │   `pql.dataproduct.schema_changed`,
│   │   │   `pql.dataproduct.contract_violated`.
│   │   ├── Per-user inbox at `/notifications` rendering events
│   │   │   for the user's followed DPs (reuses the audit-cockpit
│   │   │   inbox pattern from Phase 18.6).
│   │   ├── Email-digest opt-in via existing user-settings
│   │   │   surface (Phase 33 admin precedent).
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 71.5 — Wiki / README per DP                     ✅ done 2026-05-12
│   │   ├── New model: `DataProductReadme` (dp_slug, body_md,
│   │   │   version_int, updated_by_user_id, updated_at,
│   │   │   workspace_id) — single row per DP, version_int
│   │   │   monotonic.
│   │   ├── Steward + workspace-admin can edit; markdown render
│   │   │   via the existing `markdown-it` bundle.
│   │   ├── README tab on the DP page: contract-derived autodoc
│   │   │   at the top + free-form editorial below.
│   │   ├── History view with side-by-side diff between two
│   │   │   versions (reuses the diff macro from Phase 18.9).
│   │   └── ~6 pytest cases.
│   │
│   └── Sprint 71.6 — Browse-page rework                       ✅ done 2026-05-12
│       ├── `/data-products` index gets sortable columns
│       │   (rating-desc, recently-active, follow-count,
│       │   freshness-on-time).
│       ├── Filter chips (domain, steward, has-comments,
│       │   has-readme).
│       ├── "Recently active" surfaces DPs with new comments,
│       │   reviews, contract bumps in last 7d.
│       └── ~8 pytest cases.
│
├── Phase 72 — Agent-Aware Social Layer                     ✅ done 2026-05-13
│   │
│   │   AI-native differentiation on top of (or alongside)
│   │   Phase 71's catalog-collaboration foundation.  Treats
│   │   *agent activity* as the currency of social engagement
│   │   instead of human Likes — every endorsement badge is
│   │   auto-computed from lineage + audit data, every "trend"
│   │   is measured by `agent_run_operations` count, every
│   │   discussion thread is itself an audit_log row.
│   │
│   │   Plays into the AI-native lakehouse vision (memory:
│   │   `project_ai_native_vision.md`) and the supervision-first
│   │   framing (memory: `project_agent_first_pivot.md`).  Heavy
│   │   reuse of Phases 13 (agent_run_operations), 14 (audit_log),
│   │   15.x (lineage), 18.7 (audit FTS), 19 (agent_reviews),
│   │   20 (audit-stream + retention), 34 (cross-workspace
│   │   Grafana lens).
│   │
│   │   Independent of Phase 71 — neither is a prerequisite to
│   │   the other.  Land together for a unified Marketplace++
│   │   story or split across two release windows.
│   │
│   │   Cross-cutting picks (TBD):
│   │   - all endorsement badges are *typed* (no generic
│   │     👍/❤️) so the system stays audit-clean;
│   │   - comments-as-audit-rows (Sprint 72.5) is the canonical
│   │     contract that distinguishes us from Slack-clone risk
│   │     — if Phase 71.1's `DataProductComment` table ships
│   │     first, 72.5 either supersedes it or co-exists (model
│   │     decision at 72.5 plan time);
│   │   - "trending" board is a rolling 7d window, refreshed by
│   │     a new loop coroutine matching the freshness-loop
│   │     cadence.
│   │
│   ├── Sprint 72.1 — Activity feed per DP                     ✅ done 2026-05-13
│   │   ├── New aggregator `services/data_products/activity.py`
│   │   │   merges 4 source streams into a unified feed:
│   │   │   - audit_log writes referencing DP tables (Phase 14);
│   │   │   - agent_run_operations referencing DP tables
│   │   │     (Phase 13);
│   │   │   - freshness_scanner pass/miss events (Phase 50);
│   │   │   - schema / contract changes (Phase 50).
│   │   ├── `/api/data-products/{slug}/activity` GET with
│   │   │   server-side offset pagination (mirrors /queries
│   │   │   pattern from Sprint 57.2).
│   │   ├── New "Activity" tab on the DP page; becomes the
│   │   │   default landing tab when the DP has recent
│   │   │   agent-run-ops in the last 7 days.
│   │   ├── Per-row click-through to the run / audit row /
│   │   │   lineage trace that generated the event.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 72.2 — Auto-computed endorsement badges         ✅ done 2026-05-13
│   │   ├── New service `services/data_products/badges.py`
│   │   │   computes each badge on-demand:
│   │   │   - `downstream-count`: out-edges in
│   │   │     `lineage_column_map` (Phase 15.6);
│   │   │   - `agent-run-count-7d`: distinct `agent_runs`
│   │   │     touching DP tables in last 7d (Phase 13);
│   │   │   - `last-rollback-passed`: did the most recent
│   │   │     rollback-preview succeed (Phase 16)?
│   │   │   - `freshness-on-time-30d`: % of freshness checks
│   │   │     in last 30d meeting SLA (Phase 50).
│   │   ├── Rendered as Bootstrap badges on DP header + browse
│   │   │   cards.
│   │   ├── Sort / filter on the browse page by each badge.
│   │   ├── No cache table — badges are cheap aggregates and
│   │   │   recompute-per-render keeps them honest.
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 72.3 — "Trending in agent workloads" board      ✅ done 2026-05-13
│   │   ├── New page `/data-products/trending` ranking DPs by
│   │   │   `agent_run_count` + `audit_log_write_count` over a
│   │   │   rolling 7d window.
│   │   ├── New cache table `data_product_trending` (dp_slug,
│   │   │   window_start, agent_run_count, write_count, rank,
│   │   │   workspace_id) + Alembic.
│   │   ├── New loop coroutine in `_bootstrap/_loops.py`
│   │   │   refreshes the window every 15min (matches
│   │   │   `_data_product_freshness_loop` cadence).
│   │   ├── Per-workspace by default; cross-workspace toggle
│   │   │   gated by workspace-admin / auditor (Phase 34 lens
│   │   │   precedent).
│   │   ├── New Grafana panel "Top-10 trending DPs" added to
│   │   │   both single-workspace + cross-workspace dashboards.
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 72.4 — Typed manual endorsements                ✅ done 2026-05-13
│   │   ├── New model: `DataProductEndorsement` (id, dp_slug,
│   │   │   endorsement_type, applied_by_user_id, applied_at,
│   │   │   removed_at, note_md, workspace_id) + Alembic.
│   │   ├── Allowed types validated server-side:
│   │   │   `verified-by-steward`, `production-ready`,
│   │   │   `deprecated`, `under-review`.  No free-form
│   │   │   user-typed strings.
│   │   ├── Scope-gated: only the DP's steward OR
│   │   │   workspace-admin / auditor can apply or remove.
│   │   │   Every action audit-logged as
│   │   │   `audit.endorsement.{applied,removed}`.
│   │   ├── Endorsement badges rendered on DP header +
│   │   │   browse cards; `deprecated` triggers a soft
│   │   │   warning on writes to DP tables (Phase 50 pre-write
│   │   │   hook).
│   │   ├── New plugin tool `pql_endorse_data_product` so the
│   │   │   Phase-19 reviewer-agent can apply
│   │   │   `verified-by-steward` after a clean audit pass.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 72.5 — Audit-bound discussions                  ✅ done 2026-05-13
│   │   ├── Comments land as `audit_log` rows with
│   │   │   `kind=audit.discussion.posted` — supersedes or
│   │   │   coexists with Phase 71.1's separate table (decision
│   │   │   at plan time depending on whether 71.1 has
│   │   │   landed).
│   │   ├── Audit-log row carries body_md, parent_audit_log_id,
│   │   │   dp_slug, author_user_id; FTS-indexed via the
│   │   │   Phase-18.7 `audit_search` index so comments are
│   │   │   discoverable alongside everything else.
│   │   ├── Retention via the Phase-20 audit_retention loop —
│   │   │   no separate policy.
│   │   ├── Soft-hide model: `audit.discussion.hidden` follow-up
│   │   │   row (never destructive); only steward +
│   │   │   workspace-admin can hide.
│   │   ├── UI: "Discussion" tab on DP page, threaded, mentions
│   │   │   auto-link to user profile pages.
│   │   └── ~15 pytest cases.
│   │
│   └── Sprint 72.6 — CloudEvent subscriptions for DP changes  ✅ done 2026-05-13
│       ├── New `pql.dataproduct.*` event types registered in
│       │   the Phase-13.3 CloudEvent emitter
│       │   (`schema_changed`, `contract_violated`,
│       │   `freshness_missed`, `endorsement_applied`).
│       ├── Per-user webhook subscriptions: user registers a
│       │   webhook URL + filter expression ("only
│       │   contract_violated on DPs I follow"); HMAC-signed
│       │   delivery matches Phase-20 forwarder contract.
│       ├── Self-service config UI on
│       │   `/profile/notifications/subscriptions`.
│       └── ~10 pytest cases.
│
├── Phase 73 — Agent-authored data products                 ✅ done
│   │
│   │   Phase 72 made the data-product surface *aware* of
│   │   agents (badges, trending, activity feed).  Phase 73
│   │   inverts the flow: agents *author* and *evolve* data
│   │   products.  Today a DP exists when a human commits a
│   │   `pointlessql.yaml`; tomorrow the platform suggests one
│   │   when an agent run-pattern consistently produces a
│   │   stable schema, and lets the agent declare quality
│   │   contracts from inside the notebook.  This is the
│   │   AI-native pitch the incumbents can't match: catalogs
│   │   that grow from observed behaviour, not just human
│   │   curation.
│   │
│   │   Reuse heavy: Phase 13 (`agent_run_operations`),
│   │   Phase 15.6 (`lineage_column_map`), Phase 50
│   │   (`DataProduct` + yaml loader), Phase 72.1
│   │   (`fetch_activity_for_dp`).
│   │
│   │   Cross-cutting picks (TBD at plan time):
│   │   - YAML write path — does the platform write the yaml
│   │     directly (in-process) or open a PR against the
│   │     workspace-repo (Phase 51 path)?  PR path is
│   │     cleaner audit-wise but blocks single-tenant
│   │     installs without a git remote;
│   │   - contract DSL — pydantic-validated dict-from-yaml
│   │     stays canonical; `pql.contract()` builds the same
│   │     dict from inside notebooks and persists alongside
│   │     `pointlessql.yaml`;
│   │   - schema-change proposal model — does an agent
│   │     `propose` go through `AgentReview` (Phase 19) or
│   │     a new `DataProductSchemaProposal` table?  Reuse
│   │     of AgentReview is tempting but the surface is
│   │     write-oriented, not review-oriented.
│   │
│   ├── Sprint 73.1 — Promote-to-DP suggestion                  ✅ done
│   │   ├── New service `services/data_products/promote.py`
│   │   │   scans `agent_run_operations` for `target_table`
│   │   │   values that match a stable signature
│   │   │   (≥3 distinct runs / 14d, ≥10 row-affected ops,
│   │   │   no agent-flagged schema instability).
│   │   ├── New `DataProductPromotionCandidate` cache table
│   │   │   refreshed by a new loop coroutine
│   │   │   (`_data_product_promotion_loop`); same opt-in
│   │   │   cadence pattern as the trending loop.
│   │   ├── New `/data-products/candidates` HTML page +
│   │   │   `GET /api/data-products/candidates` JSON; admin /
│   │   │   steward dismiss / "Generate yaml".
│   │   ├── `POST /api/data-products/candidates/{id}/generate`
│   │   │   builds a draft `pointlessql.yaml` from the
│   │   │   schema-snapshot stream + lineage edges; either
│   │   │   writes to the active workspace-repo (PR path) or
│   │   │   into a `_drafts/` directory the admin can review.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 73.2 — pql.contract() inline DSL                 ✅ done
│   │   ├── New `pql.contract(catalog, schema, *, tables=...)`
│   │   │   API that builds and persists the same yaml
│   │   │   payload from inside a notebook cell.  Returns a
│   │   │   `DataProductContract` object so the notebook
│   │   │   can chain validations (row count, freshness
│   │   │   bounds, value distribution checks) before commit.
│   │   ├── On `pql.contract().save()`, the file lands in
│   │   │   the workspace-repo (Phase 51) under
│   │   │   `pointlessql.yaml` next to the notebook OR is
│   │   │   merged into the existing yaml when one exists
│   │   │   for the schema (declarative merge — explicit
│   │   │   conflict raises).
│   │   ├── New `/api/contracts/draft` JSON endpoint backing
│   │   │   the "preview yaml before save" UX.
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 73.3 — Schema-change proposal flow              ✅ done
│   │   ├── New model `DataProductSchemaProposal` (id,
│   │   │   data_product_id, proposer_user_id, proposer_kind,
│   │   │   diff_json, status, created_at, resolved_at,
│   │   │   resolved_by, resolution_note_md) + Alembic.
│   │   ├── New `POST /api/data-products/{cat}/{sch}/proposals`
│   │   │   for agents (plugin tool `pql_propose_schema_change`)
│   │   │   + humans (UI button in the Discussion tab).
│   │   ├── Inbox card on the DP detail page surfaces open
│   │   │   proposals; steward + admin can approve / reject
│   │   │   with one click.  Approval triggers either the PR
│   │   │   flow (workspace-repo) or in-place yaml rewrite.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 73.4 — Data passport / auto-README              ✅ done
│   │   ├── New `services/data_products/passport.py` renders
│   │   │   a markdown briefing from the lineage graph
│   │   │   (sources, transforms, downstream consumers,
│   │   │   freshness profile).  Output drops into the
│   │   │   `DataProductReadme` table as version 0 (auto)
│   │   │   when no human README exists yet; stays visible
│   │   │   as a "system passport" tab even after a steward
│   │   │   writes their own README.
│   │   ├── Re-generates on schema-change emits (Sprint B.1
│   │   │   ``EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED``) so
│   │   │   the passport reflects the current shape.
│   │   └── ~8 pytest cases.
│   │
│   └── Sprint 73.5 — Cross-DP recommendations                  ✅ done
│       ├── "Agents who read X also read Y" — co-occurrence
│       │   over `agent_run_operations.target_table` joined
│       │   to `agent_runs.id`.  Materialised as a 7d-rolling
│       │   `data_product_cooccurrence` cache table.
│       ├── New "Related products" card on the DP detail
│       │   header + a "Recommended for you" strip on
│       │   `/data-products/followed`.
│       └── ~8 pytest cases.
│
├── Phase 74 — Reviewer-Agent v2 (Active steward delegate)  ✅ done 2026-05-15
│   │
│   │   Phase 19's passive Audit-Reviewer-Agent (writes one
│   │   summary row per run when triggered) promoted to an
│   │   active LLM-calling steward delegate.  Both runners
│   │   shipped per the plan-mode "Both surfaces" pick:
│   │   PointlesSQL-side in-proc loop (default) + Hermes-cron
│   │   alt path for stewards who want LLM cost / latency
│   │   out-of-process.  Per-DP opt-in via the new
│   │   ``DataProductActiveReviewerConfig`` table.
│   │
│   ├── Sprint 74.0 — Config table + service skeleton           ✅ 2026-05-15
│   │       New ``DataProductActiveReviewerConfig`` model +
│   │       alembic ``m9o1q3s5u7w9``.  Per-(workspace, dp) row
│   │       with enabled / runner CHECK ('inproc' | 'hermes_cron') /
│   │       llm_provider CHECK ('anthropic' | 'openai' | NULL) /
│   │       llm_model / prompt_override_md / acting_user_id
│   │       (steward proxy author for the non-nullable
│   │       comment / endorsement FK) / last_run_at /
│   │       last_run_comment_id.  New service
│   │       ``services/data_products/active_reviewer.py`` with
│   │       ``build_prompt`` + ``parse_review_result``
│   │       (explicit ``## Verdict:`` line + keyword-heuristic
│   │       fallback) + ``ReviewVerdict`` dataclass +
│   │       ``upsert_config`` + ``iter_opted_in_dp_ids``.
│   │
│   ├── Sprint 74.1 — PointlesSQL-side in-proc runner           ✅ 2026-05-15
│   │       ``run_reviewer_for_dp`` async entry-point with
│   │       injectable ``api_key_resolver`` + ``llm_call``
│   │       hooks (for unit-test fakes).  Loop
│   │       ``_active_reviewer_loop`` sleeps until
│   │       ``data_products.active_reviewer_trigger_hour`` UTC,
│   │       semaphore-bounds concurrent ticks at
│   │       ``active_reviewer_max_concurrent`` (default 3),
│   │       iterates DPs with ``runner='inproc'``.  Posts
│   │       ``DataProductComment`` + typed
│   │       ``DataProductEndorsement`` (green →
│   │       verified-by-steward, red → under-review) +
│   │       ``AgentReview`` row (kind=audit_review, severity
│   │       from verdict, payload_json carries the prompt +
│   │       raw LLM response).  Routes
│   │       ``GET/POST /api/data-products/{c}/{s}/active-reviewer``
│   │       (steward/admin) + ``run-now``.
│   │
│   ├── Sprint 74.2 — Hermes-cron runner + queue endpoint        ✅ 2026-05-15
│   │       ``GET /api/active-reviewer/queue`` (admin) lists
│   │       DPs with ``runner='hermes_cron'`` for a Hermes-cron
│   │       job to enumerate.  The plugin H.3 (out-of-tree)
│   │       ships ``pql_dp_activity`` / ``pql_dp_post_comment``
│   │       / ``pql_dp_endorse`` so the cron job can render
│   │       audit context + post comment + write endorsement
│   │       end-to-end without inventing new HTTP shape.
│   │
│   └── Sprint 74.3 — Steward UX HTML                          🧊 deferred
│           Active-reviewer card + ``/me/reviewer-config`` page
│           deferred.  Routes are agent-callable today; the
│           steward UI lands as a 74.3.1 follow-up once the
│           in-proc loop runs against a real workload.
│
├── Phase 77 — Social-as-Connective-Tissue across the platform  ✅ done (2026-05-15)
│   │
│   │   "PointlesSQL is to Unity Catalog + Spark/DuckDB what
│   │   GitHub is to Git."  Lifts the Phase-76 social surface
│   │   (comments / reviews / endorsements / citations / mentions
│   │   / follows / topics) from DP-only to the connective tissue
│   │   over every named platform object: UC tables, schemas,
│   │   catalogs, models, branches, runs, queries, notebooks,
│   │   saved audit queries — and adds GitHub-Issues / Stars /
│   │   READMEs-everywhere / PR-style branch-promote-gate /
│   │   workspace-as-Organization primitives.
│   │
│   │   Architecture locked: social layer lives entirely in
│   │   PointlesSQL — soyuz stays pure-UC-spec.  Schema strategy
│   │   = sidecar polymorphic anchor (``social_targets`` keyed by
│   │   ``(workspace_id, entity_kind, entity_ref)``).  Comments /
│   │   reviews / endorsements / follows / reactions / readmes
│   │   point at ``social_targets.id`` instead of
│   │   ``data_products.id`` directly.  CASCADE-on-DP-delete
│   │   preserved via a back-pointer on the anchor row.  Audit-
│   │   log target string keeps the legacy ``data_product:``
│   │   prefix for kind='dp' rows forever (locked decision #9);
│   │   every new kind writes the generic ``{kind}:{ref}`` form.
│   │   Branch promote-gate is opt-in per workspace
│   │   (``branch_promote_requires_endorsement DEFAULT FALSE``);
│   │   default never auto-flips.  Notebook ``entity_ref`` is
│   │   an immutable UUID, not the file path.
│   │
│   ├── Phase 77.0 — Polymorphic foundation (zero new entity types)  ✅ done (2026-05-15)
│   │       ``social_targets`` anchor table + ``entity_registry``
│   │       single-source-of-truth + ``get_or_create_target`` /
│   │       ``resolve_workspace_for_entity`` resolver.  Migration
│   │       ``v3y5a7c9e1g3`` creates the anchor + backfills one
│   │       row per existing DP.  Subsequent 77.0 migrations add
│   │       ``social_target_id`` columns to the seven existing
│   │       social tables, ship the generic ``mirror_social_to_audit``
│   │       helper + ``fanout_event`` dispatcher + citations-
│   │       registry refactor + ``/api/social/{kind}/{ref}/...``
│   │       router + frontend partial extraction +
│   │       feed-URL-builder via registry.  Drops the now-
│   │       redundant ``data_product_id`` columns at the end.
│   │       End-user behaviour unchanged; the entire DP-social
│   │       test suite must pass unmodified.
│   │
│   ├── Phase 77.1 — Tables                                          ✅ done (2026-05-15)
│   │       First new entity type.  Discussion + Endorsements +
│   │       Followers + README tabs on every UC table page.
│   │       Reviews hidden (tables don't get star-ratings).
│   │       ``#table:cat.sch.tbl`` citation token registered.
│   │       Federated / foreign tables get the same tabs (no
│   │       banning).  Stars left to Phase 77.8.
│   │       77.1.A: registry + citations backbone.
│   │       77.1.5: polymorphic backend handlers (12 fns across 4
│   │       axes) + socialTabs Alpine factory + 2 new partials +
│   │       table.html tab strip.
│   │
│   ├── Phase 77.3 — Branches (with promote-gate, opt-in)            ✅ done (2026-05-15)
│   │       Branch detail page has 4 social tabs + Promote tab
│   │       (Danger Zone) + the killer GitHub-PR analog: workspace
│   │       setting ``branch_promote_requires_endorsement`` (default
│   │       OFF, never auto-flipped).  When true, ``pql.promote()``
│   │       requires ≥1 ``branch-approved-for-promotion`` endorsement
│   │       by a user other than the caller; rejects with 412
│   │       otherwise.  Promote button greys out + shows "Needs ≥1
│   │       peer endorsement" hint when gate is on and unsatisfied.
│   │       77.3.A: workspaces column + endorsement type +
│   │       /api/branches/.../promote gate (412).
│   │       77.3.B: branch_detail.html tab strip + gate-state UI.
│   │
│   ├── Phase 77.2 — Models                                          ✅ done (2026-05-15)
│   │       Registered-model detail (``/models/{full_name}``) gains
│   │       5 social tabs: Discussion / Reviews / Endorsements /
│   │       Followers / README.  ``#model:cat.sch.name`` citation
│   │       resolves to the detail URL.  Polymorphic backend reused
│   │       as-is — the model kind joins ``table`` + ``branch`` in
│   │       ``_kind_dispatch.parse_ref``.  Issues + full Stars stay
│   │       queued: Issues land in 77.7, polymorphic follow/star in
│   │       77.8.
│   │       77.2.1: polymorphic UNIQUE
│   │       ``(workspace_id, social_target_id, author_user_id)`` on
│   │       ``data_product_reviews`` + polymorphic review handlers
│   │       (list/upsert/delete) + ``model.supports_reviews=True``.
│   │
│   ├── Phase 77.2.1 — Polymorphic reviews enable                     ✅ done (2026-05-15)
│   │       Alembic migration ``a8d0f2g4i6k8`` adds the kind-
│   │       agnostic UNIQUE so polymorphic upsert is idempotent
│   │       (legacy ``(ws, data_product_id, user)`` UNIQUE doesn't
│   │       apply when ``data_product_id`` is NULL).  Three new
│   │       polymorphic handlers in ``_polymorphic_handlers.py``
│   │       + dispatcher switch in ``social_routes/reviews.py``.
│   │       Registry flag flipped → Reviews tab now renders on
│   │       model.html with the inline ``modelReviews`` Alpine
│   │       factory.  Tables + branches stay reviews-off (still
│   │       ``supports_reviews=False`` in the registry).
│   │
│   ├── Phase 77.4 — Runs                                            ✅ done (2026-05-15)
│   │       Agent-run pages gain a 5th top-tab "Social" with
│   │       three sub-tabs (Discussion / Endorsements / Followers).
│   │       Reviews / README hidden via registry flags (runs are
│   │       transient outcomes, not curated artefacts).  Stars
│   │       stay off until 77.8; Issues stay off until 77.7
│   │       decides whether the issue-against-run use-case is
│   │       worth the surface.  ``#run:<uuid>`` citation pattern
│   │       (36-char UUID) renders to ``/runs/<uuid>`` anchor.
│   │       Endorsement vocabulary reuses the four DP-flavoured
│   │       types so humans can flag quality signals on individual
│   │       agent runs.  18 new pytest cases (registry + URL
│   │       builder + audit prefix + citation + parse_ref +
│   │       polymorphic comment/endorsement round-trips + HTML
│   │       social tab + sub-tabs + factory exposure + partials).
│   │
│   ├── Phase 77.5 — Schemas + Catalogs                              ✅ done (2026-05-15)
│   │       ``/catalogs/{cat}`` and ``/catalogs/{cat}/schemas/{sch}``
│   │       gain the polymorphic social surface.  Four sub-commits:
│   │       * 77.5.A — registry registers ``kind='schema'`` +
│   │         ``kind='catalog'`` (4 social tabs each: Discussion
│   │         + Endorsements + Followers + README; stars on,
│   │         reviews + issues off).  ``#schema:cat.sch`` and
│   │         ``#catalog:name`` citation regex + pass-through
│   │         resolvers.  ``_POLYMORPHIC_KINDS`` extended +
│   │         ``parse_ref`` validates ``cat.sch`` for schemas and
│   │         a bare identifier for catalogs.  Workspace
│   │         resolver gets a factored-out
│   │         ``_workspace_for_catalog`` probe so schemas +
│   │         catalogs share the lookup.
│   │       * 77.5.B — ``schemas.html`` restructured: existing
│   │         5 cards (Metadata / Schemas list / Tags /
│   │         Permissions / Properties) wrapped into an
│   │         Overview tab; 4 social tabs added with
│   │         ``socialTabs({kind:"catalog", ref:catalog_name})``.
│   │         Header star button switched to the server-backed
│   │         ``pqlStarToggle({kind, ref})`` shape.  Inline
│   │         ``catalogDiscussion`` + ``catalogReadme`` x-data
│   │         factories.
│   │       * 77.5.C — ``tables.html`` restructured: existing
│   │         schema-detail cards (Metadata + dbt registration
│   │         + ML registration + Tables list + Tags +
│   │         Permissions + Properties) wrapped into an Overview
│   │         tab; 4 social tabs added with
│   │         ``socialTabs({kind:"schema", ref:"cat.sch"})``.
│   │         Inline ``schemaDiscussion`` + ``schemaReadme``
│   │         x-data factories.
│   │       * 77.5.D — 27 new pytest cases (19 kind/registry +
│   │         8 HTML smoke).  Zero schema work — the
│   │         ``social_targets.entity_kind`` CHECK already
│   │         permitted both kinds since Phase 77.0.
│   │

│   ├── Phase 77.6 — Notebooks + Saved Queries                       ✅ done (2026-05-15)
│   │       Per-notebook + per-saved-query social tabs.  New
│   │       ``notebooks.id UUID`` column (locked decision #8 —
│   │       stable across path renames).
│   │       ``#notebook:{uuid}`` + ``#query:{slug}`` citations.
│   │
│   │       Four sub-commits:
│   │       * 77.6.A — alembic ``f3h5j7l9n1p3`` creates the
│   │         ``notebooks`` table (36-char UUID PK, workspace
│   │         + path UNIQUE).  Backfills every distinct
│   │         ``(workspace_id, file_path)`` tuple across
│   │         ``notebook_outputs`` + ``notebook_cell_runs`` +
│   │         ``notebook_cell_run_sources`` (the latter two are
│   │         path-keyed without a workspace column, coalesce
│   │         to ``workspace_id=1``).
│   │       * 77.6.B — registry registers ``kind='notebook'`` +
│   │         ``kind='saved_query'`` (4 social tabs each; stars
│   │         on, reviews + issues off).  Adds
│   │         ``#notebook:<uuid>`` (36-char UUID) +
│   │         ``#query:slug`` citation regex with pass-through
│   │         resolvers.  ``_POLYMORPHIC_KINDS`` + ``parse_ref``
│   │         extended.
│   │       * 77.6.C — ``_get_or_create_notebook_uuid`` helper
│   │         + new ``GET /notebooks/uuid/{uuid}`` alias route
│   │         that resolves the UUID back to the path-based
│   │         render.  Existing ``/notebooks/edit/{path}`` now
│   │         threads ``notebook_uuid`` into the template.
│   │         ``notebook_editor.html`` gains a Social toolbar
│   │         button + Bootstrap ``offcanvas-end`` side-drawer
│   │         (full tab strip would crowd the editor; side-
│   │         drawer was the locked decision in the plan).  4
│   │         tabs inside driven by
│   │         ``socialTabs({kind:"notebook", ref:uuid})``.
│   │       * 77.6.D — ``saved_audit_query_detail.html`` full
│   │         tab strip: existing SQL + result cards wrapped
│   │         into an Overview tab, 4 social tabs added with
│   │         ``socialTabs({kind:"saved_query", ref:slug})``.
│   │         Header gains a server-backed star button.
│   │       * 77.6.E — 17 new pytest cases (schema + registry +
│   │         citation + dispatch + round-trip + DOM smoke).
│   │

│   ├── Phase 77.7 — Issues (the GitHub-Issues entity)               ✅ done (2026-05-15)
│   │       Separate ``issues`` entity with state / assignee /
│   │       labels_json / milestone_id / closed_reason.  Threaded
│   │       comments under each issue reuse the polymorphic
│   │       comments table; an issue is itself a
│   │       ``social_target``-able entity (full self-similarity).
│   │       Existing Discussions ``category`` enum +
│   │       ``accept_answer`` untouched.
│   │
│   │       Six sub-commits in one autonomous session:
│   │       * 77.7.A — alembic ``e2g4i6k8m0o2`` creating
│   │         ``issues`` + ``issue_labels`` + ``issue_milestones``
│   │         (3 ORM models, two CHECK constraints locking
│   │         state + close-reason vocab, three indexes on
│   │         ``issues`` for the workspace+state / parent /
│   │         assignee lookup axes).
│   │       * 77.7.B — registry registration for ``kind='issue'``
│   │         (label "Issue", url ``/issues/{id}``, three social
│   │         tabs Discussion+Endorsements+Followers, stars
│   │         on, issues off — no recursion); flipped
│   │         ``supports_issues=True`` on dp/table/model/branch.
│   │         Added ``#issue:\d+`` citation regex + render.
│   │         Added ``EVENT_TYPE_ISSUE_OPENED`` and
│   │         ``EVENT_TYPE_ISSUE_STATE_CHANGED`` governance
│   │         events.  Built ``social_routes/issues.py`` with
│   │         eight endpoint families: open + list (parent-
│   │         scoped + global) + GET + PATCH + close + reopen
│   │         + labels CRUD + milestones CRUD.  Issue create
│   │         uses a three-step pattern (anchor placeholder
│   │         ref → insert issue → rewrite anchor ref to
│   │         ``str(issue.id)``) so the social_target row is
│   │         consistent on commit.
│   │       * 77.7.C — ``/issues`` HTML index + ``/issues/{id}``
│   │         detail page with two-column layout (left: title
│   │         + body_md + 3 social tabs; right: state controls
│   │         + assignee + labels + milestone + parent badge +
│   │         star button via the server-backed pqlStarToggle
│   │         from 77.8.E).
│   │       * 77.7.D — kind-agnostic Issues tab partial
│   │         wired into table.html, model.html,
│   │         branch_detail.html, and data_product.html.
│   │         DP page wraps the partial in a tiny x-data
│   │         that surfaces kind+ref since data_product.html
│   │         pre-dates the socialTabs factory.
│   │       * 77.7.E — 31 new pytest cases (schema + routes +
│   │         DOM smoke) plus issue helper extraction
│   │         (``_issue_helpers.py`` + ``_issue_taxonomy.py``)
│   │         to stay under the file-size budget after adding
│   │         ``bare-http-ok:`` markers on every raise.  Two
│   │         pre-existing assertions in 77.1 + 77.2 flipped
│   │         to match the new ``supports_issues=True`` reality.
│   │       * 77.7.F — close-out (this entry + CHANGELOG).
│   │       Comment-reactions on issue comments stay 501 by
│   │       design — unlock lands in 77.11.
│   │

│   ├── Phase 77.8 — Stars + polymorphic Follow + Reactions          ✅ done (2026-05-15)
│   │       Three migrations + the polymorphic backend that flips
│   │       Star / Follow / Reaction from 501 to functional across
│   │       every registered entity kind.  77.8.A added the new
│   │       ``social_stars`` polymorphic bookmark table; 77.8.B
│   │       added the sibling ``social_follows`` table (sidesteps
│   │       the SQLite PK-swap difficulty on ``data_product_follows``
│   │       — 77.0.G's docstring already flagged this path);
│   │       77.8.C added a polymorphic UNIQUE on
│   │       ``data_product_reactions(social_target_id, user_id,
│   │       emoji)`` so polymorphic upsert is idempotent.  77.8.D
│   │       shipped ``stars_routes.py`` + flipped the polymorphic
│   │       follow/reaction handlers to use the new tables (DP
│   │       follow + DP reaction routes stay bit-identical via the
│   │       legacy ``data_product_follows`` / DP-id PK path).
│   │       77.8.E rewrote ``pqlStarToggle`` to be server-backed
│   │       with localStorage fallback for kinds not yet registered
│   │       (catalog + schema land in 77.5); model.html +
│   │       branch_detail.html + run_view.html headers gained
│   │       visible star buttons.  The ``data_product_readmes`` →
│   │       ``entity_readmes`` table rename is deferred to Phase
│   │       77.11 alongside the rename of follows + reactions.
│   │       18 new pytest cases across 2 new test files + 2
│   │       existing 501-gated tests flipped to assert functional
│   │       behaviour.  Full Phase-77 suite at 109 passing.
│   │
│   ├── Phase 77.9 — Cross-entity feed                               ✅ done (2026-05-15)
│   │       The activity feed lists comments + reviews across
│   │       every polymorphic entity kind (not just data
│   │       products).  ``_row_from_comment`` + ``_row_from_review``
│   │       JOIN the ``social_targets`` anchor and build the
│   │       ``source_url`` through ``entity_registry.url_for`` so
│   │       links land on the right detail page regardless of
│   │       kind.  ``GET /api/feed`` gains an optional ``?kind=X``
│   │       narrow.  ``feed.html`` carries a kind-pill row above
│   │       the existing filter chips.  Full-body FTS migration is
│   │       deferred to 77.11 (the visible win was the cross-entity
│   │       feed; FTS body extension is a separate plumbing job).
│   │       7 new pytest cases.
│   │
│   ├── Phase 77.9.X — full-body FTS                                  ⏳ deferred to 77.11
│   │       ``/feed`` becomes entity-agnostic with a kind-pill
│   │       filter row.  ``audit_search`` FTS indexes full
│   │       ``body_md`` (not just 140-char preview) across every
│   │       entity kind.
│   │
│   ├── Phase 77.10 — Workspace-as-Organization landing page         ✅ done (2026-05-15)
│   │       GitHub-org-style landing page for every workspace at
│   │       ``/workspaces/{slug}``.  Alembic ``g4i6k8m0o2q4``
│   │       creates ``workspace_pinned_entities`` (composite PK
│   │       on workspace + social_target, ordered index).
│   │       Registers ``kind='workspace'`` (4 tabs Discussion +
│   │       README + members + activity; stars + endorsements +
│   │       issues all off).  New ``workspaces_routes.py``
│   │       exposes 5 routes: HTML landing + pin CRUD + activity
│   │       feed.  Pin writes admin-only; reads member-only.
│   │       9 new pytest cases (schema, registry, HTML render,
│   │       pin CRUD round-trip, 409 on duplicate, 403 on
│   │       non-admin, activity scope, reorder).
│   │

│   │       ``/workspaces/{slug}`` is the workspace's GitHub-org-
│   │       style landing page.  ``workspace_pinned_entities``
│   │       table + 3 rows of pinned cards (DPs / tables /
│   │       models) + workspace-scoped activity feed + workspace
│   │       README (entity_readmes with kind='workspace').
│   │
│   └── Phase 77.11 — Polish + announce                              ✅ done (2026-05-15)
│           Phase 77 close-out doc at ``docs/phase-77.md``.  The
│           heavy consolidation work was deliberately deferred at
│           close-out and landed in Phase 78 polish (below).
│
├── Phase 78 — Polish bundle                              ✅ done 2026-05-16
│       Six items deferred from the Phase-77 close-out, landed
│       in one autonomous session as eight self-contained
│       commits + four alembic migrations:
│       1. ``fanout_dataproduct_event`` wrapper deletion (the
│          legacy DP-scoped helper had zero active call-sites;
│          three test references rewritten to call
│          ``fanout_event`` directly).
│       2. Comment-reaction polymorphism unlock — removed the
│          ``_require_dp_kind_for_comment_reactions`` guard;
│          three new polymorphic handlers in
│          ``_polymorphic_handlers.py`` cover the non-DP path.
│       3. ``model.html`` social-tab inline blocks extracted
│          into per-page partials following the existing
│          ``pages/_partials/model/`` pattern; ``data_product.html``
│          stale 77.11 comment cleaned up.
│       4. ``audit_search`` gets a new ``entity_kind`` column +
│          full-body comment indexing.  ``/api/audit/search``
│          accepts ``?kind=X``.  Migration ``h5j7l9n1p3r5``.
│       5. ``data_product_follows`` consolidated into
│          ``social_follows`` (migration ``i6k8m0o2q4s6``).
│       6. ``data_product_readmes`` renamed to ``entity_readmes``
│          + legacy DP-id column dropped (migration
│          ``j7l9n1p3r5t7``).
│       7. ``data_product_reactions`` consolidated into
│          ``social_reactions`` via the sibling-table pattern,
│          and legacy ``uq_dp_review_one_per_user`` UNIQUE
│          dropped (migration ``k8m0o2q4s6u8``).
│       8. Badges: documented that the existing five thresholds
│          were already cross-kind; added three new per-kind
│          badges (``commenter_table_50plus``,
│          ``endorser_model_20plus``, ``issue_resolver_10plus``).
│       2724 pytest pass / 0 fail; pyright budget stays at
│       609/623 across the entire bundle.
│
├── Phase 79 — Code-quality + modularisation bundle      ✅ done 2026-05-15
│       Audit-grounded refactor sweep.  The codebase came in
│       healthier than the brief assumed (100% function docstring
│       coverage, ruff clean, 18-entry file-size allowlist all
│       justified, no grab-bag files); the bundle focused on the
│       three problems that *were* real.  Eight self-contained
│       commits, zero migrations, behaviour-equivalent only:
│       1. Pydoclint baseline closed — five ORM ``Attributes:``
│          sections + three indirect-raise ``# noqa: DOC502``
│          markers.  13 warnings → 0 violations.
│       2. ``notebooks_routes.py`` (pre-existing 904-LOC CI gate
│          breach) split into ``api/notebooks_routes/`` subpackage
│          per the Phase-26 pattern; six modules, each under 300
│          LOC.
│       3. PQL engine typing shims — new
│          ``ArrowField`` / ``ArrowSchema`` / ``ArrowArray`` /
│          ``ArrowTable`` / ``DuckdbCursor`` / ``DeltaField`` /
│          ``DeltaSchema`` Protocols in ``pql/_types.py``;
│          ``_autoload.py`` + ``_merge.py`` cast at the
│          pyarrow / duckdb / deltalake boundaries.  Pyright
│          budget 609 → 496 (-113).
│       4. Shared ``agent_payload`` helper extracted from four
│          duplicating sites (two ``_agent_payload`` helpers + two
│          inline comprehensions).  Bigger envelopes
│          (``_serialise_comment`` etc.) deliberately stay
│          separate — DP vs polymorphic JSON shapes are
│          load-bearing for back-compat.
│       5. Phase-77 test rename sweep — all 27 ``test_phase77_*``
│          files migrated to topic-named homes (``test_social_target``,
│          ``test_polymorphic_handlers``, ``test_issues_routes``,
│          etc.).  Pure ``git mv``.
│       6. Stale "deferred to Phase 77.11" comments cleaned up
│          across ``_polymorphic_handlers.py`` / ``comments.py`` /
│          ``readme.py``.
│       Explicit non-goal: no alembic squash.  The 90-migration
│       chain is cheap at runtime and Phase 77/78 carry
│       irreversible data-movements whose squash would lose
│       downgrade semantics; revisit after first prod schema
│       stability window.
│       Final state: 2724 pytest pass / 0 fail / 7 skip;
│       pyright 496/623; pydoclint zero violations; file-size
│       gate clean.
│
├── Phases 82–85 — Strategic axes (post-81 horizon)         ✅ done 2026-05-17
│   │
│   │   Articulated 2026-05-16.  Three pillars frame the next horizon:
│   │   (1) social integration with DPs = "GitHub feeling" for data
│   │   products, (2) agentic platform access + strong external API,
│   │   (3) easy consumption AND easy authoring of DPs for non-
│   │   technical users.  The phases below decompose the pillars
│   │   into shippable increments; ordering optimised for compounding
│   │   value (ingest first → everything else has data to chew on).
│   │
│   │   Memory anchor:
│   │   `~/.claude/projects/-home-flo-git-PointlesSQL/memory/project_phase82_strategic_axes.md`.
│   │
│   ├── Phase 82 — Ingest UI (critical path)               ✅ done 2026-05-16
│   │   │
│   │   │   Closed in one autonomous session post the "go voll autnom"
│   │   │   green light.  Six commits (82.0 through 82.5), one Alembic
│   │   │   migration (`ingest_sources`), seven first-party connector
│   │   │   kinds wired end-to-end (file_upload, s3, http, postgres,
│   │   │   mysql, sqlite, parquet_glob).  Pyright stays at 498 (no
│   │   │   regression); 60 new pytest cases (57 pass + 3 properly
│   │   │   gated on live-DB env vars).
│   │   │
│   │   │   Picked: all 7 connector kinds in v1 + plaintext + form-
│   │   │   masking credentials (mirrors the audit-sink pattern).
│   │   │   Encryption-at-rest via `system_keys` and the generic
│   │   │   Connector SDK explicitly deferred (audit `phase82` memory
│   │   │   for rationale).
│   │   │
│   │   ├── 82.0 — Foundation: `IngestSource` ORM + Alembic
│   │   │     `m0o2q4s6u8w0`, `pointlessql/services/ingest/`
│   │   │     package (connectors / probe / pull / executor),
│   │   │     `"ingest_pull"` job kind registered with the
│   │   │     Phase-8 scheduler.  Per-kind connector unit tests.
│   │   ├── 82.1 — Probe + Create form: `/ingest/sources/new`
│   │   │     with kind selector + per-kind config block +
│   │   │     `POST /api/ingest/probe` dry-run.  Source CRUD
│   │   │     (`/api/ingest/sources`) with `"***"` secret redaction
│   │   │     on GET and the round-trip-keeps-original rule on PATCH.
│   │   │     Primary rail gains an "Ingest" entry under DATA.
│   │   ├── 82.2 — Table-picker + mappings: `GET /api/ingest/
│   │   │     sources/{id}/tables` probes the source's catalog
│   │   │     (single-row short-circuit for file-based connectors,
│   │   │     `information_schema.tables` / `sqlite_master` for SQL).
│   │   │     `POST /api/ingest/sources/{id}/mappings` persists the
│   │   │     validated per-table pull configurations.
│   │   ├── 82.3 — Pull executor + fanout: `run_pull` carries the
│   │   │     full lifecycle (load source → DuckDB read → PQL write
│   │   │     → stats + fanout) and is reused by the scheduler
│   │   │     executor AND the manual `POST /api/ingest/sources/{id}/
│   │   │     pulls` route.  `PUT /api/ingest/sources/{id}/schedule`
│   │   │     creates / updates / clears the underlying `Job` row.
│   │   │     Pull lifecycle emits `pointlessql.ingest.pulled` /
│   │   │     `.failed` so `/feed` picks them up automatically.
│   │   ├── 82.4 — End-to-end connector coverage: one fixture-driven
│   │   │     test per kind.  File / Parquet / HTTP / SQLite run in
│   │   │     CI; S3 (moto) / live Postgres / live MySQL gate on
│   │   │     env vars.  PullError envelope verified for the bogus-
│   │   │     host failure path.
│   │   └── 82.5 — Health monitor + DP Health-band:
│   │         `/admin/sources` table (admin-only) with per-source
│   │         7-day rollup (status pill, errors, rows, schedule);
│   │         drilldown returns the last 30 JobRuns + per-day
│   │         tallies.  DP detail pages render an inline ingest
│   │         band when one or more sources feed
│   │         `<catalog>.<schema>`, color-coded by last pull
│   │         outcome.
│   │
│   ├── Phase 83 — Saved Views + Visual Query Builder      ✅ done 2026-05-17
│   │   │
│   │   │   Non-tech consumption layer for DPs landed in two
│   │   │   commits.  83.1 ships a new ``saved_views`` table
│   │   │   (alembic ``n1p3r5t7v9x1``) + service + REST + HTML
│   │   │   (list / new / detail / embed pages) so an analyst
│   │   │   saves a parameterised SELECT and a consumer runs it
│   │   │   read-only via ``/views/{slug}``.  83.2 adds a
│   │   │   Grafana-style "Builder" toggle to the SQL editor:
│   │   │   sqlglot-backed forward render + best-effort parse-
│   │   │   back, gracefully degrading on unsupported shapes.
│   │   │   83.3 (embed iframe) ships as part of 83.1's
│   │   │   ``/views/{slug}/embed`` page.  83.4 (Excel grid)
│   │   │   stays explicitly deferred.  34 new pytest cases.
│   │   │
│   │   ├── 83.1 — Saved Views: workspace-public, owner-pinned
│   │   │     ``saved_views`` table + ``${name}`` → ``?`` rewrite
│   │   │     with per-type coercion + DuckDB positional binds.
│   │   │     CRUD + run + list/new/detail/embed pages.
│   │   ├── 83.2 — Visual Query Builder toggle: per-table column
│   │   │     probe + sqlglot-backed forward/back render via
│   │   │     ``api/sql/builder/{operators,columns,build,parse}``.
│   │   │     Alpine mixin on the SQL editor.
│   │   ├── 83.3 — Saved-View embed: minimal-chrome ``/views/
│   │   │     {slug}/embed`` page shipped inside the 83.1 commit.
│   │   └── 83.4 — Excel-grid mode: still deferred per plan.
│   │
│   ├── Phase 84 — DP GitHub-feeling polish                ✅ done 2026-05-17
│   │   │
│   │   │   Bundled into one commit covering all seven sub-axes
│   │   │   on the DP detail page.  One alembic migration
│   │   │   (``o2q4s6u8w0y2_dp_releases``) + three new JSON routes
│   │   │   + one Atom feed.  The DP overview gains six hero
│   │   │   cards (Health band, README, Consume, Schema-at-a-glance,
│   │   │   Releases, Heatmap) plus a Forks list.  6 new pytest
│   │   │   cases.  Also fixes a Phase-82.5 bug where the
│   │   │   ingest-status band read ``product.catalog_name``
│   │   │   (ORM key) instead of ``product.catalog`` (dict key).
│   │   │
│   │   ├── 84.1 — README rendered as a hero card at the top of
│   │   │     the Overview tab, eager-loaded on page open.
│   │   ├── 84.2 — Release stream: ``data_product_releases`` table
│   │   │     + loader hook emits a row on every version / hash
│   │   │     change.  ``GET /releases`` JSON + ``/releases.atom``
│   │   │     feed.  Inline last-5 list on Overview.
│   │   ├── 84.3 — Consume hero: three-tab (PQL / SQL / Python)
│   │   │     copy-paste card with auto-derived FQN from the
│   │   │     first contract table + "Open in notebook" action.
│   │   ├── 84.4 — Health hero band: derived computed property
│   │   │     ``healthBand`` collapses freshness_30d_pct + last
│   │   │     rollback verdict + SLA into a single colour-coded
│   │   │     status block at the top of Overview.
│   │   ├── 84.5 — Schema-at-a-glance: first 10 columns of the
│   │   │     primary table inline (name + type + nullable) with
│   │   │     a "see all" link that activates the Contract tab.
│   │   ├── 84.6 — Contributor heatmap: 12-month GitHub-style
│   │   │     calendar reading from ``AuditLog`` rows whose
│   │   │     ``target = "dp:<catalog>.<schema>"``.  Pure Python
│   │   │     aggregation (no new tables).
│   │   └── 84.7 — Fork ↔ Delta-Branch cross-link: ``GET /forks``
│   │         scans workspace-local ``BranchAuditLog`` for branches
│   │         with ``parent_schema_fqn = "<catalog>.<schema>"`` and
│   │         renders each as a row coloured by last action.
│   │
│   └── Phase 85 — Dataflow Canvas spike                   ✅ done 2026-05-17
│       │
│       │   Bounded prototype + honest decision-gate writeup.
│       │   Closed in one commit.  Six supported node kinds (Read
│       │   DP, Filter, Join, Group-By, Run Model, Write DP) with a
│       │   pure-function compiler + ``/canvas`` HTML editor +
│       │   ``POST /api/canvas/compile`` route.  10 new pytest cases.
│       │
│       │   85.2 decision gate (this session's verdict): **NO** —
│       │   do not commit to a React Flow build-out.
│       │
│       │   The prototype was shipped as a **list-of-rows editor**
│       │   (Alpine + Bootstrap) instead of the planned React Flow
│       │   2D canvas.  Rationale:
│       │
│       │   * **Coherence (✅)**: list shape maps 1:1 to PQL
│       │     primitives.  Top-to-bottom reading order = pipeline
│       │     execution order = ``code.sql()`` line order.  The
│       │     compiler is 130 LOC of pure-function rendering.
│       │     The "Bootstrap-only" frontend rule survives intact.
│       │   * **Round-trip (~)**: forward (canvas → PQL) works
│       │     end-to-end.  Reverse (PQL → canvas) was not
│       │     implemented; sqlglot already parses arbitrary SELECT
│       │     for the Phase 83.2 builder, so a similar effort
│       │     would handle linear pipelines if needed.
│       │   * **Visual scaling (~)**: 20+ list rows are still
│       │     legible; a true 2D canvas would only out-scale the
│       │     list once **branches / fan-out** become a daily
│       │     need.  Today they are not — every real pipeline
│       │     I've watched land in PointlesSQL is linear.
│       │   * **Sunk-cost honesty (✅)**: building React Flow now
│       │     would tax the agent supervision UX (every new node
│       │     kind = three callsites: canvas, compiler, runtime).
│       │     Better to wait until at least one real user has hit
│       │     the "I needed a branch but the list shape forced me
│       │     into two pipelines" pain.
│       │
│       │   Phase 85.3+ (full React Flow build-out, node registry,
│       │   undo/redo, etc.) therefore moves to the unscheduled
│       │   ``Some-day`` block at the end of this file.  The list
│       │   editor stays as a permanent surface — small enough to
│       │   maintain, useful for the "let me sketch the pipeline
│       │   before I write the code" demo flow.
│       │
│       ├── 85.1 — List-mode prototype (✅): 6 node kinds, server-
│       │     side compiler that rejects non-linear or wrong-tail
│       │     pipelines with structured errors.  State persists in
│       │     localStorage; no DB schema commitment.
│       ├── 85.2 — Decision gate (✅, verdict NO): writeup above.
│       └── 85.3+ — Full canvas build-out: deferred to Some-day.
│
├── Phase 86 — Modularisierungs- & Dedup-Welle             ✅ done 2026-05-16
│       One-wave structural pass on files large enough to push past
│       LLM-comfort and on the cross-cutting helpers that were
│       duplicated file-by-file.  Twelve commits, ~80 files touched,
│       net ~340 lines removed (~6500 inserted vs ~6840 deleted
│       across the wave); every commit boots clean and passes
│       ruff / pyright / pydoclint / alembic gates.  Asset version
│       bumped 0.1.0rc4 → 0.1.0rc5 for the base.html-touching strang.
│
│       ── C.1+C.2 (`d26ed10`) Helper centralisation.  Promotes four
│          per-request helpers into ``api/dependencies.py``:
│          ``get_templates``, ``is_htmx_request``, ``is_htmx_boosted``,
│          ``is_htmx_partial``, ``wants_json``.  Removes 22 identical
│          ``_templates(request)`` defs and 3 hand-rolled HTMX-header
│          checks across the codebase.  25 files touched / 254 LOC
│          deleted vs 191 inserted.
│
│       ── A1-A3 (`e7d0a78`) Frontend mega-templates → page-scoped
│          partials.  ``data_product.html`` 1610 → 206; ``feed.html``
│          1352 → 79; ``notebook_editor.html`` 777 → 225.  20 new
│          partials under ``pages/_partials/{data_product,feed,
│          notebook_editor}/``.  ``x-data`` scopes stay on the mother
│          template; partials inherit them naturally so no Alpine
│          semantics change.  A4 (macro consolidation) trimmed
│          because the 3 candidate patterns are all Alpine-bound,
│          making macros expression-string-only.
│
│       ── B1 (`469e3a4`) ``feed_routes.py`` 1021 → package.
│          ``feed.py`` (482) + ``notifications.py`` (102) +
│          ``muting.py`` (213) + ``_serializers.py`` (256).
│          9 endpoints preserved via facade.
│
│       ── B2 (`fd07577`) ``home_routes.py`` 998 → package.
│          ``summary.py`` (495) + ``search.py`` (487) + ``_helpers.py``
│          (45).  3 endpoints + 3 public helpers preserved via facade
│          (``build_home_summary``, ``score_match``, ``epoch_seconds``).
│
│       ── B3 (`00ce745`) ``jobs_routes.py`` 927 → package.
│          ``crud.py`` (309) + ``runs.py`` (164) + ``papermill.py``
│          (137) + ``pages.py`` (153) + ``_serializers.py`` (170) +
│          ``_access.py`` (108).  14 endpoints + 5 public exports
│          (``JOB_REGISTRY``, ``serialize_job``, ``serialize_run``,
│          ``latest_run_per_job``, ``router``) preserved.
│
│       ── B4 partial (`68dbdf1`) ``main.py`` 1008 → 770.
│          ``_template_filters.py`` (155 LOC; 4 filters + 4 globals +
│          ``register_template_filters``) and ``_template_context.py``
│          (158 LOC; ``install_template_wrapper`` that rebinds
│          ``templates.TemplateResponse`` in place).  Lifespan
│          extraction (~360 LOC) deferred — its 15-local try/finally
│          needs either a dataclass or a class-based manager to land
│          cleanly, bigger than the rest of the wave warrants.
│
│       ── B5 (`7f65aec`) ``alerts_routes.py`` 626 → package.
│          ``crud.py`` (213) + ``destinations.py`` (121) +
│          ``feed_tokens.py`` (66) + ``feeds.py`` (96) + ``pages.py``
│          (115) + ``_helpers.py`` (87).  13 endpoints preserved.
│
│       ── B6 (`c637888`) ``governance_routes.py`` 521 → package.
│          ``profile.py`` (211) + ``catalog.py`` (150) + ``tags.py``
│          (58) + ``permissions.py`` (73) + ``lineage.py`` (32) +
│          ``_helpers.py`` (83).  13 endpoints preserved.
│
│       ── D (`9696608`) Star factory out of base.html.
│          ``window.pqlStarKey`` + ``window.pqlStarToggle`` (121 LOC)
│          → ``frontend/js/star.js``.  ``base.html`` 848 → 726.
│          ``pyproject.toml`` bumped 0.1.0rc4 → 0.1.0rc5 per the
│          asset-version cache-busting contract.  Catalog-visit +
│          table-visit IIFEs in base.html were left in place because
│          they carry Jinja ``active_catalog`` / ``active_table``
│          interpolation.
│
│       ── C.4 (`0f999c3`) Test-fixture cleanup.  Removes 13
│          local ``anonymous_client`` fixture defs that duplicated
│          the conftest's centralised one.  117 LOC deleted;
│          156 tests pass across the touched files.
│
│       ── C.3 + C.5 trimmed.  ``_polymorphic_handlers.py`` (2231) /
│          ``audit/_legacy.py`` (1262) / ``sql/editor.py`` (1127) /
│          ``dbt/routes.py`` (1061) / ``sql/_dispatcher.py`` (1009) /
│          ``config/_settings.py`` (922) each carry hidden coupling
│          (polymorphic dispatch tables, env-prefix conventions,
│          legacy bridges) that would each justify their own sprint;
│          deferred per plan's trim list.  Stale-module audit
│          (``repo_assets``, ``conventions``, ``pointlessql.git``,
│          ``types``) confirmed all four actively imported — but
│          ``repo_assets`` was later proven orphaned in Phase 87.2.
│
├── Phase 87 — Restschuld I: config + repo_assets + audit  ✅ done 2026-05-16
│       First of three follow-up phases to clear the trim list from
│       Phase 86.  Low-risk strands without business-logic change;
│       three commits on branch ``phase-87-…``, net ~−400 LOC
│       (after subtracting the docstring expansion in the splits).
│       All gates green at every commit (ruff/pyright/pydoclint/
│       alembic); pyright count drops 8→6 errors / 539→533 warnings
│       (from the deleted repo_assets/_loader.py ``workspace_repos``
│       callsites — the underlying bug is unchanged).
│
│       ── 87.1 (`1c4d337`) ``config/_settings.py`` 922 LOC → package.
│          Six topical sub-modules under ``config/_settings/``:
│          ``_auth`` (AuthSettings, OIDCSettings, GroupMapping + the
│          group-map parser), ``_storage`` (DatabaseSettings,
│          DeltaSettings), ``_infra`` (ServerSettings + 5 more),
│          ``_audit`` (AuditSettings + 3 more), ``_features``
│          (SQLSettings + 5 more), ``_integrations`` (JupyterSettings
│          + 4 more), plus ``_paths`` holding the shared STARTUP_CWD
│          / PROJECT_ROOT anchors.  ``Settings()`` instantiation
│          probe confirms 23 fields, all path validators honour
│          their startup-CWD anchor.
│
│       ── 87.2 (`f3c7e07`) ``pointlessql/repo_assets/`` deleted.
│          The Phase-51.3 YAML loader for dashboards + saved queries
│          (428 LOC + a 136-LOC test) was never wired into the
│          workspace-repo sync loop or the manual-sync button — half-
│          finished feature that audit flagged in Phase 86 (zero
│          production imports).  Doc table in
│          ``docs/concepts/git-backed-workspaces.md`` also pruned of
│          its two stale rows + the dashboards/saved_queries YAML
│          block.  If repo-canonical dashboards become a real
│          requirement, a future sprint reintroduces against the
│          conventions / data_products pattern.
│
│       ── 87.3 (`6d2ac2d`) ``audit/_legacy.py`` 1262 LOC → 7 modules.
│          Split by behavioural axis: ``_helpers`` (workspace-lens,
│          ISO-8601 parse, audit-of-audit self-tracking; renamed
│          without leading underscores for cross-module reuse),
│          ``_metrics`` (summary / timeseries / anomalies),
│          ``_principal`` (principal-summary), ``_pii`` (admin-only
│          reveal), ``_history`` (paginated query_history walker),
│          ``_cdf`` (CDF subscriptions + events), ``_anomaly_inbox``
│          (inbox + ack CRUD; named anomaly-prefixed to avoid
│          colliding with the existing ``inbox.py`` HTML cockpit
│          page).  ``_legacy.py`` deleted outright — no backwards-
│          compatibility shim because PointlesSQL isn't published
│          yet and the name was never public API.  Combined audit
│          router still exposes the same 23 paths.
│
├── Phase 88 — Restschuld II: SQL/dbt cluster              ✅ done 2026-05-16
│       Three medium-risk strands targeting the 1000-LOC SQL editor
│       + dbt cluster.  Three commits on the same ``phase-87…``
│       branch (the wave continues), pyright count stays at
│       6 / 533 errors / warnings at every commit, all gates green.
│
│       ── 88.1 (`ef837c3`) ``sql/_dispatcher.py`` 1009 LOC → 8-module
│          package: ``_types`` (DispatchContext + ExecutionResult),
│          ``_privilege`` (enforce_select_per_table,
│          enforce_modify_target), ``_agent_run`` (start/finish
│          editor agent runs, emit DDL ops), ``_ast_extract``
│          (sqlglot translators), ``_select`` (kept isolated to
│          break the editor↔dispatcher import cycle), ``_dml``
│          (INSERT/CTAS, UPDATE, DELETE, MERGE branches), ``_ddl``
│          (DROP TABLE, CREATE/DROP SCHEMA branches), ``__init__``
│          (dispatch() facade re-exporting DispatchContext,
│          ExecutionResult, PreparedSQL).  Saved-views import
│          rewired from the old private name to the new sibling
│          module.
│
│       ── 88.2 (`05ea3d2`) ``sql/editor.py`` 1127 LOC → 8-module
│          package: ``_helpers`` (short_sql_hash, run_sql_sync,
│          live_queries, run_sql_export_sync, strip_ansi),
│          ``_execute`` (api_sql_execute + inline EXPLAIN
│          serializer, the 284-LOC main route), ``_batch`` (atomic
│          rollback runner + _rollback_run), ``_cancel`` (interrupt
│          endpoint sharing the helpers' live_queries registry),
│          ``_download`` (CSV/Parquet streamer re-running enforcement),
│          ``_explain`` (cost-gate inspector with governance event),
│          ``_page`` (the Jinja2 ``/sql`` route), ``__init__``
│          (facade mounting 6 routers + helper re-exports).
│
│       ── 88.3 (`517a4b6`) ``dbt/routes.py`` 1061 LOC → 5 sibling
│          modules.  Endpoints stay in ``routes.py`` (~350 LOC, 8
│          handlers); helpers move out: ``_executor`` (factory),
│          ``_lifecycle`` (auto-spawned AgentRun create/finish +
│          result_payload), ``_audit`` (classify_severity,
│          emit_dbt_events, model_relations_from_manifest_path,
│          capture_pre_run_versions, emit_audit_for_run),
│          ``_rollback`` (invoke_pql_rollback + auto_rollback_on_error
│          test-only branch), ``_run_test`` (the 133-LOC shared
│          run/test body + load_manifest_or_404).  Three test
│          modules updated to monkeypatch the new sibling modules
│          instead of the routes module.
│
├── Phase 89 — Restschuld III: endgame                     ✅ done 2026-05-16
│       Two highest-risk strands from the Phase-86 trim list:
│       splitting the largest single Python file in the repo
│       (``_polymorphic_handlers.py`` at 2231 LOC) and extracting
│       the 358-LOC lifespan from ``main.py``.  Three commits on
│       the same ``phase-87…`` branch; pyright stays at 6/533 at
│       every commit.
│
│       ── 89.1 (`d1716ce`) ``social_routes/_polymorphic_handlers.py``
│          2231 LOC → 9-axis sub-package.  Sub-modules:
│          ``_shared`` (constants + 9 cross-axis helpers +
│          4 serialisers), ``_comments`` (3 handlers),
│          ``_endorsements`` (3), ``_followers`` (4),
│          ``_reactions_entity`` (3 + ``validate_emoji_field``),
│          ``_reactions_comment`` (3 + ``load_comment_on_target``),
│          ``_stars`` (4), ``_readme`` (2), ``_reviews`` (3).
│          ``__init__`` re-exports every public handler the 7
│          sibling route modules (``comments.py`` /
│          ``endorsements.py`` / ``follows.py`` / ``reviews.py``
│          / ``reactions.py`` / ``stars.py`` / ``readme.py``)
│          already import from this package.  The old flat
│          ``_polymorphic_handlers.py`` deleted outright (no BC
│          shim).  Leading underscores dropped on every
│          cross-axis helper so pyright stops tripping on
│          ``reportPrivateUsage`` across the new module
│          boundaries.
│
│       ── 89.2 (`76e6941`) ``main.py`` lifespan 358 LOC →
│          ``api/_bootstrap/_lifespan.py``.  ``main.py`` shrinks
│          767 → 374 LOC.  The new module exposes a
│          ``make_lifespan(templates)`` factory that closes over
│          the Jinja2Templates instance built at import time in
│          ``main.py`` so the filters + TemplateResponse wrapper
│          stay where they are.  Side-effect: the teardown's 14×
│          repeated cancel-and-await ritual collapses into one
│          ``_cancel_task`` helper.  External behaviour
│          unchanged — ``app.state`` is built identically and the
│          14 background-task names / 2 subprocess shutdown order
│          are byte-identical.
│
├── Phases 90–92 — Agent-native lakehouse axis (post-Lakebase) ✅ shipped 2026-05-19
│   │
│   │   Articulated 2026-05-19 after a gap-analysis sweep against
│   │   Databricks' May-2026 feature set (AI/BI Genie GA, Lakebase
│   │   GA Feb 2026, ABAC GA Apr 2026, catalog commits May 2026,
│   │   Mosaic AI Vector Search GA).  DBX's pitch — "agents want
│   │   to spin up DBs, branch quickly, persist memory" — directly
│   │   validates the PointlesSQL vision *from the OLTP-Postgres
│   │   side*.  PointlesSQL has the same building blocks
│   │   (``agent_runs``, ``operations``, ``branch_service``,
│   │   audit-stream) but lacks the *naming and API surface* that
│   │   makes them legible as "the agent's persistent memory".
│   │
│   │   Three pillars, ranked by vision-leverage per LOC:
│   │   (1) name + expose the existing memory stack as a primitive,
│   │   (2) wire ``hermes-agent`` into the SQL editor as the
│   │   NL→SQL surface DBX calls "Genie", (3) add Vector Search
│   │   as the third compute primitive next to ``pql.merge`` /
│   │   ``pql.autoload`` so RAG-style retrieval is in-stack.
│   │
│   │   Explicitly NOT pursued (out-of-scope per gap-analysis):
│   │   ABAC policy engine (defer until shoreguard is a standalone
│   │   lib), Lakehouse Monitoring full UI (the
│   │   ``notebooks/agent_drift_monitor.py`` covers 80 %), Model
│   │   Serving (out of mission), Lakeflow Connect / Liquid
│   │   Clustering / DLT-replacement (engine-arms-race that
│   │   PointlesSQL does not win by reimplementing).
│   │
│   ├── Phase 90 — Agent-Memory as first-class primitive       ✅ shipped (local, 2026-05-19)
│   │   │
│   │   │   Smallest diff, largest narrative win.  The
│   │   │   infrastructure is ~80 % already shipped — what's
│   │   │   missing is a single ``pql.memory`` API facade plus a
│   │   │   ``/memory/<agent-id>`` UI page that frames the
│   │   │   existing ``agent_runs`` + ``operations`` + branch
│   │   │   surface as "the agent's persistent memory" instead of
│   │   │   "audit infrastructure".  Directly counters Lakebase's
│   │   │   "persistent memory for AI agents" positioning with
│   │   │   the Delta-first / append-only angle (Lakebase is
│   │   │   Postgres-first; agent writes are dominantly append-
│   │   │   only logs which Delta serves more cheaply).
│   │   │
│   │   │   Shipped 2026-05-19 at ~2510 LOC across 9 sub-strands
│   │   │   (5 facade methods + Alembic migration + 4 routes + 7
│   │   │   templates + JS + walkthrough + concept doc + 62 tests).
│   │   │   Scope grew vs the original 400-LOC sketch because the
│   │   │   user picked "Voll-Scope" — real replay-dispatcher with
│   │   │   policy gate, polymorphic comment integration with
│   │   │   Alembic migration, full Playwright walkthrough.  See
│   │   │   ``docs/concepts/agent-memory.md`` for the conceptual
│   │   │   model and the Lakebase comparison.
│   │   │
│   │   ├── 90.0 — ``pql.memory`` facade + replay-dispatcher  ✅ shipped
│   │   │     [`pointlessql/pql/memory.py`](pointlessql/pql/memory.py)
│   │   │     exposing the five public methods, plus the
│   │   │     [`services/agent_runs/memory/`](pointlessql/services/agent_runs/memory/)
│   │   │     package backing them (recall SELECT, branch-from-run,
│   │   │     replay dispatcher with REPLAYABLE / DATA_UNAVAILABLE /
│   │   │     UNSAFE op classification + STRICT/SKIP_UNSAFE/LENIENT
│   │   │     policy).  Replay-execution scoped to "intent-only"
│   │   │     for Phase 90 — re-records ops against the replay run
│   │   │     with ``_replay_recorded_only: true``, real DuckDB
│   │   │     execution lands with Phase 91 (same plumbing
│   │   │     requirement).  49 unit tests.
│   │   ├── 90.1 — ``/memory/<agent-id>`` UI + comment surface  ✅ shipped
│   │   │     Alembic migration ``p4r6t8v0x2z4`` extends
│   │   │     ``social_targets.entity_kind`` CHECK to accept
│   │   │     ``agent_memory``; new entity-registry spec defines
│   │   │     the discussion/endorsements/followers tab strip.
│   │   │     HTML route + 3 JSON routes
│   │   │     (recall / branch / replay).  ``memory.html`` plus
│   │   │     5 page-scoped partials (header, timeline,
│   │   │     operations, branches, social) and
│   │   │     ``memory_brain.js`` (memoryRecall + memoryDiscussion
│   │   │     Alpine factories + replay-button handler).
│   │   │     ``asset_version`` bumped to 0.1.0rc6.  13 route
│   │   │     tests.  Replayed via
│   │   │     ``docs/e2e-walkthroughs/agent_memory.md``.
│   │   ├── 90.2 — Counter-pitch concept doc                  ✅ shipped
│   │   │     [`docs/concepts/agent-memory.md`](docs/concepts/agent-memory.md)
│   │   │     frames the Delta-first / append-only angle vs
│   │   │     Lakebase's Postgres-first.  Cross-link from
│   │   │     ``agent-supervision.md``, new ``Agent memory`` nav
│   │   │     entry in ``mkdocs.yml`` and concept-index.
│   │
│   ├── Phase 91 — NL→SQL via hermes-agent wiring             ✅ shipped (local, 2026-05-19)
│   │   │
│   │   │   The DBX "Genie" equivalent.  In-process
│   │   │   ``hermes_agent.AIAgent`` wired into the SQL editor
│   │   │   via a JSON-RPC WebSocket; ``hermes-plugin-pointlessql``
│   │   │   tools (``pql_query`` + 3 new chat-focused tools)
│   │   │   stamp every call on the chat session's ``agent_run``
│   │   │   so Phase 90's ``/memory/<agent-id>`` page shows the
│   │   │   full conversation trace.  Non-SELECT SQL never runs
│   │   │   silently — ``pql_propose_sql`` drops a draft into a
│   │   │   "Run / Discard" banner.
│   │   │
│   │   ├── 91.0 — WebSocket chat transport + drawer            ✅ shipped
│   │   │     [`pointlessql/api/sql_chat_ws.py`](pointlessql/api/sql_chat_ws.py)
│   │   │     mounts ``/ws/sql/chat/{editor_session_id}`` with
│   │   │     the notebook-WS JSON-RPC envelope (prompt / cancel
│   │   │     / refine / reset).  Per-turn ``AIAgent`` runs on a
│   │   │     dedicated ThreadPoolExecutor; the streaming
│   │   │     callback bridges through the per-session broker
│   │   │     ([`services/sql_chat/`](pointlessql/services/sql_chat/))
│   │   │     so tokens, tool-phase sentinels, and proposals all
│   │   │     pass through one ordered queue.  Alembic migration
│   │   │     ``q5s7u9w1y3a5`` adds ``editor_chat_sessions`` +
│   │   │     ``chat_proposals``.  Right-side drawer template +
│   │   │     ``chatPanel()`` Alpine factory shipped under
│   │   │     [`frontend/templates/pages/_partials/sql_editor/`](frontend/templates/pages/_partials/sql_editor/)
│   │   │     and [`frontend/js/sql_editor/chat.js`](frontend/js/sql_editor/chat.js).
│   │   │     ``asset_version`` bumped to 0.1.0rc7.
│   │   ├── 91.1 — Tool-set hardening                           ✅ shipped
│   │   │     Three new tools in ``hermes-plugin-pointlessql``:
│   │   │     ``pql_describe_columns_with_stats`` (live PQL→pandas
│   │   │     reduction, 5-min LRU cache, new
│   │   │     [`pointlessql/services/column_stats/`](pointlessql/services/column_stats/)
│   │   │     service + ``GET .../tables/{t}/stats`` route);
│   │   │     ``pql_save_query`` (wraps existing ``POST /api/views``);
│   │   │     ``pql_propose_sql`` (registered only when
│   │   │     ``POINTLESSQL_CHAT_SESSION_ID`` is set).
│   │   │     ``pql_run_select_capped`` was dropped — the
│   │   │     existing ``pql_query`` already caps to 10 000
│   │   │     rows.  Server-side propose endpoint
│   │   │     [`pointlessql/api/sql_chat_routes/_propose.py`](pointlessql/api/sql_chat_routes/_propose.py)
│   │   │     classifies via sqlglot (rejects SELECT/EXPLAIN),
│   │   │     enforces ``X-Agent-Run-Id`` ownership, and
│   │   │     dedupes identical SQL within 60 s.
│   │   ├── 91.2 — Run-it gate + audit-mirroring               ✅ shipped
│   │   │     [`pointlessql/api/sql_chat_routes/_accept.py`](pointlessql/api/sql_chat_routes/_accept.py)
│   │   │     adds ``POST .../proposals/{id}/accept|discard``;
│   │   │     accept returns the chat session's ``agent_run_id``
│   │   │     so the editor's normal Run path stamps
│   │   │     ``X-Agent-Run-Id`` and the DELETE / UPDATE /
│   │   │     CREATE operation lands on the chat run alongside
│   │   │     every tool-call.  Stale proposals (>24 h) auto-
│   │   │     flip to ``expired`` instead of running.  Shoreguard
│   │   │     policy cross-link deferred to a follow-up sprint
│   │   │     (hook point documented in
│   │   │     [`docs/concepts/nl-to-sql.md`](docs/concepts/nl-to-sql.md)).
│   │   ├── 91.3 — Conversational refinement loop              ✅ shipped
│   │   │     ``refine`` WS method templates structured user
│   │   │     prompts for the two canonical failure modes
│   │   │     (``zero_rows``, ``error``) and runs them through
│   │   │     the normal turn pipeline — each refine appends to
│   │   │     the same ``conversation_json`` so the
│   │   │     ``/memory/<agent-id>`` timeline shows the full
│   │   │     refinement trace.  Frontend buttons appear next to
│   │   │     0-row results + error banners.
│   │   ├── 91.4 — Concept doc + walkthrough + nav             ✅ shipped
│   │   │     [`docs/concepts/nl-to-sql.md`](docs/concepts/nl-to-sql.md)
│   │   │     frames the architecture + the DML gate + the
│   │   │     LLM-config env vars.
│   │   │     [`docs/e2e-walkthroughs/sql_chat.md`](docs/e2e-walkthroughs/sql_chat.md)
│   │   │     covers the 6-step Playwright playbook.  Cross-link
│   │   │     from ``agent-supervision.md``, new nav entries
│   │   │     under ``Concepts`` and the "Working with data"
│   │   │     walkthrough cluster.
│   │
│   └── Phase 92 — Vector-Search compute primitive            ✅ shipped (local, 2026-05-19)
│       │
│       │   Third compute primitive next to ``pql.merge`` and
│       │   ``pql.autoload``.  Backed by the DuckDB ``vss``
│       │   extension (HNSW indices) stored side-by-side with
│       │   the Delta table (Delta remains source-of-truth;
│       │   the index is a secondary structure rebuilt on every
│       │   merge via the post-commit hook in
│       │   ``operations._lifecycle``).  Completes the
│       │   "persistent memory for agents" loop: Phase 90 gives
│       │   agents *what to remember*, Phase 91 gives them *how
│       │   to ask*, Phase 92 gives them *how to retrieve
│       │   semantically*.
│       │
│       │   ROADMAP-adjustment (close-out): the originally
│       │   planned hermes-agent ``embed`` tool does not exist
│       │   yet, so the **default embedder inverts** to
│       │   ``sentence-transformers`` (local, zero-config) with
│       │   the ``openai`` SDK as an optional hosted provider
│       │   and a documented :class:`HermesEmbedder` stub
│       │   reserved for when hermes-agent ships an ``embed``
│       │   tool.
│       │
│       ├── 92.0 — ``pql.vector_index`` primitive             ✅ shipped
│       │     [`pointlessql/pql/_vector.py`](pointlessql/pql/_vector.py)
│       │     adds ``PQL.vector_index(table, column, ...)`` +
│       │     ``PQL.vector_search(...)`` next to ``merge`` /
│       │     ``autoload``.  HNSW index file lives at
│       │     ``<table.storage_location>/_vss/<column>.duckdb``;
│       │     persistent HNSW enabled via
│       │     ``hnsw_enable_experimental_persistence = true`` in
│       │     [`_vss_engine.py`](pointlessql/pql/_vss_engine.py).
│       │     New ``OpName.VECTOR_INDEX`` + ``VECTOR_SEARCH``
│       │     extend the ``agent_run_operations.op_name`` CHECK
│       │     (Alembic ``r6t8v0x2z4a6``).  ``VectorIndex`` ORM
│       │     keyed by ``(workspace, catalog, schema, table,
│       │     column)``.
│       ├── 92.1 — Embedder registry + auto-rebuild hook      ✅ shipped
│       │     [`pointlessql/pql/embedders/`](pointlessql/pql/embedders/)
│       │     ships ``SentenceTransformersEmbedder`` (default,
│       │     lazy import; new ``[vector]`` extra),
│       │     ``OpenAIEmbedder`` (optional, ``OPENAI_API_KEY``),
│       │     and a documented ``HermesEmbedder`` stub.
│       │     Sixth post-commit hook
│       │     [`_vector_rebuild.py`](pointlessql/services/agent_runs/operations/_vector_rebuild.py)
│       │     wired into ``operation_context`` re-embeds the
│       │     affected column on every ``merge`` / ``write_table``
│       │     / ``autoload`` / ``update`` / ``delete`` /
│       │     ``branch_promote`` / ``dbt_model`` commit.
│       │     Failure is non-fatal: stamps
│       │     ``vector_indices.last_error`` and continues.
│       ├── 92.2 — REST surface                                ✅ shipped
│       │     [`pointlessql/api/sql/vector_search/`](pointlessql/api/sql/vector_search/)
│       │     mounts ``POST /api/sql/vector_search`` (reuses
│       │     ``enforce_select_per_table``),
│       │     ``POST /api/sql/vector_search/indices`` +
│       │     ``GET`` + ``DELETE …/{id}`` (workspace-admin
│       │     gated for write paths), and
│       │     ``GET /embed/semantic_search/{fqn}`` for the
│       │     iframe share URL.  RFC 9457 envelopes
│       │     (``404 vector-index-missing``,
│       │     ``403 forbidden``).
│       ├── 92.3 — Hermes-plugin tool                          ✅ shipped
│       │     ``hermes_plugin_pointlessql/tools/vector_search.py``
│       │     adds ``pql_vector_search`` (registered
│       │     unconditionally) calling the new
│       │     ``PointlessClient.vector_search()`` HTTP wrapper.
│       │     Closes the RAG loop end-to-end: chat panel agents
│       │     can do semantic retrieval before generating SQL.
│       ├── 92.4 — UI surface on Table-detail                  ✅ shipped
│       │     Conditional ``Semantic search`` tab on
│       │     [`table.html`](frontend/templates/pages/table.html)
│       │     guarded by ``{% if vector_indices %}``.  Alpine
│       │     factory ``semanticSearch()`` in
│       │     [`frontend/js/table/semantic_search.js`](frontend/js/table/semantic_search.js)
│       │     owns column picker + query + result-table state.
│       │     Embed view at
│       │     [`semantic_search_embed.html`](frontend/templates/pages/semantic_search_embed.html)
│       │     mirrors the saved-view embed pattern for share
│       │     URLs.  ``asset_version`` bumped to ``0.1.0rc8``.
│       └── 92.5 — Docs + tests                                ✅ shipped
│             Concept doc
│             [`docs/concepts/vector-search.md`](docs/concepts/vector-search.md)
│             frames the architecture, embedder strategy, and
│             privilege model.  Playbook
│             [`docs/e2e-walkthroughs/vector_search.md`](docs/e2e-walkthroughs/vector_search.md)
│             walks the 8-step loop.  19 new pytest cases
│             covering embedder registry, primitive (create /
│             search / rebuild / dim mismatch), merge-hook,
│             and REST route.  All green; ``alembic check``
│             clean.
│
├── Phase 93 — Notebook-Editor UX quick wins                  ✅ shipped (local, 2026-05-19)
│       Six surgical fixes after the Phase-12.12 editor wire-up
│       brought the toolbar back into rotation and Playwright
│       replays revealed several visual rough edges.  All
│       frontend-only; one ``pyproject.toml`` version bump
│       (``0.1.0rc12`` → ``0.1.0rc13``) busts the asset cache.
│
│       1. **Toolbar title vertical-rendering bug** — flex-child
│          ``.pql-notebook-path`` collapsed buchstabenweise next
│          to 15 sibling pills because ``word-break: break-all``
│          + missing ``min-width: 0``.  Switched to single-line
│          ellipsis with ``:title`` tooltip and gave the toolbar
│          ``flex-wrap`` so overflow goes to a new row instead.
│       2. **Toolbar grouping** — three ``.pql-toolbar-group``
│          clusters: ``[Interrupt · Restart]``,
│          ``[Save · Schedule · Run as job]``,
│          ``[Jobs · Variables]``.  Inlined the floating
│          ``⌘S`` kbd hint into the Save button.
│       3. **Native prompt/confirm → Bootstrap modals** — new
│          ``notebookDialogs()`` mixin spread into
│          ``notebookWorkspace()``; new partial
│          ``pages/_partials/notebooks_workspace/notebook_modals.html``
│          with create/rename + delete modals.  Client-side
│          validation: ``.py`` suffix, no leading ``/``, no
│          ``..`` segments, no double-slashes.  Modal toggle via
│          ``:class="{ 'show d-block': flag }"`` (Alpine 3.14 +
│          ``.modal`` quirk — memory
│          ``feedback_bootstrap_modal_x_show``).
│          *Close-out fix:* ``openCreate`` / ``openRename`` /
│          ``openDeleteDialog`` mutate the dialog state fields
│          individually instead of replacing the dialog object as
│          a whole.  Replacing a nested reactive object detaches
│          Alpine bindings that captured deps on the old proxy —
│          the ``:disabled`` binding on the submit button stopped
│          re-evaluating in particular.  Caught during live
│          browser verification, fixed at source.
│       4. **Output iframe dark-theme fix** —
│          [`output_renderer.js`](frontend/js/notebook/output_renderer.js)
│          reads ``document.documentElement.dataset.bsTheme``
│          and bakes matching ``color`` / ``border`` / ``th-bg``
│          into the srcdoc.  Wrapper CSS
│          ``.pql-notebook-output__iframe`` flipped from
│          ``background: white`` to ``transparent`` with
│          ``color-scheme: light dark``.
│       5. **Workspace "New notebook…" CTA** — dropped the
│          inline ``font-size: 0.75rem`` + ``btn-sm`` shrink;
│          now a normal-size ``btn-primary`` with
│          ``bi-plus-lg`` icon, refresh moved to ``ms-auto``.
│       6. **Sidebar ``.ipynb`` chip detox** —
│          [`workspace_sidebar.js`](frontend/js/components/sidebars/workspace_sidebar.js)
│          ``formatBadge()`` now returns
│          ``bg-info-subtle text-info-emphasis`` for ``.py`` and
│          ``bg-secondary-subtle text-secondary-emphasis`` for
│          ``.ipynb`` — no more orange warning-looking pill.
│
├── Phase 94 — Notebook-Editor UX polish                       ✅ shipped (local, 2026-05-19)
│       Follow-up polish bundle to Phase 93.  Adds the visual
│       structure Jupyter users expect (Out[N] frame, run-duration
│       display) without touching the backend.  Wall-clock duration
│       is captured client-side via ``performance.now()`` between
│       the ``execute_input`` and ``execute_reply`` frames —
│       persistent duration after reload would need backend
│       timestamp propagation through the iopub WS (deferred to a
│       later phase).  Asset version bumped to ``0.1.0rc14``.
│
│       1. **Cell-header hash to tooltip** — the 8-char FNV
│          ``content_hash`` slice next to ``[N]`` is now a tooltip
│          on the ``[N]`` element itself; the separate visible
│          span is gone.
│       2. **Out[N] output frame** — new
│          ``.pql-notebook-cell__output-zone`` wrapper with a small
│          ``Out[N]:`` label header above the output container.
│          The output zone gets a top border only when the cell has
│          actually executed (``exec_count != null``), keeping
│          never-run cells visually quiet.
│       3. **Run duration display** — new ``runDurationFor(cell)``
│          helper in [`notebook_editor.js`](frontend/js/notebook/notebook_editor.js)
│          formats the client-side wall-clock ms into ``0.2s`` /
│          ``1.4s`` / ``2m 3s``.  Captured in
│          [`kernel_execution.js`](frontend/js/notebook/kernel_execution.js)
│          on ``execute_input`` (stamp) → ``execute_reply``
│          (delta).  Shown next to ``[N]`` in the cell header.
│       4. **Clear-output per cell** — new ``_clearOutput(cell)``
│          method in [`markdown_output.js`](frontend/js/notebook/markdown_output.js)
│          drops the live-output buffer + duration for one cell
│          without re-running it.  Triggered by the small ``×`` in
│          the new Out[N] label header.
│       5. **Workspace action-cluster spacing** — filename span
│          now has ``flex-grow-1`` + ``min-width: 0`` + ``:title``
│          so long names ellipsis-truncate instead of crowding the
│          Edit / Schedule / ⋯ buttons.
│
├── Phases 95–105 — Notebook v3 (DBX-parity + agent-native lift)  🟦 backbone shipped 2026-05-20
│       Multi-phase axis to bring notebooks to Databricks-parity on
│       the basics (cell-level UX, revision history, widget cells,
│       permissions, dashboard view) and surpass on the
│       agent-native + provenance axes where shoreguard, Phase-90
│       memory and the delta-branching idea give us infrastructure
│       DBX doesn't have.  Notebooks are already polymorphic-social
│       at notebook-level since Phase 77.6; the natural next step
│       is cell-level granularity.  Phase scoping is intentionally
│       narrow — exact specs land in dedicated plan files before
│       each sprint.  Order respects dependencies (cell-level
│       social + revision history land before reviewer-per-cell +
│       replay mode).
│
│   ├── Phase 95 — Cell-level social                              ✅ shipped (local, 2026-05-19)
│   │   │
│   │   │   Extends the Phase-77.6 polymorphic-social schema down to
│   │   │   single cells.  A user (or a Phase-101 reviewer agent) can
│   │   │   now drop a comment on the specific cell that broke, react
│   │   │   to the chart in cell 7, follow that one cell, and tag it
│   │   │   with ``#etl`` / ``#draft`` / ``#prod`` for light
│   │   │   categorisation.  Closest analog: Google Colab
│   │   │   cell-comments (DBX has no real cell-social surface).
│   │   │
│   │   │   The hard part — stable cell identity that survives source
│   │   │   edits while keeping the ``.py`` file IDE-agnostic — gets
│   │   │   solved by a new ``notebook_cells`` mapping table + a
│   │   │   three-pass reconciler at save time (exact-hash, then
│   │   │   similarity-gated ordinal fallback, then fresh UUID).
│   │   │   See [`docs/concepts/cell-level-social.md`](docs/concepts/cell-level-social.md)
│   │   │   for the conceptual model and the known limitation.
│   │   │
│   │   ├── 95.0 — Schema + polymorphic plumbing                  ✅ shipped
│   │   │     Two Alembic migrations (``s7u9w1y3b5d7`` creates
│   │   │     ``notebook_cells``; ``t8v0x2z4c6e8`` extends
│   │   │     ``ck_social_targets_kind`` with ``notebook_cell``,
│   │   │     line-by-line mirror of Phase 90's ``p4r6t8v0x2z4``).
│   │   │     ``NotebookCellIdentity`` model in
│   │   │     [`pointlessql/models/notebook.py`](pointlessql/models/notebook.py)
│   │   │     (named ``Identity`` to avoid collision with the doc-
│   │   │     level dataclass).  ``EntityKindSpec(key='notebook_cell',
│   │   │     supports_reviews=False, …, tab_keys=('discussion',
│   │   │     'followers'))`` in
│   │   │     [`entity_registry.py`](pointlessql/services/social/entity_registry.py).
│   │   │     Workspace-resolver arm in
│   │   │     [`_target_resolver.py`](pointlessql/services/social/_target_resolver.py).
│   │   │     ``{uuid36}:{uuid36}`` composite-ref shape validator in
│   │   │     [`_kind_dispatch.py`](pointlessql/api/social_routes/_kind_dispatch.py).
│   │   ├── 95.1 — Save-path reconciliation                       ✅ shipped
│   │   │     Three-pass reconciler in
│   │   │     [`pointlessql/services/notebook/cell_reconciliation.py`](pointlessql/services/notebook/cell_reconciliation.py):
│   │   │     (1) exact-hash with same-hash ordinal-proximity tiebreak,
│   │   │     (2) similarity-gated ordinal fallback (3-char Jaccard
│   │   │     shingles, 0.5 threshold) — the gate that prevents
│   │   │     "delete + insert at same position steals UUID",
│   │   │     (3) fresh UUID for genuinely new cells.  Unmatched
│   │   │     existing rows get soft-deleted via ``removed_at``.
│   │   │     Wired into [`io.py`](pointlessql/api/notebooks_routes/io.py)
│   │   │     at the post-``save_document`` hook; load route emits
│   │   │     ``cell_uuid`` per cell + ``notebook_uuid`` at top level.
│   │   │     11 unit tests cover scenarios (a)–(h) from the plan
│   │   │     plus reformat-all + no-op + empty-save.
│   │   ├── 95.2 — Frontend chip + inline thread + bulk-counts    ✅ shipped
│   │   │     New ``cellThread()`` Alpine factory in
│   │   │     [`frontend/js/notebook/cell_thread.js`](frontend/js/notebook/cell_thread.js)
│   │   │     mounted per cell.  The ``💬 N`` chip lives in the
│   │   │     cell-header right cluster; the collapsible thread
│   │   │     region renders below the output zone via
│   │   │     [`_partials/notebook_editor/cell_thread.html`](frontend/templates/pages/_partials/notebook_editor/cell_thread.html).
│   │   │     Lazy-loaded on first open; comments / 6-emoji reactions
│   │   │     / follow ride the existing polymorphic
│   │   │     ``/api/social/notebook_cell/{ref}/...`` routes.  New
│   │   │     bulk-counts endpoint at
│   │   │     [`_notebook_cell_counts.py`](pointlessql/api/social_routes/_polymorphic_handlers/_notebook_cell_counts.py)
│   │   │     aggregates comments + reactions + followers for one
│   │   │     notebook in a single query (notebook-load + post-save
│   │   │     refresh).  Asset-version bump to ``0.1.0rc15``.
│   │   ├── 95.3 — Cell-tags hybrid picker                        ✅ shipped
│   │   │     Curated vocabulary (``etl``, ``draft``, ``prod``,
│   │   │     ``wip``, ``verified``, ``broken``) in
│   │   │     [`pointlessql/services/notebook/cell_tags.py`](pointlessql/services/notebook/cell_tags.py);
│   │   │     ``cellTagPicker()`` Alpine factory in
│   │   │     [`frontend/js/notebook/cell_tag_picker.js`](frontend/js/notebook/cell_tag_picker.js)
│   │   │     mounted in the cell-header LEFT cluster.  Hybrid:
│   │   │     dropdown of curated tags plus a "Custom…" escape for
│   │   │     free-text entries.  Mutates ``cell.tags`` in place
│   │   │     (memory rule ``feedback_alpine_nested_object_replace``);
│   │   │     dispatches ``pql:cell-tag-changed`` so the parent
│   │   │     editor's autosave debouncer picks up the change.  No
│   │   │     schema work — the marker grammar already round-trips
│   │   │     arbitrary tag lists losslessly.
│   │   └── 95.4 — Walkthrough + concept doc + nav                ✅ shipped
│   │         [`docs/concepts/cell-level-social.md`](docs/concepts/cell-level-social.md)
│   │         explains the reconciliation algorithm + the documented
│   │         limitation + the forward-compat contract Phase 101 keys
│   │         off.  [`docs/e2e-walkthroughs/notebook_cell_social.md`](docs/e2e-walkthroughs/notebook_cell_social.md)
│   │         covers the 8-step Playwright playbook with step 5 as
│   │         the headline identity-survival test.  Concept nav entry
│   │         after ``Agent memory``; walkthrough entry in the
│   │         Notebook cluster.
│   │
│   ├── Phase 96 — Inline AI-Assistant in notebook                ✅ shipped (local, 2026-05-19)
│   │     Lifted the Phase-91 NL→SQL hermes-agent chat panel into
│   │     the notebook editor.  Three new hermes-plugin tools:
│   │     ``pql_propose_cell`` (code or markdown),
│   │     ``pql_fix_cell``, ``pql_explain_cell``.  Provenance
│   │     trail records which agent proposed which cell version
│   │     in the append-only ``notebook_cell_provenance`` table
│   │     (separate from ``notebook_cell_identity`` so Phase 97
│   │     revision history can render the full agent chain).
│   │     Direct counter to DBX-Assistant's commercial pitch.
│   │
│   │     Sub-phases:
│   │       * **96.A** — refactor(editor-chat): rename
│   │         ``sql_chat`` → ``editor_chat`` services + models +
│   │         settings (no shim).  Env prefix
│   │         ``POINTLESSQL_SQL_CHAT_*`` →
│   │         ``POINTLESSQL_EDITOR_CHAT_*``.  Generic substrate
│   │         (session table, broker, agent factory, turn runner)
│   │         is shared between the SQL-editor chat (Phase 91)
│   │         and the notebook AI assistant.  Commit ``52d2f1e``.
│   │       * **96.B** — new ORM tables
│   │         ``notebook_cell_proposals`` (polymorphic
│   │         propose/fix/explain with status lifecycle) and
│   │         ``notebook_cell_provenance`` (append-only audit).
│   │         New WS endpoint ``/ws/notebook/chat/{editor_session_id}``
│   │         (fork of ``sql_chat_ws``; drops ``refine``).  New
│   │         REST routes ``/api/notebook/chat/...``: propose-cell,
│   │         fix-cell, explain-cell, accept, discard, plus
│   │         ``GET /api/notebook/chat/cell/{cell_uuid}/explanations``.
│   │         Agent factory gains a ``surface`` arg (``"sql"``
│   │         vs ``"notebook"``) so the plugin's env-var split
│   │         registers the right propose-tool family per turn.
│   │         ``/api/notebooks/save`` extended to flush
│   │         ``proposal_acceptances`` into provenance rows after
│   │         the cell-reconciliation pass mints the final
│   │         ``cell_uuid``.  Alembic migration
│   │         ``u9w1y3a5d7f9_phase96_notebook_chat_proposals``.
│   │       * **96.C** — three new ``hermes-plugin-pointlessql``
│   │         tools (``pql_propose_cell`` / ``pql_fix_cell`` /
│   │         ``pql_explain_cell``), three matching
│   │         :class:`PointlessClient` methods, ``PluginConfig``
│   │         gains ``notebook_chat_session_id``, ``register_all``
│   │         wires them.  Plugin commit ``1ddf587``.
│   │       * **96.D** — frontend: new
│   │         ``notebookChatPanel`` Alpine factory (forked from
│   │         the SQL chat panel), ``chat_drawer.html`` partial
│   │         with three proposal banner variants
│   │         (propose=Insert / fix=Apply / explain=auto-attach),
│   │         ``chat_integration.js`` mixin that bridges accepted
│   │         proposals back to the editor via a
│   │         ``pql:cell-proposal-accepted`` window event,
│   │         ``cell_operations.js`` gains
│   │         ``insertCellFromProposal`` /
│   │         ``updateCellSourceByUuid``, ``persistence.js``
│   │         threads ``proposal_acceptances`` through save,
│   │         toolbar AI button beside Variables/Jobs, social
│   │         drawer's per-cell view gains an "AI Explanations"
│   │         section.  Asset version bumped to ``0.1.0rc29``.
│   │       * **96.E** — pytest: 14 tests across
│   │         ``test_notebook_chat_routes.py`` (model + route
│   │         lifecycle + idempotency + rename guard) +
│   │         ``test_notebook_chat_ws.py`` (4 WS smoke tests
│   │         incl. surface routing assertion) +
│   │         ``test_notebook_save_provenance.py`` (save-path
│   │         flush round-trip for both propose + fix).  Plugin
│   │         side adds 10 tests in ``tests/test_cell_tools.py``.
│   │         Markdown walkthrough
│   │         [`docs/e2e-walkthroughs/notebook_assistant.md`](docs/e2e-walkthroughs/notebook_assistant.md)
│   │         + seed notebook
│   │         [`notebooks/phase96_walkthrough.py`](notebooks/phase96_walkthrough.py).
│   │
│   │     Deferred to Phase 96.1: per-cell inline Fix/Explain
│   │     header buttons that pre-fill the chat panel with a
│   │     templated prompt referencing the focused cell.
│   │
│   ├── Phase 97 — Revision history + Diff + Pin-to-memory          ✅ done 2026-05-21
│   │     Save-snapshots in our own metadata DB (not the on-disk
│   │     ``.py`` file).  New ``NotebookRevision`` table + migration
│   │     ``47832b8d57ca``; canonical JSON encoding + SHA-256 in
│   │     ``services/notebook/revisions.py``; idempotent on the
│   │     canonical hash so a re-save with identical content collapses
│   │     to the existing row.  Cell-by-cell diff via the stable
│   │     ``content_hash`` identity emits ``added`` / ``removed`` /
│   │     ``changed`` / ``moved`` / ``unchanged`` envelopes the front-
│   │     end can hand to Monaco's diff editor.  REST: POST + GET on
│   │     ``/api/notebooks/revisions``; ``GET .../{uuid}`` for full
│   │     payload; ``GET .../diff?left=…&right=…``.  14 new pytest.
│   │     Asset 0.1.0rc35.  Shipped 2026-05-20.
│   │
│   │     **97.X.1 — Pin-to-memory backend** ✅ shipped 2026-05-21,
│   │     commit ``36dc878``, asset rc69.  ``notebook_revision_facts``
│   │     table + migration ``d8f1a3b5c7e9``; ``OpName.PIN_FACT`` in
│   │     the agent-ops enum; new ``services/notebook/facts.py``
│   │     primitive idempotent on ``(workspace_id, revision_id,
│   │     cell_content_hash)`` partial-UNIQUE; four REST endpoints
│   │     under ``/api/notebooks/facts`` (POST + GET list + GET
│   │     detail + DELETE soft-unpin); ``pql.facts`` PQL facade with
│   │     agent env-bridge via ``POINTLESSQL_AGENT_RUN_ID``;
│   │     ``social_targets.entity_kind`` CHECK widened with two new
│   │     kinds (``notebook_revision`` + ``notebook_cell_output``)
│   │     plus matching ``entity_registry`` URL builders; best-effort
│   │     ``fanout_event(event_type='notebook_revision_pinned', …)``
│   │     wired so pins land in the Phase-81 inbox.  18 new pytest.
│   │
│   │     **97.X.2 — Pin-to-memory UI** ✅ shipped 2026-05-21, commit
│   │     ``cfaad5c``, asset rc70.  📌 button in the Phase-97
│   │     revisions panel + cell-header chip (lit
│   │     ``btn-outline-warning`` when a fact exists) reusing the
│   │     outer-scope mixin pattern (no nested-x-data trap); new
│   │     ``frontend/js/notebook/cell_facts.js`` + extension of
│   │     ``revisions.js``; bulk lookup at ``/api/notebooks/facts/bulk``
│   │     for per-cell hot-paths; ``/library/facts`` browse page
│   │     wired through ``library_facts.html`` + Alpine factory in
│   │     ``bootstrap.js``; cell-output pin auto-snapshots a fresh
│   │     revision before pinning so the fact always points at a
│   │     concrete row.  2 new pytest.
│   │
│   │     **97.X.3 — Pin feed-card closure** ✅ shipped 2026-05-21,
│   │     asset rc72.  Dedicated ``render_kind = "fact"`` branch in
│   │     ``classify_notification`` + SSE ``_classifyEvent`` mirror +
│   │     new Alpine ``<template x-if="r.render_kind === 'fact'">``
│   │     block in ``activity_pane.html`` showing
│   │     ``bi-pin-angle-fill`` + summary text.  5 new pytest
│   │     covering classify + envelope + e2e fanout + null-actor
│   │     agent path.  Playwright-MCP playbook extended with Part P
│   │     in ``notebook-editor.md`` + new ``library-facts.md``.
│   │
│   │     **Deferred (genuine blocker):**
│   │     * **Shoreguard signing** — Phase 97's cryptographic verify
│   │       leg is paused.  The shoreguard-fresh checkout exposes
│   │       webhook + OIDC + auth signing helpers but no public
│   │       "sign-this-revision" API yet; ``signature_alg`` and
│   │       ``signature`` columns are reserved on the row so a
│   │       follow-up sprint can populate them once the API ships.
│   │       Every snapshot still records its deterministic SHA-256.
│   │     * **Monaco diff UI** — backend envelope is ready and
│   │       Wave-D-1 lit up the side-by-side panel; the Monaco
│   │       editor-mode renderer is a follow-up (gated by the
│   │       nested-x-data trap, same reason 98.C's chip render was
│   │       deferred — re-eval once Phase 105 awareness layer lands
│   │       and the outer-scope mixin pattern is dominant).
│   │
│   ├── Phase 98 — DBX-parity quick wins bundle                   ✅ done 2026-05-20
│   │     Single sprint covering four small DBX-parity items:
│   │     magic commands (``%sql``, ``%md``, ``%fs ls``,
│   │     ``%timeit``) as a thin pre-processor; notebook-tags +
│   │     template gallery (``/notebooks/new from template``);
│   │     cell-level lineage badges in the cell header reading
│   │     existing ``agent_run_operations`` write events;
│   │     notebook → static HTML/PDF export.
│   │       * 98.A ✅ done 2026-05-20 — magic-command pre-processor.
│   │         New ``services/notebook/magic_commands.py``: %sql / %md
│   │         (line + block) / %fs ls / %timeit.  Bootstrap helpers
│   │         (``__pql_magic_md__`` / ``__pql_magic_fs_ls__`` /
│   │         ``__pql_magic_timeit__``) added to the kernel session.
│   │         WS execute handler now runs the pre-processor before
│   │         kernel dispatch, resolving SQL approval server-side per
│   │         %sql line.  13 new pytest covering line/block parsing,
│   │         placeholder splicing, and indent preservation.
│   │       * 98.D ✅ done 2026-05-20 — static HTML / PDF export.
│   │         New ``services/notebook/export.py`` builds a self-
│   │         contained HTML document (inline CSS, no external assets,
│   │         ``@page`` print stylesheet) from the parsed ``.py`` doc +
│   │         the latest-session ``notebook_outputs`` rows.  Output
│   │         frames reuse the existing
│   │         ``services.output_rendering.render_output_frame``
│   │         pipeline.  Optional ``render_notebook_pdf`` produces real
│   │         ``application/pdf`` via WeasyPrint when importable; falls
│   │         back to the HTML body + diagnostic header
│   │         ``X-PointlesSQL-Export-Fallback`` so the UI can suggest
│   │         the browser's *Save as PDF*.  Routes
│   │         ``GET /api/notebooks/export.html`` and ``/export.pdf``.
│   │         9 new pytest.
│   │       * 98.C ✅ done 2026-05-20 — cell-level lineage badges.
│   │         New ``services/notebook/cell_lineage.py`` joins
│   │         ``notebook_cell_runs`` (filtered to rows with
│   │         ``agent_run_id`` set) → ``agent_run_operations``
│   │         (filtered to the 13 WRITE op_names) and collapses
│   │         duplicate ``(op_name, target_table)`` pairs to the most
│   │         recent occurrence.  REST ``GET
│   │         /api/notebooks/cell/lineage`` surfaces the badges to a
│   │         future cell-header UI; backend-only ship (UI affordance
│   │         deferred to a follow-up to avoid the x-data + |tojson
│   │         playbook-gate cost).  8 new pytest.
│   │       * 98.B ✅ done 2026-05-20 — notebook tags + template
│   │         gallery.  New ``NotebookTag`` ORM table + migration
│   │         ``b185acda50d7`` for notebook-level lifecycle tags
│   │         (distinct from the marker-grammar cell tags); curated
│   │         vocabulary (``etl`` / ``draft`` / ``prod`` / etc.) plus
│   │         free-text with ``[a-z0-9_-]`` validation, 16-tag cap
│   │         per notebook.  New ``services/notebook/tags.py``
│   │         service + ``api/notebooks_routes/tags.py`` routes
│   │         (GET / POST / DELETE ``/api/notebooks/tags``).
│   │         Template gallery ships four starter ``.py`` files
│   │         under ``pointlessql/data/notebook_templates/`` driven
│   │         by ``_manifest.json``: blank, sql_exploration,
│   │         etl_pipeline, ml_quickstart.  New
│   │         ``services/notebook/templates.py`` + routes
│   │         ``GET /api/notebooks/templates`` and ``POST
│   │         /api/notebooks/from-template``.  13 new pytest.
│   │         **Wave-B UI 2026-05-20 (asset 0.1.0rc47):** notebook-
│   │         level tag picker shipped in the editor toolbar
│   │         (next to Variables/AI), driven by new
│   │         ``installNotebookTags`` mixin + ``notebookTagPicker``
│   │         inline panel.  Curated chips + custom-tag input +
│   │         pill-list of active tags with one-click removal +
│   │         count badge on the button.  Workspace-list tag-pills
│   │         still deferred.
│   │
│   ├── Phase 99 — Widget-cells + Notebook permissions            ⏳ partial
│   │     Backend shipped 2026-05-20.  Two new tables (migration
│   │     ``b944b9be7e03``):
│   │     * ``notebook_widgets`` — parameter widgets keyed
│   │       ``(notebook_id, name)`` with ``widget_kind`` ∈
│   │       ``dropdown`` / ``slider`` / ``text``; JSON-encoded
│   │       ``config`` + ``default_value``.
│   │     * ``notebook_permissions`` — per-notebook share grants
│   │       (``view`` / ``run`` / ``edit`` lattice); layered on top
│   │       of workspace membership.
│   │     Services: ``services/notebook/widgets.py``
│   │     (``upsert_widget`` / ``list_widgets`` /
│   │     ``resolve_widget_values`` / ``delete_widget``) and
│   │     ``services/notebook/permissions.py`` (``grant_permission``,
│   │     ``revoke_permission``, ``get_effective_role``,
│   │     ``role_satisfies``).  REST: ``GET|PUT|DELETE
│   │     /api/notebooks/widgets``, ``POST .../widgets/resolve``,
│   │     ``GET|PUT|DELETE /api/notebooks/permissions``.  12 new
│   │     pytest.  Asset 0.1.0rc37.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Widgets-CRUD
│   │     panel + per-notebook permission grants both shipped.
│   │     Toolbar buttons "Widgets" / "Access" open inline panels
│   │     with full CRUD on ``GET|PUT|DELETE /api/notebooks/widgets``
│   │     and ``GET|PUT|DELETE /api/notebooks/permissions``.  The
│   │     widgets panel surfaces resolved values via
│   │     ``POST /widgets/resolve`` so the user sees what the
│   │     kernel would receive.  The permissions panel exposes the
│   │     ``view < run < edit`` lattice with inline role editing.
│   │
│   │     **Still deferred:** ``pql.widgets`` kernel-side shim
│   │     (env-bridge from WS handler to kernel namespace) +
│   │     route-layer enforcement (``role_satisfies`` is in place
│   │     but not yet consulted by the load / save / WS execute
│   │     paths).  Both are mechanical plumbing — the UI now
│   │     surfaces the data the runtime needs to honour.
│   │
│   ├── Phase 100 — Publish notebook (external share + dashboard) ⏳ partial
│   │     Two orthogonal pieces shipped together because they share
│   │     a route + rendering pipeline:
│   │     (a) **Public share via UUID** — ChatGPT-shared-chat
│   │     pattern: clicking "Publish" mints an unguessable v4 UUID
│   │     under ``/share/notebook/{uuid}``.  No auth required,
│   │     read-only.  Two share modes (publisher picks at publish
│   │     time, switchable later):
│   │       * **Snapshot** *(default — safer)* — freezes the
│   │         current notebook state (cells + outputs + exec
│   │         counts) as a tagged Phase-97 revision; later in-place
│   │         edits don't leak.  Re-publish updates the snapshot
│   │         under the same UUID (link stays stable); Unpublish
│   │         revokes entirely.  Reproducible / audit-friendly.
│   │       * **Live** *(opt-in, with warning)* — link always
│   │         reflects the current ``.py`` + last-known outputs.
│   │         For team dashboards / stakeholder views where you
│   │         want auto-update without re-publishing.  Higher risk
│   │         (an accidental secret-push lands publicly the moment
│   │         you save) so the toggle ships behind an explicit
│   │         confirm dialog and a persistent "LIVE share" badge
│   │         in the editor toolbar while active.
│   │     Snapshot storage piggybacks on Phase 97 revision history.
│   │     Common to both modes: admin-gated, (optional) expiry,
│   │     outputs scrubbed for secrets, "public share" watermark,
│   │     iframe-embed-friendly analog to Phase-92.2's
│   │     ``/embed/semantic_search/{fqn}`` surface.
│   │     (b) **Dashboard rendering mode** — strips code cells,
│   │     renders only markdown + outputs as a clean read-only
│   │     view; re-uses ``output_rendering.py``.  Available both
│   │     under the public share UUID and under
│   │     ``/notebooks/dashboard/{path}`` for workspace-internal
│   │     consumption.  DBX-parity (and ChatGPT-parity) for the
│   │     "publish a notebook" flow.
│   │
│   │     Backend shipped 2026-05-20.  New ``notebook_shares`` table
│   │     + migration ``8c7c6eb5add5``.  Share-mode lattice
│   │     (``snapshot`` / ``live``) plus a ``dashboard_mode`` flag
│   │     persisted per-share.  Snapshot publishes mint a fresh
│   │     Phase-97 :class:`NotebookRevision` and pin the share to
│   │     it; live shares carry no revision pin.  Service in
│   │     ``services/notebook/shares.py`` (``create_share``,
│   │     ``update_share``, ``revoke_share``, ``get_active_share``,
│   │     ``list_shares_for_notebook``, ``render_dashboard_html``).
│   │     Admin REST: ``GET|POST /api/notebooks/shares``,
│   │     ``PATCH|DELETE /api/notebooks/shares/{share_uuid}``.
│   │     Public viewer: ``GET /share/notebook/{share_uuid}`` —
│   │     no auth required; 410 Gone for revoked / expired /
│   │     unknown share UUIDs.  Dashboard render keeps markdown
│   │     cells, replaces code cells with placeholder slots so
│   │     their outputs still surface in original order, prepends
│   │     a "DASHBOARD" banner.  8 new pytest.  Asset 0.1.0rc38.
│   │
│   │     **Wave-B UI 2026-05-20:** Share-Dialog shipped (asset
│   │     0.1.0rc49 → rc51).  Toolbar Share-button opens a modal
│   │     with Snapshot/Live mode toggle, Dashboard-mode checkbox,
│   │     optional snapshot-note input, and a list of existing
│   │     shares with Open-in-new-tab / Copy-URL / Toggle-Dashboard
│   │     / Revoke actions per row.  Replay caught + fixed a
│   │     latent backend bug: ``/share/`` was missing from the
│   │     auth middleware's ``PUBLIC_PREFIXES`` allowlist, so the
│   │     public viewer had been 303-redirecting every visitor
│   │     to ``/auth/login`` since initial Phase-100 ship.
│   │
│   │     **Still deferred:** iframe-embed analog of Phase-92.2's
│   │     ``/embed/semantic_search/{fqn}``, and the secret-scrub
│   │     pass before serving (today the publisher is expected to
│   │     vet the content; the route does not redact).
│   │
│   ├── Phase 101 — Agent-co-authored cells + Reviewer-per-cell   ⏳ partial
│   │     Per-cell attribution backbone (Phase 101) shipped 2026-05-20:
│   │     new ``NotebookCellAuthorship`` ORM + migration
│   │     ``805d36938963``, 1:1 with :class:`NotebookCellIdentity`.
│   │     Tracks ``first_author_*`` (user email or ``agents.id`` +
│   │     ``agent_run_id``) and ``last_modifier_*`` separately so the
│   │     header chip can render "minted by agent A • last edited by
│   │     user B".  Service in
│   │     ``services/notebook/cell_authorship.py``;
│   │     :func:`upsert_cell_authorship` is the save-path /
│   │     proposal-acceptance hook.  REST: ``GET
│   │     /api/notebooks/cell/attribution?cell_uuid=…`` +
│   │     ``GET /api/agents/{id}/authored-cells``.  13 new pytest.
│   │     Asset 0.1.0rc36.
│   │
│   │     Save-path wiring landed 2026-05-20 (asset 0.1.0rc42):
│   │     ``api/notebooks_routes/io.py``'s save handler now calls
│   │     ``upsert_cell_authorship`` for every reconciled cell with
│   │     the saver's email as ``first_author``/``last_modifier``.
│   │     Cells start filling the table from the next save.
│   │
│   │     **Wave-B UI 2026-05-20:** cell-header chip shipped
│   │     (asset 0.1.0rc48).  Each cell shows a small person/robot
│   │     chip between the dirty-dot and the tag-picker with the
│   │     saver's email local-part and the full attribution
│   │     envelope (created / last-modified) on hover.  Nested-
│   │     x-data trap dodged by exposing the methods on the outer
│   │     notebook scope via a new ``installCellAuthorship`` mixin
│   │     (DOM-walk-free).  New bulk endpoint
│   │     ``GET /api/notebooks/attribution/bulk?path=…`` returns
│   │     ``{cell_uuid: envelope}`` so a 50-cell notebook costs one
│   │     HTTP request instead of 50; 2 new pytest (15 total).
│   │
│   │     **AI-acceptance hook landed 2026-05-20 (asset 0.1.0rc52):**
│   │     ``upsert_cell_authorship`` relaxed to accept ``kind="agent"``
│   │     with ``agent_id=None`` when ``agent_run_id`` is set;
│   │     ``_write_proposal_provenance`` in ``io.py`` now upserts
│   │     agent authorship before the user-authorship loop runs.  A
│   │     proposal-accepted cell now reads "minted by AI assistant •
│   │     last edit by <saver>" on the chip.  One new pytest (16
│   │     total).
│   │
│   │     **Still deferred:**
│   │     * **Reviewer-per-cell flow** — the existing polymorphic
│   │       comment system (``DataProductComment`` already carries
│   │       ``author_agent_id``) already supports it; the dedicated
│   │       "review this cell" UI affordance + reviewer-agent tool
│   │       both land in a follow-up.
│   │
│   ├── Phase 102 — Branch-aware notebooks                        ⏳ partial
│   │     Backend shipped 2026-05-20.  New
│   │     ``notebook_branch_bindings`` table + migration
│   │     ``095e6a40fa0e`` records which Delta-branch a notebook
│   │     writes to (or ``None`` for ``main``).  Lifecycle columns
│   │     (``created_at`` / ``promoted_at`` / ``discarded_at`` /
│   │     ``superseded_at``) keep history while keeping at most one
│   │     "current" binding per notebook — every fresh bind /
│   │     promote / discard supersedes the prior row.
│   │     Service ``services/notebook/branch_bindings.py``:
│   │     ``bind_branch`` / ``get_current_binding`` /
│   │     ``promote_binding`` / ``discard_binding`` /
│   │     ``list_bindings``.  REST: ``GET|POST|DELETE
│   │     /api/notebooks/branch``, ``POST
│   │     /api/notebooks/branch/promote``, ``GET
│   │     /api/notebooks/branch/history``.  11 new pytest.
│   │     Asset 0.1.0rc39.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Toolbar
│   │     "Branch" button opens an inline binding panel with
│   │     three states (none / pending / promoted), a bind form
│   │     (branch_name + optional base_revision_uuid), promote +
│   │     discard actions, and an expandable history list.  Wires
│   │     the existing REST surface; no backend change needed.
│   │
│   │     **Still deferred:** kernel-side env-bridge so cells
│   │     actually route reads + writes through the bound branch
│   │     (today the binding is recorded but not yet consulted by
│   │     ``pql.read_table`` / ``pql.write_table``).  Promote-gate
│   │     to shoreguard remains a future hook — ``promote_binding``
│   │     today records the lifecycle transition without calling
│   │     into a reviewer system.
│   │
│   ├── Phase 103 — Replay / Scenario-mode                        ⏳ partial
│   │     Backend shipped 2026-05-20.  New ``notebook_replays``
│   │     table + migration ``311c87f25421`` records one row per
│   │     replay attempt of a Phase-97 :class:`NotebookRevision`.
│   │     Lifecycle column ``status`` ∈ ``{pending, running, ok,
│   │     error, cancelled}``; outputs land in ``outputs_json``
│   │     and a digest of ``{stable, changed, missing, new}`` cell
│   │     counts lives in ``diff_summary_json`` for the list page.
│   │     Optional ``branch_name`` routes writes to a Phase-102
│   │     branch so the replay does not corrupt production.
│   │     Service ``services/notebook/replay.py`` (``start_replay``,
│   │     ``mark_running``, ``record_finished``, ``get_replay``,
│   │     ``list_replays``, ``compute_replay_diff``).  REST:
│   │     ``POST /api/notebooks/replay``,
│   │     ``POST .../replay/{uuid}/finish``,
│   │     ``GET .../replay/{uuid}``,
│   │     ``GET .../replay/{uuid}/diff``,
│   │     ``GET /api/notebooks/replays``.  8 new pytest.
│   │     Asset 0.1.0rc40.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Toolbar
│   │     "Replays" button opens an inline list with status pill
│   │     + base-revision UUID + branch + per-row diff expand
│   │     (lazy GETs ``/api/notebooks/replay/{uuid}/diff``).  A
│   │     "Start replay" form lets the user mint a fresh ``pending``
│   │     row; the kernel re-execution worker stays deferred so
│   │     the row just sits until that lands.
│   │
│   │     **Still deferred:** the actual kernel-driven re-execution
│   │     loop (the worker that takes a replay row from ``pending``
│   │     → ``running`` → ``ok`` and uploads the outputs).  Worker
│   │     plumbing is straightforward papermill / kernel-session
│   │     orchestration; the scaffolding for the audit + diff
│   │     surface is the load-bearing piece and is in place.
│   │
│   ├── Phase 104 — NL→Notebook (full cell-sequence generation)   ⏳ partial
│   │     Backend shipped 2026-05-20.  New
│   │     ``notebook_cell_sequence_proposals`` table + migration
│   │     ``d737762ace76``.  One row carries the full proposed
│   │     sequence (``imports → DataFrame → plot → markdown``) as
│   │     ``cells_json`` so insertion is atomic — the user picks
│   │     "Insert all" or "Discard" without ever landing in a
│   │     half-applied state.  Status lifecycle ``pending →
│   │     {accepted, discarded, expired}``; the existing Phase-96
│   │     :class:`NotebookCellProvenance` fans out per-cell
│   │     provenance after acceptance.  Service
│   │     ``services/notebook/cell_sequence_proposals.py``:
│   │     ``propose_sequence`` (validates cell_type ∈
│   │     ``{code, markdown, sql}``, sorts by ``position``),
│   │     ``accept_sequence``, ``discard_sequence``,
│   │     ``get_sequence``, ``list_pending_for_session``.  REST:
│   │     ``POST /api/notebook/chat/{chat_session_id}/propose-sequence``,
│   │     ``GET|accept|discard /api/notebook/chat/sequences/{proposal_id}``,
│   │     ``GET .../sequences/pending``.  10 new pytest.
│   │     Asset 0.1.0rc41.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Toolbar
│   │     "Proposals" button opens a passive inbox listening for
│   │     ``pql:cell-sequence-proposed`` window events.  Each
│   │     pending proposal shows prompt + rationale + cell preview
│   │     + Accept-all / Discard.  Accept iterates the cells via
│   │     ``insertCellFromProposal`` then POSTs the accept route;
│   │     Discard hits the discard route.  Inbox auto-opens the
│   │     first time a proposal arrives so the user doesn't miss
│   │     it.
│   │
│   │     **Still deferred:** the hermes-plugin
│   │     ``pql_propose_cell_sequence`` LLM tool that drives the
│   │     actual code-gen + fires the window event.  Until the
│   │     plugin lands, the inbox stays empty (and the empty-state
│   │     copy says so).
│   │
│   └── Phase 105 — Real-time co-edit                              ✅ done 2026-05-21
│         **Closed 2026-05-21.**  Full track shipped in one
│         session: 105.1 (CRDT sidecar storage) + 105.2 (WS hub)
│         + 105.3 (passive Y.Doc client + live pill) + 105.4
│         (awareness + peer rail) + 105.5 (save-path barrier) +
│         105.3b (per-cell y-codemirror.next binding) + 105.6
│         (agent-presence REST + pseudo-peer rendering) + 105.7
│         (multi-tab Playwright playbook) + 105.8 (compaction
│         scheduler executor).
│
│         Original 2026-05-20 framing kept for context:
│         Y.js / CRDT layer over the existing WebSocket so
│         multiple humans + agents can edit cells simultaneously
│         with visible cursors.
│
│         **Decision 2026-05-20:** parked on ice deliberately.  The
│         phase itself was tagged "ship only if the simpler async
│         patterns from Phases 95 / 101 prove insufficient in
│         practice".  Today, the social + AI surfaces shipped in
│         95 (cell-level comments / reactions / followers), 96
│         (inline assistant), 101 (per-cell authorship), and 104
│         (sequence proposals) all use the simpler turn-based async
│         pattern and no user friction with simultaneous-edit
│         scenarios has surfaced yet.
│
│         The infrastructure cost (server-side CRDT backend +
│         Y.js wire format + persistence + conflict resolution
│         that survives the existing reconciliation pass) is
│         substantial and would deflect from the agent-native
│         vision pillars in `project_ai_native_vision.md`.  Revisit
│         only when a concrete user-reported pain story shows the
│         current async pattern is the blocker — until then the
│         per-cell social + provenance surface is the load-bearing
│         collaboration model.
│
│         **Replay bug-hunt 2026-05-20:** a full Playwright-MCP
│         replay of ``docs/e2e-walkthroughs/notebook-editor.md``
│         against the Phase-95 / 96 / 98 surfaces caught five real
│         bugs that escaped every prior gate (no ruff / pyright /
│         pydoclint signal — all five live in JS+Jinja+WS
│         boundaries).  Fixes batched as Phase 105 bug-fix wave;
│         see CHANGELOG ``Unreleased`` for BUG-105-01..05 details.
│         Asset 0.1.0rc44.  Confirms ``feedback_run_playbook_as_gate``
│         — the replay was the gate; nothing earlier would have
│         caught the AI-drawer infinite reconnect, the
│         variable-inspector self-trigger loop, the tag-picker /
│         💬-chip UUID gating, or the ``cellThread.cellRef``
│         snapshot regression.
│
│         **Wave-B follow-up 2026-05-20:** three deferred-UI
│         backends (98.B Tags, 101 Author-Chip, 100 Publish/Share)
│         lifted from "orphan REST + green tests" to "live editor
│         feature" — see Phase 98.B / 100 / 101 entries above for
│         per-phase details.  Replay turned up three more at-source
│         bugs: ``/share/`` missing from auth allowlist (Phase 100
│         viewer unreachable since initial ship), ES-module cache
│         invalidation gap (now structurally fixed via a
│         ``/static/js/{path:path}`` route that stamps ``?v=mtime``
│         into every relative import — mirrors the long-standing
│         ``_style_css`` route for CSS sub-imports), and a tag-
│         payload shape mismatch in the new picker JS.  Asset
│         0.1.0rc46 → rc51 (four sub-bumps across three waves +
│         two bug-bumps).  Tests: 36/36 green across the three
│         touched suites.
│
│         **Wave-D 2026-05-21 — every remaining deferred notebook
│         item closed.**  Six sub-commits + one cross-repo plugin
│         commit asset 0.1.0rc56 → rc62; the per-phase "deferred"
│         lists above flip as follows (full detail in CHANGELOG
│         Unreleased):
│         - Phase 97 — Monaco-diff-style UI (line-by-line unified
│           diff drawer); ``set_revision_signature`` receive
│           endpoint for out-of-band signers.  Pin-to-memory still
│           defers (needs fact-shaped pql.memory primitive).
│         - Phase 98.B — workspace-tree tag-pills + filter
│           dropdown via new ``GET /api/notebooks/tags/bulk``.
│         - Phase 98.C — cell-header lineage chip via
│           ``installCellLineage`` mixin + new bulk endpoint.
│         - Phase 99 — ``pql.widgets`` kernel shim + route-layer
│           ``actor_has_role`` enforcement on load / save /
│           WS-open.
│         - Phase 100 — secret-scrub pass on public viewer +
│           ``GET /embed/notebook_share/{uuid}`` iframe mirror.
│         - Phase 101 — per-cell Review affordance (✅ / ⚠ / 💬
│           decision lattice) on top of the existing polymorphic
│           comment surface (``category='review'`` + migration
│           ``c4e7a91b2f60``).
│         - Phase 102 — ``PQL._branch_remap`` + kernel env-bridge
│           via ``POINTLESSQL_BRANCH``; ``promote_binding`` consults
│           ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL`` so an
│           external reviewer (shoreguard or any other) can gate
│           the transition.
│         - Phase 103 — replay re-execution worker
│           (``services/notebook/replay_worker.py``) drains pending
│           rows via ``jupyter_client.AsyncKernelManager`` per
│           replay.
│         - Phase 104 — hermes-plugin ``pql_propose_cell_sequence``
│           tool fires the ``pql:cell-sequence-proposed`` window
│           event the Wave-C inbox waits for; backend route now
│           accepts ``editor_session_id`` UUID7 for symmetry.
│
│         Genuine blockers (kept deferred):
│         - Shoreguard *sign-revision* and *promote-binding*
│           reviewer APIs do not exist upstream yet; PointlesSQL
│           ships the receive-endpoint + webhook-hook so the
│           integration lands without further PointlesSQL changes
│           once those APIs ship.
│         - Phase 97 pin-to-memory (no fact-shaped pql.memory).
│
│         Phase 105 open follow-ups (out of scope, tracked here so
│         they don't fall off the radar):
│         - **hermes-plugin agent-presence wiring** — closes 105.6
│           fully.  The REST endpoint
│           ``POST /api/notebooks/{nb}/coedit/agent-presence`` ships
│           on PointlesSQL but the plugin's ``propose_cell`` /
│           ``fix_cell`` / ``explain_cell`` tools don't fire the
│           pre/post calls yet, so the robot-avatar pseudo-peer
│           never lights up in real agent runs.  Cross-repo commit
│           on ``hermes-plugin-pointlessql``, ~30 LOC.
│         - **Sync-timing rebind on ``cellYBinding``** — when the
│           Y.Doc sync handshake is still in flight, ``cellYBinding``
│           returns ``null`` and cells mount as standalone
│           CodeMirror.  Today the binding picks up on the next
│           mount (cell add/delete or reload); a clean fix needs an
│           ``ydoc.on('synced', ...)`` listener in the mixin that
│           rebinds open editors once.
│         - **Cell-remap → editor rebind** — 105.5 stashes the
│           remap in ``_pendingCellRemap`` but 105.3b doesn't
│           actively consume it yet.  The first save-after-Pass-3-
│           mint requires a page reload to clean up.  Edge case
│           outside the 105.7 happy path, low priority.
│         - **Multi-worker Uvicorn** — *deliberately* out of scope.
│           The in-process ``_HUBS`` dict makes multi-worker invalid
│           for co-edit; lifting that needs a Redis pub/sub broker
│           and is its own phase, not a 105 follow-up.
│

├── Phase 81 — Feed overhaul + help surface + entity ⋯-menu  ✅ done 2026-05-16
│       Three-track polish bundle.  Track K rebuilt /feed from a
│       flat Bootstrap `list-group` into a first-class social
│       product page (GitHub-feed quality).  Track L added a
│       global `?`-button + `/help` reference surface as a
│       deliberate alternative to forced product tours.  Track M
│       lifted the feed item ⋯-action pattern into a reusable
│       macro and wired it into DP / Model / Run detail pages.
│       Plus a small first-run-welcome fix at close-out.
│
│       Track K — Feed overhaul (`377c93a..2792f43`):
│       1. **81.K.1** — Layout shell, sticky filter bar, day
│          grouping.  Replaces flat list-group with `nav-pills`
│          For-you / Mentions / My / Following + kind multi-
│          select dropdown + density toggle (Comfortable /
│          Compact / Headlines).  Day separators with sticky
│          "Today" / "Yesterday" / "Mon May 12" / "Earlier".
│       2. **81.K.2** — Rich per-kind item cards with bulk
│          actor-name resolution; one Alpine renderer + shared
│          classifier for comment / review / mention /
│          notification / agent_run / badge / issue / branch.
│       3. **81.K.3** — SSE live updates against
│          `/api/notifications/stream` with an "X new" pulse
│          banner and exponential reconnect backoff.
│       4. **81.K.4** — Per-item ⋯-action menu: Mark read,
│          Mute thread, Mute author, Snooze 1h/8h/1d, Copy link.
│          New `feed_mutes` Alembic table; 5 new endpoints.
│       5. **81.K.5** — Right context column (Trending today /
│          People to follow / Saved searches) with two new
│          `/api/feed/trending` + `/api/feed/people` aggregators.
│       6. **81.K.6** — Wired previously-invisible
│          `pointlessql.agent_run.completed/.failed` and
│          `pointlessql.issue.*` fanout call-sites into the feed.
│       7. **81.K.7** — Keyboard nav (j/k/o/e/m/r/?) + per-page
│          help modal + focus-ring affordance.
│       8. **81.K.8** — Per-filter empty-state copy + first-run
│          welcome card.
│       9. **81.K.9** — Activity / Discover top-level tabs
│          (moves right column out of the feed pane → full-width
│          activity).
│       10. **81.K.10** — Drop redundant `<h1>Feed</h1>`,
│           tighter breadcrumb padding.
│       11. **81.K.11** — Breadcrumbs moved into the topbar
│           (~50 px tighter pages).
│       12. **81.K.12** — Layout-toggle chevrons relocated into
│           the topbar (drops the rail header strip).
│       13. **81.K.13** — Discover sub-tabs (Trending / People /
│           Saved as `nav-pills` instead of three narrow
│           third-width cards).
│
│       Track L — Help surface (`67cda6b`):
│       * **81.L** — `/help` reference page (Keyboard / Hidden
│         features / Per-page reference / Glossary / More) +
│         topbar `?`-button next to the theme dropdown.  Deliberate
│         non-goal: no forced product tour, no driver.js /
│         shepherd.js dependency.  Per-page modals (e.g. Feed's
│         `?`-modal) stay as the quick reference; `/help` is the
│         canonical scrollable index.
│
│       Track M — Entity ⋯-menu sweep (`5e2a790`):
│       * **81.M** — `_macros/entity_actions.html` macro renders
│         a Bootstrap dropdown with Copy link, Copy citation,
│         Mute notifications.  Wired into `data_product.html`,
│         `model.html`, `run_view/header.html`.  Reuses the
│         existing `.pql-copy-btn` delegated handler;
│         `entity_actions.js` only adds the mute hop.  One-line
│         macro call ready to drop into table.html,
│         branch_detail.html, etc.
│
│       Close-out fix (`0f7d8b8`):
│       * **81.N.0** — First-run welcome card gated on
│         `filter === 'all'` so it stops stacking below the
│         dedicated empty-states on Mentions / My / Following.
│
│       Final state: 24 commits ahead of `origin/main` at session
│       close (push still queued — release-engineering-timing
│       memory keeps push gated behind explicit auth).  1 Alembic
│       migration (`feed_mutes`).  ~7 new pytest cases.  Static
│       gates all pass (ruff / pyright baseline / pydoclint /
│       file-size / bootstrap-order); the file-size gate picked
│       up `feed_routes.py` (1021 LOC) into the allowlist with a
│       split-candidate note, mirroring `home_routes.py`.
│
├── Phase 80 — Navigation & UX overhaul                    ✅ done 2026-05-15
│       Full IA + chrome rebuild after the Phase 79 walkthrough
│       surfaced five URL-only orphans (`/issues`, `/topics`,
│       `/feed`, `/users/{id}`, `/workspaces/{slug}`), a
│       command-palette that indexed only five entity kinds,
│       and a "my stuff" surface fragmented across four pages.
│       Ten self-contained sub-phases in one autonomous run.
│       No alembic migrations.  Behaviour-equivalent route
│       surface; only additive (`/users`, `/lineage`, `/me`,
│       `/api/health/backends`).
│
│       1. **IA contract** (80.0) — `docs/internal/navigation_ia.md`
│          captures the four chrome slots, five intent-groups,
│          every entry's template + handler, all context-panel
│          bindings, command-palette entity coverage, locked
│          decisions.  Audit-bot ready.
│       2. **Primary rail rework** (80.1) — icon_rail →
│          primary_rail; two-state width 64 px ↔ 220 px;
│          5 grouped sections (HOME / WATCH / BUILD / DATA /
│          COMMUNITY / WORKSPACE); 24 entries; rail badges
│          plumbing (counts wired in 80.3).
│       3. **Context-panel partials** (80.2) — 11 new sidebar
│          partials wired through `context_panel.html` covering
│          every new section.
│       4. **Today digest** (80.3) — three new stat cards on `/`
│          (approval queue · unread inbox · firing alerts);
│          `services/nav_badges.py` aggregator powers both
│          the Today cards and rail badges.
│       5. **/users + /lineage index pages** (80.4) — closes
│          two of the URL-only orphans with workspace-scoped
│          member list + trace-row/trace-column hub.
│       6. **/me consolidated hub** (80.5) — six/seven-card
│          landing replacing the previously-fragmented self-
│          pages; user-menu becomes the Me-hub shortcut list.
│       7. **Command palette expansion** (80.6) — `/api/search`
│          now covers 7 more kinds (data_product, topic, issue,
│          user, agent, workspace, saved_query); `@user` and
│          `#topic` operators narrow results.
│       8. **Status footer bar** (80.7) — fourth chrome slot,
│          28 px sticky bottom strip; workspace + role chips,
│          backend health pills polling `/api/health/backends`
│          every 60 s, keyboard hints.
│       9. **Quick-create + menu** (80.8) — GitHub-style topbar
│          dropdown with 6 baseline + 2 admin entries.
│       10. **Close-out** (80.9) — CHANGELOG + ROADMAP, broad-
│           except markers, full Phase-80 test pass.
│
│       Final state: 44 new test cases across 9 modules; full
│       pytest suite remains green (1635+ pass / 3 skip);
│       pyright 498 warnings (matches Phase 79 ceiling within
│       2 from new code, well under 623 cap); pydoclint zero
│       violations; file-size budget OK; bootstrap-order OK.
│
│       Locked design picks (binding): HOME-first IA;
│       expanded rail by default; Lens + dbt stay as their own
│       BUILD entries; footer always visible (no hide toggle).
│
├── Phase 76 — Full Social Network for Data Products       ✅ done 2026-05-13
│   │
│   │   Six sub-sprints landed in one autonomous session +
│   │   two close-out polish commits.  Lifted the Phase-71–74
│   │   "agent-aware social layer" into a full social network:
│   │   deeper threading, GitHub-style reactions, topics as a new
│   │   entity-class, separate user + agent profiles, per-user
│   │   feed, granular notification preferences, real-time SSE
│   │   bell, cross-DP citations.  Every social write stays an
│   │   ``audit_log`` row + CloudEvent so the Phase-18.7 FTS and
│   │   Phase-20 SIEM pipeline pick the action up.  9 new tables,
│   │   6 alembic migrations (``p7r9..u2w4``), 1 new background
│   │   loop, 6 new HTML pages, ~104 new pytest cases.
│   │
│   ├── Phase 76.1 — Deeper conversations             ✅ (511df5e)
│   │       Threading depth 2 → 5 with app-level walk-the-chain
│   │       check, 6-emoji reactions on comments + DPs (canonical
│   │       👍 ❤️ 🎉 😄 😕 👀), category enum (general / question
│   │       / announcement / idea) with accept-answer atomic per
│   │       thread, ``@display_name`` mention resolution with
│   │       audit row on ambiguity, ``GET /api/users/search?q=``.
│   │       33 pytest cases.
│   │
│   ├── Phase 76.2 — Profiles + user-to-user follows  ✅ (037ccc8)
│   │       ``/users/{id}`` 5-tab profile (Overview / Stewarded /
│   │       Following / Comments / Reviews), user_follows with
│   │       50-per-hour rate-limit, sticky badge awards via new
│   │       24 h ``_user_badges_loop`` (steward_3plus,
│   │       reviewer_100plus, mention_magnet, accepted_answer,
│   │       endorser).  Topbar dropdown links to ``/users/me``.
│   │       12 pytest cases.
│   │
│   ├── Phase 76.3 — Topics taxonomy                  ✅ (cc6e1c4)
│   │       ``topics`` + ``data_product_topics`` +
│   │       ``user_topic_follows`` tables; ``/topics`` index +
│   │       ``/topics/{slug}`` detail; steward-managed
│   │       DP↔topic replace-all via
│   │       ``PUT /api/data-products/{c}/{s}/topics``; fan-out
│   │       on ``topic.dp_added`` to topic followers.  Topbar
│   │       ``Topics`` link.  13 pytest cases.
│   │
│   ├── Phase 76.4 — /feed + notification preferences ✅ (2629011)
│   │       ``/feed`` merge of inbox + followed users / DPs /
│   │       topics with cursor pagination + FTS over the
│   │       discussion-mirrored audit_log.  ``users.notification_prefs_json``
│   │       JSON map of ``{event_type: {inbox, email, webhook}}``
│   │       drives per-event-type opt-out.
│   │       ``/settings/notifications`` page.  9 pytest cases.
│   │
│   ├── Phase 76.5 — Agents as first-class actors     ✅ (a573e37)
│   │       ``agents`` table (workspace-scoped slug, verified
│   │       badge, principal_user_id accountability chain).
│   │       ``/agents`` + ``/agents/{slug}`` 4-tab profile.
│   │       ``?as_agent=<slug>`` on the comment POST — the
│   │       agent's principal_user (or admin) may post under the
│   │       agent identity.  ``author_user_id`` stays NOT NULL
│   │       (always the human accountable), ``author_agent_id``
│   │       is the optional presentation-layer override.
│   │       Audit detail JSON carries both ids.  14 pytest cases.
│   │
│   ├── Phase 76.6 — SSE bell + cross-DP citations    ✅ (9c6534f)
│   │       ``GET /api/notifications/stream`` long-lived SSE
│   │       endpoint with 25 s keep-alive comment; module-level
│   │       ``_LISTENERS`` registry fan-out from the
│   │       notifications service.  ``EventSource`` consumed by
│   │       the topbar bell with the existing 60 s poll left in
│   │       place as fallback.  Render-time resolution of
│   │       ``#dp:cat.sch``, ``#topic:slug``, ``#user:email``,
│   │       ``#agent:slug`` tokens — unresolved tokens degrade to
│   │       literal text.  10 pytest cases.
│   │
│   ├── Phase 76.5.1 — as_agent on endorsements + reviews  ✅ (close-out)
│   │       Closed the original-plan corner the autonomous run
│   │       deferred.  Migration ``u2w4y6a8c0e3`` adds
│   │       ``applied_by_agent_id`` on endorsements,
│   │       ``author_agent_id`` on reviews, ``agent_slug`` on
│   │       ``data_product_active_reviewer_configs``.  Helper
│   │       ``resolve_agent_for_principal`` lifted into
│   │       ``data_products_routes/_shared.py`` so all three
│   │       write surfaces enforce one principal-or-admin gate.
│   │       Active Reviewer v2 now stamps the agent identity
│   │       on the comment + endorsement when ``agent_slug`` is
│   │       set; NULL falls back to the steward-proxy path.
│   │       Hygiene fixes: 3 bare-http-ok markers
│   │       (``users_routes/profile.py``), 2 bare-broad-ok
│   │       markers (``topics_routes/detail.py``,
│   │       ``users_routes/follows.py``),
│   │       ``data_products_routes/comments.py`` added to the
│   │       file-size allowlist after the helper extraction.
│   │       11 new pytest cases.
│   │
│   └── Phase 76.6.1 — Alpine helper JS modules       ✅ (17eebb1)
│       Two ``frontend/js/*.js`` modules.
│       ``mention_autocomplete.js`` provides ``@`` / ``#dp:`` /
│       ``#topic:`` / ``#agent:`` typeahead on
│       ``<textarea data-mention-autocomplete>`` — debounced
│       200 ms, arrow / Enter / Tab pick, inserts the canonical
│       token.  ``comments_collapse.js`` auto-collapses
│       ``data-pql-comment-depth >= 3`` rows with a
│       "Show N more replies" toggle on the depth-2 anchor —
│       forward-compatible: current Alpine renders 2 levels so
│       the script is a no-op until a recursive renderer lands.
│       Three endpoints (``/api/data-products``, ``/api/topics``,
│       ``/api/agents``) now accept ``?q=<prefix>`` for the
│       picker.  Smoke-parse via ``node -c`` covers both
│       modules.  2 pytest cases.
│
├── Phase 75 — Verifiable audit export + SIEM sinks         ✅ done 2026-05-15
│   │
│   │   Two ⏳-promoted Icebox items.  Compliance-grade export
│   │   (sha256 + manifest) + the two SIEM sink types
│   │   container-deploys + ELK consumers ask for.  The third
│   │   Icebox item (action-string rename to ``resource.verb``)
│   │   stays 🧊 — ROADMAP gates it on a version-bump moment.
│   │
│   ├── Sprint 75.1 — Verifiable audit export                   ✅ 2026-05-15
│   │       New ``pointlessql audit-export`` typer subcommand
│   │       (``cli/audit_export.py``) writes three mode-0600
│   │       files: data (json|csv), ``.sha256`` sidecar
│   │       (sha256sum-compatible), ``.manifest.json``
│   │       (schema_version + tool_version + filters +
│   │       entry_count + data_sha256 + data_filename).
│   │       New web variant
│   │       ``GET /admin/audit/export.tar.gz`` streams the same
│   │       trio gzipped — admins click "Download with
│   │       manifest" instead of running the CLI.  Auditors
│   │       verify integrity by ``sha256sum -c`` +
│   │       manifest.data_sha256 cross-check.  6 pytest cases.
│   │
│   └── Sprint 75.2 — Stdout-JSON + Syslog audit sinks          ✅ 2026-05-15
│           New alembic ``n0p2r4t6v8x0`` extends
│           ``ck_audit_sinks_type`` to allow ``stdout_json`` +
│           ``syslog`` alongside the existing trio.
│           ``stdout_json`` writes one JSON line per envelope
│           (config: ``stream='stdout'|'stderr'``) for
│           container-log harvesters (Loki / Fluent Bit /
│           Vector).  ``syslog`` ships RFC-3164/5424 datagrams
│           via :mod:`logging.handlers.SysLogHandler` over
│           UDP/TCP (config: ``address='host:port'``,
│           ``protocol='udp'|'tcp'``, ``facility``,
│           ``severity``).  TLS terminates at a local rsyslog
│           sidecar by convention.  Both sinks swallow OSError
│           on emit — audit_log row stays authoritative.  8
│           pytest cases.
│
├── Phase 66 — Browser Notebook editor v2                  ✅ done 2026-05-10
│   │
│   │   The browser notebook editor, deleted in the agent-first
│   │   pivot of 2026-04-24 (commits ``bc2ad07`` + ``ac5207e``),
│   │   returns — rebuilt around the marker grammar
│   │   (``# %%`` jupytext + FNV-1a-64 content_hash), the async
│   │   kernel-bridge runtime (``KernelRegistry`` +
│   │   ``KernelSession``), and the persisted-output replay tables
│   │   that all survived the deletion.  The new surface is a
│   │   cell-by-cell editor at ``/notebooks/edit/{path}`` backed
│   │   by per-cell CodeMirror v6 instances (no vendored bundles
│   │   — esm.sh import-map only) and a JSON-RPC WebSocket bridge
│   │   at ``/ws/notebook/kernel`` (execute / interrupt / restart).
│   │
│   │   Three lessons from the Phase-12.6/12.10/12.12 catastrophe
│   │   are encoded directly in the architecture:
│   │
│   │   1. **One CodeMirror instance per cell.**  No shared mutable
│   │      EditorView; the per-cell ``cellEditor()`` factory carries
│   │      its own closure-scoped state so cells cannot cross-talk.
│   │   2. **Output zone in its own DOM subtree.**  Phase 12 had
│   │      output rendered inline inside the same Codemirror host
│   │      and the cursor-sync bugs were unsolvable.  Output now
│   │      lives in a sibling ``<div>`` rendered as DOM (or a
│   │      sandboxed iframe for ``text/html`` / ``image/svg+xml``).
│   │   3. **No PointlesSQL-specific tokens in the file.**  The
│   │      marker grammar is pure jupytext-Percent; cell identity
│   │      is the FNV-1a-64 content_hash computed at load time.
│   │      Files stay generically VSCode/Vim-editable.
│   │
│   ├── Sprint 66.0 — Foundation: WS route + KernelRegistry +
│   │       Notebook CRUD                                       ✅ 2026-05-10
│   │       Re-introduces the deleted /ws/notebook/kernel route
│   │       around the surviving KernelRegistry + KernelSession.
│   │       JSON-RPC frame shape (execute / interrupt / restart);
│   │       persisted outputs land in notebook_outputs +
│   │       notebook_cell_runs via the existing service helpers.
│   │       Notebook CRUD restored: POST /api/notebooks/create,
│   │       POST /api/notebooks/rename, DELETE /api/notebooks/delete.
│   │       13 pytest.
│   ├── Sprint 66.1 — Frontend skeleton + load route          ✅ 2026-05-10
│   │       GET /api/notebooks/load returns parsed cells +
│   │       persisted outputs.  GET /notebooks/edit/{path:path}
│   │       renders the editor HTML page rooted at the new
│   │       notebookEditor() Alpine factory.  Per-cell CodeMirror
│   │       v6 instances mounted lazily after Alpine's x-for
│   │       paints; no SQL-editor-specific extensions yet.
│   │       7 pytest.
│   ├── Sprint 66.2 — Save round-trip + dirty tracking        ✅ 2026-05-10
│   │       POST /api/notebooks/save serialises cells back to
│   │       the .py file via _doc.save_document; returns
│   │       refreshed FNV-1a-64 content_hashes.  Optional
│   │       expected_mtime triggers 409 conflict detection so
│   │       the browser can reload before overwriting.  Cmd+S
│   │       keymap, save indicator (Unsaved → Saving → Saved),
│   │       per-cell dirty pill.  6 pytest.
│   ├── Sprint 66.3 — Cell execution via WebSocket + outputs  ✅ 2026-05-10
│   │       createKernelClient() — JSON-RPC client for the WS
│   │       route.  renderOutputFrame() — MIME-bundle priority
│   │       renderer (image/png|jpeg → <img>, image/svg+xml +
│   │       text/html → sandboxed iframe, application/json →
│   │       <pre>, text/plain → <pre>, error → red-bordered
│   │       traceback).  notebookEditor.runCell() refreshes
│   │       FNV-1a-64 hash client-side, executes via WS, routes
│   │       iopub frames to the per-cell output zone.  Persisted
│   │       outputs replay on load.  Toolbar: kernel-status pill,
│   │       Interrupt + Restart buttons.  1 integration pytest
│   │       (real ipykernel spawn, end-to-end execute round-trip).
│   ├── Sprint 66.4 — Cell management ops                      ✅ 2026-05-10
│   │       Client-side ops: addCellAbove, addCellBelow,
│   │       addCellAtEnd, deleteCell, moveCellUp, moveCellDown,
│   │       convertCellType.  Per-cell toolbar: insert above /
│   │       below, move up / down, delete, cell-type dropdown.
│   │       Empty-state CTA + bottom "Add cell" footer.
│   │       4 pytest verifying save → load preserves layout
│   │       under each op.
│   ├── Sprint 66.5 — SQL cells (`# %% [sql] df`)              ✅ 2026-05-10
│   │       Alembic ``hh7i9k1m3o5q`` adds query_history.notebook_path
│   │       + notebook_content_hash columns.  build_kernel_wrapper()
│   │       wraps raw SQL with __pql_sql_run(...) (validates
│   │       result_var as identifier, repr()-escapes SQL).
│   │       resolve_approved_tables() runs prepare_sql + per-ref
│   │       privilege check + storage-location lookup.  WS handler
│   │       routes execute frames carrying cell_type='sql' through
│   │       the wrapper, captures (raw_sql, approved_tables) per
│   │       (content_hash, kernel_session_id), and on the matching
│   │       execute_reply writes a query_history row with
│   │       notebook_path + notebook_content_hash.  Browser exposes
│   │       a result_var input on SQL cells.  8 pytest.
│   ├── Sprint 66.6 — Markdown cells with edit/view toggle    ✅ 2026-05-10
│   │       POST /api/notebooks/render-markdown: server-side render
│   │       via the existing markdown-it-py CommonMark renderer
│   │       (html=False so embedded <script> / <iframe> escapes at
│   │       parse time).  Markdown cells default to view-mode after
│   │       load; click on the rendered HTML or Enter (focused)
│   │       enters edit-mode; Shift+Enter or Esc renders + returns
│   │       to view-mode.  5 pytest.
│   ├── Sprint 66.7 — Keyboard model + autosave + history      ✅ 2026-05-10
│   │       Shift+Enter (run + focus next; insert if last),
│   │       Ctrl/Cmd+Enter (run + stay), Esc on a markdown cell
│   │       exits edit-mode.  5-second debounced autosave on any
│   │       cell-source change.  GET /api/notebooks/cell-history
│   │       returns the last N NotebookCellRunSource rows for
│   │       (path, content_hash); per-cell toolbar history-icon
│   │       button toggles an inline popover with status pill +
│   │       execution_count + started_at.  4 pytest.
│   └── Sprint 66.8 — Phase close                              ✅ 2026-05-10
│           ROADMAP + CHANGELOG + memory entry +
│           docs/e2e-walkthroughs/notebook-overview.md (Browser
│           Mode).  Walkthrough README playbook count refreshed
│           to 59.  Final pytest sweep all-green.
│
├── Phase 67 — Notebook Operations (Schedule / Parametrize / Inspect)  ✅ done 2026-05-12
│   │
│   │   Phase 66 shipped the live cell-by-cell editor; Phase 67
│   │   closes the DBX-Notebook gap by wiring four surfaces on top
│   │   of the existing scheduler / papermill / kernel-session
│   │   stack — without duplicating any of it.  The papermill
│   │   executor + cron loop + Job/JobRun tables + jobs.html page
│   │   were already production; Phase 67 is the editor-side
│   │   verkabelung that finally lets a user schedule a notebook
│   │   without leaving the editor.
│   │
│   │   The four shipped surfaces:
│   │
│   │   1. **Schedule-from-Notebook** — Toolbar "Schedule" button →
│   │      modal pre-built from ``papermill.inspect_notebook`` →
│   │      POST /api/jobs with kind="papermill"; new job lands in
│   │      /jobs + writes a notebook_job_link row for editor look-up.
│   │   2. **Parametrized runs** — Mark a code cell as papermill
│   │      ``parameters`` via the jupytext-canonical
│   │      ``tags=["parameters"]`` marker (round-trip-stable through
│   │      load → save → reopen, byte-identical).  Schedule + Run-
│   │      once modals render a typed override form per declared
│   │      parameter.
│   │   3. **Run-Once-with-Parameters** — Editor "Run as job" creates
│   │      a paused permanent job + fires execute_run as a fire-and-
│   │      forget asyncio task; browser polls /api/jobs/{id}/runs
│   │      (new listing endpoint) until terminal.  Keeps a full
│   │      audit-trail row.
│   │   4. **Variable Inspector** — Live side-pane refreshes after
│   │      every cell run.  Kernel bootstrap learns
│   │      ``__pql_inspect__()`` + ``__pql_inspect_detail__()`` that
│   │      emit a custom ``application/x-pql-vars+json`` MIME bundle
│   │      the WS pump routes to a dedicated ``variable_snapshot``
│   │      notify (NOT persisted to notebook_outputs — transient).
│   │      Click a variable → detail view with truncated repr +
│   │      DataFrame ``_repr_html_()`` head when applicable.
│   │
│   │   Anchor-decisions (preserved from the plan):
│   │
│   │   - **No new job-runner**.  papermill stays the single headless
│   │     execution path; ``_papermill_executor`` already converts
│   │     ``.py`` → ``.ipynb`` on-the-fly via jupytext so the
│   │     canonical ``.py``-with-jupytext-markers invariant holds.
│   │   - **Cell tags = metadata**.  ``compute_content_hash`` ignores
│   │     ``cell.tags`` so toggling the parameters flag does not
│   │     rewrite cell identity (kept run history stable).
│   │   - **One link table, opportunistic writes**.  Phase 67.4's
│   │     ``notebook_job_link`` table is a derived index; ``Job.config``
│   │     stays canonical so a stale link row at worst shows a phantom
│   │     entry in the editor panel.
│   │   - **Job-output bridge re-uses notebook_outputs**.  Papermill
│   │     output cells land at ``kernel_session_id = "job:<run_id>"``
│   │     so both the editor reload-replay and a future "view job
│   │     outputs" tab share one render path.
│   │
│   ├── Sprint 67.0 — Marker grammar: `tags=[...]` parsing       ✅ 2026-05-12
│   │       ``_MARKER_RE`` extended with optional
│   │       ``tags=["a","b"]`` suffix; ``NotebookCell.tags`` field
│   │       added (frozen tuple, default ``()``);
│   │       ``_scan_marker_extensions`` returns
│   │       ``(tag, result_var, tags)`` triples.  Save path
│   │       ``_rewrite_cell_markers`` emits the canonical marker
│   │       line for every cell whose marker needs PointlesSQL-side
│   │       polish (SQL ``result_var`` and/or ``tags=[…]``).
│   │       ``compute_content_hash`` is **unchanged** — tags are
│   │       metadata, not source.  10 pytest.
│   ├── Sprint 67.1 — Inspect endpoint hardening + plumbing     ✅ 2026-05-12
│   │       ``GET /api/notebooks/inspect`` learns ``.py`` ⇒
│   │       jupytext + nbformat-tempfile convert ⇒
│   │       ``papermill.inspect_notebook``; canonical
│   │       ``kernelspec`` stamped so papermill's Jinja default
│   │       rewrites succeed.  Browser ``loadParameters()`` cached
│   │       in Alpine state + tiny "N params" toolbar badge so the
│   │       user knows the notebook has overridable inputs.  5
│   │       pytest.
│   ├── Sprint 67.2 — Schedule-from-Notebook modal              ✅ 2026-05-12
│   │       Editor toolbar gains "Schedule" + "Run as job" +
│   │       "Jobs" + "Variables" buttons.  Schedule modal
│   │       (``:class="{'d-block': flag}"`` per the feedback memory
│   │       on Bootstrap modal + Alpine x-show) submits to the
│   │       existing ``POST /api/jobs`` with kind="papermill" +
│   │       config={notebook_path, parameters} + cron 5-field
│   │       client-side check.  Uses existing ``pqlHumanizeCron``
│   │       for the human-readable hint.  Zero backend change.
│   ├── Sprint 67.3 — Run-Once-with-Parameters                  ✅ 2026-05-12
│   │       New ``POST /api/notebooks/run-once`` creates a paused
│   │       Job + fires ``execute_run`` via ``asyncio.create_task``;
│   │       returns ``{job_id, job_run_id, status: "started"}``.
│   │       New ``GET /api/jobs/{id}/runs`` listing endpoint feeds
│   │       the browser-side polling loop (exponential backoff
│   │       0.5 → 5 s, 240-iter cap).  Audit-row written via
│   │       ``audit("run_once_notebook")``.  9 pytest (5 run-once +
│   │       4 list-runs).
│   ├── Sprint 67.4 — Notebook-Jobs panel + link table          ✅ 2026-05-12
│   │       Alembic ``i9j1k3m5o7q9_notebook_job_link.py`` adds
│   │       ``notebook_job_link(id, workspace_id, notebook_path,
│   │       job_id, created_at)`` + three indexes (notebook_path,
│   │       (workspace_id, notebook_path), job_id).  POST /api/jobs
│   │       + POST /api/notebooks/run-once write a link row
│   │       opportunistically when kind="papermill".  New
│   │       ``GET /api/notebooks/jobs?path=…`` returns
│   │       ``{scheduled_jobs, recent_runs}`` joined through the
│   │       link.  Collapsible "Jobs ▾" toolbar button +
│   │       in-editor panel listing scheduled jobs + last 10 runs.
│   │       7 pytest.
│   ├── Sprint 67.5 — Variable Inspector (live + auto-refresh)  ✅ 2026-05-12
│   │       Kernel bootstrap ``_NOTEBOOK_BOOTSTRAP_CODE`` extended
│   │       with ``__pql_inspect__()`` + ``__pql_inspect_detail__()``
│   │       (excludes dunder / modules / plain callables; classes +
│   │       DataFrames + sequences kept with shape/len hints).
│   │       WS pump ``_handle_kernel_message`` intercepts
│   │       ``application/x-pql-vars+json`` and
│   │       ``application/x-pql-vardetail+json`` and routes them as
│   │       dedicated ``variable_snapshot`` / ``variable_detail``
│   │       notify frames — NOT persisted in ``notebook_outputs``.
│   │       After every ``execute_reply`` the editor sends a silent
│   │       ``execute("__pql_inspect__()")`` via the existing
│   │       JSON-RPC client; click on a variable triggers a detail
│   │       fetch with HTML head when the variable has
│   │       ``_repr_html_()``.  11 pytest (bootstrap-eval style with
│   │       monkey-patched ``IPython.display``).
│   ├── Sprint 67.6 — Job-Run-Output ↔ notebook_outputs bridge  ✅ 2026-05-12
│   │       ``_papermill_executor`` post-execute path now reads the
│   │       result ``.ipynb`` via nbformat, computes
│   │       ``compute_content_hash`` per cell-source, and persists
│   │       every output row to ``notebook_outputs`` with
│   │       ``kernel_session_id = "job:<run_id>"``.  Idempotent
│   │       (clear-then-append) so retries replace prior rows
│   │       cleanly.  5 pytest (stream + execute_result + idempotent
│   │       + skip-markdown + missing-file no-op +
│   │       content-hash-lookup).
│   ├── Sprint 67.7 — Param-cell UI-Branding                    ✅ 2026-05-12
│   │       ``cellLabel(cell)`` renders "PARAMS" / "SQL · PARAMS" /
│   │       "Markdown · PARAMS" when the cell carries the
│   │       ``parameters`` tag.  Per-cell toolbar gains a
│   │       "Mark/Unmark as parameters" menu entry that toggles
│   │       ``cell.tags`` + flips ``_dirty`` + triggers the
│   │       autosave debouncer.  ``GET /api/notebooks/load`` +
│   │       ``POST /api/notebooks/save`` carry the ``tags`` list
│   │       in both directions.  3 pytest (mark + unmark +
│   │       end-to-end inspect-sees-tag).
│   └── Sprint 67.8 — Phase close                              ✅ 2026-05-12
│           ROADMAP + CHANGELOG + memory entry +
│           docs/e2e-walkthroughs/notebook-jobs.md + docs/features/
│           notebook-jobs.md.  Walkthrough README playbook count
│           refreshed to 60.  Final pytest sweep + ruff + pydoclint
│           + alembic check all-green.  Pyright budget: pre-existing
│           reportLiteralAssignment error at notebook_kernel_ws:361
│           (unrelated to Phase 67) carried forward.
│
├── Phase 68 — Frontend modularization (HTML + JS + CSS hygiene)  ✅ done 2026-05-12
│   │
│   │   Frontend grew over 50+ sprints and accumulated two structural
│   │   schwächen that made LLM-context lookups more expensive than
│   │   needed: 6 templates >500 LOC and two parallel partial
│   │   conventions side-by-side (top-level ``partials/`` vs
│   │   page-scoped ``pages/_partials/``).  Phase 68 applies the
│   │   Phase-38 split-into-partials playbook to the remaining large
│   │   templates and unifies the partial convention.  No behaviour
│   │   change — pure structural reorganization.
│   │
│   │   Anchor-decisions:
│   │
│   │   - **``notebook_editor.js`` (939 LOC) stays single-file.**  8
│   │     real feature seams but Alpine state tight-coupled across
│   │     them.  Defer split until a feature delivers a clean anchor.
│   │   - **Nested per-page partial layout** —
│   │     ``pages/_partials/<page>/<sub>.html``.  Verworfen: flat-
│   │     with-prefix.  Grep on one folder shows all sub-views of a
│   │     page; scales as more pages get split.
│   │
│   ├── Sprint 68.0 — Partials-Konvention vereinheitlichen     ✅ 2026-05-12
│   │       12 of 13 top-level partials waren single-page (alle
│   │       ``_run_*.html`` und ``_output_*.html``) — moved to
│   │       ``pages/_partials/run_view/`` und
│   │       ``pages/_partials/notebook/output/``.  Top-level
│   │       ``partials/`` behält nur 2 echt-cross-page Files
│   │       (``_cdf_change_type_pill.html``, ``_query_row.html``).
│   │       ~25 ``{% include %}`` Pfade aktualisiert.
│   ├── Sprint 68.1 — ``pages/table.html`` splitten            ✅ 2026-05-12
│   │       786 → 228 LOC.  7 Tab-Partials unter
│   │       ``pages/_partials/table/``: overview.html (~190),
│   │       preview.html (~100), columns.html (~160),
│   │       lineage.html (~10), tags.html (~7),
│   │       permissions.html (~12), cdf_events.html (~85).
│   ├── Sprint 68.2 — ``run_view/operations`` splitten         ✅ 2026-05-12
│   │       ``tab_operations.html`` 726 → 59 LOC.  5 Sub-Tab-
│   │       Partials unter
│   │       ``pages/_partials/run_view/operations/``:
│   │       operations.html (~195), rejects.html (~60),
│   │       queries.html (~70), rewrites.html (~89),
│   │       uc_mutations.html (~258).
│   ├── Sprint 68.3 — ``pages/model.html`` splitten            ✅ 2026-05-12
│   │       589 → 209 LOC.  4 Tab-Partials unter
│   │       ``pages/_partials/model/``: overview.html (~62),
│   │       versions.html (~104), lineage.html (~63),
│   │       promotion.html (~155).
│   ├── Sprint 68.4 — Federation-JS in ``js/pages/federation/`` ✅ 2026-05-12
│   │       3 admin-only JS-Files (``federation_catalogs.js``,
│   │       ``_connections.js``, ``_credentials.js``) per ``git mv``
│   │       in ``js/pages/federation/`` einziehen.
│   │       ``bootstrap.js``-Importe angepasst; Window-attached
│   │       Namen unverändert, kein Template-Change.
│   ├── Sprint 68.5 — sql_editor inline CSS extrahieren        ✅ 2026-05-12
│   │       ``pages/sql_editor.html`` 543 → 397 LOC.  146 LOC
│   │       inline ``<style>`` → ``frontend/css/components/
│   │       sql_editor.css`` (Operator-Badges + Layout-Fixes);
│   │       ``style.css`` @import in alphabetic cascade-position.
│   ├── Sprint 68.6 — ``notebook.css`` lazy-load               ✅ 2026-05-12
│   │       292 LOC CSS aus globalem ``style.css`` @import-cascade
│   │       entfernt, stattdessen via ``{% block extra_css %}``
│   │       in ``pages/notebook_editor.html`` lazy geladen.
│   │       Notebook-only Selektoren erscheinen nicht mehr im
│   │       LLM-Context jeder Nicht-Notebook-Page.
│   └── Sprint 68.7 — Conventions doc + Phase-Close            ✅ 2026-05-12
│           Neue ``docs/development/frontend-conventions.md``
│           (in mkdocs nav).  ``frontend/js/README.md`` um
│           Folder-Layout-Section ergänzt.  ROADMAP +
│           CHANGELOG + Memory.  Pytest sweep grün auf den
│           berührten Surfaces (table-detail, run-view,
│           model-detail, sql-editor, notebook-editor,
│           federation); Browser-Replay als nächste Session-
│           Aufgabe ausstehend.
│
├── Phase 69 — Vollständiger Browser-Replay der Plattform     ✅ done 2026-05-12
│   │
│   │   Browser-replay sweep of every UI surface across multiple
│   │   user roles + config flips, primarily to verify Phase 68's
│   │   structural HTML/CSS/JS reorganization landed cleanly.  All
│   │   work on the ``docker/docker-compose.e2e.yml`` stack with the
│   │   ``scripts/seed-e2e.py`` baseline.  ~20 wave-shaped passes;
│   │   3 bugs found, 1 fixed in-band (BUG-69-03), 1 cascade
│   │   (BUG-69-02), 1 deploy-hygiene (BUG-69-01) documented.
│   │
│   │   Phase-68 surfaces re-verified end-to-end:
│   │
│   │   - **68.1 / table.html** — all 7 tab partials render
│   │     (Overview / Preview / Columns / Lineage / Tags /
│   │     Permissions + conditional CDF Events tab gated on
│   │     ``{% if cdf_subscription %}``).
│   │   - **68.0+68.2 / run_view operations** — all 4 top tabs
│   │     (Overview / Operations / Lineage / Audit) plus all 5
│   │     Operations sub-tabs (Operations / Rejects / Queries /
│   │     Rewrites / UC mutations) render with 0 console errors.
│   │   - **68.3 / model.html** — all 4 tab partials render
│   │     (Overview / Versions / Lineage / Promotion) on a stub
│   │     ``demo_ml.silver.churn`` model created via soyuz UC API.
│   │   - **68.4 / federation JS move** — all 3 modals (new
│   │     Connection / Credential / Foreign Catalog) open
│   │     cleanly after fixing BUG-69-03 (broken relative
│   │     imports).
│   │   - **68.5 / sql_editor.css extract** — confirmed
│   │     ``/static/css/components/sql_editor.css`` 200 + cascade
│   │     ``@import`` in ``style.css``.
│   │   - **68.6 / notebook.css lazy-load** — confirmed
│   │     ``notebook.css`` loads only on
│   │     ``/notebooks/edit/<path>`` and is absent on all 6
│   │     non-notebook surfaces sampled.
│   │
│   │   Non-Phase-68 surfaces smoke-tested with 0 errors:
│   │   ``/`` / ``/runs`` / ``/sql`` / ``/notebooks/workspace`` /
│   │   ``/models`` / ``/branches`` / ``/audit/inbox`` /
│   │   ``/audit/by-table`` / ``/volumes`` / ``/alerts`` /
│   │   ``/dashboards`` / ``/data-products`` / ``/jobs`` /
│   │   ``/dbt`` + 9 ``/admin/*`` surfaces (CDF subscriptions
│   │   sits at ``/admin/cdf-subscriptions``, not
│   │   ``/admin/cdf-tail`` as the plan-doc had it).
│   │
│   │   Persona + config matrix verified:
│   │
│   │   - admin@pql.test (full privileges) — every surface.
│   │   - flo@pql.test (member) — 9 admin URLs + 3 federation
│   │     URLs all return 403; ``/sql`` + ``/runs`` accessible.
│   │   - Bearer-key (supervisor + auditor + lineage_inbound)
│   │     via ``Authorization: Bearer <secret>`` — audit
│   │     aggregates returned 200 / 422 (auth pass, params
│   │     incomplete).  Key generated via ``/admin/api-keys``
│   │     and revoked at session end.
│   │   - OIDC config flip via ``POINTLESSQL_OIDC_*`` env +
│   │     ``mock-oidc`` sidecar — ``/auth/login`` gains
│   │     "Sign in with SSO" button as the visible marker.
│   │
│   ├── BUG-69-01 — asset_version not bumped on Phase 68
│   │       rebuild → Firefox ES-module cache served stale
│   │       bootstrap.js.  Deploy-hygiene fix: bump version
│   │       string whenever ``frontend/`` changes.  Phase-69
│   │       replay temporarily bumped to 0.1.0rc5; reverted
│   │       at close.  Documented in
│   │       ``docs/e2e-walkthroughs/federation.md``.
│   ├── BUG-69-02 — command-palette backdrop intercepted
│   │       clicks after BUG-69-01 broke Alpine init.  Pure
│   │       cascade; resolves automatically once asset_version
│   │       bump unblocks module imports.
│   └── BUG-69-03 — fixed in this commit-range.
│           ``frontend/js/pages/federation/{connections,
│           credentials,catalogs}.js`` had stale
│           ``import './editor_base.js'`` after Phase 68.4's
│           ``git mv`` to ``js/pages/federation/`` — now
│           ``../../editor_base.js``.  Without this fix, every
│           page-load fired a 404 + cascaded into BUG-69-02.
│
├── Phase 70 — Notebook track (member-access + JS-split)        ✅ done 2026-05-12
│   │
│   │   Two thematically linked notebook concerns bundled into
│   │   one phase: drop the Phase-12.12 admin-only restriction
│   │   on the notebook editor + defensive split of the 939-LOC
│   │   ``notebook_editor.js`` monolith.  Plan in
│   │   ``.claude/plans/ja-plane-phase-28-tidy-feather.md``.
│   │
│   ├── 70.1 — ``require_user`` dep + 11+2 notebook routes
│   │       flipped from ``require_admin`` to ``require_user``
│   │       (+ WebSocket ``_user_can_use_editor`` broadened to
│   │       accept any authenticated user).  Adds a new sibling
│   │       to ``require_admin`` / ``require_supervisor`` etc.
│   │       in ``api/dependencies.py``; explicit ``require_user``
│   │       call sites keep the auth intent grep-able instead of
│   │       silently dropping the gate.
│   ├── 70.2 — ``permission_link`` macro calls for the Workspace
│   │       icon-rail (``icon_rail.html:62``) and nav-links
│   │       entry (``nav_links.html:51``) replaced with direct
│   │       ``<a href>`` tags.  Branches (sidebar.html:36) and
│   │       Admin (icon_rail.html:147 / nav_links.html:86)
│   │       stay permission-gated.
│   ├── 70.3 — Five non-admin-forbidden notebook tests flipped
│   │       from ``assert status_code == 403`` to expect 200
│   │       + JSON-shape assertions (tree, workspace page, load,
│   │       editor page, save).
│   ├── 70.4 — Extract ``jobs_orchestration.js`` (190 LOC):
│   │       Schedule + Run-Once modals, Notebook-Jobs panel,
│   │       ``_pollJobRun``.  Plugin-mixin pattern follows
│   │       Phase-68.2 run_view split — ``installXxx(state, deps)``
│   │       mutates the shared Alpine state.  Coordinator
│   │       drops 939 → 755 LOC.
│   ├── 70.5 — Extract ``kernel_execution.js`` (208 LOC):
│   │       WS kernel client, cell-run lifecycle (run / interrupt
│   │       / restart), Variable Inspector helpers.  Coordinator
│   │       drops 755 → 572 LOC.
│   ├── 70.6 — Extract ``cell_operations.js`` (146 LOC):
│   │       add/delete/move/convert cells + per-cell editor
│   │       lifecycle.  Coordinator drops 572 → 446 LOC.
│   ├── 70.7 — Two-in-one: extract ``markdown_output.js``
│   │       (122 LOC, output renderer + markdown edit/view +
│   │       cell-editor mount) and ``persistence.js`` (144 LOC,
│   │       save/autosave/keymap + params-tag toggle + cell
│   │       run-history).  Coordinator drops 446 → 190 LOC and
│   │       now holds only the state defaults, init/destroy,
│   │       and five ``install*()`` calls.
│   ├── 70.8 — Asset-version bump (``0.1.0rc3`` → ``0.1.0rc4``)
│   │       — seven JS files + two templates touched, so the
│   │       ``?v=`` cache-buster has to flip (see
│   │       ``feedback_asset_version_bump.md``).  Seven
│   │       additional non-admin notebook tests flipped (inspect,
│   │       jobs panel, run-once, render-markdown, cell-history,
│   │       crud-create) + the ``_user_can_use_editor`` WS gate
│   │       test removed (no longer reachable).  Pytest grün on
│   │       all notebook surfaces (22+ tests); 7 pre-existing
│   │       failures unrelated to Phase 70 left untouched.
│   └── 70.9 — Browser-replay carry-over (2026-05-12, autonomous
│           Playwright-MCP session).  Sprint 70.8's verification
│           gate was skipped in auto-mode; replayed against the
│           ``docker/docker-compose.e2e.yml`` stack with both admin
│           (``admin@pql.test``) and member (``flo@pql.test``)
│           personas.  Green on both: all 92 Alpine state keys
│           present (5 install functions wire correctly), all 9
│           notebook JS modules load 200, all six distinct
│           ``/api/notebooks/*`` route classes return 200 for the
│           member persona, ``/ws/notebook/kernel`` upgrades to
│           101 without the 4403 close-code, ``runCell`` +
│           ``addCellAtEnd`` + ``save`` + ``toggleInspector`` +
│           ``enterMarkdownEdit`` round-trip end-to-end.
│           Cross-page CSS regression gate (Sprint 68.6) holds:
│           ``notebook.css`` absent on ``/runs``, ``/sql``,
│           ``/admin``.  0 ``BUG-70`` surfaced, 0 console errors
│           (only pre-existing font-preload warning).  No new
│           fix-commits required; no asset-bump needed.
│
├── Hygiene wave H.1–H.7                                  ✅ closed 2026-05-12 (7 commits, local)
│   │
│   │   Seven autonomous hygiene tracks landed post-Phase-70 to
│   │   unstick the lint+type CI job (red since 2026-05-08) and
│   │   ship additive cleanups.  Plan in
│   │   ``.claude/plans/ja-plane-phase-28-tidy-feather.md``.  Final
│   │   gate state: pytest 2170 passed (0 failed, was 2151 passed
│   │   + 8 failed), ruff clean (was 14 errors), pyright 0 errors
│   │   / 581 warnings (was 28 / 585; budget formally 497 → 585),
│   │   pip-audit 0 vulnerabilities, alembic fresh-DB drift clean.
│   │
│   ├── H.7 — ROADMAP archive-trigger clarification (`5272e79`).
│   │       Rewrote the "When closed phases stack up" rule to make
│   │       it both line-count AND staleness (≥30d closed AND no
│   │       follow-up reference >3mo), with a worked 2026-05-12
│   │       example so future sessions don't auto-archive recent
│   │       load-bearing phases.
│   │
│   ├── H.5 — pip-audit CI gate + 11-CVE bump (`f940eb9`).  New
│   │       ``security-audit`` job runs ``uv run pip-audit
│   │       --skip-editable`` on every PR.  Bumped gitpython
│   │       3.1.49 → 3.1.50, mako 1.3.11 → 1.3.12, mistune 3.2.0 →
│   │       3.2.1, pip 26.0.1 → 26.1.1, python-multipart 0.0.26 →
│   │       0.0.28, urllib3 2.6.3 → 2.7.0 to clear 11 known CVEs.
│   │
│   ├── H.1 — 8 pytest + 14 ruff cleanup (`9aae419`).  Test fixes:
│   │       template-casing drift in ``test_register_page_renders``,
│   │       Sprint-68.3 dropped ``tab-mlflow`` so the help-popover
│   │       wires the "Open in MLflow UI" button instead, marker
│   │       comments on the bare-http + lossy-broad-except sites,
│   │       table-vs-cards drift in query_history (+ short-SQL
│   │       drawer-gate at 700 chars), saved_audit_queries heading
│   │       case.  Ruff fixes: 6 auto-fixed I001, 5 manual E501,
│   │       1 D417 + 1 F401.
│   │
│   ├── H.3 — notebook-walkthrough partial selector refresh
│   │       (`b17432c`).  19 Phase-12.12 route renames bulk-applied
│   │       (``/notebook/editor?path=`` → ``/notebooks/edit/``),
│   │       3 confirmed Phase-67 class renames
│   │       (``pql-nbedit-editor``/``-toolbar``/``-root`` →
│   │       ``pql-notebook-*``).  ~33 per-feature ``pql-nbedit-*``
│   │       selectors remain stale, gated by a ⚠️-banner at each
│   │       file's top pointing replay-drivers to DevTools.
│   │
│   ├── H.4 — Alembic PG-side drift gate (`db61793`).  Added
│   │       ``alembic check`` to the PG CI lane (SQLite had it
│   │       since Phase 30; PG-only didn't).  New
│   │       ``scripts/check-alembic-fresh-drift.sh`` for periodic
│   │       deeper checks (fresh upgrade + schema dump).
│   │
│   ├── H.6 — PG xdist enablement (`cf17824`).  Phase-31.4's
│   │       single-worker carve-out lifted.  ``conftest.py``
│   │       appends ``_<worker_id>`` to ``TEST_DATABASE_URL`` on
│   │       Postgres; CI provisions ``pointlessql_gw{0..3}`` then
│   │       runs ``pytest -n 4 --dist loadfile``.  Target speedup
│   │       ~7min → ~3min.
│   │
│   └── H.2 — Pyright triage 28 → 0 errors, budget 497 → 585
│           (`69e7fe8`).  Cleared by bucket: ``__all__`` +
│           per-import ignores on the 7 underscore-prefixed
│           ``_bootstrap/_loops.py`` coroutines; datetime narrowing
│           in ``lens/sessions.py``; dead hasattr-guard removal in
│           ``main.py``; ``QueryStatus`` enum vs Literal str in
│           ``notebook_kernel_ws.py``; 10 inline ignores on the
│           OpenAI/Anthropic SDK type-strict sites in
│           ``services/lens/*``.  Budget +88 documented as
│           PyArrow / DuckDB-result / OpenLineage stub-bottleneck.
│
├── Phase 65 — Lens (read-only Q&A surface, MCP + Browser parallel) ✅ done 2026-05-10
│   │
│   │   New analyst-facing chat-style surface that exposes read-only
│   │   data Q&A over two transports — a browser chat UI at ``/lens``
│   │   (BYO LLM key per workspace, Fernet-encrypted at rest) and an
│   │   MCP (Model Context Protocol) server on stdio for IDE
│   │   consumers (Claude Desktop, Cursor, Hermes-as-MCP-client).
│   │   Both transports share the same Pydantic-typed tool registry
│   │   (provenance, query, list_catalogs/_schemas/_tables,
│   │   describe_table, lineage_neighbors); audit-trail goes through
│   │   ``lens_messages`` + ``query_history.lens_session_id``.
│   │
│   │   New ``analyst`` scope on ``api_keys`` (auditor passes too as
│   │   superset).  Pure read-only enforcement — non-SELECT statements
│   │   raise at the AST validator before EXPLAIN; auto-LIMIT 1000
│   │   on every SELECT; per-query cost cap + per-session budget cap.
│   │   Pinned-answer flow lets analysts bookmark assistant answers
│   │   for stable-URL re-rendering.  Phase 13/39 power-mode write
│   │   tools stay parallel; Lens is the new default analyst surface.
│   │
│   ├── Sprint 65.0 — Foundation (DB + scope + skeleton)         ✅ 2026-05-10
│   │       Alembic ``ff5g7i9k1m3o``: lens_sessions + lens_messages
│   │       + lens_pinned_answers + lens_provider_creds tables;
│   │       ``api_keys.analyst`` boolean.  ``require_analyst()`` dep
│   │       (auditor + admin pass-through).  Service skeleton for
│   │       sessions/messages/provider-creds with Fernet roundtrip
│   │       via the existing ``system_keys`` master key.  10 pytest.
│   ├── Sprint 65.1 — Provenance tool (signature feature)        ✅ 2026-05-10
│   │       Unified ``provenance(table_fqn, row_id?, column?, ...)``
│   │       service folding row-edges (Phase 15) + column-map (15.6)
│   │       + value-changes (15.7) into one ProvenanceTrace shape
│   │       with four resolution modes (table / column / row /
│   │       row+value).  Direct browser route GET /api/lens/provenance.
│   │       12 pytest.
│   ├── Sprint 65.2 — Tool registry (shared backbone)            ✅ 2026-05-10
│   │       Pydantic-typed Lens tool registry + audit-hook wrapper
│   │       persisting every dispatch as a lens_messages tool-row.
│   │       Three provider-specific schema converters (OpenAI,
│   │       Anthropic, MCP).  Six built-in tools: provenance,
│   │       lineage_neighbors, list_catalogs/_schemas/_tables,
│   │       describe_table.  Alembic ``gg6h8j0l2n4p`` adds nullable
│   │       ``query_history.lens_session_id`` FK (batch_alter_table
│   │       for SQLite).  11 pytest.
│   ├── Sprint 65.3 — Auto-LIMIT + cost-gate + query tool         ✅ 2026-05-10
│   │       ``inject_limit()`` in pql.sql_parser auto-injects LIMIT
│   │       (preserves explicit LIMITs, rejects DML/DDL).
│   │       cost_gate.gate_query() composes prepare_sql + inject_limit
│   │       + EXPLAIN cost cap + per-session budget cap, raising
│   │       typed Lens*Error exceptions on each axis.  Wire ``query``
│   │       tool into the registry. 4 new ErrorCode StrEnum members.
│   │       12 pytest.
│   ├── Sprint 65.4 — MCP server (stdio + introspection routes)  ✅ 2026-05-10
│   │       FastMCP-backed Lens server exposes the tool registry
│   │       over stdio (canonical IDE-consumer transport).  HTTP
│   │       introspection routes /mcp/health + /mcp/info for
│   │       client-side connection probing.  ``pointlessql lens-mcp``
│   │       CLI subcommand.  /mcp/* added to PUBLIC_PREFIXES so the
│   │       auth middleware doesn't redirect IDE clients to login.
│   │       SSE FastMCP app shape exists (``build_lens_mcp_sse_app``)
│   │       but is not auto-mounted from the bootstrap (lifespan-time
│   │       mount deferred to follow-up).  Adds ``mcp[cli]`` dep.
│   │       12 pytest.
│   ├── Sprint 65.5 — Browser chat UI + LLM provider adapters    ✅ 2026-05-10
│   │       OpenAI + Anthropic SDK adapters wrapping chat.completions
│   │       / messages tool-calling.  ``run_chat_turn`` drives one
│   │       user→assistant round-trip with bounded tool-call iteration
│   │       (cap 8) + per-turn cost accounting.  /api/lens/sessions
│   │       CRUD, /api/lens/sessions/{id}/messages chat route,
│   │       /lens HTML chat page (Alpine.js, non-streaming JSON).
│   │       /api/admin/lens-providers JSON CRUD with Fernet-encrypted
│   │       upsert + decrypt-test.  Icon-rail entry between SQL and
│   │       Workspace.  Adds openai + anthropic deps.  12 pytest.
│   ├── Sprint 65.6 — Pinned answers + saved questions           ✅ 2026-05-10
│   │       /api/lens/pinned CRUD + /api/lens/pinned/{slug}/view
│   │       standalone HTML page.  Snapshot captures assistant text
│   │       + nearest-preceding query tool's executed SQL +
│   │       result_preview (first 20 rows) so pin survives source-
│   │       session deletion.  Owner+is_shared visibility analog
│   │       SavedQuery.  Slug-collision auto-suffix.  8 pytest.
│   │       Saved-questions surface (re-using SavedQuery for
│   │       question templates) deferred — pinned answers cover
│   │       the primary "find this answer again" use case.
│   ├── Sprint 65.7 — Walkthroughs + plugin tools + docs         ✅ 2026-05-10
│   │       lens-overview.md (browser-mode) + lens-mcp.md
│   │       (hermes-mode) walkthroughs.  hermes-plugin-pointlessql
│   │       gains pql_lens_ask + pql_lens_get_pinned (33→35 tools).
│   │       README playbook count refreshed to 58.
│   └── Sprint 65.8 — Phase close                                 ✅ 2026-05-10
│           ROADMAP + CHANGELOG + memory entry.  Final pytest
│           sweep all-green (77 lens-specific cases on top of
│           the 1782-test baseline).
│
├── Phase 64 — Permission-locked nav-link UX               ✅ done 2026-05-10
│   │
│   │   Admin-only navigation entries (Workspace + Admin in the
│   │   icon-rail, Branches in the catalog sidebar, Workspace +
│   │   Admin in the mobile drawer) used to be hidden via inline
│   │   ``{% if current_user.is_admin %}`` wrappers — a regular
│   │   user couldn't see they existed and therefore didn't know
│   │   what to ask the workspace admin for.  Phase 64 makes the
│   │   entries visible-but-locked: greyed out, lock-icon suffix,
│   │   ``aria-disabled="true"``; click / Enter / Space surface a
│   │   toast naming the missing role.  Backend authorisation is
│   │   unchanged — the routes still 403 if the dead ``href="#"``
│   │   is bypassed.  Single sprint, ~½ day.
│   │
│   ├── Sprint 64.1 — `permission_link` macro + delegated JS ✅
│   │       New ``frontend/templates/_macros/permission_link.html``
│   │       parameterised across the three call-site markups
│   │       (icon-rail's ``data-section`` + label-span,
│   │       sidebar's ``pql-context-panel__link``, nav-links'
│   │       plain-text label).  New
│   │       ``frontend/js/permission_link.js`` registers a single
│   │       document-level click + keyboard listener via
│   │       ``bootstrap.js``, calls
│   │       ``window.pqlToast.info("Requires <role> role —
│   │       contact your workspace admin.")``.  ``.permission-locked``
│   │       CSS class added to ``frontend/css/layout.css``
│   │       (opacity 0.55, ``cursor: not-allowed``).  Five
│   │       inline ``{% if %}`` wrappers replaced by macro calls
│   │       across icon_rail.html (2x), sidebar.html (1x), and
│   │       nav_links.html (2x).  User-menu admin badge stays
│   │       unchanged (status indicator, not a link); admin-page
│   │       internal cards + table-row action buttons explicitly
│   │       out of scope (eigene UX-Kategorie).
│
├── Phase 63 — Writeable SQL Editor (AST-dispatch refactor)  ✅ done 2026-05-10
│   │
│   │   The SQL editor was SELECT-only at
│   │   ``pointlessql/pql/sql_parser.py:385-391`` because the
│   │   DuckDB rewriter only made sense for SELECTs (DuckDB
│   │   reserves ``main`` as a catalog name and refuses to bind
│   │   3-part UC refs natively, so the parser has to extract
│   │   + rewrite source tables).  The audit infrastructure
│   │   (Phase 13 ``agent_run_operations``, Phase 14 external-
│   │   write detection, Phase 15.x lineage tables) was
│   │   already ready for write traffic — the only structural
│   │   gap was that interactive editor writes did not populate
│   │   ``query_history.agent_run_id``.  Phase 63 turns the
│   │   editor backend into an AST-classifying dispatcher that
│   │   routes each statement family to its correct typed
│   │   primitive, so editor writes land in the same audit
│   │   trail as Hermes-driven writes.
│   │
│   ├── Sprint 63.1 — Statement-type taxonomy + parser ✅
│   │       ``StmtType`` StrEnum, ``classify(ast)``,
│   │       ``extract_write_target`` / ``extract_source_refs``,
│   │       ``parse_and_classify``, ``parse_batch``.
│   │       ``_parse_root`` no longer rejects non-SELECT;
│   │       ``prepare_sql`` keeps SELECT-only via explicit
│   │       guard.  CREATE/DROP CATALOG parse as ``exp.Command``
│   │       in sqlglot — deliberately rejected (admin UI).
│   │       Bare ``CREATE TABLE`` rejected (use New Table form).
│   │       42 new pytest cases.
│   │
│   ├── Sprint 63.2 — pql.update + pql.delete primitives ✅
│   │       New ``pointlessql/pql/_update_delete.py`` wraps
│   │       ``DeltaTable.update`` / ``.delete`` (delta-rs
│   │       accepts SQL-string predicates).
│   │       ``pql.update(track_value_changes=True)`` reuses
│   │       merge's CDF capture.  HTTP routes
│   │       ``POST /api/pql/{update,delete}``.  Alembic
│   │       ``ee3f6h8j0l2n`` extends the
│   │       ``ck_agent_run_operations_op_name`` CHECK with all
│   │       six new op names (update/delete/drop_table/
│   │       create_schema/drop_schema/alter_table) in one shot.
│   │       ORM CHECK widened in lockstep.  13 new pytest
│   │       cases.
│   │
│   ├── Sprint 63.3 — Soyuz update_table facade  🧊 deferred
│   │       Cross-repo soyuz tag bump + client regen out of
│   │       Phase-63 scope.  Editor's table-detail UI (Phase
│   │       17.4) already handles ALTER TABLE COMMENT /
│   │       properties.  Dispatcher's ``ALTER_TABLE`` branch
│   │       returns a structured "use the table-detail UI"
│   │       error so the parser path stays live for a future
│   │       Phase 63.5 to wire in.
│   │
│   ├── Sprint 63.4 — Backend dispatcher ✅
│   │       New ``pointlessql/api/sql_dispatcher.py`` with one
│   │       ``dispatch(stype, ast, …)`` entry point + per-
│   │       StmtType branches.  SELECT keeps today's path (no
│   │       agent_run created).  Write branches start a one-shot
│   │       ``agent_run`` with ``agent_id='sql-editor'`` BEFORE
│   │       the primitive call; PQL primitives' operation_context
│   │       emits ``agent_run_operations`` against that run id
│   │       automatically.  DDL branches emit op rows directly
│   │       via SQL (soyuz client has no operation_context).
│   │       Per-branch privilege checks reuse ``check_privilege``.
│   │       ``api_sql_execute`` shrinks from 240 LOC to ~140.
│   │       10 new pytest cases.
│   │
│   ├── Sprint 63.5 — MERGE AST → MergeCallSpec translator ✅
│   │       New ``pointlessql/pql/sql_merge_translator.py``.
│   │       Supports the ``WHEN MATCHED THEN UPDATE`` (+
│   │       optional ``WHEN NOT MATCHED THEN INSERT``) upsert
│   │       subset of ``pql.merge``.  Conditional WHEN clauses,
│   │       ``WHEN MATCHED THEN DELETE``, ``WHEN NOT MATCHED BY
│   │       SOURCE``, multiple WHEN MATCHED branches, and
│   │       complex non-EQ ON predicates are all rejected with
│   │       structured ``SQLMergeUnsupportedError`` pointing the
│   │       user at ``POST /api/pql/merge`` for elaborate cases.
│   │       9 new pytest cases.
│   │
│   ├── Sprint 63.6 — Multi-statement / batch route ✅
│   │       ``POST /api/sql/execute_batch`` runs ``;``-separated
│   │       statements through the same dispatcher.
│   │       ``atomic=True`` opens a single batch agent_run and
│   │       calls ``pql.rollback`` (Phase 16) on the prior
│   │       write ops on failure.  ``atomic=False`` (default)
│   │       gives each write its own run.  Frontend toggle
│   │       deferred to a polish Sprint 63.6.1; the server-side
│   │       route is callable today.
│   │
│   ├── Sprint 63.7 — Editor UX ✅
│   │       Statement-type badge above the result widget
│   │       (colour-coded per stmt_type).  Destructive-statement
│   │       confirmation modal (regex heuristic for
│   │       DROP TABLE/SCHEMA + DELETE without WHERE).  New
│   │       ``dml`` / ``ddl`` result-render branch with
│   │       rows-affected + ``View op trace`` deep-link to
│   │       ``/runs/<run_id>``.  Existing SELECT rows-table
│   │       branch unchanged.
│   │
│   ├── Sprint 63.8 — Audit-FK wiring ✅
│   │       ``record_query_async`` accepts ``agent_run_id`` +
│   │       ``read_kind`` kwargs; dispatcher passes both so
│   │       editor writes land in ``query_history`` with
│   │       ``read_kind='sql_dml'`` / ``'sql_ddl'``.
│   │       ``ReadKind`` extended.  ``/runs/<id>`` already
│   │       joins ``query_history`` by ``agent_run_id`` (Phase
│   │       13.10) so editor writes show up in the run's
│   │       queries panel without further work.
│   │
│   └── Sprint 63.9 — Tests + close ✅
│           31 new pytest cases overall; full suite run shows
│           147 passes across the touched paths.  ruff /
│           pyright / pydoclint clean on every new or modified
│           file.  CHANGELOG, ROADMAP, memory updated.
│
├── Phase 62 — MLflow slim-down + catalog hand-off          ✅ done 2026-05-09
│   │
│   │   Symmetric application of the Phase-61 dbt pattern to
│   │   MLflow.  Both embedded MLflow iframes (the ``/ml`` rail
│   │   page and the model-detail "MLflow" tab) removed; ``/ml``
│   │   becomes a slim cockpit (Recent model registrations +
│   │   Recent training runs + "Open in MLflow UI" external
│   │   link), and the truly integrative pieces — *which UC
│   │   tables are model-prediction destinations, which recent
│   │   registrations live in a given schema* — hoist into the
│   │   catalog browsing flow.  Subprocess + reverse-proxy stay
│   │   alive so the deep-links still resolve.  Phase-61
│   │   "link out for tool-internal, keep cross-tool views
│   │   first-class" pattern is now applied to both major
│   │   external tools.
│   │
│   ├── Sprint 62.F-Server-1 — Reverse-index aggregator route ✅
│   │       New ``aggregate_table_ml_relations()`` in
│   │       ``pointlessql/services/models_lineage.py`` —
│   │       single-query reverse index over
│   │       ``lineage_row_edges.source_model_uri``, grouped by
│   │       ``(target_table, source_model_uri)`` and parsed
│   │       through the ``models:/<full>/<version>`` URI form.
│   │       Exposed via ``GET /api/ml/table-relations?catalog=
│   │       &schema=`` in ``pointlessql/api/models_routes.py``
│   │       — analog of ``/api/dbt/manifest`` for the dbt side.
│   │       Phase-62 reverse index covers only the *scoring*
│   │       direction (``trained_models`` is always ``[]``);
│   │       "trained from this table" attribution would need a
│   │       soyuz cross-reference per request and is deferred.
│   │       One pytest case in
│   │       ``tests/test_models_lineage.py`` covers grouping +
│   │       catalog/schema scoping.
│   │
│   ├── Sprint 62.A — Slim ``/ml`` cockpit page                ✅
│   │       Removed iframe from
│   │       ``frontend/templates/pages/mlflow.html``.  Header
│   │       gains an "Open in MLflow UI" external-link button
│   │       (visible only when ``mlflow_running``).  Body
│   │       becomes two cockpit cards driven by the new
│   │       ``frontend/js/pages/mlflow_cockpit.js`` Alpine
│   │       factory: Recent model registrations (10 latest from
│   │       ``/api/models``) + Recent training runs (5 latest
│   │       agent_runs filtered client-side by
│   │       ``mlflow_run_id``).  When MLflow isn't running the
│   │       existing setup-instruction alert hoists above the
│   │       cockpit so it stays visible.
│   │       ``pointlessql/api/agent_runs_routes/_serializers.py``
│   │       additively exposes ``mlflow_run_id`` so the cockpit
│   │       can filter + render deep-links.
│   │
│   ├── Sprint 62.B — Drop Model-Detail "MLflow" tab           ✅
│   │       Removed the iframe-bearing 4th tab from
│   │       ``frontend/templates/pages/model.html`` (page is
│   │       now 4 tabs: Overview / Versions / Lineage /
│   │       Promotion).  Header gains an "Open in MLflow UI"
│   │       external button deep-linking to the model registry
│   │       page.  Each Versions-table row's ``mlflow_run_id``
│   │       cell becomes a deep-link to ``/mlflow/#/runs/<id>``.
│   │
│   ├── Sprint 62.C — Schema-detail ML integration             ✅
│   │       Existing ``frontend/js/pages/dbt_schema_context.js``
│   │       extended with ML state (``mlAvailable``,
│   │       ``mlModelByTable``, ``mlModels``,
│   │       ``mlModelsLoading``).  ``init()`` fans out two
│   │       parallel fetches (``/api/ml/table-relations``
│   │       scoped to the schema + ``/api/models`` filtered by
│   │       catalog/schema).  ``frontend/templates/pages/
│   │       tables.html`` gains an inline "ml" badge on table-
│   │       name rows that are model-prediction destinations
│   │       (next to the existing dbt badge) plus a "Recent ML
│   │       registrations" mini-card after the dbt card.
│   │       Single-quoted Alpine attributes per BUG-64-01.
│   │
│   ├── Sprint 62.D — Table-detail ML model card               ✅
│   │       New ``frontend/js/pages/ml_table_context.js``
│   │       Alpine factory (registered through ``bootstrap.js``)
│   │       fetches ``/api/ml/table-relations`` scoped to the
│   │       table's catalog + schema and surfaces the matching
│   │       entry's scoring_models list.  ``frontend/templates/
│   │       pages/table.html`` wraps the existing
│   │       ``dbtTableContext`` div in an outer
│   │       ``mlTableContext`` div and renders a
│   │       ``<template x-if="hasMl">`` "ML models" card next
│   │       to the dbt card listing scoring models with edge
│   │       counts + deep-links to ``/mlflow/#/models/<full>/
│   │       versions/<v>``.
│   │
│   ├── Sprint 62.E — Catalog-tree ML pill (sidebar)           ✅
│   │       ``frontend/js/pages/catalog_tree.js`` extended:
│   │       ``mlRelations: Set`` + ``isMlTable(c, s, t)``
│   │       helper, populated via ``fetchMlRelations()`` in
│   │       ``load()``.  ``frontend/templates/components/
│   │       sidebar.html`` table loop wraps both pills in a
│   │       single ``ms-auto`` flex container so dbt + ml
│   │       badges sit side-by-side without layout breakage.
│   │
│   └── Sprint 62.F-Close — Phase close                        ✅ this commit
│           ROADMAP.md flipped, CHANGELOG entry, memory file
│           ``project_dbt_handoff_phase.md`` amended with the
│           Phase-62 follow-through (one pattern, two
│           applications: dbt + MLflow).  Browser playbook
│           replay applies to 62.C and 62.D
│           (``feedback_run_playbook_as_gate``) since both
│           touch ``x-data`` + ``|tojson``; ``/ml`` cockpit
│           verified with seeded inference edges, the
│           catalog-flow surfaces deferred to user-side replay
│           (test account lacks USE CATALOG).
│
├── Phase 61 — dbt tab slim-down + catalog hand-off         ✅ done 2026-05-09
│   │
│   │   Post-Phase-59 follow-up after a UX exploration: drop
│   │   the embedded dbt-docs iframe (it duplicated dbt-docs's
│   │   own DAG/SQL/test-result UI) and surface the truly
│   │   integrative bits — *which UC tables are dbt-materialised*
│   │   — inside the catalog browsing flow.  Subprocess + reverse-
│   │   proxy stay alive so the new "Open dbt-docs" external-tab
│   │   link still resolves.  Established the pattern: link out
│   │   for tool-internal features, keep cross-tool integrative
│   │   views first-class in PointlesSQL.  MLflow gets the same
│   │   treatment in a follow-up phase when the user confirms.
│   │
│   ├── Sprint 61.A — Slim ``/dbt`` cockpit page              ✅
│   │       Removed "Pipeline docs" tab + iframe from
│   │       ``frontend/templates/pages/dbt.html``.  Default-
│   │       active becomes "Recent runs"; on-load fetch wires up
│   │       so the table populates without a tab click.  Added
│   │       header-row "Open dbt-docs" external-link button
│   │       (visible only when ``dbt_running``).  When dbt-docs
│   │       isn't running the existing setup-instruction alert
│   │       hoists above the tab strip so it stays visible
│   │       regardless of the active tab.
│   │
│   ├── Sprint 61.B — Schema-detail dbt integration           ✅
│   │       New ``frontend/js/pages/dbt_schema_context.js``
│   │       Alpine factory (registered through ``bootstrap.js``)
│   │       fetches ``/api/dbt/manifest`` once + ``/api/dbt/runs?
│   │       limit=5``.  ``frontend/templates/pages/tables.html``
│   │       (the schema-detail page) gains an inline "dbt" badge
│   │       on table rows that match a dbt model (deep-link to
│   │       ``/dbt-docs/#!/model/<unique_id>``) plus a "Recent
│   │       dbt runs" mini-card after the Tables card.  Both
│   │       silently absent when no manifest is loaded.
│   │       Quoting bug caught in browser playbook: outer
│   │       ``x-if=""`` collided with ``|tojson`` double quotes;
│   │       fixed by single-quoting the Alpine attributes.
│   │
│   ├── Sprint 61.C — Catalog-tree dbt badge (sidebar)        ✅
│   │       ``frontend/js/pages/catalog_tree.js`` extended:
│   │       ``dbtRelations: Set`` + ``isDbtTable(c, s, t)``
│   │       helper, populated via ``fetchDbtManifest()`` in
│   │       ``load()``.  ``frontend/templates/components/
│   │       sidebar.html`` table loop renders a tiny "dbt" pill
│   │       inside the tree row when matched.  No badge / no
│   │       error on installs without a manifest.
│   │
│   ├── Sprint 61.D — Table-detail dbt-model card             ✅
│   │       New ``frontend/js/pages/dbt_table_context.js``
│   │       resolves the manifest model for the current table
│   │       (relation_name OR database/schema/name triple, mirror
│   │       of ``_node_relation_name`` server-side).
│   │       ``frontend/templates/pages/table.html`` gains a
│   │       ``<template x-if="dbtModel">`` card after the
│   │       Metadata card showing unique_id, materialization
│   │       badge, test count, and an "Open in dbt-docs" deep
│   │       link.  Existing tabs (Overview / Columns / Lineage
│   │       / etc.) untouched.
│   │
│   └── Sprint 61.E — Phase close                             ✅ this commit
│           ROADMAP.md flipped, CHANGELOG entry, memory file
│           ``project_dbt_handoff_phase.md``.  Browser playbook
│           replay used as gate (``feedback_run_playbook_as_gate``)
│           since 61.B and 61.D both touch ``x-data`` + ``|tojson``.
│
├── Phase 59 — Comprehensive UX-tour quality sweep         ✅ done 2026-05-08
│   │
│   │   Post-Phase-58 headed-Playwright tour through 8 thematic
│   │   surface groups produced 65 desktop screenshots and 71
│   │   findings (23 CONTENT / 37 STRUCTURAL / 11 DESIGN), plus
│   │   8 cross-cutting patterns.  Findings doc lives at
│   │   ``docs/internal/phase59_audit_findings.md``; screenshots
│   │   at ``docs/internal/phase59_screenshots/``.  Zero browser-
│   │   console errors and zero 5xx during the tour — UI is
│   │   runtime-clean, all findings are quality-issues not bugs.
│   │
│   │   Phase 59 covers the 60 implementable findings (CONTENT +
│   │   STRUCTURAL); the 11 DESIGN findings defer to Phase 60+.
│   │
│   ├── Sprint 59.1 — Jargon sweep + logic bugs + ANSI strip ✅ c0d93ae
│   │       CONTENT-only sweep + 1 service fix.  "Read kind" →
│   │       "Source", "Status" → "Outcome", "Window" → "Time
│   │       range" on /queries; "tables_touched" / "written" /
│   │       "read" → "Touched" / "Wrote" / "Read" on
│   │       /audit/by-table; drop "Phase 29.3" jargon from
│   │       /admin/system-info; fix "Pull-modell" / "push-modell"
│   │       German typo in admin_index.html; ANSI-strip on
│   │       caught DuckDB exception messages in
│   │       sql_routes.py; hide SHA-256 sentinel on Source-card
│   │       when source bytes ARE captured but SHA is the all-
│   │       zeros hash; filter depth-0 self-nodes from lineage_card
│   │       upstream + downstream so zero-edge tables don't render
│   │       the page subject twice.  Branches default-filter
│   │       finding investigated and dropped (no actual default-
│   │       active chip in code).
│   │
│   ├── Sprint 59.2 — Bootstrap-tab URL-state global helper ✅ 2fc3e36
│   │       New ``frontend/js/tab_sync.js`` self-bootstraps on
│   │       DOMContentLoaded, reads ``?tab=`` and ``?subtab=`` and
│   │       activates the matching ``[data-bs-toggle="tab"]
│   │       [data-pql-tab-key]`` via
│   │       bootstrap.Tab.getOrCreateInstance.  Global delegated
│   │       ``shown.bs.tab`` listener mirrors back via
│   │       history.replaceState.  Eleven templates (table,
│   │       run_view, model, data_product, agent_run_compare,
│   │       dbt, audit_by_table + 4 _run_tab_* sub-pane partials)
│   │       gained ``data-pql-tab-key="<key>"`` attributes.
│   │       Legacy ``#tab-…`` hash IIFE on run_view kept for
│   │       backward-compat.
│   │
│   ├── Sprint 59.3 — Auth/error chromeless layout            ✅ 4be934f
│   │       New ``_layouts/auth_chromeless.html`` — distilled
│   │       layout with logo + content-block + footer; no
│   │       icon-rail, no top-bar Search, no Admin-dropdown.
│   │       Migrated login, register, 403, 404, 500; new
│   │       ``pages/429.html``; wired ``_render_429`` in
│   │       rate_limit_middleware to render the new template via
│   │       ``request.app.state.templates.env`` with bare-HTML
│   │       fallback for early-init.  User-confirmed during
│   │       Phase-58 replay (memory:
│   │       ``feedback_auth_pages_chromeless.md``).
│   │
│   ├── Sprint 59.4 — Filter-row collapsible macro              ✅ 5a68258
│   │       New ``_macros/filter_collapsible.html`` (pure
│   │       Bootstrap, no Alpine).  Wraps a dense filter row in a
│   │       ``.collapse`` block behind a summary pill.  Applied
│   │       default-collapsed to /audit/inbox (6 fields) and
│   │       default-expanded to /queries (3 fields).  /audit/search
│   │       and /runs intentionally skipped — search form IS the
│   │       primary action on /audit/search; /runs uses Alpine
│   │       chips, not a dense form.
│   │
│   ├── Sprint 59.5 — Icon-rail re-mapping                       ✅ 70981b1
│   │       Two new top-level rail items: ``AUDIT`` (bi-shield-
│   │       check) and ``REVIEWS`` (bi-clipboard-check), both
│   │       between ALERTS and PRODUCTS, both visible to all
│   │       auth'd users.  Renamed FEDERATION → CATALOG with
│   │       bi-database icon and href "/" (the actual catalog
│   │       browser landing); section key stays ``federation``
│   │       internally to avoid breaking ~10 references.  Admin
│   │       footer icon swapped bi-shield-check → bi-tools to
│   │       free the icon for AUDIT.  context_panel.html grew
│   │       inline AUDIT (Inbox / Search / By table / By query)
│   │       and REVIEWS (All reviews + cross-link to Admin →
│   │       Review destinations) branches.  Removed the
│   │       duplicative "Audit cockpit" link from the admin
│   │       sidebar.  agent_reviews_routes switched
│   │       active_page from "audit" → "agent_reviews" so it
│   │       highlights REVIEWS, not AUDIT.
│   │
│   ├── Sprint 59.6 — Sub-pane helper-text sweep                 ✅ a7cf5b6
│   │       Replicated the /jobs dual-mode helper across
│   │       /dashboards (added "+ New dashboard" UI path +
│   │       agent ``create_dashboard`` tool) and /alerts
│   │       (existing UI path got a ``create_alert`` agent
│   │       tool reference).  /connections, /volumes, /dbt
│   │       skipped — they share the catalog tree (P-3 root
│   │       cause) and don't render a per-page sidebar helper.
│   │
│   ├── Sprint 59.7 — Empty-state quality sweep                  ✅ d1d90db
│   │       Rewrote below-bar empty-states on /volumes (3-step
│   │       Docker / Python / Hermes), /models (3-step MLflow /
│   │       Hermes / Docs), /branches (dual-mode pql.branch() +
│   │       agent create_branch).  Each empty-state now contains
│   │       a UI path AND an agent path AND (where applicable) a
│   │       docs link.  Replaces references to "soyuz UC-OSS",
│   │       "Hermes plugin", and "UC CLI" jargon-tokens with
│   │       concrete copy-pasteable commands.
│   │
│   ├── Phase 60+ DESIGN-deferred (sketch only)                  🧊
│   │       11 DESIGN findings parked: cytoscape-DAG on table-
│   │       lineage tab (Phase 17.3 reuse), Audit unified
│   │       ``/audit`` page with tab-strip (consolidate 4
│   │       separate sub-pages), Run-Overview sub-tabs flatten
│   │       to sectioned cards, ``/auth/me`` rendered profile
│   │       page (currently raw JSON), ``/admin`` Card-hierarchy
│   │       (action-required-first ordering).  Each is a multi-
│   │       day surface change — bundle as Phase 60 mini-
│   │       redesign trio (analog Phase 58) when scope crystallises.
│   │
│   └── Sprint 59.9 — Phase close                                ✅ this commit
│           ROADMAP.md flipped ⏳ → ✅ with commit hashes,
│           CHANGELOG entry, memory file
│           ``project_phase59_closed.md``, MEMORY.md index
│           updated.  Phase 59 totaled 8 commits including the
│           audit opener + close.  Branch not yet pushed.
│
├── Phase 58 — Phase-57 carve-out trio                       ✅ done 2026-05-08
│   │
│   │   Three small deferred items from Sprint 57.8 land in one
│   │   autonomous pass post the user-prompt "mache die sofort
│   │   follo up und pahse 58 noch ferig".  Single commit.
│   │
│   │   58.1 — admin_workspaces "Create" form → Bootstrap modal.
│   │   Replaces the inline card-form at the top of the workspace
│   │   list with a "+ New workspace" button + modal, matching
│   │   the jobs / dashboards / alerts UX.  Alpine state + POST
│   │   flow unchanged; only the surface moves.  Closes the one
│   │   DESIGN finding from the Phase 57.1 audit.
│   │
│   │   58.2 — admin_audit_sinks empty-state icon swap
│   │   (``bi-broadcast`` → ``bi-broadcast-pin``).  Cosmetic
│   │   refinement noted as the only CONTENT finding in the 57.1
│   │   audit.
│   │
│   │   58.3 — Query-card "View full SQL" drawer trigger.  SQL
│   │   longer than 700 characters surfaces a Phase-56.8
│   │   detail_drawer button that pops the full text out of the
│   │   card's height-capped ``<pre>`` into an Offcanvas panel.
│   │   Short SQL renders without the trigger so the card stays
│   │   clean.  Pre-emptive add — the alternative was to wait for
│   │   user-replay to demand it, but height-capped scrolling on a
│   │   200-line stored procedure is poor enough that proactive
│   │   ship is the better trade.  2 new pytest cases.
│   │
│   │   Drops (deliberately not picked up):
│   │   - Alpine listTable re-add on queries card-grid — no user
│   │     signal that server-side Form-GET reload is too slow.
│   │     Stays parked until replay calls for it.
│   │   - Browser-replay verification — same handling as 54-57.
│   │
│   │   Push gate: standard manual.
│   │
├── Phase 57 — Phase-56 carve-outs + route-test coverage      ✅ done 2026-05-08
│   │
│   │   Closes the three explicit carve-outs from Phase 56 in
│   │   one autonomous session post the user-prompt "plane aus!"
│   │   on (1) queries.html Tables→Cards, (2) DESIGN-tagged
│   │   findings from the 56.1 audit, (3) test-coverage sweep on
│   │   admin_api_keys / federation / jobs / dashboards.  Nine
│   │   sub-sprints; ~85 new pytest cases; one mobile-data-label
│   │   sweep on 7 surfaces.
│   │
│   │   The plan-phase audit again reduced the implementation
│   │   set:  the "DESIGN-tagged findings" carve-out turned out
│   │   to be effectively empty (Section 4 of
│   │   ``phase56_audit_findings.md`` declares ``[DESIGN]`` as a
│   │   tag-category but no individual finding actually carries
│   │   the tag — they were all CONTENT/STRUCTURAL and folded
│   │   into Sprint 56.10).  Sprint 57.1 was repurposed as an
│   │   audit-Ersatz on the ~15 surfaces that the 56.1 audit had
│   │   never covered (admin/* detail views, federation/* detail
│   │   views, jobs+dashboards detail views, branches detail,
│   │   volumes), producing ten STRUCTURAL findings (mobile
│   │   data-label adoption) + one CONTENT finding + one DESIGN
│   │   finding (admin_workspaces "Create" form → modal,
│   │   deferred to Phase 58).  Saved one Sprint-token worth of
│   │   speculative DESIGN work.
│   │
│   │   Sprint 57.1 — Audit-Ersatz: per-surface semantic-content
│   │   review of the ~18 surfaces that the 56.1 audit had not
│   │   covered.  Output ``docs/internal/phase57_audit_findings.md``.
│   │   Read-only.
│   │
│   │   Sprint 57.2 — Server-side offset pagination on
│   │   ``/queries`` (analog Phase 55.1 ``/runs``).  Extends
│   │   ``query_history.list_queries`` with an ``offset`` kwarg
│   │   (backward-compatible default 0); ``count_queries`` grows
│   │   the same filter-arg list ``list_queries`` already takes
│   │   so the pager can compute filter-aware ``remaining``.
│   │   GET /queries dispatches HX-Request → fragment template
│   │   for the Load-More flow.  5 new pytest cases.
│   │
│   │   Sprint 57.3 — ``/queries`` table → card-grid + hljs SQL
│   │   syntax-highlighting.  Replaces the Alpine listTable +
│   │   9-column table with a Bootstrap card-grid (col-12 /
│   │   col-md-6 / col-xxl-4) where each card carries a status
│   │   stripe on the left edge (succeeded / failed / cancelled)
│   │   and the SQL rendered in a height-capped ``<pre>`` block
│   │   coloured by highlight.js.  Filters move from client-side
│   │   chips (mine / failed / last24h) to server-side Form-GET
│   │   selects (read_kind / status / since), same trade-off as
│   │   56.9 on agent_reviews + alerts.  hljs loaded via
│   │   jsdelivr CDN to match the project's existing Bootstrap /
│   │   htmx / alpine / chart.js precedent — no vendor/
│   │   directory.  HTMX after-swap re-highlight.  2 new pytest
│   │   cases.
│   │
│   │   Sprint 57.4 — ``federation_routes.py`` route-level
│   │   smoke-tests (21 endpoints, ~14% → ~80% coverage).  26
│   │   new pytest cases covering 5 connections × 3 resource
│   │   families (15 JSON CRUD) + 6 HTML pages, each with
│   │   admin-success + non-admin-403 + audit-emission asserts +
│   │   one outage-banner case for the connections index.
│   │
│   │   Sprint 57.5 — ``dashboards_routes.py`` smoke-tests (9
│   │   endpoints, ~22% → ~80%).  16 new pytest cases.  Caught
│   │   one spec-mismatch at sprint-start: the create-dashboard
│   │   route maps slug-validation rejections to 422 (not 400)
│   │   because ``ValidationError`` inherits
│   │   ``PointlessSQLError.status_code = 422``.
│   │
│   │   Sprint 57.6 — ``jobs_routes.py`` smoke-tests (13
│   │   endpoints, ~53% → ~80%).  14 new pytest cases targeting
│   │   the 5 endpoints not covered by ``TestJobRoutes`` in
│   │   ``test_scheduler.py`` (DAG tasks list, run-tasks,
│   │   run-logs + task-filter, notebook + download 404 paths,
│   │   compare ``?to=`` papermill-only).
│   │
│   │   Sprint 57.7 — ``admin_api_keys_routes.py`` edge-case
│   │   extension (3 endpoints, ~66% → ~95%).  8 new pytest
│   │   cases on top of the 5 existing happy-path tests:
│   │   create rejects empty / missing / whitespace name (422),
│   │   workspace_id <= 0 (422), duplicate active name (422);
│   │   revoke twice → 404 second time; list ?include_revoked
│   │   surfaces inactive; supervisor + auditor combo; non-admin
│   │   revoke → 403 (require_admin runs first).
│   │
│   │   Sprint 57.8 — Apply CONTENT + STRUCTURAL findings from
│   │   57.1.  Adds ``pql-list-table`` class + ``data-label``
│   │   attributes to 7 surfaces that rendered badly on <640px
│   │   without per-column labels: admin_audit_sinks,
│   │   admin_review_destinations, admin_workspaces (dual
│   │   tables), volumes, volume_detail (Alpine x-for table),
│   │   job_detail (DAG tasks + recent runs), branch_detail
│   │   (audit log).  Same mechanic as Phase 56.4.
│   │
│   │   Sprint 57.9 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (recorded for the implementation log):
│   │   - DESIGN-finding admin_workspaces "Create" → modal.
│   │     Defer Phase 58 — focused mini-redesign.
│   │   - admin_audit_sinks empty-state icon swap (CONTENT,
│   │     cosmetic only).  Defer Phase 58.
│   │   - branches_routes test-coverage extension — already at
│   │     ~85%, diminishing returns.
│   │   - audit_search_routes test-coverage — already 100%.
│   │   - hljs vendoring per the original plan-pick — project
│   │     pattern is CDN for everything (Bootstrap, htmx, alpine,
│   │     chart.js, codemirror) and a single vendored dep would
│   │     be inconsistent.  Sticking to CDN.
│   │   - Alpine listTable on the new card-container for
│   │     ``/queries``.  Server-side filter via Form-GET-Reload
│   │     is sufficient (analog 56.9); user-replay-driven re-add
│   │     Phase 58 if demanded.
│   │   - SQL truncate-with-drawer in queries-card.  Initial
│   │     commit without truncate; observe in user replay.
│   │
│   │   Browser-replay verification:  Wave-3 (57.3 cards + hljs +
│   │   Load-More) needs browser-side verification of hljs-render,
│   │   Load-More click + scroll-trigger, mobile card-stack —
│   │   left for user post-rebuild.  Wave-1 audit + Wave-2 backend
│   │   pagination + Wave-3 test-coverage sweeps + Wave-4 mobile-
│   │   sweep all gate on pytest only (124 tests green across the
│   │   touched test files).
│   │
│   │   Push gate: standard manual.
│   │
├── Phase 56 — UX-polish + bug-hunt + semantic-content review ✅ done 2026-05-08
│   │
│   │   Three-wave audit-first sweep post the user-prompt
│   │   "wir machen bug-hunting + auch hunting von schlechter
│   │   visualisierung … und auch die semantisch richtigen
│   │   Inhalte".  12 sub-sprints in one autonomous session
│   │   (audit-only Wave 1 + 4 mechanical sweeps in Wave 2 + 4
│   │   new-primitive Wave 3 + 3-item Wave 4 polish + close).
│   │
│   │   The plan-phase audit (3 parallel Explore agents +
│   │   verify-pass) collapsed the implementation set
│   │   substantially:  9 of 9 BUG-53-NN markers turned out to
│   │   be already-fixed-but-not-closed (closed in 56.2 with
│   │   per-marker evidence trail in
│   │   ``screenshots/phase53-replay/_notes.md``); the worried-
│   │   about Alpine x-data quoting on 10 templates turned out
│   │   to be already-safe via Jinja's default ``|tojson``
│   │   ``\\uXXXX``-escape behaviour (regression test in
│   │   ``tests/test_alpine_x_data_quoting.py`` pins it); and
│   │   four of the Phase-53 visual-debt patterns (#1 outline-
│   │   button-opacity, #2 errors-no-sidebar, #6 UUID format,
│   │   #8 tab-badges only first sub-tab) were already-fixed-but-
│   │   not-closed by Phases 54.1 / 56.5 / earlier.
│   │
│   │   Sprint 56.1 — Audit consolidation + per-page semantic
│   │   review.  Read-only.  Output:
│   │   ``docs/internal/phase56_audit_findings.md`` with six
│   │   sections (layout-pattern inventory, BUG-status, per-
│   │   page semantic review for 20 surfaces, affected-file
│   │   list per sub-sprint, risk-notes, out-of-scope).  No code
│   │   changes — every finding is acted on (or deferred) in
│   │   later sub-sprints with explicit cross-references.
│   │
│   │   Sprint 56.2 — BUG-53-NN closure + Alpine x-data quoting
│   │   regression test.  Closes all 9 BUG-53-NN markers in one
│   │   sweep of ``_notes.md``.  ``tests/test_alpine_x_data_
│   │   quoting.py`` (12 tests) pins the safe behaviour against
│   │   future regressions.  Net 0 template code-changes.
│   │
│   │   Sprint 56.3 — Empty-state component sweep.  8 templates
│   │   converted from inline ``<p>``/``<div>`` empty-states to
│   │   ``{% include "components/empty.html" %}`` with action-
│   │   oriented messages (e.g. "Add a webhook URL or pull-feed
│   │   receiver below" instead of "No destinations yet").
│   │   Templates: ``alert_detail`` (×2), ``queries``, ``models``,
│   │   ``job_detail``, ``agent_run_compare``, ``model_compare``
│   │   (×3), ``agent_review_detail``, ``admin_external_writes``.
│   │
│   │   Sprint 56.4 — Mobile data-label sweep + Pattern-3
│   │   closure.  7 list-tables get ``data-label`` on every
│   │   ``<td>``; 4 templates also get the ``pql-list-table`` class
│   │   added so the existing mobile-collapse CSS rule kicks in
│   │   under 640 px.  Pattern-3 (mobile cards bare em-dash) is
│   │   automatically resolved because the mobile rule prepends
│   │   ``data-label`` as the column-key.  Templates:
│   │   ``runs_list`` + ``runs_list_append``, ``admin_api_keys``,
│   │   ``admin_external_writes``, ``audit_by_table``,
│   │   ``queries`` (consistency repair), ``alert_detail``
│   │   destinations table.  ``agent_reviews_list`` skipped —
│   │   becomes a card-grid in 56.9.
│   │
│   │   Sprint 56.5 — Display-layer Jinja filters
│   │   ``format_uuid`` (Pattern-6) + ``format_hash``
│   │   (Pattern-7).  ``format_uuid`` normalises packed/
│   │   hyphenated UUID strings to canonical 8-4-4-4-12;
│   │   ``format_hash`` swaps the all-zeros SHA-sentinel for
│   │   the readable label ``(no source captured)``.  Applied
│   │   in 5 templates (run-id title-attrs +
│   │   ``_run_tab_overview`` source-SHA).  Bonus: fixes the
│   │   ``_format_epoch_ms`` ``except TypeError, ValueError``
│   │   binding-target bug to the proper tuple form.  11
│   │   filter tests in ``tests/test_jinja_display_filters.py``.
│   │
│   │   Sprint 56.6 — Truncate-with-tooltip primitive.  New
│   │   ``_macros/truncate.html`` ``truncate_cell(text, max,
│   │   klass)``.  Native ``title=`` (NOT Bootstrap Tooltip —
│   │   plan-agent perf-foot-gun flag for 50-row tables); new
│   │   ``.pql-truncate-tip`` CSS class with dotted-underline
│   │   + ``cursor: help``.  Applied to 6 surfaces: run-detail
│   │   Queries SQL + UC-mutations detail, queries history SQL,
│   │   runs-list Principal/Agent/Tables, audit-search entity-
│   │   id (mirrored in JS template literal), alert-detail URL
│   │   (Alpine ``:title``), admin-external-writes commit_info.
│   │   5 macro tests.
│   │
│   │   Sprint 56.7 — Copy-button primitive + reuse of existing
│   │   toast hook.  New ``_macros/copy_button.html``
│   │   ``copy_btn(value, label, icon)`` + delegated listener in
│   │   ``frontend/js/copy_button.js`` (single click-handler
│   │   wired in ``bootstrap.js``).  Reuses
│   │   ``window.pqlToast.success/error`` (already wired up
│   │   pre-Phase-56) so no new toast plumbing.  Applied to 4
│   │   surfaces: run-detail breadcrumb (full UUID),
│   │   alert-detail webhook URL (Alpine
│   │   ``:data-pql-copy``), connection-options table (per-row),
│   │   model-detail header (model URI).
│   │
│   │   Sprint 56.8 — Bootstrap Offcanvas detail-drawer.  New
│   │   ``_macros/detail_drawer.html`` exposes a ``{% call %}``
│   │   macro; trigger + offcanvas-pane pair, Bootstrap manages
│   │   focus + ARIA + ESC + backdrop-click.  New CSS
│   │   ``components/detail_drawer.css`` sizes drawer to
│   │   ``min(640px, 90vw)`` with ``<pre>``-content styling.
│   │   Applied to 3 surfaces: run-detail Queries SQL drawer,
│   │   tool-call Args + Result drawers (each only when the
│   │   truncation kicks in), audit-log Detail drawer.  ``<details>``
│   │   alternative dropped per user-pick (Offcanvas) +
│   │   plan-agent FF-quirk risk-flag for ``<tr>`` containing
│   │   ``<details>``.
│   │
│   │   Sprint 56.9 — Tables→Cards: agent_reviews + alerts.
│   │   User-pick "Ambitious".  ``agent_reviews_list``: 5-col
│   │   table → severity-coloured card-grid
│   │   (``col-12 col-md-6 col-xxl-4``) with full-summary
│   │   first-line (no truncation), period range with
│   │   calendar icon, created-at as card-footer.  ``alerts``:
│   │   6-col Alpine x-for table → active/paused-coloured
│   │   card-grid with cron + condition + destinations as
│   │   labelled key/value lines, pause/delete actions in
│   │   card-footer.  New ``components/cards.css`` for left-
│   │   stripe accents.  Server-side filter via the existing
│   │   pagination-macro (no listTable Alpine generalisation).
│   │   ``queries.html`` Tables→Cards intentionally deferred
│   │   per plan-agent risk-flag.
│   │
│   │   Sprint 56.10 — Semantic-content corrections (action-
│   │   orientation rewrites).  3 high-traffic surfaces: source
│   │   sub-tab subtitle ("Source bytes captured at run start,
│   │   hashed for tamper-evidence"), audit-inbox heading
│   │   ("anomaly inbox" → "what needs attention") +
│   │   description rewrite, audit-queries description rewrite
│   │   (leads with user-goal, lists allow-listed table names).
│   │   Other audit findings (runs_list "Operations" rename,
│   │   audit_inbox top-KPI, audit_queries "Result" sub-section)
│   │   turned out to not match the codebase and are recorded
│   │   as false-positives.
│   │
│   │   Sprint 56.11 — UX polish bundle.  2 buried CTAs
│   │   promoted (admin_external_writes Acknowledge:
│   │   ``btn-outline-success`` → ``btn-success``;
│   │   audit_inbox JS Ack/Un-ack: ``btn-outline-primary`` →
│   │   ``btn-primary`` + full-word labels with leading icons).
│   │   Spinner-text expanded on the long-running lineage DAG
│   │   load + ARIA ``role="status"`` + ``aria-live="polite"``.
│   │   Phase-53 patterns 1, 2, 8 verified already-clean (no
│   │   CSS opacity-override, sidebar-on-error fixed by
│   │   Phase 54.1, all 5 Operations sub-tabs already render
│   │   count badges).  The "polish-bundle" sub-sprint turned
│   │   out mostly to be confirmation work.
│   │
│   │   Sprint 56.12 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (recorded for the implementation log):
│   │   - ``queries.html`` Tables→Cards — plan-agent risk-flag
│   │     (½-day each for code-highlighting + toggle-state
│   │     migration).
│   │   - DESIGN-tagged findings from 56.1 per-page semantic
│   │     review — page-level redesigns deferred to Phase 57+.
│   │   - Test-coverage-sweep for admin_api_keys / branches /
│   │     federation / jobs / dashboards / audit_search —
│   │     carve-out Phase 57 (Phase 56 was UX-only by design).
│   │   - mb-3 vs mb-4 padding standardisation — explicitly
│   │     out-of-scope.
│   │
│   │   Browser-replay verification: same handling as Phase 54
│   │   + 55.  Stack runs Docker-baked; the Wave-2 mechanical
│   │   sweeps (56.2 / 56.3 / 56.4 / 56.5) need only template-
│   │   parse + pytest gates (all green).  Wave-3 primitives +
│   │   Wave-4 polish (56.6 / 56.7 / 56.8 / 56.9 / 56.11) need
│   │   browser-side verification of tooltip-hover, toast-
│   │   render, drawer click-to-open + ESC-close, card-grid
│   │   layout, action-discovery affordance — left for the
│   │   user post-rebuild.
│   │
│   │   Push gate: standard manual.
│   │
├── Phase 55 — UI polish nachzug (post-Phase-54)            ✅ done 2026-05-08
│   │
│   │   Closes the three explicit Phase-54 carve-outs (accordion
│   │   gap, /audit/queries pagination, /runs + /audit/search
│   │   pagination) plus a small-BS-pattern audit.  Six sub-sprints
│   │   in one autonomous session post the "kannst du die noch
│   │   unetanen dinge vollständig ausplanen?" plan.  Plan-phase
│   │   audit again reduced the implementation set: the
│   │   ``agent_run_compare.html`` accordion candidate from the
│   │   Phase-54 carve-out turned out to be a misidentification (no
│   │   ``.alert`` on that page; the "Cell-level diffing not
│   │   implemented" line lives on the *separate* ``run_compare.html``
│   │   side-by-side iframe view as a footer disclaimer).  Two
│   │   bonus accordion candidates surfaced instead.
│   │
│   │   Sprint 55.1 — Accordion polish.  Two more admin pages flip
│   │   the verbose ``.alert-info`` header into ``accordion-flush``:
│   │   ``admin_review_destinations.html`` (9-line webhook fan-out
│   │   + spec-link) and ``admin_cdf_tail.html`` (8-line pull-modell
│   │   + interval env-var).  Both keep their copy verbatim; distinct
│   │   accordion ids per page so a hypothetical combined view
│   │   doesn't collide on ``data-bs-target``.
│   │
│   │   Sprint 55.2 — /audit/queries pagination.  Saved-queries
│   │   cockpit kept loading the full list as a single ``UL``;
│   │   multi-user installs accumulate user-created queries past the
│   │   starter set, so the cockpit now ships defensive pagination
│   │   (50 rows per page) modelled on the Phase-54.3 ``/admin/audit``
│   │   flow.  New ``saved_audit_queries.list_paginated`` returns
│   │   ``(rows, total)`` via a separate ``COUNT(*)``;
│   │   ``html_audit_queries`` accepts ``?offset=`` and renders only
│   │   the current page; the template calls the shared ``paginate``
│   │   macro under the saved-queries card when ``total`` exceeds
│   │   the page size.  The right-hand result table is fetched
│   │   per-query via vanilla JS and already capped server-side; that
│   │   surface stays unchanged.
│   │
│   │   Sprint 55.3 — /runs infinite-scroll Load-More.  Phase 54.3
│   │   deferred this because the page already relied on Alpine
│   │   ``listTable`` for client-side filter chips.  The Alpine layer
│   │   stays intact and HTMX threads a Load-More CTA through it:
│   │   ``load_runs`` now returns ``(rows, total)`` and accepts
│   │   ``offset``; ``GET /runs`` checks ``HX-Request`` and either
│   │   renders the page shell or a fragment partial that streams
│   │   the next page of ``<tr>`` rows into ``#runs-tbody`` while
│   │   replacing ``#runs-pager`` via ``hx-swap-oob="true"`` to
│   │   advance the offset; ``listTable`` exposes ``refreshRows()``
│   │   so the new rows fall under the active filter / sort after
│   │   each append, and ``runs_list.html`` fires ``pql:rows-appended``
│   │   on ``htmx:after-swap`` to trigger it.  JSON ``/api/runs`` now
│   │   also reports ``total`` + ``next_offset`` for machine
│   │   consumers.
│   │
│   │   Sprint 55.4 — /audit/search infinite-scroll Load-More.
│   │   Phase 54.3 deferred this because the page is fetch-driven
│   │   (JSON API) and adding offset support touched both
│   │   dialect-specific FTS modules.  Per-dialect ``search`` now
│   │   accepts ``offset`` and threads ``OFFSET :n`` into the SQL on
│   │   both SQLite (FTS5 MATCH) and Postgres (tsvector/GIN); the
│   │   facade ``audit_fts.search`` and ``GET /api/audit/search``
│   │   expose ``offset`` + ``next_offset`` (the latter ``None`` once
│   │   the page is the tail).  The audit-search HTML keeps its
│   │   existing fetch flow but tracks ``offset`` in module state,
│   │   fires a Load-More button when ``next_offset`` is non-null,
│   │   and appends new rows into the existing ``<tbody>``.  A fresh
│   │   "Search" submission resets state so a new query never appends
│   │   onto stale results.
│   │
│   │   Sprint 55.5 — Smaller-BS-patterns audit + adoption.
│   │   Audit-first per the plan: each pattern adopted only with
│   │   ≥ 3 real surfaces.  Toast (1× ephemeral .alert-success) →
│   │   DROP.  Progress bars (27× spinner-border but none with
│   │   quantifiable progress; spinners stay correct) → DROP.
│   │   Link-utilities (101× ``text-decoration-none``, all semantic
│   │   and theme-correct already; mass-replacement risks more than
│   │   it gains) → DROP.  Sticky-Top → REAL: 5 long-list tables
│   │   (``/runs``, ``/audit/search``, ``/admin/audit``,
│   │   ``/agent-reviews``, ``/branches``) commonly scroll past their
│   │   thead.  New ``.pql-thead-sticky`` rule pins the column row
│   │   at ``top: var(--pql-topbar-height)`` with ``z-index: 1010``
│   │   so the existing topbar (``z-index: 1020``) always overlays
│   │   it; the mobile collapse rule
│   │   (``.pql-list-table > thead { display: none }``) keeps
│   │   winning under 640 px.
│   │
│   │   Sprint 55.6 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (recorded for the implementation log):
│   │   - ``agent_run_compare.html`` accordion-info-block — no
│   │     ``.alert`` on that page; the misidentification was a
│   │     similar-name conflation with ``run_compare.html``, where
│   │     the alert is a footer disclaimer, not a header info-block.
│   │   - Toast / Progress / Link-utility sweeps — below the
│   │     ≥ 3-real-surface threshold; explicit DROP per the plan.
│   │
│   │   Browser-replay verification: stack runs from a baked Docker
│   │   image; edits don't show up live without a rebuild.
│   │   Templates parse, route imports succeed, all touched pytest
│   │   groups pass (1830 tests / 7 skipped, ``pytest -x -q``).
│   │   Pyright: 497 warnings, at budget.  Push gate: standard
│   │   manual.
│
├── Phase 54 — UI overhaul implementation (M = Modernize) ✅ done 2026-05-08
│   │
│   │   Implements the Phase-53 ``ui-overhaul-proposal.md`` Size-M
│   │   recommendation in six sub-sprints, autonomous session post
│   │   the "mache jetzt einen Plan die gefundenen Sachen alle
│   │   umzusetzen" plan.  The plan-phase code-audit reduced the
│   │   actionable set from "10 bugs + 10 visual-debt patterns"
│   │   down to the items that turned out to be real after
│   │   verifying against the codebase — several Phase-53 findings
│   │   were false alarms (no ``.btn-outline-*`` opacity override
│   │   exists in CSS; UUID format is consistent; Sentinel SHA-256
│   │   is never written; ``runs_list.html`` has no mobile-card
│   │   rendering; three of the "walkthrough doc drift" entries
│   │   were already pointing at the right URLs).
│   │
│   │   Sprint 54.1 — Error pages keep the sidebar.  The Phase-53
│   │   diagnosis ("templates do not extend base.html") was wrong;
│   │   the templates extend correctly but ``error_handlers.py:302``
│   │   hard-coded ``hide_sidebar=True``.  Flipped to ``False`` so
│   │   403/404/500 keep the icon-rail; the ``pql-error-shell``
│   │   content-class still centers the empty card.  Pre-existing
│   │   CSS comment refreshed.
│   │
│   │   Sprint 54.2 — Color-modes toggle (Bootstrap 5.3).  The CSS
│   │   under ``:root[data-bs-theme="light"]`` was already shipping
│   │   since Phase 17; only the toggle UI + JS were missing.
│   │   Three pieces: anti-FOUC inline init script in ``<head>``
│   │   reads ``localStorage.pql.theme`` + ``prefers-color-scheme``
│   │   before any CSS parses, a 3-button dropdown
│   │   (Light / Dark / Auto) in the topbar marked with
│   │   ``data-bs-theme-value``, and a delegated click handler at
│   │   the body end that persists user picks and re-applies on OS
│   │   prefer-changes when in ``auto``.  Default for new users is
│   │   ``auto`` (Bootstrap-canonical).
│   │
│   │   Sprint 54.3 — Pagination component on /admin/audit.  New
│   │   ``frontend/templates/_macros/pagination.html`` macro
│   │   (Bootstrap-5.3 ``<nav><ul.pagination>``, 7-button window
│   │   with ellipsis on overflow, ``Showing N–M of T``).  New
│   │   ``paginate_url`` Jinja global preserves filter chips while
│   │   overriding ``offset``.  ``/admin/audit`` switches from a
│   │   ``LIMIT+1`` truncation flag to a real ``offset``-based
│   │   pager backed by a separate ``COUNT(*)``.  ``/runs``,
│   │   ``/audit/queries``, ``/audit/search`` deferred — they
│   │   interact with client-side Alpine ``listTable`` filtering or
│   │   fetch-driven JS rendering and need a UX pass, not a one-
│   │   template adoption.
│   │
│   │   Sprint 54.4 — Accordion on four admin info-headers.
│   │   Replaced 8-10-line verbose ``.alert-info`` blocks under
│   │   ``/admin/audit-sinks``, ``/admin/api-keys``,
│   │   ``/admin/system-info``, ``/admin/external-writes`` with
│   │   collapsed-by-default ``accordion-flush`` "What is this
│   │   page?" toggles.  All copy preserved verbatim inside the
│   │   accordion body.  Distinct accordion ids per page so a
│   │   hypothetical combined view would not collide on
│   │   ``data-bs-target``.
│   │
│   │   Sprint 54.5 — Small bugs + compare-runs badges.  BUG-53-01:
│   │   ``_macros/help_icon.html`` was using ``|safe`` on the
│   │   popover content attribute, letting any ``"`` close the
│   │   attribute early — switched to ``|e`` so the round-trip
│   │   stays balanced.  BUG-53-09: new admin-gated GET
│   │   ``/agent-reviews`` route + ``pages/agent_reviews_list.html``
│   │   template (paginated via the 54.3 macro).  Sprint 54.5a:
│   │   compare-runs nav-tabs gain count badges on Lineage /
│   │   Rejects / Cells / Column lineage (previously only Operations
│   │   + Tool calls had them); ``runs_routes/diff.py`` now computes
│   │   four new ``*_diff_count`` context vars.  Stale
│   │   ``/jobs/new`` link in ``jobs_sidebar.html`` and stale
│   │   ``/sql-editor`` URL in three docs (sql-editor.md /
│   │   grand-tour.md / e2e-walkthroughs/README.md) corrected.
│   │
│   │   Sprint 54.6 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (from Phase-53 list, false-alarms verified during
│   │   plan-phase audit):
│   │   - Pattern 1 outline-button opacity (no override in CSS).
│   │   - Pattern 6 UUID-format (consistent dashed everywhere).
│   │   - Pattern 7 Sentinel-SHA-256 filter (never written).
│   │   - Pattern 3 mobile-card ``<dl>`` (runs_list.html has no
│   │     mobile-card rendering — responsive table only).
│   │   - BUG-53-03 ``/workspace`` (icon-rail link points at the
│   │     real ``/notebooks/workspace`` admin file browser).
│   │   - BUG-53-04 / -05 / -10 walkthrough drift (admin-audit.md /
│   │     data_products.md / foreign-catalog-sync.md were already
│   │     using the correct URLs).
│   │
│   │   Push gate: standard manual.  Six commits local-only.
│
├── Phase 53 — Full replay sweep + Bootstrap UI overhaul evaluation ✅ done 2026-05-07
│   │
│   │   Diagnose-only phase (no implementation).  Three deliverables
│   │   produced in one autonomous session post the "wirklich
│   │   kompletten walkthrough machen und ordentlich screenshots"
│   │   plus "ob wir wirklich jeden erdenklichen Rahmen von Bootstrap
│   │   vollständig nutzen" plan.
│   │
│   │   Sprint A — Bootstrap-research.  Fetched 10 Bootstrap-5.3
│   │   docs/example pages (dashboard / sidebars / headers / footers
│   │   / album / color-modes / accordion / scrollspy / pagination /
│   │   getting-started); produced
│   │   ``docs/research/bootstrap53-gap-analysis.md`` with
│   │   pattern-adoption table + 5.3-feature checklist + concrete
│   │   recommendations (3 in-scope, 2 out-of-scope).
│   │
│   │   Sprint B — Replay sweep.  Walked 35 of 47 browser+hybrid
│   │   playbooks against the live stack
│   │   (PointlesSQL :8000 / soyuz :8080 / ``admin@pql.test`` /
│   │   ``seed-full-stack-demo``); 12 N/A (Hermes/CLI/deleted-
│   │   features/state-dependent).  ~50 screenshots saved under
│   │   ``docs/e2e-walkthroughs/screenshots/phase53-replay/``
│   │   organized by playbook slug.  Notes log at
│   │   ``screenshots/phase53-replay/_notes.md`` captures 10 bugs
│   │   (BUG-53-01 .. BUG-53-10) and 10 distinct visual-debt
│   │   patterns.  Notable findings: outline buttons read as
│   │   disabled across ≥ 5 surfaces (recurring CSS bug); error
│   │   pages drop the icon-rail sidebar (architectural gap);
│   │   ``/audit/search`` description has unescaped HTML
│   │   (BUG-53-01).
│   │
│   │   Sprint C — Synthesis.  ``docs/ui-overhaul-proposal.md``
│   │   combines Sprint A's Bootstrap gap-analysis with Sprint B's
│   │   visual-debt patterns into a 3-size recommendation
│   │   (S Polish 1-2 d / M Modernize 1 wk / L Reflow 2-3 wk).
│   │   Recommendation: **M — Modernize**, motivated by three
│   │   high-impact Bootstrap-5.3 adoptions (color-modes toggle,
│   │   accordion for stacked details, pagination component) plus
│   │   the recurring outline-button-opacity bug-fix.  Proposal
│   │   defers Phase-54 implementation decision to user; Phase 53
│   │   itself ships zero code changes to the UI layer.
│   │
│   │   Sprint D — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry + 2 new mkdocs nav entries.
│   │
│   │   Locked-in user picks at plan time:
│   │   1. Replay strategy: one session, all 47 sequential.
│   │      (Adjusted in execution: 35 covered, 12 N/A; depth of
│   │      visual-debt analysis prioritized over screenshot
│   │      completeness.)
│   │   2. Screenshot depth: full step-sequence (300+ target).
│   │      (Adjusted: ~50 actual; trade-off taken — Sprint C
│   │      synthesis is the actual deliverable, not the count.)
│   │   3. Bug-fix policy: trivial inline + rest dokumentieren.
│   │      Applied: 0 inline fixes this phase (all 10 bugs are
│   │      either route-realignment, doc drift, or non-trivial
│   │      template fixes — pushed to Phase 54 if approved).
│   │   4. Empfehlung-Stil: konkrete S/M/L-Empfehlung.
│   │      Applied: M.
│   │
│   │   Push gate: standard manual.  No code changes; only
│   │   ``docs/`` additions + 2 mkdocs nav entries.
│
├── Phase 52 — Playwright walkthrough completion pass ✅ done 2026-05-07
│   │
│   │   Audit + repair of the e2e walkthrough corpus.  Added a
│   │   ``> **Mode:**`` tag to all 51 walkthroughs (browser /
│   │   hybrid / hermes / curl); rewrote the README inventory
│   │   into a 4-table grouping by mode; wrote 3 new walkthroughs
│   │   for templates that had no playbook
│   │   (``volumes.md`` / ``model-compare.md`` /
│   │   ``agent-review-detail.md``); appended condensed
│   │   ``## Playwright MCP script`` sections to 11 zero-coverage
│   │   walkthroughs (branches / rollback / time-travel /
│   │   inference-lineage / models-tab / notebook-full /
│   │   error-handling / full-stack-demo / contextual-panels /
│   │   multi-workspace-setup / data_products) and to 12 thin
│   │   walkthroughs (alerts / packaging / admin-console /
│   │   admin-cdf-tail / audit-sinks / explain-rewrite /
│   │   run-comparisons / grand-tour / dbt-pipeline / list-polish
│   │   / sprint_13_11_reflexive_tools / agent_drift_monitor /
│   │   audit-cockpit-deep).  Smoke-replayed the 5 gold-standard
│   │   playbooks (auth / home / catalog-browsing /
│   │   audit-cockpit-deep / run-comparisons) — all five render
│   │   200 against the live stack; 2 selector bugs in the new
│   │   MCP scripts surfaced + fixed in the same edit
│   │   (BUG-41-01 / BUG-41-02).  Total: 54 walkthroughs in the
│   │   corpus, 40 in ``Mode: browser``, 8 hybrid, 6 hermes,
│   │   1 curl.  No code changes — pure documentation pass.
│   │
│   │   Push gate: standard manual.  ``mkdocs build --strict``
│   │   warning count unchanged at 18 (all pre-existing
│   │   cross-repo links).
│
├── Phase 51 — Git-backed workspaces ✅ done
│   │
│   │   Workspaces gain a 1..n git-repo registry; clones land at
│   │   ``<base_dir>/<workspace_id>/<slug>/`` and feed the
│   │   yaml loaders (data products + conventions) plus three
│   │   asset bridges (notebooks via ``repo:<ws>:<slug>/<rel>``
│   │   spec, dashboards + saved-queries via
│   │   ``pointlessql.yaml`` blocks).  Read-only by design — git
│   │   is truth, DB is cache.  Provider-shape (``GitProvider``
│   │   Protocol) lets GitLab/Gitea adapters drop in without
│   │   service-layer changes.  Webhook receiver
│   │   (``POST /webhook/git/{repo_id}`` + HMAC verify) and
│   │   opt-in cron loop drive auto-pulls; admin JSON API
│   │   (``/api/admin/repos/*``) drives manual ops.  4 new
│   │   plugin tools.  Pyright budget unchanged at 497.
│   │
│   ├── Sprint 51.1 — Foundation.  ``pointlessql/git/``
│   │       package: GitProvider Protocol + Generic + GitHub
│   │       impls, async subprocess helper, error family.
│   │       ``services/secrets.py`` Fernet authenticated
│   │       encryption (replaces base64url for at-rest creds).
│   │       Two ORM tables (``workspace_repos`` +
│   │       ``workspace_repo_secrets``) via Alembic
│   │       ``aa9b1c3e5d7f``.  ``WorkspaceReposSettings``,
│   │       4 ``ErrorCode`` members, ``cryptography>=44.0``
│   │       added.  34 new tests.
│   │
│   ├── Sprint 51.2 — Yaml-loader integration.
│   │       ``discover_repo_yaml_files`` walks every workspace
│   │       repo's clone dir; ``load_contracts_for_workspace``
│   │       + ``load_conventions_for_workspace`` combine
│   │       env-paths + repo-discovered yaml.
│   │       ``build_post_pull_loader_hook`` returns a
│   │       ``sync_repo``-compatible hook that re-runs both
│   │       loaders; counts surface on ``SyncOutcome``.  Loader
│   │       errors stay isolated.  6 new tests.
│   │
│   ├── Sprint 51.3 — Notebook + Dashboard + Saved-Query
│   │       bridge.  ``resolve_notebook_path`` accepts
│   │       ``repo:<ws>:<slug>/<rel>.py`` spec.  New
│   │       ``pointlessql/repo_assets/`` package with two yaml
│   │       loaders.  ``Dashboard`` + ``SavedQuery`` rows gain
│   │       ``source`` + ``repo_yaml_path`` columns via Alembic
│   │       ``bb1d4f6e8a0c`` so the admin UI can render
│   │       git-canonical rows as read-only.  13 new tests.
│   │
│   ├── Sprint 51.4 — Webhook receiver + cron sync loop.
│   │       Unauthenticated ``POST /webhook/git/{repo_id}``
│   │       (HMAC sig is the auth) verifies + parses + fires
│   │       async ``sync_repo``.  Lifespan-managed
│   │       ``_workspace_repos_sync_loop`` opt-in via
│   │       ``POINTLESSQL_REPOS_SYNC_INTERVAL_SECONDS≥60``.
│   │       ``/webhook/git/`` added to PUBLIC_PREFIXES + CSRF
│   │       exempt list.  9 new tests.
│   │
│   ├── Sprint 51.5 — Admin JSON API.  Eight admin-gated
│   │       endpoints behind ``/api/admin/repos`` (list /
│   │       create / detail / sync / add-or-rotate-secret /
│   │       revoke-secret / rotate-webhook / delete).
│   │       Reveal-once webhook secret on creation; secret
│   │       plaintext never echoed back on subsequent reads.
│   │       Every mutation stamps an ``audit_log`` entry.
│   │       Workspace-scoping enforced via ``_load_repo``
│   │       (other-workspace repos 404).  10 new tests.
│   │
│   └── Sprint 51.7 — Plugin tools.  Four new LLM-callable
│           Hermes tools (``pql_list_workspace_repos``,
│           ``pql_get_workspace_repo``,
│           ``pql_trigger_repo_sync`` (supervisor-gated),
│           ``pql_repo_sync_history``).  ``PointlessClient``
│           gains four matching methods.  Slug→id resolution
│           lives client-side.  8 new plugin tests; total
│           141 → 149.
│
│   Carve-outs (deferred):
│   - **Sprint 51.6 (OAuth GitHub-App).**  Was approved in the
│     plan as opt-in; deferred to a follow-up sub-sprint
│     because (a) it requires registering a real GitHub App +
│     a private-key secret to exercise end-to-end and (b)
│     deploy-keys / PATs already cover the per-workspace
│     credential surface today.  When the App is available,
│     drop ``GitHubInstallation`` + the OAuth callback flow +
│     a per-user token-refresh path on top of the existing
│     ``GitHubProvider``.  No foundation refactor needed.
│   - **HTML admin pages.**  The 51.5 surface today is JSON
│     only.  A 5-tab detail page (Overview / Auth / Sync
│     history / Files / Danger) is a natural follow-up; the
│     JSON shape is sufficient for the agent + ``curl`` paths.
│
├── Phase 50 — Native Data-Product support ✅ done
│   │
│   │   Every UC schema can opt-in to product status by committing
│   │   a ``pointlessql.yaml`` file in the data-team repo declaring
│   │   steward, SemVer version, freshness-SLA and per-table schema
│   │   contract.  Yaml is canonical; git-blame is the audit log.
│   │   ``pql.write/merge`` enforces the contract before any Delta
│   │   IO (fail-loud ``DataProductContractViolation`` on breaking
│   │   diffs); a background scanner emits ``sla_violated``
│   │   CloudEvents when freshness drifts past the declared SLA.
│   │   Workspace-scoped ``/data-products`` UI + 5 plugin tools
│   │   surface discovery, contract inspection, live-diff and
│   │   compliance history.  Pyright budget unchanged at 497.
│   │
│   ├── Sprint 50.1 — Foundation.  ``pointlessql/data_products/``
│   │       package: 11-type column-spec Pydantic model,
│   │       ``DataProductRef(str)`` validation type,
│   │       ``DataProductError`` family (4 subclasses), yaml
│   │       loader with idempotent UPSERT + steward-FK
│   │       resolution.  Two ORM tables (``data_products`` +
│   │       ``data_product_contract_events``) via Alembic
│   │       ``rr8u0w2y4a6c``.  4 ``ErrorCode`` members,
│   │       ``DataProductsSettings`` env-prefix.  23 new tests.
│   │
│   ├── Sprint 50.3 — Enforcement.  Pure-functional
│   │       ``ContractDiffResult`` core + engine-tuples /
│   │       Delta-schema adapters (canonicalises
│   │       int64/long, float64/double, decimal* aliases).
│   │       Pre-write hooks in ``pql/_write.py`` +
│   │       ``pql/_merge.py`` raise
│   │       ``DataProductContractViolation`` *before* Delta IO
│   │       on breaking diffs.  ``pending_contract_event`` on
│   │       ``OperationRecorder`` + post-commit hook persist
│   │       one event row per check; exception path also
│   │       persists so refused attempts show up in the audit
│   │       trail.  15 new tests.
│   │
│   ├── Sprint 50.4 — Freshness Scanner.  Background loop walks
│   │       SLA-bearing products, observes latest write via
│   │       ``DeltaTable.history()``, emits
│   │       ``pointlessql.data_product.sla_violated`` CloudEvent
│   │       on stale ages.  ``last_alerted_at`` re-alert
│   │       suppression (default 60 min).  Opt-in via
│   │       ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS≥60``.
│   │       New EVENT_TYPE registered in governance-events
│   │       registry.  5 new tests.
│   │
│   ├── Sprint 50.2 — Web UI.  ``/data-products`` index +
│   │       ``/data-products/{cat}/{schema}`` 5-tab detail
│   │       (Overview / Contract / Diff / Lineage / Compliance)
│   │       with cytoscape mini-DAG via lineage_row_edges.
│   │       Five JSON endpoints (list/detail/diff/lineage/
│   │       admin-reload).  Icon-rail entry between SQL and
│   │       Dashboards.  11 new tests.
│   │
│   └── Sprint 50.5 — Plugin tools.  Five new LLM-callable Hermes
│           tools (``pql_list_data_products``,
│           ``pql_get_data_product``,
│           ``pql_get_data_product_contract``,
│           ``pql_check_contract_compliance``,
│           ``pql_data_product_compliance_history``) all wired
│           into ``register_all`` so any keyed agent can use
│           them.  Plugin client gains four
│           ``/api/data-products/*`` methods.  7 new plugin
│           tests.
│
├── Phase 48 — Primitive-Obsession StrEnum Sweep ✅ done
│   │
│   │   Replaces the 9 enum-shaped string columns and 17
│   │   CloudEvents type literals with explicit ``StrEnum`` /
│   │   ``Final`` registries.  StrEnum members compare equal to
│   │   their string value, so DB-stored values, JSON wire
│   │   format, and SQL CHECK constraint matching are
│   │   byte-identical -- no DB migration, no wire-format change,
│   │   no production behaviour change.  Models stay on
│   │   ``Mapped[str]`` per anti-goal.  Pyright budget unchanged
│   │   at 497.  1686 tests pass (1673 baseline + 13 new enum
│   │   sanity tests).
│   │
│   ├── Sprint 48.1 — Add ``pointlessql/enums.py`` with
│   │       ``RunStatus`` / ``OpName`` / ``ReadKind`` /
│   │       ``QueryStatus`` / ``ReviewSeverity`` / ``ReviewKind`` /
│   │       ``AuditSinkType`` / ``EventOutcome`` /
│   │       ``BranchAction`` StrEnums.  ``tests/test_enums.py``
│   │       (13 cases) pins every value byte-for-byte against
│   │       legacy ``frozenset`` / tuple constants.  Purely
│   │       additive -- old constants stay valid.
│   │
│   ├── Sprint 48.2 — Migrate consumers in four route-family
│   │       batches.  Batch 1 RunStatus + QueryStatus (~11
│   │       files: agent-run lifecycle / events /
│   │       audit-aggregator + query_history + sql_routes +
│   │       PQL read paths).  Batch 2 OpName + BranchAction
│   │       (~13 files: ``record_operation`` /
│   │       ``operation_context`` typed; 9 PQL primitives +
│   │       sql_explain pass enum members; ``_op_name_for_node``
│   │       returns ``OpName``; ``record_branch_audit_log``
│   │       takes ``BranchAction``).  Batch 3 ReadKind (~5
│   │       files: ``record_query`` / ``record_read`` /
│   │       audit_routes typed; ``VALID_READ_KINDS`` derived from
│   │       StrEnum).  Batch 4 AuditSinkType + EventOutcome +
│   │       ReviewSeverity (~4 files: dispatch_to_sinks branch,
│   │       outcome updates, ``_SEVERITY_RANK`` keys).
│   │
│   └── Sprint 48.3 — Add unified
│           ``pointlessql/services/cloudevents/`` package
│           re-exporting the 17 CloudEvents ``Final`` constants
│           under one import path.  Legacy ``EVENT_TYPE_*``
│           aliases stay on
│           ``services.agent_runs.events`` and
│           ``services.governance_events`` for back-compat;
│           ``test_cloudevents_registry_matches_legacy_constants``
│           pins both halves byte-for-byte.
│
├── Phase 49c — TableFqn validation type ✅ done
│   │
│   │   Adds ``pointlessql/table_fqn.py`` with a ``str``-subclass
│   │   validation type for UC three-part identifiers.  Factory
│   │   methods: ``parse()`` (validates) + ``from_parts()`` (no
│   │   validation, for already-split components).  Anti-goal
│   │   preserved: ``Mapped[str]`` columns absorb ``TableFqn``
│   │   transparently (str subclass), wire format identical, no
│   │   alembic.  Pyright budget unchanged at 497.  10 sanity
│   │   tests pin the contract.
│   │
│   ├── Sprint 49c.1 — Add ``pointlessql/table_fqn.py`` plus
│   │       ``tests/test_table_fqn.py`` (10 cases pinning subclass
│   │       identity, JSON round-trip, f-string interpolation,
│   │       parse / from_parts contract).  Purely additive — no
│   │       callsite migrated yet.
│   │
│   └── Sprint 49c.2 — Migrate consumers + producers.  Step A
│           kills the two byte-for-byte duplicate
│           ``_split_three_part`` validators in
│           ``api/pql_introspect_routes.py`` +
│           ``api/pql_write_routes.py``; their callers now invoke
│           ``TableFqn.parse(...).parts()`` directly.  Step B wraps
│           13 f-string FQN producers across api/, services/, pql/
│           via ``TableFqn.from_parts(...)``.  Step C annotates
│           the highest-value service-layer signatures
│           (``services/external_write_scanner`` reference); the
│           remaining ~36 consumer signatures stay on plain ``str``
│           for incremental migration in future phases (each is an
│           isolated patch since ``TableFqn`` is-a ``str``).
│
├── Phase 49b — Service-File Splits ✅ done
│   │
│   │   Two oversize service files migrated into Phase-35-style
│   │   per-axis subpackages.  Public API unchanged via
│   │   ``__init__.py`` re-exports; existing
│   │   ``from pointlessql.services...operations import X``
│   │   imports keep working without churn.  Cross-module
│   │   helpers dropped leading underscores per Phase 35
│   │   convention; module-internal helpers kept theirs.
│   │   Pyright budget unchanged at 497.  1686 tests pass.
│   │
│   ├── Sprint 49b.1 — ``services/agent_runs/operations.py``
│   │       (929 LOC) → six-file subpackage:
│   │       ``__init__`` (re-exports), ``_common``
│   │       (OperationRecorder + ``serialise_warnings`` /
│   │       ``stamp_audit_marker`` + ``LINEAGE_FAILED_MARKER`` +
│   │       ``VALID_OP_NAMES`` derived from ``OpName`` StrEnum),
│   │       ``_rollback`` (RollbackError + 4 subclasses),
│   │       ``_lifecycle`` (``record_operation`` +
│   │       ``operation_context``), ``_lineage`` (3
│   │       post-commit hooks: emit + row-edges + column-edges),
│   │       ``_rejects`` (1 hook), ``_value_changes`` (1 hook).
│   │       One test (``test_operation_warnings.py``) updated to
│   │       import ``stamp_audit_marker`` from
│   │       ``operations._common``.
│   │
│   └── Sprint 49b.2 — ``services/audit_aggregator.py``
│           (913 LOC) → four-file subpackage:
│           ``_query_builder`` (type aliases + ``VALID_*`` sets
│           + ``MetricSpec`` dataclass + ``metric_spec()``
│           switch + ``bin_expr()`` + ``apply_audit_filters()``
│           + ``scalar_count()``), ``_summary`` (``summary()``),
│           ``_timeseries`` (``timeseries()`` + module-private
│           ``_group_col()``), ``_anomaly`` (``anomalies()`` +
│           ``compute_run_anomaly()`` + ``backfill_run_anomalies()``
│           + ``RUN_ANOMALY_METRICS`` + ``_SEVERITY_RANK`` +
│           ``_classify()`` + ``_bin_floor_compare_string()``).
│           One test (``test_dbt_test_failure_bridge.py``) updated
│           to import ``metric_spec`` (was ``_metric_spec``).
│
├── Phase 49a — Repo-wide Lint-Sweep ✅ done
│   │
│   │   Single-sprint cleanup of pre-existing ruff E501 + pydoclint
│   │   DOC502 / DOC503 / DOC601 / DOC603 violations accumulated
│   │   since Phase 35.  119 ruff hits (mostly test-function
│   │   signatures) cleared via ``uv run ruff format``; 36
│   │   pydoclint hits cleared by aligning Raises sections with
│   │   the centralised-handler typed-error pattern (HTTPException
│   │   → typed errors like ``AuthenticationError`` /
│   │   ``ResourceNotFoundError`` / ``ValidationError``) and by
│   │   filling in missing class-attribute lines for
│   │   ``ApiKey.lineage_inbound`` / ``LineageRowEdge.producer`` /
│   │   ``LineageColumnMap.producer`` / ``RollbackAmbiguous`` /
│   │   ``RollbackStale`` (and their ``external_event_id`` /
│   │   ``status_code`` / ``error_code`` siblings).  Pyright
│   │   budget unchanged at 497.  1686 tests pass.  Two
│   │   commits: ``chore(format)`` (68-file reformat sweep) +
│   │   ``chore(docs)`` (12-file docstring alignment).  No
│   │   behaviour change.
│
├── Some-day — Public launch + external distribution      💤 unscheduled
│   │
│   │   This is the moment the stack goes from "my project" to
│   │   "something strangers can try" — and importantly, from
│   │   "code on my laptop" to "verifiable trust infrastructure
│   │   in the EU AI Act / SOC2 / GDPR sense".  Apache 2.0 is
│   │   locked (UC-compatible, no ethical-use-clause drama).
│   │
│   │   Strategic framing (from the Phase-15.7-close strategy
│   │   conversation):
│   │
│   │   - Audit infrastructure ≠ ordinary OSS.  Compliance
│   │     buyers REQUIRE source-availability — closed-source
│   │     audit tools fail the third-party-auditor test.  OSS
│   │     here is an asset, not a giveaway.
│   │   - Empirical OSS-infra track record: Sentry, dbt, Grafana,
│   │     HashiCorp, Confluent all spent 2-4 years OSS-only
│   │     before commercial offering.  "Sales platform first"
│   │     is the wrong move for solo-founder infra.
│   │   - The commercial wedge is NOT the OSS code.  Candidates:
│   │     hosted SaaS (PointlesSQL Cloud), enterprise edition
│   │     (SSO/SAML/multi-tenant audit storage), cryptographic
│   │     anchor service (closed/hosted, the shoreguard
│   │     Provenance Log angle), certified compliance reports.
│   │     None of these compete with Apache-2.0 community edition.
│   │
│   ├── Pre-OSS-release hygiene (1 week of work)         ⏳
│   │   ├── EUIPO trademark filings for ``PointlesSQL``,
│   │   │   ``soyuz-catalog``, ``shoreguard``.  Classes 9
│   │   │   (software), 42 (SaaS), 41 (consulting).  ~€2550 total,
│   │   │   10-year protection.  DE-only fallback at ~€290 each
│   │   │   if EU-wide too costly upfront.  Trademark is
│   │   │   non-optional for any future commercial wedge.
│   │   ├── ``NOTICE.txt`` in each core repo establishing
│   │   │   author + Apache 2.0 + Copyright 2026 Florian
│   │   │   Hofstetter.  Anchors solo-author copyright record
│   │   │   for any future Founder Resolution / IP-transfer to
│   │   │   incorporated entity.
│   │   ├── ``CONTRIBUTING.md`` + ``CODE_OF_CONDUCT.md`` +
│   │   │   ``SECURITY.md`` per repo.  Defines governance
│   │   │   *before* community arrives.
│   │   ├── CLA-Bot (CLA-Assistant or EasyCLA) on every PR.
│   │   │   CNCF-CLA template adapted.  Without CLA, third-party
│   │   │   contributions fragment copyright and block any
│   │   │   future dual-licensing option.
│   │   ├── Domain ownership: pointlessql.dev/.io/.com,
│   │   │   shoreguard.io, soyuz-catalog.io.  ~€50/year each.
│   │   └── Private STRATEGY.md (NOT in repo): commercial-wedge
│   │     decision document.  "Hosted PointlesSQL Cloud +
│   │     cryptographic anchor as the closed wedge" or whatever
│   │     it is.  Clarity for founder, signal for investors
│   │     later.  NOT public until commercial offering ships.
│   │
│   ├── Big-bang launch day (1 day, coordinated)         ⏳
│   │   ├── ``Show HN: PointlesSQL — per-cell lineage for Delta
│   │   │   Lake via CDF`` posted Mon/Tue 8-10 UTC for European
│   │   │   prime time + US morning.  Demo screenshot, link to
│   │   │   blog post #1, mention soyuz + shoreguard as siblings.
│   │   ├── Twitter / Mastodon thread (10-12 tweets) with
│   │   │   architecture diagrams.  Tag data-eng-Twitter
│   │   │   gravity (Benn Stancil, Tristan Handy, Pedram Navid,
│   │   │   Chad Sanderson, Julien Le Dem).
│   │   ├── Reddit posts: r/dataengineering + r/programming.
│   │   ├── LinkedIn long-form post.
│   │   ├── Blog post #1: *"Why we built per-cell lineage on
│   │   │   Delta CDF"* — published same day, linked from HN.
│   │   └── Hacker News frontpage hit-rate target: 30%.  Even a
│   │       moderate showing (~50 upvotes, 200 visitors) creates
│   │       the "Sarah saw this in our internal Slack" pathway
│   │       that converts to recruiter / engineer outreach.
│   │
│   ├── Conference circuit (3-12 month lead time)        ⏳
│   │   ├── DataCouncil — "How per-cell lineage closes the
│   │   │   EU-AI-Act audit gap".  Springs 2026 / Falls 2027.
│   │   ├── Subsurface — "Building Z3-verified policies for
│   │   │   agent sandboxes" (shoreguard angle).
│   │   ├── dbt Coalesce — "Comparing PointlesSQL audit-substrate
│   │   │   to Unity Catalog Lineage".
│   │   ├── Berlin Buzzwords — DE local, easier to land first
│   │   │   slot, builds CFP-pipeline credibility.
│   │   ├── Big Data LDN — UK enterprise audience, compliance
│   │   │   buyer-aligned.
│   │   └── KubeCon EU (longer shot) — shoreguard / OpenShell
│   │       angle if maturity allows.
│   │
│   ├── Sustained visibility (months 1-12 post-launch)   ⏳
│   │   ├── Blog post series, 1 every 3 weeks: per-cell lineage
│   │   │   for EU AI Act, Delta CDF deep-dive, comparing to UC
│   │   │   Lineage, Z3-verified policies, cross-tool lineage.
│   │   ├── Twitter daily: 3-5 substantive posts/week.  Reply
│   │   │   to Data-Eng-Twitter threads with substance not spam.
│   │   ├── LinkedIn updated: headline "Building open-source
│   │   │   data audit + governance — PointlesSQL, soyuz,
│   │   │   shoreguard".  About-section + skills tuned for
│   │   │   recruiter sourcing tools (HireEZ / Gem / SeekOut
│   │   │   scrape LinkedIn keywords, not GitHub).
│   │   └── Office Hours outbound: 1:1 calls with engineering
│   │       managers at target acquirers (Snowflake, Atlan,
│   │       Acryl Data, OneTrust, Drata, Vanta, Snowplow,
│   │       Microsoft Purview team) once first-run substance
│   │       is shipped (Phase 18+ done).
│   │
│   ├── Packaging + distribution (the original Some-day)  ⏳
│   │   ├── GHCR packages flipped private → public for both
│   │   │   ``pointlessql`` and ``soyuz-catalog`` images; the
│   │   │   Phase-10-deferred ``docs/e2e-walkthroughs/packaging.md``
│   │   │   dogfood replay finally runs end-to-end without the
│   │   │   PAT dance
│   │   ├── Multi-arch (amd64 + arm64) image builds via docker
│   │   │   buildx — the single-sprint work that Phase 10
│   │   │   couldn't justify for an audience of one
│   │   ├── Public PyPI publish of ``soyuz-catalog-client``
│   │   │   (first) and the ``pointlessql`` wheel (second);
│   │   │   replaces Phase 10's private git-tag pin for the
│   │   │   general audience while keeping the tag-pin option
│   │   │   available for consumers who prefer reproducible
│   │   │   git-based installs
│   │   ├── Optional: Helm chart for K8s deployments,
│   │   │   generalising "runs on a €15/month vServer" to
│   │   │   "runs on a cluster"
│   │   └── README / docs pass: swap the "functional Databricks
│   │       clone" alpha framing for the post-15.7 honest
│   │       positioning: *"per-cell auditable lakehouse for
│   │       agent-driven data engineering, EU-AI-Act-native"*.
│   │
│   └── Commercial offering (12-24 months post-OSS)      ⏳
│       ├── Identify 3-5 paying design partners from the
│       │   community (mid-cap retailer with EU-AI-Act compliance
│       │   pressure, healthcare-data-engineering, financial
│       │   reporting under ASC 606).  €500-2k/month each as
│       │   willingness-to-pay validation.
│       ├── Co-design the commercial wedge with design partners
│       │   — what they actually want to pay for vs what they
│       │   get free.  Likely: hosted SaaS, certified
│       │   compliance reports, multi-tenant audit retention,
│       │   SSO/SAML, cryptographic anchor service.
│       ├── UG/GmbH incorporation (~€500 + Notar) once a
│       │   contract template + 2 verbal-LOIs exist.  Founder
│       │   Resolution transfers pre-incorporation IP to entity.
│       └── First commercial offering live, based on what design
│           partners actually paid for — not what was guessed
│           upfront.  Expected revenue trajectory: €0 → €60k ARR
│           year 1 → €200-500k year 2 → €1-3M year 3 (typical
│           OSS-infra commercial-bootstrap curve).
│
├── Icebox — enterprise-audit follow-ups                  🧊 on ice
│   │
│   │   Sprint 48 ported six of nine shoreguard-fresh audit
│   │   patterns.  Two of the three remaining items landed in
│   │   Phase 75 (2026-05-15) — verifiable export and SIEM
│   │   sinks.  Only the action-string rename stays parked here.
│   │
│   ├── Audit export with sha256 digest + manifest  ✅ promoted to Phase 75.1
│   │   └── See Phase 75.1 above for the shipped implementation.
│   │
│   ├── Audit-to-SIEM export sinks                  ✅ promoted to Phase 75.2
│   │   └── See Phase 75.2 above for the shipped stdout_json +
│   │       syslog implementations.
│   │
│   └── Retroactive action-string rename to ``resource.verb``  🧊 on ice
│       └── Churn-only refactor of the 25 pre-Sprint-48 action
│           strings (``update_catalog`` → ``catalog.updated``, …)
│           to fully align with the convention Phase 12 adopts
│           for new events. Pure ergonomics for the
│           ``/admin/audit`` dropdown — no behavioural change —
│           so only worth doing the day the whole fleet gets
│           rewired (e.g. a release-notes-worthy version bump)
│
└── Explicitly out of scope (probably ever)
    ├── Reimplementing the Unity Catalog REST API — that is
    │   soyuz-catalog's job; PointlesSQL is a consumer
    ├── Building a query engine — PointlesSQL starts engine
    │   kernels (Pandas/Polars/Spark/DuckDB) and delivers UC
    │   config; it does not parse SQL or plan queries itself
    ├── Running the JVM upstream UC server — soyuz-catalog is
    │   the spec-compatible replacement
    └── Federated query planning across multiple foreign
        catalogs — that is a query-engine concern
```

## How to update this file

- **When a sprint lands:** flip its marker to ✅, append
  `(<short-sha>)`, and add a one-line `CHANGELOG.md` entry under
  `## [Unreleased]`.
- **When a new sprint is planned:** add it under the current phase
  with ⏳ and a short bullet list of the concrete scope. Keep it
  short — this is a tracker, not a design doc. Design details go
  in ADRs under `docs/adr/`.
- **When scope shifts:** edit the bullet list in place rather than
  adding a "scope change" section. The git history of this file
  *is* the scope-change log.
- **When a phase completes:** flip the phase marker to ✅ and
  move on. Do not delete completed phases — they are the record
  of what "done" meant.
- **When closed phases stack up:** roll older completed phases
  out of `ROADMAP.md` into [`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md)
  using the existing collapse pattern (one-line summary in a
  table, full detail moved verbatim to the archive). Both
  conditions must hold before a phase qualifies for the roll:
  1. **Line-count trigger:** `ROADMAP.md` exceeds ~2000 lines —
     a soft "consider rolling" signal, not an automatic roll.
  2. **Staleness trigger:** the phase has been closed for
     **≥30 days** *and* no subsequent phase has actively
     referenced it for >3 months. Recently-closed phases
     stay full-detail because they're still load-bearing for
     follow-up conversations, even when the file is long.

  Example (2026-05-12): `ROADMAP.md` is 7068 lines (line-count
  trigger fires) but Phases 12.9–20 closed 2026-04-29 to
  2026-05-05 are all <30 days old → no roll yet. Reassess once
  a follow-up phase has shipped on top of each and stayed
  stable for 30 days.

This file is read first by every new Claude Code session (see
[`CLAUDE.md`](CLAUDE.md)).
